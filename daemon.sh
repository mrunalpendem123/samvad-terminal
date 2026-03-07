#!/bin/bash
# Samvad Daemon — Textual UI + Python core
# Hold [fn] anywhere → speak → release → auto-pastes at cursor
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Load API key ────────────────────────────────────────────────────────────────
if [ -f "$DIR/.env" ]; then
  export $(grep -v '^#' "$DIR/.env" | xargs) 2>/dev/null || true
fi
SARVAM_ENV="$HOME/Desktop/sarvam/backend/.env"
if [ -f "$SARVAM_ENV" ]; then
  while IFS= read -r line; do
    [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
    key="${line%%=*}"
    [[ -z "${!key}" ]] && export "$line" 2>/dev/null || true
  done < "$SARVAM_ENV"
fi

# ── Ensure uv is installed ──────────────────────────────────────────────────────
if ! command -v uv &> /dev/null; then
  echo "uv not found — installing..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.cargo/bin:$PATH"
fi

# ── Launch overlay indicator in background (visible when terminal is minimized)
uv run \
  --python 3.11 \
  --no-project \
  --with "pyobjc-framework-Cocoa>=10" \
  --with "pyobjc-framework-Quartz>=10" \
  --with "sounddevice>=0.4" \
  --with "numpy>=1.26" \
  --with "requests>=2.28" \
  python "$DIR/samvad-overlay.py" &
OVERLAY_PID=$!

# Kill overlay when the terminal UI exits
trap "kill $OVERLAY_PID 2>/dev/null" EXIT

# ── Launch terminal UI (main app) ────────────────────────────────────────────
exec uv run \
  --python 3.11 \
  --no-project \
  --with "textual>=0.70" \
  --with "textual-plotext>=0.2" \
  python "$DIR/samvad-ui.py"
