# Tools

Every tool the AI video editor uses. Install and test them all with:

```bash
bash setup_tools.sh
```

It's safe to re-run (cloud sessions start from a fresh machine each time,
so run it at the start of an editing session). Tools install into `~/tools`.

| tool | what it does | repo | status (last check) |
|---|---|---|---|
| **Remotion** | titles + animation (React → MP4) | `remotion-dev/remotion` | ✅ rendered a 2s 1080×1920 animated title |
| **HyperFrames** | HTML/CSS → MP4 compositions, built for agents | `heygen-com/hyperframes` | ✅ rendered the 1080×1920 starter composition |
| **FFmpeg** | cutting + audio | `FFmpeg/FFmpeg` | ✅ cut a clip and muxed an audio track |
| **Whisper** (whisper.cpp) | auto captions (speech → .srt) | `ggml-org/whisper.cpp` | ⚠️ built; speech model blocked by the cloud network (see below) |
| **yt-dlp** | pulls your own Reels for `references/` | `yt-dlp/yt-dlp` | ✅ installed, Instagram extractor present |
| MoviePy / Pillow / NumPy | this repo's background generator | `requirements.txt` | ✅ |

## Notes

- **HyperFrames isn't a green-screen tool.** The screenshot this list came
  from says "green screen cutouts", but HyperFrames turns HTML/CSS and
  animations into video (another titles/motion-graphics tool next to
  Remotion). Cutting out a background needs a separate tool if you want one.
- **Whisper model:** whisper.cpp downloads its speech model from
  `huggingface.co`, which this cloud environment's network policy blocks.
  On a Mac it downloads normally. In the cloud, add `huggingface.co` to the
  environment's allowed domains, then re-run `bash setup_tools.sh`.
- **Browser downloads:** Remotion and HyperFrames each try to download
  their own Chrome. That's blocked in cloud sessions, so the script reuses
  the preinstalled Chromium (or Google Chrome on a Mac).
- **GSAP:** HyperFrames' starter loads GSAP from `cdn.jsdelivr.net`, which
  is also blocked. The script installs it from npm and serves it locally.
- **yt-dlp + Instagram:** downloading Reels usually needs you logged in
  (`--cookies-from-browser safari` on a Mac). Only pull your own Reels or
  ones you have permission to use.
