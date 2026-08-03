"""
image_generator.py
-------------------
Reads data/posts_today.json (written by content_agent.py) and renders one
image per post, using the template (A-E) chosen for that post.

Template F (Struggle Carousel) is intentionally SKIPPED here — it needs a
human to manually add an old/archival photo, so those posts are left for
manual handling (see the printed warning).

INPUT:
    data/posts_today.json

OUTPUT:
    data/images/post_1.jpg, post_2.jpg, ... (one per non-F post)
    data/images/manifest.json  (maps each image file back to its post data,
                                 used later by the posting scripts)
"""

import os
import sys
import json
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350

FONT_DIR = "assets/fonts"
FBOLD = os.path.join(FONT_DIR, "Poppins-Bold.ttf")
FMED = os.path.join(FONT_DIR, "Poppins-Medium.ttf")
FREG = os.path.join(FONT_DIR, "Poppins-Regular.ttf")

POSTS_FILE = "data/posts_today.json"
OUTPUT_DIR = "data/images"

BRAND = "sports_world"
ACCENT = (230, 190, 60)

FLAG_COLORS = {
    "AUSTRALIA": [(0, 0, 60), (255, 205, 0)],
    "SOUTH AFRICA": [(0, 120, 60), (255, 205, 0), (0, 0, 0)],
    "NEW ZEALAND": [(0, 0, 0), (0, 0, 0)],
    "INDIA": [(255, 153, 51), (255, 255, 255), (19, 136, 8)],
    "ENGLAND": [(255, 255, 255), (200, 20, 40)],
    "PAKISTAN": [(1, 96, 55), (255, 255, 255)],
    "SRI LANKA": [(140, 20, 30), (0, 120, 60)],
    "BANGLADESH": [(0, 106, 78), (240, 20, 20)],
    "WEST INDIES": [(120, 10, 20), (255, 205, 0), (0, 0, 0)],
}

def wrap_text(text, font, max_width, draw):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= max_width:
            cur = test
        else:
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


def add_texture_lines(img, color=(255, 255, 255, 18), n=14, area=None):
    if area is None:
        area = (0, 0, W, H)
    draw = ImageDraw.Draw(img, "RGBA")
    x0, y0, x1, y1 = area
    for i in range(n):
        x = x0 + (x1 - x0) * i / n
        draw.line([(x, y0), (x - 120, y1)], fill=color, width=2)
    return img


def crest_badge(draw, cx, cy, r, ring_color, inner_color, letter="SW"):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=inner_color, outline=ring_color, width=4)
    f = ImageFont.truetype(FBOLD, int(r * 0.75))
    lw = draw.textlength(letter, font=f)
    draw.text((cx - lw / 2, cy - r * 0.55), letter, font=f, fill=ring_color)


def watermark(draw):
    # Centered at the bottom, semi-transparent so it sits quietly under the design
    wm_y = H - 50
    fw = ImageFont.truetype(FBOLD, 24)
    text_w = draw.textlength(BRAND, font=fw)
    icon_d = 36
    gap = 14
    total_w = icon_d + gap + text_w
    start_x = (W - total_w) / 2

    tg_cx, tg_cy, tg_r = start_x + icon_d / 2, wm_y, icon_d / 2
    alpha = 150
    draw.ellipse([tg_cx - tg_r, tg_cy - tg_r, tg_cx + tg_r, tg_cy + tg_r], fill=(38, 150, 220, alpha))
    draw.polygon([(tg_cx - 8, tg_cy + 2), (tg_cx + 11, tg_cy - 8), (tg_cx + 2, tg_cy + 9)], fill=(255, 255, 255, alpha))
    draw.polygon([(tg_cx - 8, tg_cy + 2), (tg_cx + 2, tg_cy + 9), (tg_cx - 3, tg_cy + 5)], fill=(210, 230, 245, alpha))
    draw.text((start_x + icon_d + gap, wm_y - 12), BRAND, font=fw, fill=(255, 255, 255, alpha))


def flag_swatch(draw, x, y, w, h, name):
    colors = FLAG_COLORS.get(name.upper(), [(120, 120, 120)])
    n = len(colors)
    seg = w / n
    for i, c in enumerate(colors):
        draw.rectangle([x + i * seg, y, x + (i + 1) * seg, y + h], fill=c)
    draw.rectangle([x, y, x + w, y + h], outline=(255, 255, 255, 120), width=1)


def base_canvas(bg_color=(10, 12, 18)):
    img = Image.new("RGB", (W, H), bg_color).convert("RGBA")
    return img


def render_A(post):
    img = base_canvas()
    draw = ImageDraw.Draw(img)
    theme = (70, 120, 220)
    draw.polygon([(0, 0), (W, 0), (W, int(H * 0.42)), (0, int(H * 0.30))], fill=theme)
    img = add_texture_lines(img, color=(255, 255, 255, 22), area=(0, 0, W, int(H * 0.42)))
    draw = ImageDraw.Draw(img)

    crest_badge(draw, W - 90, 90, 40, (255, 255, 255, 255), (255, 255, 255, 35))
    f_tag = ImageFont.truetype(FBOLD, 24)
    tag = f"{post.get('sport', '').upper()}  \u2022  {post.get('category', '').upper()}"
    draw.text((60, 70), tag, font=f_tag, fill=(15, 10, 5, 255))

    f_h = ImageFont.truetype(FBOLD, 50)
    lines = wrap_text(post.get("headline", ""), f_h, W - 120, draw)
    y = int(H * 0.50)
    for line in lines:
        draw_highlighted_line(draw, line, f_h, 60, y, post.get("highlight_phrase", ""), (255, 255, 255, 255), theme)
        y += 62

    f_foot = ImageFont.truetype(FMED, 24)
    draw.rectangle([60, y + 20, 66, y + 54], fill=theme)
    draw.text((80, y + 20), post.get("footer_text", ""), font=f_foot, fill=theme)
    watermark(draw)
    return img


def render_B(post):
    img = base_canvas((14, 20, 34))
    draw = ImageDraw.Draw(img)

    f_tag = ImageFont.truetype(FBOLD, 23)
    tag = f"{post.get('sport', '').upper()}  \u2022  {post.get('category', '').upper()}"
    tw = draw.textlength(tag, font=f_tag)
    draw.rounded_rectangle([(W - tw) / 2 - 28, 72, (W + tw) / 2 + 28, 120], radius=24, fill=ACCENT)
    draw.text(((W - tw) / 2, 84), tag, font=f_tag, fill=(20, 14, 4, 255))

    cx, cy, r = W / 2, 250, 78
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(232, 196, 80, 255))
    draw.ellipse([cx - r + 10, cy - r + 10, cx + r - 10, cy + r - 10], fill=ACCENT)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, 255), width=5)
    f_star = ImageFont.truetype(FBOLD, 58)
    sw = draw.textlength("\u2605", font=f_star)
    draw.text((cx - sw / 2, cy - 38), "\u2605", font=f_star, fill=(255, 255, 255, 230))

    grad_top = 420
    for yy in range(grad_top, H):
        a = int(225 * ((yy - grad_top) / (H - grad_top)))
        draw.line([(0, yy), (W, yy)], fill=(8, 9, 14, a))

    f_h = ImageFont.truetype(FBOLD, 40)
    lines = wrap_text(post.get("headline", ""), f_h, W - 130, draw)
    y = 900
    for line in lines:
        draw_highlighted_line(draw, line, f_h, 65, y, post.get("highlight_phrase", ""), (255, 255, 255, 255), ACCENT)
        y += 54

    f_s = ImageFont.truetype(FBOLD, 25)
    draw.text((65, y + 14), post.get("footer_text", ""), font=f_s, fill=ACCENT)
    watermark(draw)
    return img


def render_C(post):
    img = base_canvas()
    draw = ImageDraw.Draw(img)
    theme = ACCENT
    draw.rectangle([0, 0, 420, H], fill=theme)
    img = add_texture_lines(img, color=(255, 255, 255, 20), area=(0, 0, 420, H))
    draw = ImageDraw.Draw(img)

    crest_badge(draw, 90, 90, 40, (255, 255, 255, 255), (255, 255, 255, 35))
    f_tag = ImageFont.truetype(FBOLD, 20)
    tag_lines = wrap_text(f"{post.get('sport','').upper()}  \u2022  {post.get('category','').upper()}", f_tag, 300, draw)
    ty = 150
    for l in tag_lines:
        draw.text((60, ty), l, font=f_tag, fill=(20, 15, 5, 255))
        ty += 26

    f_title = ImageFont.truetype(FBOLD, 32)
    ty += 20
    title_lines = wrap_text(post.get("headline", ""), f_title, 320, draw)
    for l in title_lines[:4]:
        draw.text((60, ty), l, font=f_title, fill=(15, 10, 5, 255))
        ty += 40

    rows = post.get("table_rows") or []
    y = 150
    f_year = ImageFont.truetype(FBOLD, 32)
    f_desc = ImageFont.truetype(FMED, 24)
    for label, value in rows[:6]:
        draw.rounded_rectangle([460, y, W - 60, y + 96], radius=14, fill=(255, 255, 255, 22))
        draw.rectangle([460, y, 468, y + 96], fill=theme)
        draw.text((495, y + 14), str(label), font=f_year, fill=theme)
        val_lines = wrap_text(str(value), f_desc, W - 60 - 495 - 20, draw)
        vy = y + 52
        for vl in val_lines[:2]:
            draw.text((495, vy), vl, font=f_desc, fill=(230, 230, 230, 255))
            vy += 28
        y += 116

    f_foot = ImageFont.truetype(FMED, 22)
    draw.text((460, y + 20), post.get("footer_text", ""), font=f_foot, fill=theme)
    watermark(draw)
    return img


def render_D(post):
    img = base_canvas()
    draw = ImageDraw.Draw(img)
    theme = (200, 150, 40)
    header_h = 300
    draw.rectangle([0, 0, W, header_h], fill=theme)
    draw.polygon([(0, header_h), (W, header_h - 70), (W, header_h), (0, header_h)], fill=(10, 12, 18))
    draw = ImageDraw.Draw(img)

    crest_badge(draw, 90, 90, 40, (255, 255, 255, 255), (255, 255, 255, 40))
    f_tag = ImageFont.truetype(FBOLD, 22)
    draw.text((150, 72), f"{post.get('sport','').upper()}  \u2022  {post.get('category','').upper()}", font=f_tag, fill=(255, 255, 255, 220))
    f_title = ImageFont.truetype(FBOLD, 44)
    title_lines = wrap_text(post.get("headline", ""), f_title, W - 120, draw)
    ty = 140
    for l in title_lines[:2]:
        draw.text((60, ty), l, font=f_title, fill=(255, 255, 255, 255))
        ty += 50

    y = header_h + 30
    f_hdr = ImageFont.truetype(FBOLD, 22)
    draw.text((60, y), "#", font=f_hdr, fill=(180, 180, 190, 255))
    draw.text((110, y), "TEAM / NAME", font=f_hdr, fill=(180, 180, 190, 255))
    draw.text((W - 140, y), "VALUE", font=f_hdr, fill=(180, 180, 190, 255))
    y += 40
    draw.line([(60, y), (W - 60, y)], fill=(255, 255, 255, 60), width=2)
    y += 16

    rows = post.get("table_rows") or []
    f_rank = ImageFont.truetype(FBOLD, 28)
    f_team = ImageFont.truetype(FMED, 28)
    f_val = ImageFont.truetype(FBOLD, 28)
    for i, (label, value) in enumerate(rows[:9]):
        row_bg = (255, 255, 255, 18) if i % 2 == 0 else (255, 255, 255, 6)
        draw.rectangle([50, y, W - 50, y + 64], fill=row_bg)
        draw.text((70, y + 15), str(i + 1), font=f_rank, fill=theme if i > 2 else (255, 205, 60, 255))
        flag_swatch(draw, 115, y + 18, 46, 28, str(label))
        draw.text((175, y + 15), str(label), font=f_team, fill=(255, 255, 255, 255))
        pw = draw.textlength(str(value), font=f_val)
        draw.text((W - 70 - pw, y + 15), str(value), font=f_val, fill=(255, 255, 255, 255))
        y += 70

    f_foot = ImageFont.truetype(FMED, 22)
    draw.text((60, y + 24), post.get("footer_text", ""), font=f_foot, fill=theme)
    watermark(draw)
    return img


def render_E(post):
    img = base_canvas((14, 10, 10))
    draw = ImageDraw.Draw(img)
    theme = (230, 70, 60)
    draw.rectangle([0, 0, W, 140], fill=theme)
    draw = ImageDraw.Draw(img)

    f_rib = ImageFont.truetype(FBOLD, 28)
    draw.text((60, 52), "\u26A0  BREAKING", font=f_rib, fill=(255, 255, 255, 255))
    crest_badge(draw, W - 90, 70, 34, (255, 255, 255, 255), (255, 255, 255, 40))

    f_tag = ImageFont.truetype(FBOLD, 22)
    draw.text((60, 175), f"{post.get('sport','').upper()}  \u2022  {post.get('category','').upper()}", font=f_tag, fill=theme)

    f_h = ImageFont.truetype(FBOLD, 46)
    lines = wrap_text(post.get("headline", ""), f_h, W - 120, draw)
    y = 230
    for line in lines:
        draw_highlighted_line(draw, line, f_h, 60, y, post.get("highlight_phrase", ""), (255, 255, 255, 255), theme)
        y += 58

    y += 30
    draw.rectangle([60, y, W - 60, y + 2], fill=theme)
    f_foot = ImageFont.truetype(FMED, 24)
    draw.text((60, y + 20), post.get("footer_text", ""), font=f_foot, fill=(220, 220, 220, 255))
    watermark(draw)
    return img


TEMPLATE_RENDERERS = {"A": render_A, "B": render_B, "C": render_C, "D": render_D, "E": render_E}


def main():
    if not os.path.exists(POSTS_FILE):
        print(f"[image_generator] ERROR: {POSTS_FILE} not found. Run content_agent.py first.")
        sys.exit(1)

    with open(POSTS_FILE, "r", encoding="utf-8") as f:
        posts = json.load(f)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    manifest = []

    for i, post in enumerate(posts, 1):
        template = post.get("template", "A").upper()
        if template == "F":
            print(f"[image_generator] Post {i} uses template F (Struggle Carousel) — "
                  f"SKIPPED, needs manual image. Headline: {post.get('headline', '')[:70]}")
            continue

        renderer = TEMPLATE_RENDERERS.get(template)
        if renderer is None:
            print(f"[image_generator] Unknown template '{template}' for post {i}, defaulting to A.")
            renderer = render_A

        try:
            img = renderer(post)
        except Exception as e:
            print(f"[image_generator] ERROR rendering post {i} (template {template}): {e}")
            continue

        filename = f"post_{i}.jpg"
        path = os.path.join(OUTPUT_DIR, filename)
        img.convert("RGB").save(path, quality=93)
        manifest.append({"image": filename, "template": template, **post})
        print(f"[image_generator] Saved {path}")

    with open(os.path.join(OUTPUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"[image_generator] Done. {len(manifest)} image(s) generated.")


if __name__ == "__main__":
    main()
