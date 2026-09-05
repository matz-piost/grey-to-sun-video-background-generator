# assets/

Put your **uploaded source files** here for a generation run:

- Background image (e.g. `background.jpg`) or background video (e.g. `background.mp4`)
- Overlay images / screenshots (e.g. `analytics.png`)

These files are used **only while generating a video** — this folder is not
meant to store a permanent media library. Keep it lightweight:

- Don't commit large or final video files here.
- Delete files you no longer need for an active project.
- If you're using version control, consider adding large raw assets to
  `.gitignore` and keeping only what you need for the current edit.

## Naming tips

Use clear, reusable names so your `projects/*.json` files stay readable:

```
assets/background.jpg
assets/living-room-2.jpg
assets/analytics.png
```

If a background referenced in a project file is missing, the generator will
automatically fall back to a placeholder "grey-to-sun" gradient so you can
still test timing and overlays before your real footage is uploaded.
