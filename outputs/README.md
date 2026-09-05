# outputs/

Generated MP4 files land here, at whatever path your project's `"output"`
field points to (default: `outputs/background_video.mp4`).

- Each project (`projects/video-XXX.json`) should point to its own output
  file, e.g. `outputs/video-001-background.mp4`, so regenerating one video
  never overwrites another.
- Running the generator again with the **same** `"output"` path overwrites
  that file in place (handy for quick iterations on the same video).
- These are final, ready-to-import files — download the one you need and
  import it into Edits (or any editor) as your background layer.

This folder is a working output directory, not permanent asset storage —
feel free to delete old renders once you've downloaded what you need.
