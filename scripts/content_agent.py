"""
content_agent.py
-----------------
Generates ONE original, simple-English motivational line for the CURRENT
time-slot's category, using Groq (openai/gpt-oss-120b). Also writes a
short set of hashtags in the same call (no separate caption step needed).

Each run is tied to one category by time of day (IST):
  6:00 AM  -> Motivation
  10:00 AM -> Success
  1:00 PM  -> Attitude
  4:00 PM  -> Ego Check
  7:00 PM  -> Deep Words
  10:00 PM -> Emotional

For manual testing, set CATEGORY_OVERRIDE (one of: motivation, success,
attitude, ego_check, deep_words, emotional) to force a category regardless
of current time -- the workflow's manual "Run workflow" screen exposes
this as an input.

ENV VARS:
    GROQ_API_KEY (required)
    CATEGORY_OVERRIDE (optional)

OUTPUT:
    data/posts_today.json  -- a list with exactly one quote object
    data/history.json      -- running list of used quotes (for dedup)
"""

import os
import sys
import json
import time
import re
import requests
from datetime import datetime, timezone

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME = "openai/gpt-oss-120b"
HISTORY_FILE = "data/history.json"
OUTPUT_FILE = "data/posts_today.json"
HISTORY_MAX_ENTRIES = 500

# hour_utc -> (key, display name, accent color RGB)
CATEGORY_SCHEDULE = [
    (0,  "motivation", "Motivation", (215, 55, 45)),
    (4,  "success",    "Success",    (220, 180, 50)),
    (7,  "attitude",   "Attitude",   (150, 75, 195)),
    (10, "ego_check",  "Ego Check",  (225, 130, 35)),
    (13, "deep_words", "Deep Words", (70, 140, 195)),
    (16, "emotional",  "Emotional",  (110, 130, 180)),
]

CATEGORY_GUIDE = {
    "motivation": "Motivation, discipline, hard work, never giving up, "
                  "consistency, comeback after failure, patience, self-belief.",
    "success": "Success mindset, self-made wins, discipline over motivation, "
               "long-term thinking, becoming better than yesterday, focus.",
    "attitude": "Self-respect, confidence, independence, not seeking "
                "validation, setting boundaries, knowing your own worth.",
    "ego_check": "Reality-check lines about proving yourself through actions, "
                 "not explaining yourself, letting results speak, being "
                 "underestimated then proving people wrong. Must stay general "
                 "and about the reader's own mindset -- NEVER insulting or "
                 "aimed at any real, specific person.",
    "deep_words": "Reflective one-liners about life, human nature, trust, "
                  "time, change, silence, expectations, life lessons.",
    "emotional": "Heartbreak, missing someone, one-sided effort, moving on, "
                 "letting go, memories -- gentle and relatable, never graphic.",
}


def get_category():
    override = os.environ.get("CATEGORY_OVERRIDE", "").strip().lower()
    by_key = {c[1]: c for c in CATEGORY_SCHEDULE}
    if override in by_key:
        return by_key[override]
    now_hour = datetime.now(timezone.utc).hour
    return min(
        CATEGORY_SCHEDULE,
        key=lambda c: min(abs(c[0] - now_hour), 24 - abs(c[0] - now_hour)),
    )


def normalize(t):
    t = (t or "").lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def too_similar(a, b, threshold=0.65):
    wa, wb = set(normalize(a).split()), set(normalize(b).split())
    if not wa or not wb:
        return False
    return len(wa & wb) / min(len(wa), len(wb)) >= threshold


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


def build_prompt(category_key, category_display, history):
    guide = CATEGORY_GUIDE[category_key]
    recent = [h["quote"] for h in history if h.get("category_key") == category_key][-15:]
    recent_block = "\n".join(f"- {q}" for q in recent) if recent else "(none yet)"

    return f"""You write short, original motivational one-liners for an
Instagram/Telegram page called "ruthless.mindset". Category right now:
{category_display}.

STYLE RULES (very important):
- Use SIMPLE, everyday English. Someone with basic English should
  understand it instantly on first read. No poetic or fancy words.
- 1-2 short sentences, under 20 words total.
- Direct, punchy, real -- not cheesy or cliche.
- Plain text only: no hashtags, no emojis, no quotation marks around it.

TOPIC FOCUS: {guide}

ALREADY USED (do not repeat these or write something too similar):
{recent_block}

Return ONLY raw JSON, no markdown fences, no extra text, in this exact shape:
{{
  "quote": "the line, in simple English",
  "highlight": "a short phrase (2-4 words) copied EXACTLY from the quote --
                the single most powerful part of it",
  "hashtags": ["10 to 14 relevant hashtags, no # symbol, mixing broad tags
                like Motivation with more specific ones"]
}}
"""


def strip_code_fences(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0).strip() if match else text.strip()


def call_groq(api_key, prompt, max_retries=2):
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": 800,
        "reasoning_effort": "low",
    }
    for attempt in range(max_retries + 1):
        try:
            r = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=60)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[content_agent] Groq call failed (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                time.sleep(15)
            else:
                raise


def main():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("[content_agent] ERROR: GROQ_API_KEY not set.")
        sys.exit(1)

    hour_utc, cat_key, cat_display, accent = get_category()
    print(f"[content_agent] Category for this run: {cat_display} ({cat_key})")

    history = load_history()
    prompt = build_prompt(cat_key, cat_display, history)

    result = None
    for attempt in range(2):
        raw = call_groq(api_key, prompt)
        try:
            parsed = json.loads(strip_code_fences(raw))
        except json.JSONDecodeError as e:
            print(f"[content_agent] JSON parse failed: {e}\nRaw: {raw}")
            continue

        quote = (parsed.get("quote") or "").strip()
        if not quote:
            continue
        if any(too_similar(quote, h.get("quote", "")) for h in history if h.get("category_key") == cat_key):
            print(f"[content_agent] attempt {attempt + 1}: too similar to a past quote, retrying...")
            continue
        result = parsed
        break

    if result is None:
        print("[content_agent] ERROR: could not get a usable, non-duplicate quote.")
        sys.exit(1)

    quote = result.get("quote", "").strip()
    highlight = result.get("highlight", "").strip()
    if highlight not in quote:
        highlight = ""
    hashtags = result.get("hashtags") or []
    if not isinstance(hashtags, list):
        hashtags = []

    post = {
        "category_key": cat_key,
        "category": cat_display,
        "quote": quote,
        "highlight": highlight,
        "hashtags": hashtags[:14],
        "accent": list(accent),
    }

    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump([post], f, ensure_ascii=False, indent=2)

    history.append({
        "category_key": cat_key,
        "quote": quote,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    })
    save_history(history)

    print(f"[content_agent] Saved 1 post ({cat_display}): {quote}")


if __name__ == "__main__":
    main()
