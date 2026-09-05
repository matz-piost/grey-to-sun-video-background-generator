#!/usr/bin/env python3
"""Make quick edits to a project JSON file without hand-editing it, then
regenerate the MP4 with generate_background.py.

Examples:
    python3 edit_project.py projects/video-001.json --overlay 3 --text "Check watch time first"
    python3 edit_project.py projects/video-001.json --overlay 4 --start 20 --end 29
    python3 edit_project.py projects/video-001.json --duration 52
    python3 edit_project.py projects/video-001.json --background assets/living-room-2.jpg
    python3 edit_project.py projects/video-001.json --add-overlay --start 40 --end 45 \\
        --text "One more thing" --position upper_center --style support
    python3 edit_project.py projects/video-001.json --remove-overlay 5

Overlay numbers are 1-based, matching the order overlays appear in the JSON.
"""

import argparse
import json
import sys
from pathlib import Path


def load(path_str):
    path = Path(path_str)
    if not path.is_file():
        sys.exit(f"Project file not found: {path}")
    return path, json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", help="Project JSON to edit, e.g. projects/video-001.json")

    parser.add_argument("--duration", type=float, help="Set overall video duration (seconds)")
    parser.add_argument("--background", help="Set the background image/video path")
    parser.add_argument("--output", help="Set the output MP4 path")
    parser.add_argument("--mila-position", dest="mila_position", help="Set the mila_position value")

    parser.add_argument("--overlay", type=int, metavar="N", help="1-based index of an existing overlay to edit")
    parser.add_argument("--text", help="New text for --overlay N or --add-overlay")
    parser.add_argument("--start", type=float, help="New start time (seconds) for --overlay N or --add-overlay")
    parser.add_argument("--end", type=float, help="New end time (seconds) for --overlay N or --add-overlay")
    parser.add_argument("--position", help="New position keyword for --overlay N or --add-overlay")
    parser.add_argument("--style", help="New style preset for --overlay N or --add-overlay")
    parser.add_argument("--file", dest="file_", help="New image file path for --overlay N or --add-overlay "
                                                       "(image/screenshot overlays)")
    parser.add_argument("--animation", help="New animation for --overlay N or --add-overlay (fade, slide, pop, none)")

    parser.add_argument("--add-overlay", action="store_true", help="Append a new overlay instead of editing one")
    parser.add_argument("--type", dest="type_", help="Overlay type for --add-overlay "
                                                       "(text, teaser, image, screenshot, rect, arrow, circle)")
    parser.add_argument("--remove-overlay", type=int, metavar="N", help="1-based index of an overlay to delete")

    args = parser.parse_args()
    path, data = load(args.project)
    changed = []

    if args.duration is not None:
        data["duration"] = args.duration
        changed.append(f"duration -> {args.duration}")
    if args.background:
        data["background"] = args.background
        changed.append(f"background -> {args.background}")
    if args.output:
        data["output"] = args.output
        changed.append(f"output -> {args.output}")
    if args.mila_position:
        data["mila_position"] = args.mila_position
        changed.append(f"mila_position -> {args.mila_position}")

    overlays = data.setdefault("overlays", [])

    if args.remove_overlay is not None:
        idx = args.remove_overlay - 1
        if not (0 <= idx < len(overlays)):
            sys.exit(f"--remove-overlay {args.remove_overlay} is out of range (1-{len(overlays)})")
        removed = overlays.pop(idx)
        label = removed.get("text") or removed.get("file") or removed.get("type")
        changed.append(f"removed overlay {args.remove_overlay} ({label!r})")

    if args.add_overlay:
        start = args.start if args.start is not None else 0.0
        end = args.end if args.end is not None else start + 4.0
        new_overlay = {
            "start": start,
            "end": end,
            "type": args.type_ or "text",
            "position": args.position or "upper_center",
            "style": args.style or "support",
        }
        if args.text:
            new_overlay["text"] = args.text
        if args.file_:
            new_overlay["file"] = args.file_
        if args.animation:
            new_overlay["animation"] = args.animation
        overlays.append(new_overlay)
        changed.append(f"added overlay #{len(overlays)} ({new_overlay['type']})")

    elif args.overlay is not None:
        idx = args.overlay - 1
        if not (0 <= idx < len(overlays)):
            sys.exit(f"--overlay {args.overlay} is out of range (1-{len(overlays)})")
        ov = overlays[idx]
        if args.text is not None:
            ov["text"] = args.text
            changed.append(f"overlay {args.overlay}.text -> {args.text!r}")
        if args.start is not None:
            ov["start"] = args.start
            changed.append(f"overlay {args.overlay}.start -> {args.start}")
        if args.end is not None:
            ov["end"] = args.end
            changed.append(f"overlay {args.overlay}.end -> {args.end}")
        if args.position:
            ov["position"] = args.position
            changed.append(f"overlay {args.overlay}.position -> {args.position}")
        if args.style:
            ov["style"] = args.style
            changed.append(f"overlay {args.overlay}.style -> {args.style}")
        if args.file_:
            ov["file"] = args.file_
            changed.append(f"overlay {args.overlay}.file -> {args.file_}")
        if args.animation:
            ov["animation"] = args.animation
            changed.append(f"overlay {args.overlay}.animation -> {args.animation}")

    if not changed:
        sys.exit("No edits given. Run with --help to see available flags.")

    path.write_text(json.dumps(data, indent=2) + "\n")

    print(f"Updated {path}:")
    for c in changed:
        print(f"  - {c}")
    print(f"\nRegenerate with:")
    print(f"  python3 generate_background.py {path}")


if __name__ == "__main__":
    main()
