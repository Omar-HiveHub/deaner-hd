#!/bin/bash
# setup.command — DeanerHD simplified production kit setup
# Safe to re-run.

set -u
cd "$(dirname "$0")"

GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; BOLD="\033[1m"; RESET="\033[0m"
ok()   { printf "  ${GREEN}✓${RESET} %s\n" "$1"; }
warn() { printf "  ${YELLOW}!${RESET} %s\n" "$1"; }
err()  { printf "  ${RED}✗${RESET} %s\n" "$1"; }
step() { printf "\n${BOLD}%s${RESET}\n" "$1"; }

trap 'echo; echo "Setup interrupted. Re-run setup.command any time."; read -p "Press Enter to close..."; exit 1' INT

clear
echo "════════════════════════════════════════════════════════"
echo "  DeanerHD Production Kit setup"
echo "════════════════════════════════════════════════════════"
echo

step "[1/5] Checking Python"
PYBIN=""
for cand in python3.13 python3.12 python3.11 python3; do
  if command -v "$cand" >/dev/null 2>&1; then PYBIN="$cand"; break; fi
done
if [ -z "$PYBIN" ]; then
  err "Python 3.11+ not found. Install it from https://www.python.org/downloads/"
  read -p "Press Enter to close..."
  exit 1
fi
PYMAJOR=$($PYBIN -c "import sys; print(sys.version_info.major)")
PYMINOR=$($PYBIN -c "import sys; print(sys.version_info.minor)")
if [ "$PYMAJOR" -lt 3 ] || { [ "$PYMAJOR" -eq 3 ] && [ "$PYMINOR" -lt 11 ]; }; then
  err "Python 3.11+ required. Found $($PYBIN --version)."
  read -p "Press Enter to close..."
  exit 1
fi
ok "$($PYBIN --version)"

step "[2/5] Checking FFmpeg"
if ! command -v ffmpeg >/dev/null 2>&1; then
  warn "FFmpeg not found. Install with Homebrew: brew install ffmpeg"
else
  ok "FFmpeg installed"
fi

step "[3/5] Checking yt-dlp"
if ! command -v yt-dlp >/dev/null 2>&1; then
  warn "yt-dlp command not found yet; Python install below will add the package."
else
  ok "yt-dlp installed"
fi

step "[4/5] Installing Python packages"
if [ ! -d ".venv" ]; then
  "$PYBIN" -m venv .venv
  ok "Created .venv"
else
  ok ".venv already exists"
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet
ok "Python packages installed"

step "[5/5] Checking config"
mkdir -p 01_Ideas 02_Projects 03_Reference/channel-notes 03_Reference/past-scripts 03_Reference/transcripts clips 2>/dev/null || true
if [ ! -f "config/.env" ] && [ -f "config/.env.example" ]; then
  cp config/.env.example config/.env
  warn "Created config/.env from config/.env.example"
fi
if [ -f "config/.env" ]; then
  if grep -q "YOUTUBE_DATA_API_KEY=." config/.env; then ok "YouTube API key present"; else warn "YOUTUBE_DATA_API_KEY is optional but improves idea/video search"; fi
  if grep -q "ANTHROPIC_API_KEY=." config/.env; then ok "Anthropic API key present"; else warn "ANTHROPIC_API_KEY is only needed for wrapper-generated outlines/metadata"; fi
else
  warn "No config/.env found. The folder can still be used through Codex prompts."
fi

echo
printf "${GREEN}${BOLD}Setup check complete.${RESET}\n"
echo "Open START_HERE.md for the workflow."
read -p "Press Enter to close this window..."
