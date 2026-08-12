"""
content_agent.py
-----------------
Finds real, current sports news (India-focused, per our category strategy).

Step 1: pulls real, just-published headlines from Google News RSS (free,
no API key, no quota) across several sports-focused search queries.
Step 2: sends those real candidate headlines to Groq (openai/gpt-oss-120b)
and asks it to select + rewrite the best 2-8 of them into our post format.
The model may ONLY pick from the real candidates -- it cannot invent news.

Runs 3 times a day, as part of the single combined workflow (see
.github/workflows/generate_content.yml).

ENV VARS REQUIRED (set as GitHub Secrets):
    GROQ_API_KEY

OUTPUT:
    data/posts_today.json   <- this run's posts (used by the image + posting scripts)
    data/history.json       <- running list of used headlines (to avoid repeats)
"""

import os
import sys
import json
import time
import re
import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote
from datetime import datetime, timezone

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME = "openai/gpt-oss-120b"
MIN_POSTS = 2
MAX_POSTS = 8
HISTORY_FILE = "data/history.json"
OUTPUT_FILE = "data/posts_today.json"
HISTORY_MAX_ENTRIES = 300
MAX_ITEMS_PER_QUERY = 12

NEWS_QUERIES = [
    "India cricket news",
    "India Olympics sports news",
    "Indian athlete record award",
    "India hockey badminton wrestling boxing athletics",
    "India kabaddi football sports news",
    "world sports news today",
    "athlete retirement transfer ban doping world record",
]

CONTENT_STRATEGY = """
SPLIT: 80% India-focused content, 20% international.

PRIORITY 1 (India, ~80% of posts) -- look for:
Gold/Silver/Bronze medal wins, championship wins, India team title wins,
new national/world/Asian records by Indian athletes, "first Indian ever"
historic achievements, awards/honours received, major athlete birthdays
(big names only), milestones (100th match, 500 wickets etc.), team
selection announcements, injury updates, injury comebacks,
transfers/signings, sponsorship deals, tournament schedules, tournament
results, important official statements, Khelo India news, University
Games, Para Sports achievements, Junior/U-19/U-23 achievements,
Women's sports achievements.

PRIORITY 2 (International, ~20% of posts) -- look for:
death of a famous athlete, serious accidents, major injuries,
retirements, coach resignations, big transfers, bans/suspensions,
doping cases, major championship wins, world records, viral
interviews, official announcements, lifetime achievement awards,
hall of fame, career-ending news.

SPORTS TO TRACK: Cricket, Hockey, Football, Kabaddi, Badminton,
Wrestling, Boxing, Athletics, Shooting, Chess, Weightlifting, Archery,
Table Tennis, Tennis, Volleyball, Basketball, Kho Kho, Para Sports,
Esports (only major Indian events).

IGNORE (never pick these): match-by-match score updates, rumours, fan
reactions, gossip, clickbait, local school tournaments, low-profile
club matches, duplicate news already covered by multiple sources.

PRIORITY ORDER (highest to lowest, when choosing which stories to use):
1. Indian athlete wins any medal
2. Indian athlete creates any record
3. Indian team wins a tournament
4. Indian athlete receives a major award
5. Major Indian sports announcement
6. International retirement
7. International accident or death
8. International world record
9. International major championship
10. Other high-impact sports news
"""

TEMPLATE_GUIDE = """
Choose exactly one template code for each post, from:
  A = Magazine Editorial   -> general news, updates, statements, injuries,
                               transfers, schedules, announcements, tributes
  B = Medal/Score Highlight-> any medal win, championship win, team title
  C = Stats Grid            -> records, milestones, career stats
  D = Standings/Tally Table -> points tables, medal tallies, rankings
  E = Breaking Alert        -> bans, doping, major transfers, urgent news
  F = Struggle Carousel     -> historic "first ever" stories, retirement
                               tributes (use RARELY - needs a human to
                               later add an old/archival photo manually)
"""


def fetch_google_news_rss(query, max_items=MAX_ITEMS_PER_QUERY):
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SportsWorldAgent/1.0)"},
            timeout=20,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = []
        for item in root.findall(".//item")[:max_items]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            source_el = item.find("source")
            source = source_el.text.strip() if source_el is not None and source_el.text else ""
            if title:
                items.append({"title": title, "link": link, "pubDate": pub_date, "source": source})
        return items
    except Exception as e:
        print(f"[content_agent] RSS fetch failed for '{query}': {e}")
        return []


def gather_candidates():
    seen_titles = set()
    candidates = []
    for q in NEWS_QUERIES:
        items = fetch_google_news_rss(q)
        print(f"[content_agent] '{q}': {len(items)} items fetched")
        for it in items:
            key = it["title"].lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)
            candidates.append(it)
        time.sleep(1)
    return candidates


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def save_history(history):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    trimmed = history[-HISTORY_MAX_ENTRIES:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)


def build_prompt(history, candidates):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    recent_titles = [h.get("headline", "") for h in history[-25:]]
    history_block = "\n".join(f"- {t}" for t in recent_titles) if recent_titles else "(none yet)"

    candidates_block = "\n".join(
        f"{i}. [{c['source']}] {c['title']}" for i, c in enumerate(candidates, 1)
    ) if candidates else "(none fetched)"

    json_instructions = f"""
You must ONLY pick stories from the CANDIDATE HEADLINES list below -- these
were fetched moments ago from real news sources. Do NOT invent, add, or use
any story that is not in this list. Do NOT use outside knowledge.

Return a JSON array of the best {MIN_POSTS}-{MAX_POSTS} candidates according
to the PRIORITY ORDER and content strategy below. If fewer than {MIN_POSTS}
candidates are genuinely relevant sports news, return as many as are
relevant (can be fewer than {MIN_POSTS}). Never return more than {MAX_POSTS}.
Return ONLY raw JSON -- no markdown code fences, no explanation text before
or after, no text outside the JSON array.

Each post must be an object with these exact fields:
{{
  "sport": "e.g. Cricket",
  "category": "one short label, e.g. Gold Medal Winner",
  "template": "A" | "B" | "C" | "D" | "E" | "F",
  "headline": "1-2 sentence factual summary IN YOUR OWN WORDS based on the
               candidate title, 25-35 words",
  "highlight_phrase": "a short phrase (3-6 words) copied EXACTLY from the
                        headline field above, to be highlighted in gold in
                        the image design",
  "footer_text": "short bottom-line detail, e.g. names/date/result, under 8 words",
  "source_names": ["the source name(s) shown in brackets for that candidate"],
  "table_rows": []
}}

table_rows rule (IMPORTANT):
- If template is "C" (Stats Grid) or "D" (Standings/Tally Table), fill
  table_rows with 2-6 pairs of [label, value] representing the actual
  stats/standings you can infer from the headline, e.g. [["2018", "Gold
  Coast - Women's 48kg"], ["2022", "Birmingham - Women's 49kg"]].
- For every other template (A, B, E, F), table_rows MUST be an empty array [].

Rules:
- Do not invent quotes. Do not invent statistics beyond what's implied by the headline.
- highlight_phrase MUST be an exact substring of headline.
- Follow the PRIORITY ORDER above when choosing which candidates to include.
- Do not repeat any story listed under PREVIOUSLY USED STORIES below.
"""

    return f"""You are a sports news editor for an Indian sports news page
called SPORTS_WORLD. Right now it is {today}.

{CONTENT_STRATEGY}

{TEMPLATE_GUIDE}

CANDIDATE HEADLINES (real, fetched moments ago -- only pick from this list):
{candidates_block}

PREVIOUSLY USED STORIES (do not repeat these or very similar ones):
{history_block}

{json_instructions}
"""


def strip_code_fences(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        return match.group(0).strip()
    return text.strip()


def call_groq_with_retry(api_key, prompt, max_retries=2):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": 8000,
        "reasoning_effort": "low",
    }
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=90)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[content_agent] Groq call failed (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                print("[content_agent] waiting 20s before retry...")
                time.sleep(20)
            else:
                raise


def main():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("[content_agent] ERROR: GROQ_API_KEY environment variable not set.")
        sys.exit(1)

    history = load_history()

    candidates = gather_candidates()
    if not candidates:
        print("[content_agent] ERROR: no candidate headlines fetched from RSS. Exiting.")
        sys.exit(1)
    print(f"[content_agent] {len(candidates)} unique candidate headlines gathered.")
    candidates = candidates[:40]

    prompt = build_prompt(history, candidates)

    raw_text = call_groq_with_retry(api_key, prompt)
    cleaned = strip_code_fences(raw_text)

    try:
        posts = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"[content_agent] ERROR: could not parse Groq's JSON response: {e}")
        print("[content_agent] raw response was:")
        print(raw_text)
        sys.exit(1)

    if not isinstance(posts, list) or len(posts) == 0:
        print("[content_agent] ERROR: Groq did not return a non-empty list of posts.")
        sys.exit(1)

    posts = posts[:MAX_POSTS]

    used_headlines_lower = {h.get("headline", "").lower() for h in history}
    valid_posts = []
    for p in posts:
        headline = p.get("headline", "").strip()
        if not headline:
            continue
        if headline.lower() in used_headlines_lower:
            print(f"[content_agent] skipping duplicate: {headline[:60]}...")
            continue
        if p.get("highlight_phrase", "") not in headline:
            p["highlight_phrase"] = ""
        if not isinstance(p.get("table_rows"), list):
            p["table_rows"] = []
        valid_posts.append(p)

    if not valid_posts:
        print("[content_agent] No new posts this run (all duplicates or invalid). "
              "Writing an empty list so later steps skip cleanly.")
        valid_posts = []

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(valid_posts, f, ensure_ascii=False, indent=2)

    for p in valid_posts:
        history.append({
            "headline": p.get("headline", ""),
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        })
    save_history(history)

    print(f"[content_agent] Saved {len(valid_posts)} posts to {OUTPUT_FILE}")
    for i, p in enumerate(valid_posts, 1):
        print(f"  {i}. [{p.get('template')}] {p.get('sport')}: {p.get('headline')[:70]}")


if __name__ == "__main__":
    main()
