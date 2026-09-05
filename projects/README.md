# projects/

Each file here is the **editable source of truth** for one background
video. It's a JSON file — not the MP4 itself — so you can make a small
change and regenerate instantly instead of starting over.

Pattern:

```
projects/video-001.json   -> outputs/video-001-background.mp4
projects/video-002.json   -> outputs/video-002-background.mp4
```

## Fields

```jsonc
{
  "duration": 45,                          // seconds (default 45, hard-capped at 60 unless "allow_over_60": true)
  "background": "assets/background.jpg",   // image or video; falls back to a placeholder if missing
  "output": "outputs/video-001-background.mp4",
  "mila_position": "center_lower",         // documentation only, used by --debug-safe-zones
  "overlays": [
    {
      "start": 0,               // seconds
      "end": 4,                 // seconds
      "type": "text",           // text | teaser | image | screenshot | rect | arrow | circle
      "text": "200 views again?",
      "position": "upper_center", // upper_center|upper_left|upper_right|left_side|right_side|lower_left|lower_right|lower_center
      "style": "headline",      // headline | support | card | teaser | screenshot
                                 // headline/support/teaser = transparent, outlined caption text (no box).
                                 // headline = main-hook size; support = accent-phrase size (~half of headline).
                                 // card = the one boxed style, used by the "rect" overlay type.
      "animation": "fade"       // fade | slide | pop | none
    }
  ]
}
```

Image/screenshot overlays use `"file"` instead of `"text"`:

```json
{
  "start": 12,
  "end": 20,
  "type": "image",
  "file": "assets/analytics.png",
  "position": "left_side",
  "style": "screenshot"
}
```

## Workflow

1. **Create a new video** — either write a JSON file by hand, or duplicate
   an existing one so you keep the timing/positions as a starting point:

   ```bash
   python3 duplicate_project.py projects/video-001.json projects/video-002.json
   ```

2. **Make quick edits** with `edit_project.py` (or just open the JSON in
   any text editor):

   ```bash
   python3 edit_project.py projects/video-001.json --overlay 3 --text "Check watch time first"
   python3 edit_project.py projects/video-001.json --overlay 4 --start 20 --end 29
   python3 edit_project.py projects/video-001.json --duration 52
   python3 edit_project.py projects/video-001.json --background assets/living-room-2.jpg
   ```

3. **Regenerate the MP4:**

   ```bash
   python3 generate_background.py projects/video-001.json
   ```

4. **Download the new MP4** from `outputs/` and import it into Edits.

Regenerating with the same `"output"` path overwrites that file; change
`"output"` (or duplicate the project) to keep an old render around.
