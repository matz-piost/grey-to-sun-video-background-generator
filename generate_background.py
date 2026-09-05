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

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_BOLD = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
FONT_REGULAR = os.path.join(FONT_DIR, "DejaVuSans.ttf")
if not os.path.isfile(FONT_BOLD):
    # Fall back to whatever PIL's default bitmap font provides rather than
    # crashing on machines without DejaVu installed.
    FONT_BOLD = FONT_REGULAR = None

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


def _alpha(color, a):
    return (color[0], color[1], color[2], a)


# ---------------------------------------------------------------------------
# Overlay style presets
# ---------------------------------------------------------------------------


# "headline" / "support" / "teaser" are transparent, no-box captions: bold
# text with a thin dark outline (stroke) for readability over any footage --
# no filled card behind them. "headline" is the main-hook size; "support" is
# the accent/secondary-phrase size (roughly half the headline's font size).
# "card"/"rect" keeps an explicit filled box, for when you actually want a
# rectangle/text-card shape (not a plain caption).
STYLES = {
    "headline": dict(
        font=FONT_BOLD, font_size=92, text_color=CREAM,
        stroke_color=CHARCOAL, stroke_width=5, accent=TERRACOTTA,
    ),
    "support": dict(
        font=FONT_BOLD, font_size=46, text_color=CREAM,
        stroke_color=CHARCOAL, stroke_width=3, accent=DUSTY_BLUE,
    ),
    "teaser": dict(
        font=FONT_BOLD, font_size=66, text_color=PALE_YELLOW,
        stroke_color=CHARCOAL, stroke_width=4, accent=OLIVE,
        label="NEXT", label_color=OLIVE,
    ),
    "card": dict(
        font=FONT_BOLD, font_size=38, text_color=CHARCOAL,
        box_color=_alpha(BEIGE, 215), accent=OLIVE, accent_w=8,
        padding=(30, 20), radius=20,
    ),
    "screenshot": dict(border_color=CREAM, border_width=14, radius=20),
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


def render_text_card(text, style_name, max_width_px):
    """Transparent, no-box caption: bold text with a thin outline stroke
    for readability over any footage. Used for "text"/"teaser" overlays."""
    style = STYLES.get(style_name, STYLES["support"])
    font = ImageFont.truetype(style["font"], style["font_size"]) if style["font"] else ImageFont.load_default()
    stroke_w = style.get("stroke_width", 0)
    margin = stroke_w + 6

    usable_w = max(80, max_width_px - 2 * margin)
    lines = _wrap_text(text, font, usable_w)

    ascent, descent = font.getmetrics()
    line_h = ascent + descent + 10
    max_line_w = max(font.getlength(line) for line in lines)

    label = style.get("label")
    label_h = 0
    label_font = None
    if label:
        label_font = ImageFont.truetype(FONT_BOLD, max(18, style["font_size"] // 2)) if FONT_BOLD else ImageFont.load_default()
        l_asc, l_desc = label_font.getmetrics()
        label_h = l_asc + l_desc + 16

    card_w = int(max(max_line_w, label_font.getlength(label) if label else 0) + 2 * margin)
    card_h = int(line_h * len(lines) + label_h + 2 * margin)

    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)

    cursor_y = margin
    if label:
        draw.text((margin, cursor_y), label, font=label_font,
                  fill=style.get("label_color", style["accent"]),
                  stroke_width=max(2, stroke_w - 1), stroke_fill=style.get("stroke_color", CHARCOAL))
        cursor_y += label_h

    for line in lines:
        draw.text((margin, cursor_y), line, font=font, fill=style["text_color"],
                  stroke_width=stroke_w, stroke_fill=style.get("stroke_color", CHARCOAL))
        cursor_y += line_h

    return card


def render_boxed_text_card(text, style_name):
    """Filled rounded-rectangle text card -- used only for the explicit
    "rect" overlay type, when you actually want a card/box shape."""
    style = STYLES.get(style_name, STYLES["card"])
    font = ImageFont.truetype(style["font"], style["font_size"]) if style["font"] else ImageFont.load_default()
    pad_x, pad_y = style.get("padding", (30, 20))
    accent_w = style.get("accent_w", 8)

    usable_w = max(80, 0.8 * WIDTH - 2 * pad_x - accent_w - 10)
    lines = _wrap_text(text, font, usable_w)

    ascent, descent = font.getmetrics()
    line_h = ascent + descent + 8
    max_line_w = max(font.getlength(line) for line in lines)

    card_w = int(max_line_w + 2 * pad_x + accent_w + 10)
    card_h = int(line_h * len(lines) + 2 * pad_y)

    card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)
    radius = style.get("radius", 20)
    draw.rounded_rectangle([0, 0, card_w - 1, card_h - 1], radius=radius, fill=style["box_color"])
    draw.rounded_rectangle([0, 0, accent_w, card_h - 1], radius=radius, fill=style["accent"])

    cursor_y = pad_y
    text_x = pad_x + accent_w + 10
    for line in lines:
        draw.text((text_x, cursor_y), line, font=font, fill=style["text_color"])
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

    if FONT_BOLD:
        d.text((16, top_h + 10), "SAFE ZONE GUIDE (debug)", font=ImageFont.truetype(FONT_BOLD, 28),
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
    pos_cfg = POSITIONS[position]
    max_w_px = pos_cfg["max_w_frac"] * WIDTH

    default_style = (
        "teaser" if otype == "teaser"
        else "screenshot" if otype in ("image", "screenshot")
        else "card" if otype == "rect"
        else "support"
    )
    style_name = ov.get("style", default_style)

    if otype == "text":
        text = ov.get("text", "")
        if not text:
            print(f"[warn] overlay #{idx + 1} (text) has no 'text'; skipping")
            return None
        card = render_text_card(text, style_name, max_w_px)
    elif otype == "teaser":
        text = ov.get("text", "")
        if not text:
            print(f"[warn] overlay #{idx + 1} (teaser) has no 'text'; skipping")
            return None
        card = render_text_card(text, "teaser", max_w_px)
    elif otype in ("image", "screenshot"):
        file_path = ov.get("file")
        if not file_path or not os.path.isfile(file_path):
            print(f"[warn] overlay #{idx + 1} ({otype}) file not found: {file_path!r}; skipping")
            return None
        max_h_px = 0.34 * HEIGHT
        card = render_image_card(file_path, style_name, max_w_px, max_h_px)
    elif otype == "rect":
        text = ov.get("text")
        card = render_boxed_text_card(text, style_name) if text else render_plain_rect(ov, style_name)
    elif otype == "arrow":
        card = render_arrow(ov.get("direction", "down_left"), STYLES.get(style_name, STYLES["support"])["accent"])
    elif otype == "circle":
        card = render_circle(int(ov.get("size", 220)), STYLES.get(style_name, STYLES["support"])["accent"])
    else:
        print(f"[warn] overlay #{idx + 1} has unknown type '{otype}'; skipping")
        return None

    card_w, card_h = card.size
    x, y = compute_placement(position, card_w, card_h)

    clip = ImageClip(np.array(card)).with_duration(dur).with_start(start).with_position((x, y))

    anim = ov.get("animation", "fade")
    anim_dur = min(0.4, dur / 3) if dur > 0 else 0.2
    if anim == "none":
        pass
    elif anim == "slide":
        side = _SLIDE_SIDE_BY_POSITION.get(position, "top")
        clip = apply_slide(clip, x, y, side, anim_dur)
        clip = clip.with_effects([vfx.CrossFadeIn(anim_dur), vfx.CrossFadeOut(anim_dur)])
    else:  # "fade" / "pop" / anything else -> simple, reliable fade
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
