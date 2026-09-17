"""
image_generator.py
-------------------
Reads data/posts_today.json (written by content_agent.py -- one quote
object) and renders the final quote-card image.

Design: black background, bold quote text with one highlighted phrase in
the category's accent color, a thin long accent bar on the left, and a
brand signature (logo + "ruthless.mindset") below the quote text.

Also writes data/captions.json in the same shape the Facebook poster
already expects, so facebook_poster.py needs no changes.

INPUT:
    data/posts_today.json

OUTPUT:
    data/images/post_1.jpg
    data/images/manifest.json
    data/captions.json
"""

import os
import sys
import json
from PIL import Image, ImageDraw, ImageFont

W = H = 1080

FONT_DIR = "assets/fonts"
FBOLD = os.path.join(FONT_DIR, "Poppins-Bold.ttf")

LOGO_PATH = "96c3241a-6180-4c4b-946c-5fe208091c96.jpeg"
BRAND = "ruthless.mindset"

POSTS_FILE = "data/posts_today.json"
OUTPUT_DIR = "data/images"
CAPTIONS_FILE = "data/captions.json"


def wrap_text(text, font, max_width, draw):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_highlighted_line(draw, line, font, x, y, highlight, normal_fill, hi_fill):
    if highlight and highlight in line:
        before, _, after = line.partition(highlight)
        bw = draw.textlength(before, font=font)
        hw = draw.textlength(highlight, font=font)
        draw.text((x, y), before, font=font, fill=normal_fill)
        draw.text((x + bw, y), highlight, font=font, fill=hi_fill)
        draw.text((x + bw + hw, y), after, font=font, fill=normal_fill)
    else:
        draw.text((x, y), line, font=font, fill=normal_fill)


def circle_crop(im, size):
    im = im.resize((size, size)).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse([0, 0, size, size], fill=255)
    im.putalpha(mask)
    return im


def load_logo():
    try:
        return Image.open(LOGO_PATH)
    except Exception as e:
        print(f"[image_generator] WARNING: could not open logo at {LOGO_PATH}: {e}")
        return None


def render_card(post, logo_src):
    quote = post.get("quote", "").strip()
    highlight = post.get("highlight", "").strip()
    accent = tuple(post.get("accent", [210, 60, 50]))

    img = Image.new("RGB", (W, H), (8, 8, 8)).convert("RGBA")
    draw = ImageDraw.Draw(img)

    f_q = ImageFont.truetype(FBOLD, 42)
    max_w = W - 220
    lines = wrap_text(quote, f_q, max_w, draw)
    line_h = 54
    total_h = len(lines) * line_h
    start_y = (H - total_h) / 2

    bar_pad = 55
    bar_w = 20
    bar_x0, bar_y0 = 80, start_y - bar_pad
    bar_x1, bar_y1 = bar_x0 + bar_w, start_y + total_h - line_h + 40 + bar_pad
    draw.rounded_rectangle([bar_x0, bar_y0, bar_x1, bar_y1], radius=7, fill=accent)

    y = start_y
    for line in lines:
        draw_highlighted_line(draw, line, f_q, 140, y, highlight, (238, 238, 238, 255), accent)
        y += line_h

    icon_size = 110
    sig_y = int(y + 36)
    if logo_src is not None:
        img.alpha_composite(circle_crop(logo_src, icon_size), (140, sig_y))
    f_wm = ImageFont.truetype(FBOLD, 19)
    draw.text((140 + icon_size + 18, sig_y + icon_size / 2 - 10), BRAND, font=f_wm, fill=(210, 210, 215, 255))

    return img


def main():
    if not os.path.exists(POSTS_FILE):
        print(f"[image_generator] ERROR: {POSTS_FILE} not found. Run content_agent.py first.")
        sys.exit(1)

    with open(POSTS_FILE, "r", encoding="utf-8") as f:
        posts = json.load(f)

    if not posts:
        print("[image_generator] No posts to render (empty list).")
        with open(os.path.join(OUTPUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump([], f)
        with open(CAPTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    logo_src = load_logo()

    manifest = []
    captions = []

    for i, post in enumerate(posts, 1):
        try:
            img = render_card(post, logo_src)
        except Exception as e:
            print(f"[image_generator] ERROR rendering post {i}: {e}")
            continue

        filename = f"post_{i}.jpg"
        path = os.path.join(OUTPUT_DIR, filename)
        img.convert("RGB").save(path, quality=93)
        manifest.append({"image": filename, **post})

        hashtags = post.get("hashtags") or []
        caption_text = post.get("quote", "")
        captions.append({
            "post_index": i,
            "caption": caption_text,
            "hashtags": hashtags,
        })

        print(f"[image_generator] Saved {path}")

    with open(os.path.join(OUTPUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    with open(CAPTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(captions, f, ensure_ascii=False, indent=2)

    print(f"[image_generator] Done. {len(manifest)} image(s) generated.")


if __name__ == "__main__":
    main()
