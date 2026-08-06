"""
telegram_poster.py
-------------------
Sends ONE image (chosen by POST_INDEX) to the Telegram channel.
Runs 5 times a day, once per scheduled slot (see
.github/workflows/post_content.yml), each time with a different
POST_INDEX (1-5) passed in as an environment variable.

Telegram posts get ONLY the image — no caption (per our design).

If the requested POST_INDEX has no image (e.g. that story used
template F and was skipped by image_generator.py), this exits
cleanly without error — there's simply nothing to post at that slot.

ENV VARS REQUIRED (set as GitHub Secrets / workflow env):
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID     (e.g. @sports_world)
    POST_INDEX           (e.g. 1, 2, 3, 4, or 5)
"""

import os
import sys
import json
import requests

MANIFEST_FILE = "data/images/manifest.json"
IMAGES_DIR = "data/images"


def main():
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    post_index = os.environ.get("POST_INDEX")

    if not bot_token or not chat_id:
        print("[telegram_poster] ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set.")
        sys.exit(1)

    if not post_index:
        print("[telegram_poster] ERROR: POST_INDEX not set.")
        sys.exit(1)

    if not os.path.exists(MANIFEST_FILE):
        print(f"[telegram_poster] {MANIFEST_FILE} not found — nothing generated today yet. Exiting quietly.")
        sys.exit(0)

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    target_filename = f"post_{post_index}.jpg"
    entry = next((m for m in manifest if m.get("image") == target_filename), None)

    if entry is None:
        print(f"[telegram_poster] No image for slot {post_index} today "
              f"(likely a Struggle-Carousel story that needs a manual post). Exiting quietly.")
        sys.exit(0)

    image_path = os.path.join(IMAGES_DIR, target_filename)
    if not os.path.exists(image_path):
        print(f"[telegram_poster] ERROR: manifest points to {image_path} but the file is missing.")
        sys.exit(1)

    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    with open(image_path, "rb") as photo_file:
        response = requests.post(
            url,
            data={"chat_id": chat_id},
            files={"photo": photo_file},
            timeout=60,
        )

    if response.status_code == 200 and response.json().get("ok"):
        print(f"[telegram_poster] Sent slot {post_index} ({target_filename}) to Telegram successfully.")
        entry["telegram_sent"] = True
        with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
    else:
        print(f"[telegram_poster] ERROR: Telegram API returned {response.status_code}: {response.text}")
        sys.exit(1)


if __name__ == "__main__":
    main()
