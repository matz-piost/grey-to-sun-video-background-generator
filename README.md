# grey-to-sun-video-background-generator

A lightweight, cloud-friendly tool that generates a finished **silent MP4
background video** for short-form videos — vertical 9:16, with timed text
and image overlays — ready to sit behind you (green screen / cutout /
video overlay) in a mobile editor like CapCut's **Edits** app.

No heavy app, no UI: you edit a small JSON file and run one Python script.

- Input: a background image/video + a JSON file describing timed overlays
- Output: an actual `.mp4` file you download and import into Edits
- Nothing large is stored permanently in the repo — assets are used only
  during generation, and outputs are just working files you download and
  can delete afterward

## Video specs

- Vertical 9:16, **1080x1920**
- **30 fps**, silent (no audio track)
- Duration: from your JSON (`"duration"`), default **45s**, hard-capped at
  **60s** unless you set `"allow_over_60": true`
- Warm, calm, editorial look, built for a green-screened presenter in the
  centre/lower-centre of frame — two overlay styles only, never mixed at
  random:
  - **Editorial Hook** (`text`/`teaser`) — large, soft serif (Fraunces),
    warm cream/butter text straight over the footage, no box, no outline,
    just a subtle shadow for readability. For emotional/positioning lines.
  - **Analysis Card** (`rect`, and `image`/`screenshot`) — a cream/beige
    rounded card, charcoal Inter sans-serif text, a thin muted accent bar.
    For screenshots, numbers, analytics.
- Captions are always **horizontally centred** and confined to the **top
  third** of the frame, so they never sit over your face/body
- Overlays **pop on/off screen instantly** by default (no fade/slide
  creep) — set `"animation"` explicitly per overlay if you want one

## 1. Install dependencies

```bash
pip3 install -r requirements.txt
```

This installs MoviePy, Pillow and NumPy. MoviePy bundles its own FFmpeg
binary (via `imageio-ffmpeg`), so you don't need to separately install
FFmpeg system-wide — this keeps the setup lightweight and works in Claude
Code's cloud environment out of the box.

Two free Google Fonts (SIL Open Font License — no cost, no license to buy)
are bundled in `fonts/` so the look is consistent everywhere: **Fraunces**
for Editorial Hook headlines, **Inter** for Analysis Card text. If `fonts/`
is ever removed, the generator falls back to the system's DejaVu Serif
Bold / DejaVu Sans Bold automatically.

## 2. Upload your assets

Put your background and overlay files in `assets/` (see
`assets/README.md`):

```
assets/background.jpg      # or background.mp4 / .mov etc.
assets/analytics.png       # any screenshot/image overlays you want to include
```

If you haven't uploaded a real background yet, that's fine — leave the
`"background"` path in your JSON pointing at a file that doesn't exist yet
(or use the provided example). The generator will automatically fall back
to a **placeholder grey-to-sun gradient** so you can test timing and
overlays first, then swap in your real footage later with no other
changes needed.

## 3. Edit a project JSON

Start from `example_input.json` or `projects/video-001.json`. Each overlay
has a start/end time (seconds), a type, a position, and a style. Full
field reference: `projects/README.md`.

```json
{
  "duration": 45,
  "background": "assets/background.jpg",
  "output": "outputs/background_video.mp4",
  "mila_position": "center_lower",
  "overlays": [
    { "start": 0, "end": 4, "type": "text", "text": "200 views again?",
      "position": "upper_center", "style": "headline" },
    { "start": 5, "end": 10, "type": "text", "text": "Before blaming the niche...",
      "position": "upper_left", "style": "support" },
    { "start": 12, "end": 20, "type": "image", "file": "assets/analytics.png",
      "position": "left_side", "style": "screenshot" }
  ]
}
```

### Safe zones (built in)

Plain captions (`text` / `teaser` overlays) are always **centred** and
confined to the **top third** of the frame — they never land in the top
10% (platform UI) or drop down over your face/body in the middle/lower
frame. The `"position"` field is accepted for these but doesn't change
their placement; it's still used for `image`/`screenshot`/`rect`/`arrow`/
`circle` overlays, where `upper_center`, `upper_left`, `upper_right`,
`left_side`, or `right_side` keep them around your head/shoulders and out
of the centre. Preview the safe zones before recording:

```bash
python3 generate_background.py projects/video-001.json --debug-safe-zones
```

### Overlay types

| type                | needs               | notes |
|---------------------|---------------------|-------|
| `text`              | `text`              | Editorial Hook by default — soft serif, no box |
| `teaser`            | `text`              | Editorial Hook, for a closing/next-video line (write "Next: ..." into the text itself — no separate tag) |
| `image` / `screenshot` | `file`           | Analysis Card — framed image/screenshot |
| `rect`              | `text` (optional)   | Analysis Card — a filled text card, or a flat colour rectangle |
| `arrow`             | `direction` (optional) | simple accent arrow |
| `circle`            | `size` (optional)   | simple accent circle/highlight |

Styles — each belongs to one of the two allowed looks (set on the
overlay's `"style"`, independent of `"type"`, so any text overlay can be
either): `headline` and `support` (Editorial Hook, serif — support is
roughly half the headline size) and `teaser` (Editorial Hook, for closing
lines) vs. `card` and `screenshot` (Analysis Card, boxed). Don't mix more
than these two looks into one video.
Animations: `none` (default — pops on/off screen instantly), `fade`, `slide`, `pop`.

## 4. Run the generator

```bash
python3 generate_background.py projects/video-001.json
```

(Running with no arguments uses `example_input.json`.)

The MP4 appears at whatever path you set in `"output"` — for
`projects/video-001.json` that's `outputs/video-001-background.mp4`.

## 5. Download the MP4 and import into Edits

1. Find the file Claude generated under `outputs/` and download it.
2. AirDrop / transfer it to your phone (or download directly if you're
   running Claude Code on your phone/web).
3. Open **Edits**, start a new project, add the MP4 as your **background
   layer**.
4. Record or drop in your green-screen/cutout footage on top, matching the
   timed overlays to your `mila_position` safe area.

## Quick edits and regeneration

Don't treat an MP4 as a one-off — every video has a matching editable
project file in `projects/`:

```
projects/video-001.json  ->  outputs/video-001-background.mp4
```

**Create a new video** (start from a blank template or duplicate one):

```bash
python3 duplicate_project.py projects/video-001.json projects/video-002.json
```

**Make a quick text/timing/background edit:**

```bash
python3 edit_project.py projects/video-001.json --overlay 3 --text "Check watch time first"
python3 edit_project.py projects/video-001.json --overlay 4 --start 20 --end 29
python3 edit_project.py projects/video-001.json --duration 52
python3 edit_project.py projects/video-001.json --background assets/living-room-2.jpg
```

(You can also just open the JSON in a text editor and change it by hand —
see `projects/README.md` for the full field reference.)

**Regenerate the MP4:**

```bash
python3 generate_background.py projects/video-001.json
```

Regenerating with the same `"output"` path overwrites that file. Change
`"output"` (or duplicate the project first) if you want to keep the old
render around too.

**Then:** download the new MP4 from `outputs/` and import it into Edits.

## Demo included

This repo ships a working demo matching this script:

> "If your videos keep getting 200 views, this might not be a niche
> problem yet. I'm figuring out why people stop watching small creators,
> starting with my own videos. And the annoying thing I'm noticing is
> that I keep blaming the big thing — the niche, the account, the whole
> direction — before checking the small thing: did people even stay long
> enough to get the point? So this week I'm checking watch time before I
> let myself rebrand again."

See `example_input.json` / `projects/video-001.json` and
`outputs/video-001-background.mp4` (generated with a placeholder
background — swap in `assets/background.jpg` and regenerate once you
upload your real footage).

## Project structure

```
generate_background.py   # the generator (run this)
duplicate_project.py     # copy a project to start a new video
edit_project.py          # quick CLI edits to a project JSON
example_input.json       # standalone quick-start example
requirements.txt
assets/                  # your uploaded background/overlay files (not permanent storage)
projects/                # one editable JSON per video
  video-001.json
outputs/                 # generated MP4s land here
  video-001-background.mp4
```
