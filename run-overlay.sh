#!/bin/bash
# Samvad floating overlay — minimal recording indicator
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

_safe_load_env() {
  local envfile="$1"
  [ -f "$envfile" ] || return 0
  while IFS='=' read -r key value; do
    key="${key#"${key%%[![:space:]]*}"}"
    [[ -z "$key" || "$key" == \#* ]] && continue
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    value="${value#[\"\']}"
    value="${value%[\"\']}"
    [ -z "${!key}" ] && export "$key=$value"
  done < "$envfile"
}
_safe_load_env "$DIR/.env"
_safe_load_env "$HOME/Desktop/sarvam/backend/.env"

exec uv run \
  --python 3.11 \
  --no-project \
  --with "pyobjc-framework-Cocoa>=10" \
  --with "pyobjc-framework-Quartz>=10" \
  --with "sounddevice>=0.4" \
  --with "numpy>=1.26" \
  --with "requests>=2.28" \
  python "$DIR/samvad-overlay.py"
