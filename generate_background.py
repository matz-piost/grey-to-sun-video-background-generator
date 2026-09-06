#!/usr/bin/env python3
"""Grey-to-Sun background video generator.

Reads a JSON project file (see example_input.json / projects/*.json) and
renders a silent, vertical 9:16 MP4 background video with timed text and
image overlays -- ready to sit behind a green-screen / cutout recording in
a mobile editor such as CapCut's "Edits" app.

Usage:
    python3 generate_background.py                          # uses example_input.json
    python3 generate_background.py projects/video-001.json
    python3 generate_background.py projects/video-001.json --debug-safe-zones

If the configured background image/video file does not exist yet, a
placeholder "grey-to-sun" gradient is generated automatically so you can
test the whole pipeline before uploading your real footage.
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from moviepy import CompositeVideoClip, ImageClip, VideoFileClip, vfx

# ---------------------------------------------------------------------------
# Video specs
# ---------------------------------------------------------------------------

WIDTH, HEIGHT = 1080, 1920
FPS = 30
DEFAULT_DURATION = 45
HARD_CAP_SECONDS = 60

# Safe zones (fractions of frame height) -- keep essential overlays out of
# the very top (platform UI) and the bottom ~20% (captions / UI).
TOP_SAFE = 0.10
BOTTOM_SAFE = 0.80

# Main hook / accent captions are confined to the top third of the frame
# and always centred -- clear of Mila's face/body in the middle/lower frame.
TOP_THIRD = 1 / 3

# Two bundled fonts (fonts/, both SIL Open Font License -- free, no paid
# fonts), matching the two allowed overlay looks:
#   - Fraunces (serif) for "Editorial Hook" lines -- warm, soft, premium,
#     not a clinical grotesque, not a meme-caption font.
#   - Inter (sans) for "Analysis Card" text -- clean and calm for
#     screenshots/numbers/labels.
# Both ship as single variable files; PIL selects a weight (and, for
# Fraunces, optical size / softness) at render time. Each falls back to a
# system font if fonts/ is ever removed, so the tool still runs with no
# extra setup (weight/softness selection then has no effect).
FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
_INTER_VARIABLE = os.path.join(FONTS_DIR, "Inter-Variable.ttf")
_FRAUNCES_VARIABLE = os.path.join(FONTS_DIR, "Fraunces-Variable.ttf")
_CAVEAT_VARIABLE = os.path.join(FONTS_DIR, "Caveat-Variable.ttf")
_SANS_FALLBACK = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_SERIF_FALLBACK = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"


def _pick_font_path(preferred, fallback):
    if os.path.isfile(preferred):
        return preferred, True
    if os.path.isfile(fallback):
        return fallback, False
    return None, False


SANS_FONT_PATH, _SANS_IS_VARIABLE = _pick_font_path(_INTER_VARIABLE, _SANS_FALLBACK)
SERIF_FONT_PATH, _SERIF_IS_VARIABLE = _pick_font_path(_FRAUNCES_VARIABLE, _SERIF_FALLBACK)
# Caveat falls back to the serif face (not a real handwriting look, but
# keeps the "sticky" demo style from crashing if fonts/ is ever removed).
HAND_FONT_PATH, _HAND_IS_VARIABLE = _pick_font_path(_CAVEAT_VARIABLE, _SERIF_FALLBACK)


def load_font(size, weight="SemiBold"):
    """Load the Analysis Card sans font (Inter) at the given pixel size and
    named weight (Medium / SemiBold / Bold)."""
    if SANS_FONT_PATH is None:
        return ImageFont.load_default()
    font = ImageFont.truetype(SANS_FONT_PATH, size)
    if _SANS_IS_VARIABLE:
        try:
            font.set_variation_by_name(weight)
        except Exception:
            pass
    return font


def load_serif_font(size, opsz=90, wght=560, soft=55, wonk=0):
    """Load the Editorial Hook serif font (Fraunces) at the given pixel
    size, dialing in its optical-size/weight/softness/wonky axes for a
    warm, soft, premium-but-casual headline feel (not a novelty display
    face). Axis selection has no effect when falling back to the system's
    DejaVu Serif Bold."""
    if SERIF_FONT_PATH is None:
        return ImageFont.load_default()
    font = ImageFont.truetype(SERIF_FONT_PATH, size)
    if _SERIF_IS_VARIABLE:
        try:
            font.set_variation_by_axes([opsz, wght, soft, wonk])
        except Exception:
            pass
    return font


def load_hand_font(size, weight="Bold"):
    """Load the handwriting font (Caveat) used only by the "sticky" demo
    style -- not part of the two standard production looks."""
    if HAND_FONT_PATH is None:
        return ImageFont.load_default()
    font = ImageFont.truetype(HAND_FONT_PATH, size)
    if _HAND_IS_VARIABLE:
        try:
            font.set_variation_by_name(weight)
        except Exception:
            pass
    return font

# ---------------------------------------------------------------------------
# Colour palette -- warm / editorial, high-contrast, no neon.
# ---------------------------------------------------------------------------

CHARCOAL = (43, 43, 43, 255)
CREAM = (245, 239, 230, 255)
TERRACOTTA = (192, 101, 74, 255)
DUSTY_BLUE = (111, 143, 175, 255)
OLIVE = (138, 154, 107, 255)
BEIGE = (217, 201, 173, 255)
PALE_YELLOW = (246, 226, 160, 255)
PEACH = (243, 201, 165, 255)
BUTTER = (250, 238, 205, 255)
SHADOW_INK = (20, 16, 12)


def _alpha(color, a):
    return (color[0], color[1], color[2], a)


# ---------------------------------------------------------------------------
# Overlay style presets
# ---------------------------------------------------------------------------


# Two allowed overlay looks -- don't mix more styles into one video.
#
# Style A -- "Editorial Hook" (family="hook"): for emotional/positioning
# lines. Large, soft serif (Fraunces), warm cream/butter text directly over
# the footage -- no box, no outline, just a subtle soft shadow for
# readability. "headline" is the main hook size; "support" is the smaller
# accent/secondary-phrase size (roughly half); "teaser" is for a closing
# line -- no separate tag/label, just styled as a hook line.
#
# Style B -- "Analysis Card" (family="card"): for screenshots, numbers,
# analytics, creator examples. Cream/beige rounded card, charcoal Inter
# sans-serif text, a thin muted accent bar, no heavy shadow.
STYLES = {
    "headline": dict(
        family="hook", opsz=90, wght=560, soft=55, font_size=100,
        text_color=BUTTER,
    ),
    "support": dict(
        family="hook", opsz=40, wght=520, soft=55, font_size=50,
        text_color=BUTTER,
    ),
    "teaser": dict(
        family="hook", opsz=64, wght=560, soft=55, font_size=76,
        text_color=BUTTER,
    ),
    "card": dict(
        family="card", weight="SemiBold", font_size=36, text_color=CHARCOAL,
        box_color=_alpha(BEIGE, 225), accent=OLIVE, accent_w=6,
        padding=(34, 24), radius=20,
    ),
    "screenshot": dict(family="card", border_color=CREAM, border_width=14, radius=20),
    # "sticky" -- a one-off DEMO style, not part of the two production
    # looks above: a handwritten (Caveat) word on a torn/taped paper
    # square. Use sparingly, for a single deliberate beat, via the "rect"
    # overlay type with "style": "sticky" -- never as a default look.
    "sticky": dict(
        family="sticky", font_size=64, text_color=(40, 33, 26, 255),
        paper_color=PALE_YELLOW, tape_color=_alpha(CREAM, 210),
    ),
}

# ---------------------------------------------------------------------------
# Safe-zone overlay positions (all fractions are of the 1080x1920 frame).
# Every position is clamped at render time so it never lands in the top
# 10% or bottom 20% of the frame, no matter what's configured.
# ---------------------------------------------------------------------------

POSITIONS = {
    "upper_center": dict(x_frac=0.50, y_frac=0.16, halign="center", valign="top", max_w_frac=0.86),
    "upper_left": dict(x_frac=0.06, y_frac=0.16, halign="left", valign="top", max_w_frac=0.55),
    "upper_right": dict(x_frac=0.94, y_frac=0.16, halign="right", valign="top", max_w_frac=0.55),
    "left_side": dict(x_frac=0.06, y_frac=0.42, halign="left", valign="center", max_w_frac=0.46),
    "right_side": dict(x_frac=0.94, y_frac=0.42, halign="right", valign="center", max_w_frac=0.46),
    "lower_left": dict(x_frac=0.06, y_frac=0.74, halign="left", valign="bottom", max_w_frac=0.55),
    "lower_right": dict(x_frac=0.94, y_frac=0.74, halign="right", valign="bottom", max_w_frac=0.55),
    "lower_center": dict(x_frac=0.50, y_frac=0.74, halign="center", valign="bottom", max_w_frac=0.70),
}


def compute_placement(position_key, card_w, card_h):
    pos = POSITIONS.get(position_key, POSITIONS["upper_center"])
    anchor_x = pos["x_frac"] * WIDTH
    anchor_y = pos["y_frac"] * HEIGHT

    if pos["halign"] == "left":
        x = anchor_x
    elif pos["halign"] == "right":
        x = anchor_x - card_w
    else:
        x = anchor_x - card_w / 2

    if pos["valign"] == "top":
        y = anchor_y
    elif pos["valign"] == "bottom":
        y = anchor_y - card_h
    else:
        y = anchor_y - card_h / 2

    x = max(16, min(x, WIDTH - card_w - 16))
    min_y = TOP_SAFE * HEIGHT + 10
    max_y = BOTTOM_SAFE * HEIGHT - card_h - 10
    y = max(min_y, min(y, max_y))
    return int(x), int(y)


def caption_placement(card_w, card_h):
    """Placement for plain captions ("text"/"teaser" overlays): always
    horizontally centred, and always confined to the top third of the
    frame so it never sits over Mila's face/body in the middle/lower
    frame."""
    x = max(16, (WIDTH - card_w) / 2)
    min_y = TOP_SAFE * HEIGHT + 10
    max_y = TOP_THIRD * HEIGHT - card_h - 10
    y = max(min_y, min(TOP_SAFE * HEIGHT + 30, max_y))
    return int(x), int(y)


# ---------------------------------------------------------------------------
# Text card rendering
# ---------------------------------------------------------------------------

def _wrap_text(text, font, max_width):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if not cur or font.getlength(trial) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


# Soft drop-shadow tuning for Analysis Cards -- subtle, low-opacity, just
# enough lift to read as a card rather than a flat sticker (never "heavy").
_CARD_SHADOW_MARGIN = 18
_CARD_SHADOW_OFFSET_Y = 6
_CARD_SHADOW_BLUR = 8
_CARD_SHADOW_COLOR = (20, 16, 12, 40)


def render_card_text(text, style_name, max_width_px):
    """Style B -- Analysis Card: warm cream/beige rounded card, charcoal
    Inter text, a thin muted accent bar, a bare-minimum shadow. For
    screenshots/numbers/analytics -- used by the "rect" overlay type."""
    style = STYLES.get(style_name, STYLES["card"])
    font = load_font(style["font_size"], style.get("weight", "SemiBold"))
    pad_x, pad_y = style.get("padding", (32, 22))
    accent_w = style.get("accent_w", 6)

    usable_w = max(80, max_width_px - 2 * pad_x - accent_w - 10)
    lines = _wrap_text(text, font, usable_w)

    ascent, descent = font.getmetrics()
    line_h = ascent + descent + 10
    max_line_w = max(font.getlength(line) for line in lines)

    box_w = int(max_line_w + 2 * pad_x + accent_w + 10)
    box_h = int(line_h * len(lines) + 2 * pad_y)
    radius = style.get("radius", 20)

    m = _CARD_SHADOW_MARGIN
    canvas_w = box_w + m * 2
    canvas_h = box_h + m * 2 + _CARD_SHADOW_OFFSET_Y

    shadow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([m, m + _CARD_SHADOW_OFFSET_Y, m + box_w, m + _CARD_SHADOW_OFFSET_Y + box_h],
                          radius=radius, fill=_CARD_SHADOW_COLOR)
    shadow = shadow.filter(ImageFilter.GaussianBlur(_CARD_SHADOW_BLUR))

    card = shadow
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle([m, m, m + box_w, m + box_h], radius=radius, fill=style["box_color"])
    draw.rounded_rectangle([m, m, m + accent_w, m + box_h], radius=radius, fill=style["accent"])

    # Every line is horizontally centred within the card, so wrapped text
    # reads as a proper centred block, not a ragged left edge.
    text_x0 = m + accent_w + 10
    cursor_y = m + pad_y
    for line in lines:
        line_w = font.getlength(line)
        line_x = text_x0 + (max_line_w - line_w) / 2
        draw.text((line_x, cursor_y), line, font=font, fill=style["text_color"])
        cursor_y += line_h

    return card


# Shadow/tape tuning for the "sticky" demo style.
_STICKY_SHADOW_MARGIN = 22
_STICKY_SHADOW_OFFSET = 8
_STICKY_SHADOW_BLUR = 10
_STICKY_SHADOW_COLOR = (20, 16, 12, 75)

# A default hand-placed tilt per overlay index, used when an overlay
# doesn't set its own "rotation" -- gives a row of sticky notes a natural,
# not-quite-straight look without needing randomness.
_STICKY_WOBBLE = [-5, 4, -3, 6, -4, 3]


def _sticky_rotation(ov, idx):
    if "rotation" in ov:
        try:
            return float(ov["rotation"])
        except (TypeError, ValueError):
            pass
    return _STICKY_WOBBLE[idx % len(_STICKY_WOBBLE)]


def render_sticky_note(text, style_name, max_width_px, rotation=0.0):
    """DEMO style -- a handwritten word on a square of paper: masking tape
    across the top, a lifted corner, and a slight hand-placed tilt. Kept
    separate from the two allowed production looks (Editorial Hook /
    Analysis Card) -- use for one deliberate beat, via the "rect" overlay
    type with "style": "sticky"."""
    style = STYLES.get(style_name, STYLES["sticky"])
    font = load_hand_font(style["font_size"])
    pad = 44

    usable_w = max(80, min(max_width_px, 460) - 2 * pad)
    lines = _wrap_text(text, font, usable_w)

    ascent, descent = font.getmetrics()
    line_h = ascent + descent + 4
    max_line_w = max(font.getlength(line) for line in lines)

    note_w = int(max(max_line_w + 2 * pad, 240))
    note_h = int(max(line_h * len(lines) + 2 * pad, note_w * 0.85))

    m = _STICKY_SHADOW_MARGIN
    canvas_w = note_w + m * 2
    canvas_h = note_h + m * 2 + _STICKY_SHADOW_OFFSET

    note = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(note)
    sd.rectangle([m, m + _STICKY_SHADOW_OFFSET, m + note_w, m + _STICKY_SHADOW_OFFSET + note_h],
                 fill=_STICKY_SHADOW_COLOR)
    note = note.filter(ImageFilter.GaussianBlur(_STICKY_SHADOW_BLUR))

    draw = ImageDraw.Draw(note)
    paper = style.get("paper_color", PALE_YELLOW)
    draw.rectangle([m, m, m + note_w, m + note_h], fill=paper)

    # Lifted corner -- a small darker triangle peeling off the bottom-right,
    # with a thin bright fold-line, so it doesn't read as a flat sticker.
    peel = 30
    x0, y0 = m + note_w, m + note_h
    peel_shade = tuple(max(0, c - 45) for c in paper[:3]) + (255,)
    draw.polygon([(x0 - peel, y0), (x0, y0), (x0, y0 - peel)], fill=peel_shade)
    draw.line([(x0 - peel, y0), (x0, y0 - peel)], fill=(255, 255, 255, 130), width=2)

    # A strip of masking tape across the top, tilted a few degrees off the
    # note itself.
    tape_w, tape_h = int(note_w * 0.42), 34
    tape = Image.new("RGBA", (tape_w, tape_h), style.get("tape_color", _alpha(CREAM, 210)))
    tape = tape.rotate(-3, expand=True, resample=Image.BICUBIC)
    tape_cx, tape_cy = m + note_w / 2, m
    note.alpha_composite(tape, (int(tape_cx - tape.width / 2), int(tape_cy - tape.height / 2)))

    # Handwritten text, centred on the note.
    text_color = style.get("text_color", CHARCOAL)
    cursor_y = m + (note_h - line_h * len(lines)) / 2
    for line in lines:
        line_w = font.getlength(line)
        line_x = m + (note_w - line_w) / 2
        draw.text((line_x, cursor_y), line, font=font, fill=text_color)
        cursor_y += line_h

    if rotation:
        note = note.rotate(rotation, expand=True, resample=Image.BICUBIC)
    return note


# Soft-shadow tuning for Editorial Hook text -- a tight, subtle contact
# shadow just for readability, not a card-style drop shadow.
_HOOK_SHADOW_OFFSET_Y = 3
_HOOK_SHADOW_BLUR = 5
_HOOK_SHADOW_ALPHA = 130


def render_hook_text(text, style_name, max_width_px):
    """Style A -- Editorial Hook: large, soft serif (Fraunces), warm
    cream/butter text straight over the footage -- no box, no outline.
    For emotional/positioning lines -- used by "text" and "teaser"
    overlays."""
    style = STYLES.get(style_name, STYLES["headline"])
    font = load_serif_font(style["font_size"], style.get("opsz", 90),
                            style.get("wght", 560), style.get("soft", 55))
    margin = 16

    usable_w = max(80, max_width_px - 2 * margin)
    lines = _wrap_text(text, font, usable_w)

    ascent, descent = font.getmetrics()
    line_h = ascent + descent + 14
    max_line_w = max(font.getlength(line) for line in lines)

    canvas_w = int(max_line_w + 2 * margin)
    canvas_h = int(line_h * len(lines) + 2 * margin + _HOOK_SHADOW_OFFSET_Y)

    shadow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    cursor_y = margin
    for line in lines:
        line_w = font.getlength(line)
        line_x = margin + (max_line_w - line_w) / 2
        sd.text((line_x, cursor_y + _HOOK_SHADOW_OFFSET_Y), line, font=font,
                 fill=(*SHADOW_INK, _HOOK_SHADOW_ALPHA))
        cursor_y += line_h
    shadow = shadow.filter(ImageFilter.GaussianBlur(_HOOK_SHADOW_BLUR))

    card = shadow
    draw = ImageDraw.Draw(card)
    cursor_y = margin
    for line in lines:
        line_w = font.getlength(line)
        line_x = margin + (max_line_w - line_w) / 2
        draw.text((line_x, cursor_y), line, font=font, fill=style["text_color"])
        cursor_y += line_h

    return card


def render_image_card(file_path, style_name, max_width_px, max_height_px):
    style = STYLES.get(style_name, STYLES["screenshot"])
    img = Image.open(file_path).convert("RGBA")

    scale = min(max_width_px / img.width, max_height_px / img.height, 1.0)
    if scale < 1.0:
        new_size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
        img = img.resize(new_size, Image.LANCZOS)

    border = style.get("border_width", 12)
    radius = style.get("radius", 18)
    card_w, card_h = img.width + 2 * border, img.height + 2 * border

    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle([0, 0, card_w - 1, card_h - 1], radius=radius, fill=style.get("border_color", CREAM))

    mask = Image.new("L", (img.width, img.height), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, img.width - 1, img.height - 1], radius=max(0, radius - border // 2), fill=255
    )
    card.paste(img, (border, border), mask)
    return card


def render_plain_rect(ov, style_name):
    style = STYLES.get(style_name, STYLES["card"])
    card_w = int(ov.get("width_frac", 0.30) * WIDTH)
    card_h = int(ov.get("height_frac", 0.08) * HEIGHT)
    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle([0, 0, card_w - 1, card_h - 1], radius=style["radius"], fill=style["box_color"])
    return card


def render_arrow(direction, color):
    size = 200
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.line([(30, size - 30), (size - 50, 50)], fill=color, width=14)
    draw.polygon([(size - 70, 30), (size - 20, 40), (size - 40, 90)], fill=color)
    angles = {
        "up": 45, "up_right": 0, "right": -45, "down_right": -90,
        "down": -135, "down_left": 180, "left": 135, "up_left": 90,
    }
    angle = angles.get(direction, 0)
    return img.rotate(angle, expand=True, resample=Image.BICUBIC)


def render_circle(size, color):
    pad = 12
    img = Image.new("RGBA", (size + pad * 2, size + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([pad, pad, pad + size, pad + size], outline=color, width=10)
    return img


def render_safe_zone_guide(mila_position):
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    top_h = int(HEIGHT * TOP_SAFE)
    bottom_y = int(HEIGHT * BOTTOM_SAFE)
    d.rectangle([0, 0, WIDTH, top_h], fill=(200, 40, 40, 70))
    d.rectangle([0, bottom_y, WIDTH, HEIGHT], fill=(200, 40, 40, 70))

    center_top = int(HEIGHT * (0.34 if "lower" in (mila_position or "") else 0.28))
    center_bottom = int(HEIGHT * 0.78)
    d.rectangle([int(WIDTH * 0.2), center_top, int(WIDTH * 0.8), center_bottom],
                outline=(60, 90, 160, 220), width=6)

    d.text((16, top_h + 10), "SAFE ZONE GUIDE (debug)", font=load_font(28, "SemiBold"),
            fill=(255, 255, 255, 230))
    return img


# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------

def cover_resize_pil(img, w, h):
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    nw, nh = math.ceil(iw * scale), math.ceil(ih * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    x1, y1 = (nw - w) // 2, (nh - h) // 2
    return img.crop((x1, y1, x1 + w, y1 + h))


def cover_fit_video(clip, w, h):
    cw, ch = clip.size
    scale = max(w / cw, h / ch)
    nw, nh = math.ceil(cw * scale), math.ceil(ch * scale)
    clip = clip.with_effects([vfx.Resize((nw, nh))])
    x1, y1 = (nw - w) // 2, (nh - h) // 2
    return clip.with_effects([vfx.Crop(x1=x1, y1=y1, width=w, height=h)])


def generate_placeholder_background():
    """A calm grey-to-sun vertical gradient, used when no real background
    has been uploaded yet, so the whole pipeline can still be tested."""
    top = np.array([58, 58, 64], dtype=np.float64)
    bottom = np.array([232, 167, 102], dtype=np.float64)
    rows = np.linspace(0, 1, HEIGHT) ** 0.9
    grad = top[None, :] * (1 - rows[:, None]) + bottom[None, :] * rows[:, None]
    arr = np.repeat(grad[:, None, :], WIDTH, axis=1).astype(np.uint8)
    img = Image.fromarray(arr, "RGB")

    glow = Image.new("L", (WIDTH, HEIGHT), 0)
    gd = ImageDraw.Draw(glow)
    cx, cy, r = WIDTH // 2, int(HEIGHT * 0.78), int(WIDTH * 0.55)
    gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=90)
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    warm = Image.new("RGB", (WIDTH, HEIGHT), (255, 214, 150))
    return Image.composite(warm, img, glow)


def build_background_clip(cfg, duration):
    bg_path = cfg.get("background")
    if bg_path and os.path.isfile(bg_path):
        ext = Path(bg_path).suffix.lower()
        if ext in {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}:
            print(f"[info] Using background video: {bg_path}")
            clip = VideoFileClip(bg_path).without_audio()
            clip = cover_fit_video(clip, WIDTH, HEIGHT)
            if clip.duration < duration:
                clip = clip.with_effects([vfx.Loop(duration=duration)])
            clip = clip.with_duration(duration)
        else:
            print(f"[info] Using background image: {bg_path}")
            img = Image.open(bg_path).convert("RGB")
            img = cover_resize_pil(img, WIDTH, HEIGHT)
            clip = ImageClip(np.array(img)).with_duration(duration)
    else:
        if bg_path:
            print(f"[warn] Background '{bg_path}' not found. Using a placeholder grey-to-sun gradient instead.")
        else:
            print("[info] No background specified. Using a placeholder grey-to-sun gradient.")
        img = generate_placeholder_background()
        clip = ImageClip(np.array(img)).with_duration(duration)

    return clip.with_fps(FPS).with_position((0, 0))


# ---------------------------------------------------------------------------
# Overlays
# ---------------------------------------------------------------------------

def apply_slide(clip, target_x, target_y, side, anim_dur):
    offset = 220
    dx = -offset if side == "left" else offset if side == "right" else 0
    dy = -offset if side == "top" else offset if side == "bottom" else 0

    def pos_fn(t):
        if anim_dur <= 0 or t >= anim_dur:
            return (target_x, target_y)
        frac = t / anim_dur
        eased = 1 - (1 - frac) ** 3
        return (target_x + dx * (1 - eased), target_y + dy * (1 - eased))

    return clip.with_position(pos_fn)


_SLIDE_SIDE_BY_POSITION = {
    "upper_left": "top", "upper_right": "top", "upper_center": "top",
    "left_side": "left", "right_side": "right",
    "lower_left": "bottom", "lower_right": "bottom", "lower_center": "bottom",
}


def build_overlay_clip(ov, idx, total_duration):
    otype = ov.get("type", "text")
    try:
        start = max(0.0, float(ov["start"]))
        end = min(total_duration, float(ov["end"]))
    except (KeyError, ValueError, TypeError):
        print(f"[warn] overlay #{idx + 1} is missing a valid start/end; skipping")
        return None
    if end <= start:
        print(f"[warn] overlay #{idx + 1} has zero/negative duration ({start}-{end}); skipping")
        return None
    dur = end - start

    position = ov.get("position", "upper_center")
    if position not in POSITIONS:
        print(f"[warn] overlay #{idx + 1} has unknown position '{position}'; using 'upper_center'")
        position = "upper_center"
    is_caption = otype in ("text", "teaser")
    # Plain captions are always centred, full-width, top-third -- "position"
    # is accepted for JSON/back-compat but doesn't affect caption placement.
    pos_cfg = POSITIONS["upper_center"] if is_caption else POSITIONS[position]
    max_w_px = pos_cfg["max_w_frac"] * WIDTH

    default_style = (
        "teaser" if otype == "teaser"
        else "screenshot" if otype in ("image", "screenshot")
        else "card" if otype == "rect"
        else "support"
    )
    style_name = ov.get("style", default_style)

    # Dispatch by the resolved style's family: "hook" -> Style A (Editorial
    # Hook, no box), "card" -> Style B (Analysis Card, boxed), "sticky" ->
    # the one-off handwritten demo look. This is a per-overlay choice via
    # "style", not hard-wired to "type".
    def _render_by_family(text, style_name):
        family = STYLES.get(style_name, STYLES["support"]).get("family", "hook")
        if family == "card":
            return render_card_text(text, style_name, max_w_px)
        if family == "sticky":
            return render_sticky_note(text, style_name, max_w_px, rotation=_sticky_rotation(ov, idx))
        return render_hook_text(text, style_name, max_w_px)

    if otype == "text":
        text = ov.get("text", "")
        if not text:
            print(f"[warn] overlay #{idx + 1} (text) has no 'text'; skipping")
            return None
        card = _render_by_family(text, style_name)
    elif otype == "teaser":
        text = ov.get("text", "")
        if not text:
            print(f"[warn] overlay #{idx + 1} (teaser) has no 'text'; skipping")
            return None
        card = _render_by_family(text, style_name)
    elif otype in ("image", "screenshot"):
        file_path = ov.get("file")
        if not file_path or not os.path.isfile(file_path):
            print(f"[warn] overlay #{idx + 1} ({otype}) file not found: {file_path!r}; skipping")
            return None
        max_h_px = 0.34 * HEIGHT
        card = render_image_card(file_path, style_name, max_w_px, max_h_px)
    elif otype == "rect":
        text = ov.get("text")
        card = _render_by_family(text, style_name) if text else render_plain_rect(ov, style_name)
    elif otype == "arrow":
        card = render_arrow(ov.get("direction", "down_left"), STYLES.get(style_name, STYLES["support"])["accent"])
    elif otype == "circle":
        card = render_circle(int(ov.get("size", 220)), STYLES.get(style_name, STYLES["support"])["accent"])
    else:
        print(f"[warn] overlay #{idx + 1} has unknown type '{otype}'; skipping")
        return None

    card_w, card_h = card.size
    x, y = caption_placement(card_w, card_h) if is_caption else compute_placement(position, card_w, card_h)

    clip = ImageClip(np.array(card)).with_duration(dur).with_start(start).with_position((x, y))

    # Overlays pop on/off screen instantly by default -- no fade/slide creep.
    # Set "animation" explicitly in the JSON if you want fade/slide/pop.
    anim = ov.get("animation", "none")
    anim_dur = min(0.4, dur / 3) if dur > 0 else 0.2
    if anim == "none":
        pass
    elif anim == "slide":
        side = _SLIDE_SIDE_BY_POSITION.get(position, "top")
        clip = apply_slide(clip, x, y, side, anim_dur)
        clip = clip.with_effects([vfx.CrossFadeIn(anim_dur), vfx.CrossFadeOut(anim_dur)])
    else:  # "fade" / "pop" -> simple, reliable fade
        fade_dur = anim_dur * 0.6 if anim == "pop" else anim_dur
        clip = clip.with_effects([vfx.CrossFadeIn(fade_dur), vfx.CrossFadeOut(fade_dur)])

    return clip


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", nargs="?", default="example_input.json",
                         help="Path to a project JSON file (default: example_input.json)")
    parser.add_argument("--debug-safe-zones", action="store_true",
                         help="Overlay translucent guide bands showing the top/bottom no-go zones and Mila's centre area")
    args = parser.parse_args()

    project_path = Path(args.project)
    if not project_path.is_file():
        sys.exit(f"Project file not found: {project_path}")

    cfg = json.loads(project_path.read_text())

    duration = float(cfg.get("duration", DEFAULT_DURATION))
    if duration > HARD_CAP_SECONDS and not cfg.get("allow_over_60"):
        print(f"[warn] duration {duration:g}s exceeds the {HARD_CAP_SECONDS}s cap; clamping. "
              f'Add "allow_over_60": true to the project JSON to override.')
        duration = HARD_CAP_SECONDS

    output_path = Path(cfg.get("output", "outputs/background_video.mp4"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[info] Project: {project_path}")
    print(f"[info] Building background ({duration:.1f}s, {WIDTH}x{HEIGHT} @ {FPS}fps)...")
    bg_clip = build_background_clip(cfg, duration)

    overlays_cfg = cfg.get("overlays", [])
    if len(overlays_cfg) > 8:
        print(f"[warn] {len(overlays_cfg)} overlays configured; the style guide recommends 6-8 max.")

    overlay_clips = []
    for i, ov in enumerate(overlays_cfg):
        clip = build_overlay_clip(ov, i, duration)
        if clip is not None:
            overlay_clips.append(clip)

    layers = [bg_clip] + overlay_clips
    if args.debug_safe_zones:
        guide = render_safe_zone_guide(cfg.get("mila_position"))
        layers.append(ImageClip(np.array(guide)).with_duration(duration).with_position((0, 0)))

    final = CompositeVideoClip(layers, size=(WIDTH, HEIGHT)).with_duration(duration).with_fps(FPS)

    print(f"[info] Rendering {len(overlay_clips)} overlay(s) -> {output_path}")
    final.write_videofile(
        str(output_path),
        fps=FPS,
        codec="libx264",
        audio=False,
        preset="medium",
        ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
        logger="bar",
    )
    print(f"\n[done] Saved silent background video to: {output_path.resolve()}")


if __name__ == "__main__":
    main()
