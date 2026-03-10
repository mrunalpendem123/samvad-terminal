#!/bin/bash
# Samvad Daemon — Textual UI + Python core
# Hold [fn] anywhere → speak → release → auto-pastes at cursor
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Load API key (safe: only exports KEY=VALUE lines, no eval) ───────────────
_safe_load_env() {
  local envfile="$1"
  [ -f "$envfile" ] || return 0
  while IFS='=' read -r key value; do
    key="${key#"${key%%[![:space:]]*}"}"   # trim leading whitespace
    [[ -z "$key" || "$key" == \#* ]] && continue
    # Only allow alphanumeric + underscore keys (prevent injection)
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    value="${value#"${value%%[![:space:]]*}"}"   # trim leading whitespace
    value="${value%"${value##*[![:space:]]}"}"   # trim trailing whitespace
    value="${value#[\"\']}"   # strip leading quote
    value="${value%[\"\']}"   # strip trailing quote
    [ -z "${!key}" ] && export "$key=$value"
  done < "$envfile"
}
_safe_load_env "$DIR/.env"
_safe_load_env "$HOME/Desktop/sarvam/backend/.env"

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
