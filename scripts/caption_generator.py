"""
caption_generator.py
---------------------
Reads data/posts_today.json and writes a Facebook caption + 20 hashtags +
a Telegram cross-promotion line for EACH post, using Groq (openai/gpt-oss-120b).

Only Facebook needs captions (Telegram posts just the image), so this
output is consumed later by facebook_poster.py only.

Runs as part of the combined workflow, AFTER content_agent.py and
image_generator.py.

ENV VARS REQUIRED (set as GitHub Secrets):
    GROQ_API_KEY

OUTPUT:
    data/captions.json   <- one caption entry per post, aligned by index
"""

import os
import sys
import json
import time
import re
import requests

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME = "openai/gpt-oss-120b"
POSTS_FILE = "data/posts_today.json"
OUTPUT_FILE = "data/captions.json"
TELEGRAM_LINK = "t.me/sports_world"

BETWEEN_CALL_DELAY_SECONDS = 3
RETRY_WAIT_SECONDS = 15


def build_prompt(post):
    sport = post.get("sport", "")
    category = post.get("category", "")
    headline = post.get("headline", "")
    footer = post.get("footer_text", "")

    return f"""You are writing a Facebook caption for an Indian sports news
page called SPORTS_WORLD, about this story:

Sport: {sport}
Category: {category}
Story: {headline}
Extra detail: {footer}

Write:
1. A caption under 120 words, natural and engaging, in your own words
   (do not just repeat the story sentence word for word). Include a short
   hook at the start, then 1-2 sentences of context, then end with a
   question to encourage comments.
2. Include this exact line somewhere near the end of the caption:
   "Follow SPORTS_WORLD on Telegram for daily {sport.lower()} updates: {TELEGRAM_LINK}"
3. Exactly 20 hashtags, mixing high-competition (e.g. #Cricket, #Sports),
   medium-competition (e.g. sport+event specific), and low-competition
   (e.g. specific player/team names) tags. No duplicates.

Return ONLY raw JSON, no markdown code fences, no extra text, in this
exact shape:
{{
  "caption": "the full caption text including the Telegram line",
  "hashtags": ["Tag1", "Tag2", "... exactly 20 total, without the # symbol"]
}}
"""


def strip_code_fences(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0).strip()
    return text.strip()


def call_groq_with_retry(api_key, prompt, max_retries=1):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
    }
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[caption_generator] Groq call failed (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                print(f"[caption_generator] waiting {RETRY_WAIT_SECONDS}s before retry...")
                time.sleep(RETRY_WAIT_SECONDS)
            else:
                return None


def main():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("[caption_generator] ERROR: GROQ_API_KEY environment variable not set.")
        sys.exit(1)

    if not os.path.exists(POSTS_FILE):
        print(f"[caption_generator] ERROR: {POSTS_FILE} not found. Run content_agent.py first.")
        sys.exit(1)

    with open(POSTS_FILE, "r", encoding="utf-8") as f:
        posts = json.load(f)

    results = []

    for i, post in enumerate(posts, 1):
        prompt = build_prompt(post)
        raw_text = call_groq_with_retry(api_key, prompt)

        if raw_text is None:
            print(f"[caption_generator] post {i}: giving up after retry, using fallback caption.")
            results.append({
                "post_index": i,
                "caption": f"{post.get('headline', '')}\n\nFollow SPORTS_WORLD on Telegram: {TELEGRAM_LINK}",
                "hashtags": ["Sports", "SportsNews", "IndianSports"],
            })
        else:
            try:
                parsed = json.loads(strip_code_fences(raw_text))
                results.append({
                    "post_index": i,
                    "caption": parsed.get("caption", ""),
                    "hashtags": parsed.get("hashtags", []),
                })
                print(f"[caption_generator] post {i}: caption generated ({len(parsed.get('hashtags', []))} hashtags).")
            except json.JSONDecodeError as e:
                print(f"[caption_generator] post {i}: could not parse JSON ({e}), using fallback.")
                results.append({
                    "post_index": i,
                    "caption": f"{post.get('headline', '')}\n\nFollow SPORTS_WORLD on Telegram: {TELEGRAM_LINK}",
                    "hashtags": ["Sports", "SportsNews", "IndianSports"],
                })

        if i < len(posts):
            time.sleep(BETWEEN_CALL_DELAY_SECONDS)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"[caption_generator] Done. Saved {len(results)} caption(s) to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

def build_prompt(post):
    sport = post.get("sport", "")
    category = post.get("category", "")
    headline = post.get("headline", "")
    footer = post.get("footer_text", "")

    return f"""You are writing a Facebook caption for an Indian sports news
page called SPORTS_WORLD, about this story:

Sport: {sport}
Category: {category}
Story: {headline}
Extra detail: {footer}

Write:
1. A caption under 120 words, natural and engaging, in your own words
   (do not just repeat the story sentence word for word). Include a short
   hook at the start, then 1-2 sentences of context, then end with a
   question to encourage comments.
2. Include this exact line somewhere near the end of the caption:
   "Follow SPORTS_WORLD on Telegram for daily {{sport.lower()}} updates: {TELEGRAM_LINK}"
3. Exactly 20 hashtags, mixing high-competition (e.g. #Cricket, #Sports),
   medium-competition (e.g. sport+event specific), and low-competition
   (e.g. specific player/team names) tags. No duplicates.

Return ONLY raw JSON, no markdown code fences, no extra text, in this
exact shape:
{{
  "caption": "the full caption text including the Telegram line",
  "hashtags": ["Tag1", "Tag2", "... exactly 20 total, without the # symbol"]
}}
"""


def strip_code_fences(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def call_gemini_with_retry(client, prompt, max_retries=1):
    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
            )
            return response.text
        except Exception as e:
            print(f"[caption_generator] Gemini call failed (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                print(f"[caption_generator] waiting {RETRY_WAIT_SECONDS}s before retry...")
                time.sleep(RETRY_WAIT_SECONDS)
            else:
                return None


def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[caption_generator] ERROR: GEMINI_API_KEY environment variable not set.")
        sys.exit(1)

    if not os.path.exists(POSTS_FILE):
        print(f"[caption_generator] ERROR: {POSTS_FILE} not found. Run content_agent.py first.")
        sys.exit(1)

    with open(POSTS_FILE, "r", encoding="utf-8") as f:
        posts = json.load(f)

    client = genai.Client(api_key=api_key)
    results = []

    print(f"[caption_generator] waiting {FIRST_CALL_BUFFER_SECONDS}s before first call...")
    time.sleep(FIRST_CALL_BUFFER_SECONDS)

    for i, post in enumerate(posts, 1):
        prompt = build_prompt(post)
        raw_text = call_gemini_with_retry(client, prompt)

        if raw_text is None:
            print(f"[caption_generator] post {i}: giving up after retry, using fallback caption.")
            results.append({
                "post_index": i,
                "caption": f"{post.get('headline', '')}\n\nFollow SPORTS_WORLD on Telegram: {TELEGRAM_LINK}",
                "hashtags": ["Sports", "SportsNews", "IndianSports"],
            })
        else:
            try:
                parsed = json.loads(strip_code_fences(raw_text))
                results.append({
                    "post_index": i,
                    "caption": parsed.get("caption", ""),
                    "hashtags": parsed.get("hashtags", []),
                })
                print(f"[caption_generator] post {i}: caption generated ({len(parsed.get('hashtags', []))} hashtags).")
            except json.JSONDecodeError as e:
                print(f"[caption_generator] post {i}: could not parse JSON ({e}), using fallback.")
                results.append({
                    "post_index": i,
                    "caption": f"{post.get('headline', '')}\n\nFollow SPORTS_WORLD on Telegram: {TELEGRAM_LINK}",
                    "hashtags": ["Sports", "SportsNews", "IndianSports"],
                })

        if i < len(posts):
            print(f"[caption_generator] waiting {BETWEEN_CALL_DELAY_SECONDS}s before next call...")
            time.sleep(BETWEEN_CALL_DELAY_SECONDS)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"[caption_generator] Done. Saved {len(results)} caption(s) to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
