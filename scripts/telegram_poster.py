"""
telegram_poster.py
-------------------
Sends ALL of this run's images to the Telegram channel, one after another,
with a short delay between each (Telegram allows roughly 1 message/second
to a given chat, so we stay well under that).

Runs 3 times a day, right after content_agent.py + image_generator.py +
caption_generator.py, as part of the single combined workflow.

Telegram posts get ONLY the image — no caption (per our design).

ENV VARS REQUIRED (set as GitHub Secrets):
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID     (e.g. @sports_world)
"""

import os
import sys
import json
import time
import requests

MANIFEST_FILE = "data/images/manifest.json"
IMAGES_DIR = "data/images"
DELAY_BETWEEN_POSTS_SECONDS = 4


def send_photo(bot_token, chat_id, image_path):
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    with open(image_path, "rb") as photo_file:
        response = requests.post(
            url,
            data={"chat_id": chat_id},
            files={"photo": photo_file},
            timeout=60,
        )
    return response


def main():
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("[telegram_poster] ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set.")
        sys.exit(1)

    if not os.path.exists(MANIFEST_FILE):
        print(f"[telegram_poster] {MANIFEST_FILE} not found — nothing generated this run. Exiting quietly.")
        sys.exit(0)

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    if not manifest:
        print("[telegram_poster] No posts this run. Nothing to send.")
        sys.exit(0)

    sent_count = 0
    had_failure = False

    for i, entry in enumerate(manifest, 1):
        filename = entry.get("image")
        image_path = os.path.join(IMAGES_DIR, filename) if filename else None

        if not image_path or not os.path.exists(image_path):
            print(f"[telegram_poster] Skipping entry {i}: image file missing ({filename}).")
            continue

        response = send_photo(bot_token, chat_id, image_path)

        if response.status_code == 200 and response.json().get("ok"):
            print(f"[telegram_poster] Sent {filename} to Telegram successfully.")
            entry["telegram_sent"] = True
            sent_count += 1
        else:
            print(f"[telegram_poster] ERROR sending {filename}: {response.status_code} {response.text}")
            entry["telegram_sent"] = False
            had_failure = True

        if i < len(manifest):
            time.sleep(DELAY_BETWEEN_POSTS_SECONDS)

    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"[telegram_poster] Done. Sent {sent_count}/{len(manifest)} post(s) to Telegram.")

    if had_failure and sent_count == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
