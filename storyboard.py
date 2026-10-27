#!/usr/bin/env python3
"""Build a storyboard review dashboard for a project BEFORE exporting the MP4.

Renders one still frame per beat (overlay) using the exact same pipeline
as generate_background.py, and writes a single self-contained HTML file
where you can approve each beat or leave notes, then send the review back
to Claude for the next draft.

Examples:
    python3 storyboard.py projects/video-004.json
    python3 storyboard.py projects/video-004.json --out storyboards/custom.html

Output (default): storyboards/<project-name>-draft<N>.html

Workflow:
    1. python3 storyboard.py projects/video-XXX.json
    2. Open the HTML, approve each beat or write a change note.
    3. Click "Send back to Claude" -- it copies a review summary to paste
       into Claude, and downloads <project>-draft<N>.review.json (drop it in
       storyboards/reviews/ so Claude can read it).
    4. Claude applies the notes (edit_project.py / the JSON), bumps "draft",
       and re-runs this script. Repeat until every beat is approved.
    5. Only then: python3 generate_background.py projects/video-XXX.json
"""

import argparse
import base64
import io
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

import generate_background as gb

THUMB_W, THUMB_H = 360, 640
TEMPLATE_PATH = Path(__file__).parent / "storyboard_template.html"


def build_composite(cfg, duration):
    """Same layer stack generate_background.main() renders, minus the encode."""
    layers = [gb.build_background_clip(cfg, duration)]
    for i, ov in enumerate(cfg.get("overlays", [])):
        clip = gb.build_overlay_clip(ov, i, duration)
        if clip is not None:
            layers.append(clip)
    return gb.CompositeVideoClip(layers, size=(gb.WIDTH, gb.HEIGHT)).with_duration(duration)


def frame_to_data_uri(frame):
    img = Image.fromarray(np.asarray(frame).astype("uint8")).convert("RGB")
    img = img.resize((THUMB_W, THUMB_H), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", help="Project JSON, e.g. projects/video-004.json")
    parser.add_argument("--out", help="Output HTML path (default: storyboards/<name>-draft<N>.html)")
    args = parser.parse_args()

    project_path = Path(args.project)
    if not project_path.is_file():
        sys.exit(f"Project file not found: {project_path}")
    cfg = json.loads(project_path.read_text())

    duration = float(cfg.get("duration", gb.DEFAULT_DURATION))
    if duration > gb.HARD_CAP_SECONDS and not cfg.get("allow_over_60"):
        duration = gb.HARD_CAP_SECONDS
    draft = int(cfg.get("draft", 1))
    name = project_path.stem

    print(f"[info] Building storyboard for {project_path} (draft {draft})...")
    composite = build_composite(cfg, duration)

    beats = []
    for i, ov in enumerate(cfg.get("overlays", [])):
        try:
            start, end = float(ov["start"]), min(duration, float(ov["end"]))
        except (KeyError, ValueError, TypeError):
            continue
        if end <= start:
            continue
        # Sample just after the beat starts so build-up beats (sticky notes
        # appearing one by one) show the frame as of that beat.
        t = start + min(0.5, (end - start) / 2)
        beats.append({
            "overlay": i + 1,  # 1-based, matches edit_project.py --overlay N
            "start": start,
            "end": end,
            "type": ov.get("type", "text"),
            "style": ov.get("style", ""),
            "text": ov.get("text") or ov.get("file") or "",
            "vo": ov.get("vo", ""),
            "thumb": frame_to_data_uri(composite.get_frame(t)),
        })
    beats.sort(key=lambda b: (b["start"], b["overlay"]))

    data = {
        "project": project_path.as_posix(),
        "name": name,
        "title": cfg.get("title", name),
        "draft": draft,
        "duration": duration,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "beats": beats,
    }

    out_path = Path(args.out) if args.out else Path("storyboards") / f"{name}-draft{draft}.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # "</" can't appear raw inside a <script> block.
    payload = json.dumps(data).replace("</", "<\\/")
    html = TEMPLATE_PATH.read_text().replace("__STORYBOARD_DATA__", payload)
    out_path.write_text(html)
    print(f"[done] {len(beats)} beat(s) -> {out_path.resolve()}")


if __name__ == "__main__":
    main()
