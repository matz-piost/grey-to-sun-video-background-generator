#!/usr/bin/env python3
"""Duplicate an existing project JSON so you can start a new video from it
without losing the original as a reusable template.

Usage:
    python3 duplicate_project.py projects/video-001.json projects/video-002.json
    python3 duplicate_project.py projects/video-001.json projects/video-002.json --output outputs/video-002-background.mp4
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="Existing project JSON, e.g. projects/video-001.json")
    parser.add_argument("dest", help="New project JSON path, e.g. projects/video-002.json")
    parser.add_argument("--output", help="Override the 'output' MP4 path stored in the new project file "
                                          "(default: outputs/<new-name>-background.mp4)")
    args = parser.parse_args()

    src = Path(args.source)
    dest = Path(args.dest)

    if not src.is_file():
        sys.exit(f"Source project not found: {src}")
    if dest.exists():
        sys.exit(f"Refusing to overwrite existing file: {dest}")

    data = json.loads(src.read_text())
    data["output"] = args.output if args.output else f"outputs/{dest.stem}-background.mp4"

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, indent=2) + "\n")

    print(f"Created {dest} (output -> {data['output']})")
    print(f"Edit {dest} as needed, then run:")
    print(f"  python3 generate_background.py {dest}")


if __name__ == "__main__":
    main()
