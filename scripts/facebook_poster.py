"""
facebook_poster.py
-------------------
Posts ALL of this run's images (with their captions + hashtags) to the
Facebook Page, one after another, with a short delay between each.

Runs 3 times a day, right after telegram_poster.py, as part of the single
combined workflow. If Facebook posting fails for a post (or entirely),
this script does NOT crash the whole run — Telegram posting has already
happened by this point, and the workflow step itself also has
continue-on-error set as a second safety net.

ENV VARS REQUIRED (set as GitHub Secrets):
    FB_PAGE_ACCESS_TOKEN
    FB_PAGE_ID
"""

import os
import sys
import json
import time
import requests

MANIFEST_FILE = "data/images/manifest.json"
IMAGES_DIR = "data/images"
CAPTIONS_FILE = "data/captions.json"
DELAY_BETWEEN_POSTS_SECONDS = 5
GRAPH_API_VERSION = "v21.0"


def build_message(caption_entry):
    if not caption_entry:
        return ""
    caption = caption_entry.get("caption", "").strip()
    hashtags = caption_entry.get("hashtags", [])
    hashtag_line = " ".join(hashtags) if hashtags else ""
    if caption and hashtag_line:
        return f"{caption}\n\n{hashtag_line}"
    return caption or hashtag_line


def post_photo(page_id, access_token, image_path, message):
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/photos"
    with open(image_path, "rb") as photo_file:
        response = requests.post(
            url,
            data={"message": message, "access_token": access_token},
            files={"source": photo_file},
            timeout=60,
        )
    return response


def main():
    page_id = os.environ.get("FB_PAGE_ID")
    access_token = os.environ.get("FB_PAGE_ACCESS_TOKEN")

    if not page_id or not access_token:
        print("[facebook_poster] FB_PAGE_ID or FB_PAGE_ACCESS_TOKEN not set — skipping Facebook posting for this run.")
        sys.exit(0)

    if not os.path.exists(MANIFEST_FILE):
        print(f"[facebook_poster] {MANIFEST_FILE} not found — nothing generated this run. Exiting quietly.")
        sys.exit(0)

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    if not manifest:
        print("[facebook_poster] No posts this run. Nothing to send.")
        sys.exit(0)

    captions = []
    if os.path.exists(CAPTIONS_FILE):
        with open(CAPTIONS_FILE, "r", encoding="utf-8") as f:
            captions = json.load(f)

    sent_count = 0

    for i, entry in enumerate(manifest):
        filename = entry.get("image")
        image_path = os.path.join(IMAGES_DIR, filename) if filename else None

        if not image_path or not os.path.exists(image_path):
            print(f"[facebook_poster] Skipping entry {i + 1}: image file missing ({filename}).")
            entry["facebook_sent"] = False
            continue

        caption_entry = captions[i] if i < len(captions) else None
        message = build_message(caption_entry)

        try:
            response = post_photo(page_id, access_token, image_path, message)
            if response.status_code == 200 and "id" in response.json():
                print(f"[facebook_poster] Posted {filename} to Facebook successfully.")
                entry["facebook_sent"] = True
                sent_count += 1
            else:
                print(f"[facebook_poster] ERROR posting {filename}: {response.status_code} {response.text}")
                entry["facebook_sent"] = False
        except Exception as e:
            print(f"[facebook_poster] EXCEPTION posting {filename}: {e}")
            entry["facebook_sent"] = False

        if i < len(manifest) - 1:
            time.sleep(DELAY_BETWEEN_POSTS_SECONDS)

    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"[facebook_poster] Done. Posted {sent_count}/{len(manifest)} post(s) to Facebook.")


if __name__ == "__main__":
    main()
