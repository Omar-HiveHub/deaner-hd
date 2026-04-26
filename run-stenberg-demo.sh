#!/bin/bash
# run-stenberg-demo.sh — Render the "Stenberg Replicate-and-Beat" demo artifact
#
# Reproduces Dean's 75k-view Stenberg video using the new system:
#   1. Extracts the ORIGINAL voiceover from his published YouTube video
#      (so the comparison is apples-to-apples — same voice, new edit)
#   2. Re-gathers fresh clips with copyright-safe metadata
#   3. Auto-approves the first 8 clips (override by hand if you want curation)
#   4. Re-generates the script via Claude Opus 4.7 (biography tier)
#   5. Builds the long-form video with stat-board breaks + music bed + SFX cues
#   6. Generates metadata via Claude Haiku 4.5
#   7. Generates the thumbnail brief via Claude Opus 4.7 vision
#
# Prereqs:
#   - setup.command has run successfully (Python venv ready)
#   - config/.env has real ANTHROPIC_API_KEY + GEMINI_API_KEY (+ optional YOUTUBE)
#
# Run:
#   ./run-stenberg-demo.sh
#
# Output:
#   outputs/long-form/2026-04-26-stenberg-replicated.mp4
#   outputs/long-form/2026-04-26-stenberg-replicated-metadata.txt
#   outputs/long-form/2026-04-26-stenberg-replicated-thumbnail-brief.txt

set -u
cd "$(dirname "$0")"

GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; BOLD="\033[1m"; RESET="\033[0m"
ok()   { printf "${GREEN}✓${RESET} %s\n" "$1"; }
warn() { printf "${YELLOW}!${RESET} %s\n" "$1"; }
err()  { printf "${RED}✗${RESET} %s\n" "$1"; }
step() { printf "\n${BOLD}━━ %s ━━${RESET}\n" "$1"; }

# Activate venv if present
if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  ok "Activated .venv"
else
  warn "No .venv/ found — running with system Python. (Run setup.command first.)"
fi

PY="python3"
TOPIC="Ivar Stenberg — why he might be the greatest Swedish prospect of all time"
TITLE="stenberg-replicated"
ORIGINAL_VIDEO_ID="N5-LIV1UyHA"

# ---------------------------------------------------------------------------
# Step 1 — Pull original voiceover from YouTube
# ---------------------------------------------------------------------------
step "[1/7] Extracting original Stenberg voiceover from YouTube"

mkdir -p pipeline/recorded
VO_PATH="pipeline/recorded/stenberg-original-vo.m4a"

if [ -f "$VO_PATH" ]; then
  ok "Voiceover already extracted: $VO_PATH"
else
  yt-dlp -x --audio-format m4a --audio-quality 0 \
    -o "$VO_PATH" \
    "https://www.youtube.com/watch?v=$ORIGINAL_VIDEO_ID" 2>&1 | tail -5
  if [ -f "$VO_PATH" ]; then
    ok "Voiceover saved: $VO_PATH"
  else
    err "Failed to extract voiceover. (yt-dlp may be outdated — try: pip install -U yt-dlp)"
    err "You can drop a voiceover file into pipeline/recorded/ manually and re-run from step 4."
  fi
fi

# ---------------------------------------------------------------------------
# Step 2 — Gather fresh clips for the topic
# ---------------------------------------------------------------------------
step "[2/7] Gathering Stenberg highlight clips"

# Skip if user has already approved clips (let them curate)
APPROVED_COUNT=$(find clips/approved -maxdepth 1 -name "stenberg*.mp4" 2>/dev/null | wc -l | tr -d ' ')
if [ "$APPROVED_COUNT" -gt 0 ]; then
  ok "Found $APPROVED_COUNT pre-approved Stenberg clips — skipping gather"
else
  $PY scripts/gather_clips.py --topic "Ivar Stenberg highlights" 2>&1 | tail -10 || \
    warn "gather_clips encountered errors — check raw clips manually"
fi

# ---------------------------------------------------------------------------
# Step 3 — Auto-approve clips (override by hand for production)
# ---------------------------------------------------------------------------
step "[3/7] Auto-approving up to 8 clips for the demo"

mkdir -p clips/approved
RAW_COUNT=$(find clips/raw -maxdepth 1 -name "*.mp4" 2>/dev/null | wc -l | tr -d ' ')
APPROVED_COUNT=$(find clips/approved -maxdepth 1 -name "*.mp4" 2>/dev/null | wc -l | tr -d ' ')

if [ "$APPROVED_COUNT" -ge 6 ]; then
  ok "Already have $APPROVED_COUNT approved clips — using those"
elif [ "$RAW_COUNT" -gt 0 ]; then
  for clip in $(find clips/raw -maxdepth 1 -name "*.mp4" | sort | head -8); do
    base=$(basename "$clip" .mp4)
    if [ ! -f "clips/approved/${base}.mp4" ]; then
      mv "clip/raw/${base}.mp4" "clips/approved/${base}.mp4" 2>/dev/null || \
        cp "clips/raw/${base}.mp4" "clips/approved/${base}.mp4"
      cp "clips/raw/${base}.json" "clips/approved/${base}.json" 2>/dev/null || true
    fi
  done
  APPROVED_COUNT=$(find clips/approved -maxdepth 1 -name "*.mp4" 2>/dev/null | wc -l | tr -d ' ')
  ok "Approved $APPROVED_COUNT clips"
else
  err "No clips in clips/raw/ — gather_clips probably failed. Check API keys + yt-dlp."
fi

# ---------------------------------------------------------------------------
# Step 4 — Generate script (biography → Opus 4.7)
# ---------------------------------------------------------------------------
step "[4/7] Generating script via Claude Opus 4.7 (biography tier)"

mkdir -p pipeline/scripted
SCRIPT_OUT=$($PY scripts/generate_script.py --topic "$TOPIC" --type biography 2>&1) && {
  echo "$SCRIPT_OUT" | tail -5
  ok "Script written to pipeline/scripted/"
} || {
  err "Script generation failed:"
  echo "$SCRIPT_OUT" | tail -10
}

# ---------------------------------------------------------------------------
# Step 5 — Assemble the video with breaks + music + SFX
# ---------------------------------------------------------------------------
step "[5/7] Assembling video (visual breaks + music bed + SFX cues)"

if [ -f "$VO_PATH" ] && [ "$APPROVED_COUNT" -gt 0 ]; then
  $PY scripts/assemble_video.py --topic-type biography --title "$TITLE" 2>&1 | tail -8
  FINAL_VIDEO=$(ls -t outputs/long-form/*-${TITLE}.mp4 2>/dev/null | head -1)
  if [ -n "$FINAL_VIDEO" ] && [ -f "$FINAL_VIDEO" ]; then
    ok "Long-form rendered: $FINAL_VIDEO"
  else
    err "Assembly failed — check ffmpeg output above"
    FINAL_VIDEO=""
  fi
else
  err "Skipping assembly — missing voiceover or clips"
  FINAL_VIDEO=""
fi

# ---------------------------------------------------------------------------
# Step 6 — Metadata via Haiku 4.5
# ---------------------------------------------------------------------------
step "[6/7] Generating metadata via Claude Haiku 4.5"

if [ -n "$FINAL_VIDEO" ]; then
  $PY scripts/generate_metadata.py --video "$FINAL_VIDEO" 2>&1 | tail -3
  META_FILE="${FINAL_VIDEO%.mp4}-metadata.txt"
  [ -f "$META_FILE" ] && ok "Metadata: $META_FILE" || warn "Metadata file not found"
else
  warn "Skipping metadata — no final video"
fi

# ---------------------------------------------------------------------------
# Step 7 — Thumbnail brief via Opus 4.7 vision
# ---------------------------------------------------------------------------
step "[7/7] Generating thumbnail brief via Claude Opus 4.7"

if [ -n "$FINAL_VIDEO" ]; then
  $PY scripts/generate_thumbnail.py --video "$FINAL_VIDEO" 2>&1 | tail -3
else
  # Fall back to using the script alone if assembly didn't complete
  LATEST_SCRIPT=$(ls -t pipeline/scripted/*.md 2>/dev/null | head -1)
  if [ -n "$LATEST_SCRIPT" ]; then
    $PY scripts/generate_thumbnail.py --script "$LATEST_SCRIPT" 2>&1 | tail -3
  fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
step "Demo artifacts"
echo
[ -n "$FINAL_VIDEO" ] && echo "  📹 Long-form:    $FINAL_VIDEO"
[ -n "${META_FILE:-}" ] && [ -f "${META_FILE:-}" ] && echo "  📝 Metadata:     $META_FILE"
THUMB_FILE=$(ls -t outputs/long-form/*-thumbnail-brief.txt pipeline/scripted/*-thumbnail-brief.txt 2>/dev/null | head -1)
[ -n "$THUMB_FILE" ] && echo "  🎨 Thumbnail:    $THUMB_FILE"
LATEST_SCRIPT=$(ls -t pipeline/scripted/*.md 2>/dev/null | head -1)
[ -n "$LATEST_SCRIPT" ] && echo "  ✍️  Script:       $LATEST_SCRIPT"
echo "  🎙  Original VO:  $VO_PATH"
echo "  📚 Original transcript: voice/transcripts/20260113-${ORIGINAL_VIDEO_ID}.txt"
echo
echo "Compare side-by-side on the call:"
echo "  - Original published video: https://www.youtube.com/watch?v=${ORIGINAL_VIDEO_ID}"
echo "  - System-rendered version:  $FINAL_VIDEO"
echo
