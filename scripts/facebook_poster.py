"""
facebook_poster.py
-------------------
Sends ONE image + caption (chosen by POST_INDEX) to the Facebook Page.
Runs 5 times a day, alongside telegram_poster.py, with the same
POST_INDEX (1-5) passed in as an environment variable.

Facebook posts get the image PLUS the caption + hashtags (unlike
Telegram, which gets image only).

If the requested POST_INDEX has no image (template F, skipped) or no
matching caption, this exits cleanly without error.

ENV VARS REQUIRED (set as GitHub Secrets / workflow env):
    FB_PAGE_ACCESS_TOKEN
    FB_PAGE_ID
    POST_INDEX           (e.g. 1, 2, 3, 4, or 5)
"""

import os
import sys
import json
import requests

MANIFEST_FILE = "data/images/manifest.json"
CAPTIONS_FILE = "data/captions.json"
IMAGES_DIR = "data/images"
GRAPH_API_VERSION = "v21.0"


def main():
    access_token = os.environ.get("FB_PAGE_ACCESS_TOKEN")
    page_id = os.environ.get("FB_PAGE_ID")
    post_index = os.environ.get("POST_INDEX")

    if not access_token or not page_id:
        print("[facebook_poster] ERROR: FB_PAGE_ACCESS_TOKEN or FB_PAGE_ID not set.")
        sys.exit(1)

    if not post_index:
        print("[facebook_poster] ERROR: POST_INDEX not set.")
        sys.exit(1)

    if not os.path.exists(MANIFEST_FILE):
        print(f"[facebook_poster] {MANIFEST_FILE} not found — nothing generated today yet. Exiting quietly.")
        sys.exit(0)

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    target_filename = f"post_{post_index}.jpg"
    entry = next((m for m in manifest if m.get("image") == target_filename), None)

    if entry is None:
        print(f"[facebook_poster] No image for slot {post_index} today "
              f"(likely a Struggle-Carousel story that needs a manual post). Exiting quietly.")
        sys.exit(0)

    image_path = os.path.join(IMAGES_DIR, target_filename)
    if not os.path.exists(image_path):
        print(f"[facebook_poster] ERROR: manifest points to {image_path} but the file is missing.")
        sys.exit(1)

    caption_text = ""
    if os.path.exists(CAPTIONS_FILE):
        with open(CAPTIONS_FILE, "r", encoding="utf-8") as f:
            captions = json.load(f)
        cap_entry = next((c for c in captions if str(c.get("post_index")) == str(post_index)), None)
        if cap_entry:
            hashtags = " ".join(f"#{h}" for h in cap_entry.get("hashtags", []))
            caption_text = f"{cap_entry.get('caption', '')}\n\n{hashtags}".strip()

    if not caption_text:
        print(f"[facebook_poster] WARNING: no caption found for slot {post_index}, posting image only.")

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}/photos"
    with open(image_path, "rb") as photo_file:
        response = requests.post(
            url,
            data={"caption": caption_text, "access_token": access_token},
            files={"source": photo_file},
            timeout=60,
        )

    if response.status_code == 200 and "id" in response.json():
        print(f"[facebook_poster] Sent slot {post_index} ({target_filename}) to Facebook successfully.")
        entry["facebook_sent"] = True
        with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
    else:
        print(f"[facebook_poster] ERROR: Facebook API returned {response.status_code}: {response.text}")
        sys.exit(1)


if __name__ == "__main__":
    main()
