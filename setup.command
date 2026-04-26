#!/bin/bash
# setup.command — Deaner-HD double-click installer for non-technical users
# Idempotent: safe to re-run.
# Triggered by: double-click in Finder.

set -u

# Always work from the directory this script lives in
cd "$(dirname "$0")"

# ---------------------------------------------------------------------------
# Pretty output helpers
# ---------------------------------------------------------------------------
GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; BOLD="\033[1m"; RESET="\033[0m"
ok()   { printf "  ${GREEN}✓${RESET} %s\n" "$1"; }
warn() { printf "  ${YELLOW}!${RESET} %s\n" "$1"; }
err()  { printf "  ${RED}✗${RESET} %s\n" "$1"; }
step() { printf "\n${BOLD}%s${RESET}\n" "$1"; }

trap 'echo; echo "Setup interrupted. You can re-run this any time by double-clicking setup.command."; read -p "Press Enter to close..."; exit 1' INT

clear
echo "════════════════════════════════════════════════════════"
echo "  Deaner-HD installer"
echo "════════════════════════════════════════════════════════"
echo
echo "This will set up everything you need to run the system."
echo "Safe to re-run as many times as you want."
echo

# ---------------------------------------------------------------------------
# Step 1 — Python
# ---------------------------------------------------------------------------
step "[1/6] Checking Python..."

PYBIN=""
for cand in python3.13 python3.12 python3.11 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    PYBIN="$cand"; break
  fi
done

if [ -z "$PYBIN" ]; then
  err "Python 3.11+ not found."
  echo "    Download it from https://www.python.org/downloads/"
  echo "    (Get the macOS installer, run it, then re-run this script.)"
  read -p "Press Enter to close..."
  exit 1
fi

PYVER=$("$PYBIN" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYMAJOR=$("$PYBIN" -c "import sys; print(sys.version_info.major)")
PYMINOR=$("$PYBIN" -c "import sys; print(sys.version_info.minor)")
if [ "$PYMAJOR" -lt 3 ] || { [ "$PYMAJOR" -eq 3 ] && [ "$PYMINOR" -lt 11 ]; }; then
  err "Found Python $PYVER but need 3.11 or newer."
  echo "    Install from https://www.python.org/downloads/ then re-run this."
  read -p "Press Enter to close..."
  exit 1
fi
ok "Python $PYVER ($PYBIN)"

# ---------------------------------------------------------------------------
# Step 2 — Homebrew
# ---------------------------------------------------------------------------
step "[2/6] Checking Homebrew..."

BREW=""
for cand in /opt/homebrew/bin/brew /usr/local/bin/brew; do
  if [ -x "$cand" ]; then BREW="$cand"; break; fi
done
if [ -z "$BREW" ] && command -v brew >/dev/null 2>&1; then
  BREW="$(command -v brew)"
fi

if [ -z "$BREW" ]; then
  warn "Homebrew not found. Installing..."
  echo "    (You may be prompted for your Mac password — that's normal.)"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  for cand in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [ -x "$cand" ]; then BREW="$cand"; break; fi
  done
  if [ -z "$BREW" ]; then
    err "Homebrew install didn't finish. Try running this script again."
    read -p "Press Enter to close..."
    exit 1
  fi
fi
ok "Homebrew ($BREW)"

# ---------------------------------------------------------------------------
# Step 3 — FFmpeg
# ---------------------------------------------------------------------------
step "[3/6] Checking FFmpeg..."

FFMPEG=""
for cand in /opt/homebrew/bin/ffmpeg /usr/local/bin/ffmpeg; do
  if [ -x "$cand" ]; then FFMPEG="$cand"; break; fi
done
if [ -z "$FFMPEG" ] && command -v ffmpeg >/dev/null 2>&1; then
  FFMPEG="$(command -v ffmpeg)"
fi

if [ -z "$FFMPEG" ]; then
  warn "FFmpeg not installed. Installing via Homebrew (~2 min)..."
  "$BREW" install ffmpeg
  for cand in /opt/homebrew/bin/ffmpeg /usr/local/bin/ffmpeg; do
    if [ -x "$cand" ]; then FFMPEG="$cand"; break; fi
  done
fi
if [ -z "$FFMPEG" ]; then
  err "FFmpeg install failed. Try opening Terminal and running 'brew install ffmpeg' manually."
  read -p "Press Enter to close..."
  exit 1
fi
FFVER=$("$FFMPEG" -version 2>/dev/null | head -1 | awk '{print $3}')
ok "FFmpeg $FFVER"

# ---------------------------------------------------------------------------
# Step 4 — Python virtualenv + dependencies
# ---------------------------------------------------------------------------
step "[4/6] Installing Python packages..."

if [ ! -d ".venv" ]; then
  "$PYBIN" -m venv .venv
  ok "Created virtual environment (.venv/)"
else
  ok "Virtual environment already exists"
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip --quiet
echo "    Installing packages from requirements.txt (this takes a few minutes)..."
python -m pip install -r requirements.txt --quiet
ok "Python packages installed"

# ---------------------------------------------------------------------------
# Step 5 — Validate config/.env
# ---------------------------------------------------------------------------
step "[5/6] Checking API keys in config/.env..."

ENV_FILE="config/.env"
if [ ! -f "$ENV_FILE" ]; then
  if [ -f "config/.env.example" ]; then
    cp config/.env.example "$ENV_FILE"
    warn "Created config/.env from template. You must add your real keys."
  else
    err "config/.env not found and no template available."
    read -p "Press Enter to close..."
    exit 1
  fi
fi

MISSING=()
for KEY in ANTHROPIC_API_KEY GEMINI_API_KEY YOUTUBE_DATA_API_KEY; do
  VALUE=$(grep "^$KEY=" "$ENV_FILE" | head -1 | cut -d= -f2-)
  if [ -z "$VALUE" ] || [ "$VALUE" = "your_key_here" ]; then
    MISSING+=("$KEY")
  else
    ok "$KEY set (${#VALUE} chars)"
  fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
  warn "Missing keys: ${MISSING[*]}"
  echo "    Open config/.env in TextEdit and replace 'your_key_here' with your real keys."
  echo "    See SETUP.md Step 3 for where to get each one."
fi

# ---------------------------------------------------------------------------
# Step 6 — Final report
# ---------------------------------------------------------------------------
step "[6/6] Setup summary"

if [ ${#MISSING[@]} -eq 0 ]; then
  echo
  printf "  ${GREEN}${BOLD}✓ Setup complete.${RESET}\n"
  echo
  echo "  Open this folder in Claude Code and type:"
  printf "      ${BOLD}let's start a new video${RESET}\n"
  echo
else
  echo
  printf "  ${YELLOW}${BOLD}! Setup complete except for API keys.${RESET}\n"
  echo
  echo "  Add your missing keys to config/.env, then re-run this script to verify."
  echo "  See SETUP.md Step 3 for where to get each key."
  echo
fi

read -p "Press Enter to close this window..."
