"""
image_generator.py
-------------------
Reads data/posts_today.json (written by content_agent.py) and renders one
image per post, using the template (A-E) chosen for that post.

Template F (Struggle Carousel) is intentionally SKIPPED here -- it needs a
human to manually add an old/archival photo, so those posts are left for
manual handling (see the printed warning).

All text fields are sanitized before rendering (fancy dashes/quotes/emoji
etc. are normalized to plain ASCII) so nothing renders as a broken glyph
box. Templates B and E use a real, generic sport photo from Pexels as
background when PEXELS_API_KEY is set (falls back cleanly to the plain
color design on any failure). Every template also draws a simple
sport-relevant icon, picks its accent color from a rotating palette (so
consecutive posts don't look identical), and credits the original news
source(s) in a small line.

INPUT:
    data/posts_today.json

OUTPUT:
    data/images/post_1.jpg, post_2.jpg, ... (one per non-F post)
    data/images/manifest.json  (maps each image file back to its post data,
                                 used later by the posting scripts)
"""

import os
import re
import io
import sys
import json
import random
import unicodedata
import requests
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"

SPORT_PHOTO_QUERIES = {
    "cricket": "cricket stadium",
    "football": "football stadium night",
    "soccer": "football stadium night",
    "hockey": "field hockey",
    "badminton": "badminton court",
    "boxing": "boxing ring",
    "wrestling": "wrestling mat",
    "swimming": "swimming pool lanes",
    "athletics": "running track stadium",
    "weightlifting": "gym weights",
    "kabaddi": "indian sports stadium",
    "shooting": "archery target",
    "tennis": "tennis court",
    "table tennis": "table tennis",
    "basketball": "basketball court",
    "volleyball": "volleyball court",
    "chess": "chess board",
}

_photo_cache = {}


def fetch_sport_photo(sport):
    """Fetches a real, generic (non-copyrighted) sport photo from Pexels for
    use as a background. Returns None on ANY failure (no key, no network,
    no results, bad response) so callers can cleanly fall back to the
    plain-color design -- a missing photo must never break image
    generation."""
    if not PEXELS_API_KEY:
        return None
    query = SPORT_PHOTO_QUERIES.get((sport or "").lower(), f"{sport} sport" if sport else "sports stadium")
    if query in _photo_cache:
        return _photo_cache[query]
    try:
        resp = requests.get(
            PEXELS_SEARCH_URL,
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "per_page": 5, "orientation": "portrait"},
            timeout=15,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        if not photos:
            _photo_cache[query] = None
            return None
        photo_url = random.choice(photos)["src"]["large2x"]
        img_resp = requests.get(photo_url, timeout=20)
        img_resp.raise_for_status()
        photo = Image.open(io.BytesIO(img_resp.content)).convert("RGBA")
        _photo_cache[query] = photo
        return photo
    except Exception as e:
        print(f"[image_generator] Pexels fetch failed for '{query}': {e}")
        _photo_cache[query] = None
        return None


def photo_background(sport, tint, tint_strength):
    photo = fetch_sport_photo(sport)
    if photo is None:
        return None
    pw, ph = photo.size
    scale = max(W / pw, H / ph)
    photo = photo.resize((int(pw * scale) + 1, int(ph * scale) + 1))
    pw, ph = photo.size
    left, top = (pw - W) // 2, (ph - H) // 2
    photo = photo.crop((left, top, left + W, top + H))
    overlay = Image.new("RGBA", (W, H), tuple(tint) + (tint_strength,))
    return Image.alpha_composite(photo, overlay)

FONT_DIR = "assets/fonts"
FBOLD = os.path.join(FONT_DIR, "Poppins-Bold.ttf")
FMED = os.path.join(FONT_DIR, "Poppins-Medium.ttf")
FREG = os.path.join(FONT_DIR, "Poppins-Regular.ttf")

POSTS_FILE = "data/posts_today.json"
OUTPUT_DIR = "data/images"

BRAND = "sports_world"
ACCENT = (230, 190, 60)

DARK_PALETTE = [
    (70, 120, 220),   # blue
    (150, 60, 190),   # purple
    (20, 130, 110),   # teal
    (170, 50, 70),    # wine
    (40, 110, 70),    # forest green
    (190, 100, 30),   # burnt orange
]

LIGHT_PALETTE = [
    (230, 190, 60),   # gold
    (150, 195, 230),  # sky blue
    (190, 225, 165),  # mint
    (235, 180, 190),  # rose
    (205, 185, 230),  # lavender
    (245, 195, 145),  # peach
]


def pick_color(seed_text, palette):
    seed = sum(ord(c) for c in (seed_text or "")) or 1
    return palette[seed % len(palette)]


def darken(color, factor=0.55):
    return tuple(int(c * factor) for c in color[:3])


def draw_source_line(draw, x, y, source_names, font, fill, max_width=None):
    names = [n for n in (source_names or []) if n]
    if not names:
        return
    text = "Source: " + ", ".join(names[:3])
    if max_width:
        text = wrap_text(text, font, max_width, draw)[0]
    draw.text((x, y), text, font=font, fill=fill)

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

# ---------------------------------------------------------------------------
# Text sanitization -- prevents "tofu" / missing-glyph boxes in the rendered
# image by normalizing fancy punctuation (smart quotes, en/em dashes, etc.)
# and accented letters down to plain ASCII, which the bundled Poppins font
# is guaranteed to support.
# ---------------------------------------------------------------------------

_PUNCT_MAP = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u2032": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u2033": '"',
    "\u2013": "-", "\u2014": "-", "\u2010": "-", "\u2011": "-", "\u2012": "-",
    "\u2026": "...", "\u00a0": " ", "\u2022": "-", "\u2605": "*", "\u2606": "*",
}


def sanitize_text(text):
    if not text:
        return ""
    text = str(text)
    for bad, good in _PUNCT_MAP.items():
        text = text.replace(bad, good)
    # Fold accented Latin letters to their plain ASCII base (e.g. é -> e)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    # Anything still outside printable ASCII (emoji, stray symbols) -> space
    text = "".join(ch if 32 <= ord(ch) <= 126 else " " for ch in text)
    return re.sub(r"\s+", " ", text).strip()


def sanitize_post(post):
    for key in ("headline", "footer_text", "category", "sport", "highlight_phrase"):
        if key in post and post[key]:
            post[key] = sanitize_text(post[key])
    if isinstance(post.get("source_names"), list):
        post["source_names"] = [sanitize_text(n) for n in post["source_names"] if sanitize_text(n)]
    rows = post.get("table_rows")
    if isinstance(rows, list):
        clean_rows = []
        for row in rows:
            if isinstance(row, (list, tuple)) and len(row) == 2:
                clean_rows.append([sanitize_text(row[0]), sanitize_text(row[1])])
        post["table_rows"] = clean_rows
    return post


# ---------------------------------------------------------------------------
# Shared drawing helpers
# ---------------------------------------------------------------------------

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


def base_canvas(bg_color=(10, 12, 18), sport=None, tint_strength=140):
    if sport:
        photo = photo_background(sport, bg_color, tint_strength)
        if photo is not None:
            return photo
    img = Image.new("RGB", (W, H), bg_color).convert("RGBA")
    return img


# ---------------------------------------------------------------------------
# Sport icon -- simple, recognizable generic graphic used as an accent
# (and as the full fallback when no real photo is available). Drawn with
# plain shapes only, so it never depends on a font glyph being present.
# ---------------------------------------------------------------------------

def sport_icon(draw, cx, cy, r, sport, color):
    s = (sport or "").lower()
    lw = max(3, int(r * 0.09))

    if "cricket" in s:
        draw.rounded_rectangle(
            [cx - r * 0.15, cy - r * 0.6, cx + r * 0.32, cy + r * 0.15],
            radius=r * 0.16, outline=color, width=lw,
        )
        draw.line([(cx - r * 0.15, cy + r * 0.05), (cx - r * 0.55, cy + r * 0.55)], fill=color, width=lw)
        draw.ellipse([cx - r * 0.7, cy + r * 0.4, cx - r * 0.4, cy + r * 0.7], outline=color, width=lw)

    elif "football" in s or "soccer" in s or "kabaddi" in s or "kho kho" in s:
        draw.ellipse([cx - r * 0.6, cy - r * 0.6, cx + r * 0.6, cy + r * 0.6], outline=color, width=lw)
        try:
            draw.regular_polygon((cx, cy, r * 0.3), n_sides=5, outline=color, width=max(2, lw - 1))
        except Exception:
            draw.ellipse([cx - r * 0.2, cy - r * 0.2, cx + r * 0.2, cy + r * 0.2], outline=color, width=max(2, lw - 1))

    elif "hockey" in s:
        draw.line(
            [(cx - r * 0.45, cy - r * 0.55), (cx - r * 0.1, cy + r * 0.5), (cx + r * 0.4, cy + r * 0.5)],
            fill=color, width=lw, joint="curve",
        )
        draw.ellipse([cx + r * 0.35, cy + r * 0.3, cx + r * 0.62, cy + r * 0.57], outline=color, width=lw)

    elif "badminton" in s or "tennis" in s or "table tennis" in s or "volleyball" in s or "basketball" in s:
        draw.ellipse([cx - r * 0.55, cy - r * 0.55, cx + r * 0.1, cy + r * 0.1], outline=color, width=lw)
        draw.line([(cx, cy), (cx + r * 0.5, cy + r * 0.5)], fill=color, width=lw)
        draw.line([(cx - r * 0.15, cy + r * 0.35), (cx + r * 0.15, cy + r * 0.65)], fill=color, width=max(2, lw - 1))

    elif "box" in s or "wrestl" in s or "mma" in s or "judo" in s:
        draw.rounded_rectangle(
            [cx - r * 0.5, cy - r * 0.4, cx + r * 0.4, cy + r * 0.3],
            radius=r * 0.32, outline=color, width=lw,
        )
        draw.rounded_rectangle(
            [cx - r * 0.22, cy + r * 0.15, cx + r * 0.15, cy + r * 0.55],
            radius=r * 0.14, outline=color, width=lw,
        )

    elif "swim" in s:
        for i in range(3):
            yy = cy - r * 0.35 + i * r * 0.35
            draw.line(
                [(cx - r * 0.55, yy), (cx - r * 0.18, yy - r * 0.18), (cx + r * 0.18, yy + r * 0.18), (cx + r * 0.55, yy)],
                fill=color, width=lw, joint="curve",
            )

    elif "athlet" in s or "run" in s or "marathon" in s:
        draw.ellipse([cx - r * 0.15, cy - r * 0.55, cx + r * 0.15, cy - r * 0.25], outline=color, width=lw)
        draw.line([(cx, cy - r * 0.25), (cx, cy + r * 0.15)], fill=color, width=lw)
        draw.line([(cx, cy - r * 0.05), (cx + r * 0.4, cy - r * 0.25)], fill=color, width=lw)
        draw.line([(cx, cy + r * 0.15), (cx - r * 0.3, cy + r * 0.55)], fill=color, width=lw)
        draw.line([(cx, cy + r * 0.15), (cx + r * 0.35, cy + r * 0.5)], fill=color, width=lw)

    elif "weight" in s or "power" in s or "strength" in s:
        draw.line([(cx - r * 0.5, cy), (cx + r * 0.5, cy)], fill=color, width=lw)
        for sign in (-1, 1):
            draw.ellipse(
                [cx + sign * r * 0.55 - r * 0.2, cy - r * 0.32, cx + sign * r * 0.55 + r * 0.2, cy + r * 0.32],
                outline=color, width=lw,
            )

    elif "shoot" in s or "archery" in s:
        draw.ellipse([cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.55], outline=color, width=lw)
        draw.ellipse([cx - r * 0.28, cy - r * 0.28, cx + r * 0.28, cy + r * 0.28], outline=color, width=max(2, lw - 1))
        draw.ellipse([cx - r * 0.06, cy - r * 0.06, cx + r * 0.06, cy + r * 0.06], fill=color)

    else:
        # generic trophy -- safe default for awards, announcements, and any
        # sport not covered above
        draw.polygon(
            [(cx - r * 0.35, cy - r * 0.4), (cx + r * 0.35, cy - r * 0.4),
             (cx + r * 0.2, cy + r * 0.15), (cx - r * 0.2, cy + r * 0.15)],
            outline=color, width=lw,
        )
        draw.line([(cx - r * 0.1, cy + r * 0.15), (cx - r * 0.1, cy + r * 0.35)], fill=color, width=lw)
        draw.line([(cx + r * 0.1, cy + r * 0.15), (cx + r * 0.1, cy + r * 0.35)], fill=color, width=lw)
        draw.rectangle([cx - r * 0.3, cy + r * 0.35, cx + r * 0.3, cy + r * 0.45], outline=color, width=lw)


# ---------------------------------------------------------------------------
# Template A: Magazine Editorial
# ---------------------------------------------------------------------------
def render_A(post):
    img = base_canvas()
    draw = ImageDraw.Draw(img)
    theme = pick_color(post.get("headline", ""), DARK_PALETTE)
    draw.polygon([(0, 0), (W, 0), (W, int(H * 0.42)), (0, int(H * 0.30))], fill=theme)
    img = add_texture_lines(img, color=(255, 255, 255, 22), area=(0, 0, W, int(H * 0.42)))
    draw = ImageDraw.Draw(img)

    sport_icon(draw, W - 90, 90, 40, post.get("sport", ""), (255, 255, 255, 235))
    f_tag = ImageFont.truetype(FBOLD, 24)
    tag = f"{post.get('sport', '').upper()}  -  {post.get('category', '').upper()}"
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
    f_src = ImageFont.truetype(FREG, 20)
    draw_source_line(draw, 80, y + 54, post.get("source_names"), f_src, (150, 150, 155, 220), W - 140)
    watermark(draw)
    return img


# ---------------------------------------------------------------------------
# Template B: Medal/Score Highlight
# ---------------------------------------------------------------------------
def render_B(post):
    img = base_canvas((14, 20, 34), sport=post.get("sport", ""), tint_strength=110)
    draw = ImageDraw.Draw(img)

    f_tag = ImageFont.truetype(FBOLD, 23)
    tag = f"{post.get('sport', '').upper()}  -  {post.get('category', '').upper()}"
    tw = draw.textlength(tag, font=f_tag)
    draw.rounded_rectangle([(W - tw) / 2 - 28, 72, (W + tw) / 2 + 28, 120], radius=24, fill=ACCENT)
    draw.text(((W - tw) / 2, 84), tag, font=f_tag, fill=(20, 14, 4, 255))

    cx, cy, r = W / 2, 250, 78
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(232, 196, 80, 255))
    draw.ellipse([cx - r + 10, cy - r + 10, cx + r - 10, cy + r - 10], fill=ACCENT)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, 255), width=5)
    sport_icon(draw, cx, cy, r * 0.72, post.get("sport", ""), (255, 255, 255, 235))

    img = add_texture_lines(img, color=(255, 255, 255, 14), n=16, area=(0, 360, W, 640))
    draw = ImageDraw.Draw(img)

    grad_top = 380
    for yy in range(grad_top, H):
        a = int(225 * ((yy - grad_top) / (H - grad_top)))
        draw.line([(0, yy), (W, yy)], fill=(8, 9, 14, a))

    f_h = ImageFont.truetype(FBOLD, 40)
    lines = wrap_text(post.get("headline", ""), f_h, W - 130, draw)
    y = 640
    for line in lines:
        draw_highlighted_line(draw, line, f_h, 65, y, post.get("highlight_phrase", ""), (255, 255, 255, 255), ACCENT)
        y += 54

    f_s = ImageFont.truetype(FBOLD, 25)
    draw.text((65, y + 14), post.get("footer_text", ""), font=f_s, fill=ACCENT)
    f_src = ImageFont.truetype(FREG, 19)
    draw_source_line(draw, 65, y + 48, post.get("source_names"), f_src, (210, 210, 210, 200), W - 130)
    watermark(draw)
    return img


# ---------------------------------------------------------------------------
# Template C: Stats Grid
# ---------------------------------------------------------------------------
def render_C(post):
    img = base_canvas()
    draw = ImageDraw.Draw(img)
    theme = pick_color(post.get("headline", ""), LIGHT_PALETTE)
    draw.rectangle([0, 0, 420, H], fill=theme)
    img = add_texture_lines(img, color=(255, 255, 255, 20), area=(0, 0, 420, H))
    draw = ImageDraw.Draw(img)

    sport_icon(draw, 90, 90, 38, post.get("sport", ""), (255, 255, 255, 235))
    f_tag = ImageFont.truetype(FBOLD, 20)
    tag_lines = wrap_text(f"{post.get('sport','').upper()}  -  {post.get('category','').upper()}", f_tag, 300, draw)
    ty = 150
    for l in tag_lines:
        draw.text((60, ty), l, font=f_tag, fill=(20, 15, 5, 255))
        ty += 26

    f_title = ImageFont.truetype(FBOLD, 25)
    ty += 20
    title_lines = wrap_text(post.get("headline", ""), f_title, 345, draw)
    for l in title_lines:
        draw.text((60, ty), l, font=f_title, fill=(15, 10, 5, 255))
        ty += 33

    icon_cy = ty + 170
    if icon_cy < H - 170:
        sport_icon(draw, 210, icon_cy, 140, post.get("sport", ""), (255, 255, 255, 80))

    rows = post.get("table_rows") or []
    y = 150
    f_year = ImageFont.truetype(FBOLD, 32)
    f_desc = ImageFont.truetype(FMED, 24)
    theme_dark = darken(theme, 0.5)
    for label, value in rows[:6]:
        draw.rounded_rectangle([460, y, W - 60, y + 96], radius=14, fill=(255, 255, 255, 22))
        draw.rectangle([460, y, 468, y + 96], fill=theme_dark)
        draw.text((495, y + 14), str(label), font=f_year, fill=theme_dark)
        val_lines = wrap_text(str(value), f_desc, W - 60 - 495 - 20, draw)
        vy = y + 52
        for vl in val_lines[:2]:
            draw.text((495, vy), vl, font=f_desc, fill=(230, 230, 230, 255))
            vy += 28
        y += 116

    f_foot = ImageFont.truetype(FMED, 22)
    draw.text((460, y + 20), post.get("footer_text", ""), font=f_foot, fill=theme)
    f_src = ImageFont.truetype(FREG, 18)
    draw_source_line(draw, 460, y + 50, post.get("source_names"), f_src, (140, 140, 145, 220), W - 520)
    watermark(draw)
    return img


# ---------------------------------------------------------------------------
# Template D: Standings / Tally Table
# ---------------------------------------------------------------------------
def render_D(post):
    img = base_canvas()
    draw = ImageDraw.Draw(img)
    theme = pick_color(post.get("headline", ""), DARK_PALETTE)
    header_h = 300
    draw.rectangle([0, 0, W, header_h], fill=theme)
    draw.polygon([(0, header_h), (W, header_h - 70), (W, header_h), (0, header_h)], fill=(10, 12, 18))
    draw = ImageDraw.Draw(img)

    sport_icon(draw, 90, 90, 38, post.get("sport", ""), (255, 255, 255, 235))
    f_tag = ImageFont.truetype(FBOLD, 22)
    draw.text((150, 72), f"{post.get('sport','').upper()}  -  {post.get('category','').upper()}", font=f_tag, fill=(255, 255, 255, 220))
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
        row_bg = (26, 28, 38, 255) if i % 2 == 0 else (14, 16, 22, 255)
        draw.rectangle([50, y, W - 50, y + 64], fill=row_bg)
        draw.text((70, y + 15), str(i + 1), font=f_rank, fill=theme if i > 2 else (255, 205, 60, 255))
        flag_swatch(draw, 115, y + 18, 46, 28, str(label))
        draw.text((175, y + 15), str(label), font=f_team, fill=(255, 255, 255, 255))
        pw = draw.textlength(str(value), font=f_val)
        draw.text((W - 70 - pw, y + 15), str(value), font=f_val, fill=(255, 255, 255, 255))
        y += 70

    f_foot = ImageFont.truetype(FMED, 22)
    draw.text((60, y + 24), post.get("footer_text", ""), font=f_foot, fill=theme)
    f_src = ImageFont.truetype(FREG, 19)
    draw_source_line(draw, 60, y + 56, post.get("source_names"), f_src, (150, 150, 155, 220), W - 120)
    watermark(draw)
    return img


# ---------------------------------------------------------------------------
# Template E: Breaking Alert
# ---------------------------------------------------------------------------
def render_E(post):
    img = base_canvas((14, 10, 10), sport=post.get("sport", ""), tint_strength=165)
    draw = ImageDraw.Draw(img)
    theme = (230, 70, 60)
    draw.rectangle([0, 0, W, 140], fill=theme)
    draw = ImageDraw.Draw(img)

    f_rib = ImageFont.truetype(FBOLD, 28)
    draw.text((60, 52), "BREAKING", font=f_rib, fill=(255, 255, 255, 255))
    sport_icon(draw, W - 90, 70, 34, post.get("sport", ""), (255, 255, 255, 235))

    f_tag = ImageFont.truetype(FBOLD, 22)
    draw.text((60, 175), f"{post.get('sport','').upper()}  -  {post.get('category','').upper()}", font=f_tag, fill=theme)

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
    f_src = ImageFont.truetype(FREG, 19)
    draw_source_line(draw, 60, y + 54, post.get("source_names"), f_src, (190, 150, 145, 210), W - 120)
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
        post = sanitize_post(post)
        template = post.get("template", "A").upper()
        if template == "F":
            print(f"[image_generator] Post {i} uses template F (Struggle Carousel) -- "
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
