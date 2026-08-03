"""
content_agent.py
-----------------
Finds real, current sports news (India-focused, per our category strategy),
using Gemini + Google Search grounding, and saves today's posts as JSON.

Runs ONCE per day (see .github/workflows/generate_content.yml).

ENV VARS REQUIRED (set as GitHub Secrets):
    GEMINI_API_KEY

OUTPUT:
    data/posts_today.json   <- today's posts (used by the image + posting scripts)
    data/history.json       <- running list of used headlines (to avoid repeats)
"""

import os
import sys
import json
import time
import re
from datetime import datetime, timezone

from google import genai
from google.genai import types

MODEL_NAME = "gemini-2.5-flash"
POSTS_PER_DAY = 5
HISTORY_FILE = "data/history.json"
OUTPUT_FILE = "data/posts_today.json"
HISTORY_MAX_ENTRIES = 300

CONTENT_STRATEGY = """
SPLIT: 80% India-focused content, 20% international.

PRIORITY 1 (India, ~80% of posts) — look for:
Gold/Silver/Bronze medal wins, championship wins, India team title wins,
new national/world/Asian records by Indian athletes, "first Indian ever"
historic achievements, awards/honours received, major athlete birthdays
(big names only), milestones (100th match, 500 wickets etc.), team
selection announcements, injury updates, injury comebacks,
transfers/signings, sponsorship deals, tournament schedules, tournament
results, important official statements, Khelo India news, University
Games, Para Sports achievements, Junior/U-19/U-23 achievements,
Women's sports achievements.

PRIORITY 2 (International, ~20% of posts) — look for:
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

JSON_INSTRUCTIONS = f"""
Return EXACTLY {POSTS_PER_DAY} posts as a JSON array. Return ONLY raw JSON —
no markdown code fences, no explanation text before or after.

Each post must be an object with these exact fields:
{{
  "sport": "e.g. Cricket",
  "category": "one short label, e.g. Gold Medal Winner",
  "template": "A" | "B" | "C" | "D" | "E" | "F",
  "headline": "1-2 sentence factual summary in your own words, 25-35 words",
  "highlight_phrase": "a short phrase (3-6 words) copied EXACTLY from the
                        headline field above, to be highlighted in gold in
                        the image design",
  "footer_text": "short bottom-line detail, e.g. names/date/result, under 8 words",
  "source_names": ["names of publications this was reported by, if known"],
  "table_rows": []
}}

table_rows rule (IMPORTANT):
- If template is "C" (Stats Grid) or "D" (Standings/Tally Table), fill
  table_rows with 2-6 pairs of [label, value] representing the actual
  stats/standings, e.g. [["2018", "Gold Coast - Women's 48kg"], ["2022",
  "Birmingham - Women's 49kg"]] or [["AUSTRALIA", "87.50"], ["INDIA", "48.15"]].
- For every other template (A, B, E, F), table_rows MUST be an empty array [].

Rules:
- Only use real, verifiable, CURRENT news (use Google Search to confirm facts).
- Do not invent quotes. Do not invent statistics.
- highlight_phrase MUST be an exact substring of headline.
- Follow the PRIORITY ORDER above when choosing which stories to include.
- Do not repeat any story listed under PREVIOUSLY USED STORIES below.
"""


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


def build_prompt(history):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    recent_titles = [h.get("headline", "") for h in history[-60:]]
    history_block = "\n".join(f"- {t}" for t in recent_titles) if recent_titles else "(none yet)"

    return f"""You are a sports news editor for an Indian sports news page
called SPORTS_WORLD. Today's date is {today}.

{CONTENT_STRATEGY}

{TEMPLATE_GUIDE}

PREVIOUSLY USED STORIES (do not repeat these or very similar ones):
{history_block}

{JSON_INSTRUCTIONS}
"""


def strip_code_fences(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def call_gemini_with_retry(client, prompt, max_retries=2):
    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            )
            return response.text
        except Exception as e:
            print(f"[content_agent] Gemini call failed (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                print("[content_agent] waiting 60s before retry...")
                time.sleep(60)
            else:
                raise


def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[content_agent] ERROR: GEMINI_API_KEY environment variable not set.")
        sys.exit(1)

    time.sleep(20)

    client = genai.Client(api_key=api_key)
    history = load_history()
    prompt = build_prompt(history)

    raw_text = call_gemini_with_retry(client, prompt)
    cleaned = strip_code_fences(raw_text)

    try:
        posts = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"[content_agent] ERROR: could not parse Gemini's JSON response: {e}")
        print("[content_agent] raw response was:")
        print(raw_text)
        sys.exit(1)

    if not isinstance(posts, list) or len(posts) == 0:
        print("[content_agent] ERROR: Gemini did not return a non-empty list of posts.")
        sys.exit(1)

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
        print("[content_agent] ERROR: all posts were duplicates or invalid.")
        sys.exit(1)

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
