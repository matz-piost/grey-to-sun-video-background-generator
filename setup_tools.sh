#!/usr/bin/env bash
# Install and smoke-test every tool the AI video editor uses (see TOOLS.md).
# Safe to re-run: skips anything already installed. Works on macOS (Homebrew)
# and on Linux / Claude Code cloud sessions.
#
#   bash setup_tools.sh
#
# Tools land in ~/tools (override with TOOLS_DIR=...).
set -u

TOOLS_DIR="${TOOLS_DIR:-$HOME/tools}"
WHISPER_MODEL="${WHISPER_MODEL:-base.en}"
mkdir -p "$TOOLS_DIR"

# Chromium for Remotion / HyperFrames: reuse a preinstalled one when present
# (cloud sessions block the tools' own browser downloads).
CHROME=""
for c in /opt/pw-browsers/chromium-*/chrome-linux64/chrome \
         "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; do
  [ -x "$c" ] && CHROME="$c" && break
done
[ -n "$CHROME" ] && export PUPPETEER_EXECUTABLE_PATH="$CHROME"

# macOS ships bash 3.2 (no associative arrays), so results are plain vars.
pass() { printf -v "RESULT_$1" "PASS  %s" "$2"; }
fail() { printf -v "RESULT_$1" "FAIL  %s" "$2"; }
probe() { ffprobe -v error -show_entries stream=codec_type -of csv=p=0 "$1" 2>/dev/null | sort -u | tr '\n' ' '; }

# --- FFmpeg: cutting + audio ------------------------------------------------
if ! command -v ffmpeg >/dev/null; then
  if command -v brew >/dev/null; then brew install ffmpeg; else sudo apt-get install -y ffmpeg; fi
fi
ffmpeg -v error -y -f lavfi -i "color=c=0x2b2b2b:s=1080x1920:d=3" -f lavfi -i "sine=frequency=440:duration=3" \
  -ss 0.5 -t 1 -c:v libx264 -c:a aac -shortest "$TOOLS_DIR/ffmpeg-test.mp4" \
  && [ "$(probe "$TOOLS_DIR/ffmpeg-test.mp4")" = "audio video " ] \
  && pass ffmpeg "cut a clip and muxed an audio track" || fail ffmpeg "could not cut/mux a test clip"

# --- yt-dlp: pull your own Reels -------------------------------------------
command -v yt-dlp >/dev/null || pip3 install -q yt-dlp || brew install yt-dlp
yt-dlp --list-extractors 2>/dev/null | grep -qx Instagram \
  && pass ytdlp "v$(yt-dlp --version), Instagram extractor present" || fail ytdlp "not installed"

# --- Whisper (whisper.cpp): auto captions ----------------------------------
W="$TOOLS_DIR/whisper.cpp"
[ -d "$W" ] || git clone -q --depth 1 https://github.com/ggml-org/whisper.cpp "$W"
[ -x "$W/build/bin/whisper-cli" ] || {
  cmake -S "$W" -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DWHISPER_BUILD_TESTS=OFF >/dev/null &&
  cmake --build "$W/build" -j 4 --target whisper-cli >/dev/null
}
[ -f "$W/models/ggml-$WHISPER_MODEL.bin" ] || sh "$W/models/download-ggml-model.sh" "$WHISPER_MODEL" >/dev/null 2>&1
if [ ! -x "$W/build/bin/whisper-cli" ]; then
  fail whisper "build failed"
elif [ ! -s "$W/models/ggml-$WHISPER_MODEL.bin" ]; then
  fail whisper "built, but the $WHISPER_MODEL model download (huggingface.co) failed"
else
  ffmpeg -v error -y -i "$W/samples/jfk.mp3" -ar 16000 -ac 1 "$TOOLS_DIR/jfk.wav" 2>/dev/null || cp "$W/samples/jfk.wav" "$TOOLS_DIR/jfk.wav"
  "$W/build/bin/whisper-cli" -m "$W/models/ggml-$WHISPER_MODEL.bin" -f "$TOOLS_DIR/jfk.wav" -osrt -of "$TOOLS_DIR/whisper-test" >/dev/null 2>&1 \
    && grep -qi "country" "$TOOLS_DIR/whisper-test.srt" \
    && pass whisper "transcribed the sample clip to .srt captions" || fail whisper "transcription test failed"
fi

# --- Remotion: titles + animation ------------------------------------------
R="$TOOLS_DIR/remotion-test"
mkdir -p "$R/src"
[ -d "$R/node_modules/remotion" ] || (cd "$R" && npm init -y >/dev/null &&
  npm i -s remotion@4 @remotion/cli@4 @remotion/bundler@4 @remotion/renderer@4 react@18 react-dom@18 >/dev/null 2>&1)
cat > "$R/src/index.jsx" <<'EOF'
import {registerRoot, Composition, AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
const Title = () => {
  const f = useCurrentFrame();
  return <AbsoluteFill style={{background: '#2b2b2b', alignItems: 'center', paddingTop: 300}}>
    <div style={{color: '#FAEECD', fontSize: 110, fontFamily: 'serif',
      opacity: interpolate(f, [0, 15], [0, 1], {extrapolateRight: 'clamp'})}}>No time to edit?</div>
  </AbsoluteFill>;
};
registerRoot(() => <Composition id="Title" component={Title} durationInFrames={60} fps={30} width={1080} height={1920} />);
EOF
(cd "$R" && npx remotion render src/index.jsx Title out/title.mp4 ${CHROME:+--browser-executable="$CHROME"} >/dev/null 2>&1) \
  && [ -s "$R/out/title.mp4" ] && pass remotion "rendered a 2s 1080x1920 animated title" || fail remotion "test render failed"

# --- HyperFrames: HTML -> video compositions --------------------------------
H="$TOOLS_DIR/hf-test"
[ -d "$H" ] || (cd "$TOOLS_DIR" && npx -y hyperframes init hf-test --example blank --resolution portrait \
  --non-interactive --skip-skills --skip-transcribe >/dev/null 2>&1)
# Serve GSAP locally instead of from cdn.jsdelivr.net (blocked in cloud sessions).
(cd "$H" && [ -f gsap.min.js ] || { npm i -s gsap@3.14.2 >/dev/null 2>&1 && cp node_modules/gsap/dist/gsap.min.js .; })
sed -i.bak 's#https://cdn.jsdelivr.net/npm/gsap@[0-9.]*/dist/gsap.min.js#gsap.min.js#' "$H/index.html" && rm -f "$H/index.html.bak"
(cd "$H" && npx -y hyperframes render -o out.mp4 >/dev/null 2>&1) && [ -s "$H/out.mp4" ] \
  && pass hyperframes "rendered the 1080x1920 starter composition" || fail hyperframes "test render failed"

echo
echo "Tool check:"
for t in remotion hyperframes ffmpeg whisper ytdlp; do v="RESULT_$t"; printf "  %-12s %s\n" "$t" "${!v:-not run}"; done
