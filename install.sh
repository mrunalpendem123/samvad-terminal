#!/bin/bash
# Samvad installer (macOS + Linux)
# Usage: curl -fsSL https://raw.githubusercontent.com/mrunalpendem123/samvad-terminal/main/install.sh | bash
set -e

INSTALL_DIR="$HOME/.samvad"
REPO_RAW="https://raw.githubusercontent.com/mrunalpendem123/samvad-terminal/main"

# ── Colors ──────────────────────────────────────────────────────────────────
BOLD="\033[1m"
DIM="\033[2m"
RESET="\033[0m"
TEAL="\033[38;5;80m"
GREEN="\033[38;5;78m"
RED="\033[38;5;203m"
GRAY="\033[38;5;243m"

pass() { echo -e "  ${GREEN}✓${RESET} $1"; }
info() { echo -e "  ${TEAL}→${RESET} $1"; }
fail() { echo -e "  ${RED}✗${RESET} $1"; exit 1; }

OS="$(uname -s)"

# ── Detect display server (Linux) ─────────────────────────────────────────
DISPLAY_SERVER="x11"
if [ "$OS" = "Linux" ]; then
  if [ "${XDG_SESSION_TYPE:-}" = "wayland" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
    DISPLAY_SERVER="wayland"
  fi
fi

# ── Pick install path (prefer ~/.local/bin, fall back to /usr/local/bin) ──
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
if echo "$PATH" | grep -q "$BIN_DIR"; then
  BIN_PATH="$BIN_DIR/samvad"
  NEEDS_SUDO=false
else
  BIN_PATH="/usr/local/bin/samvad"
  NEEDS_SUDO=true
fi

# ── Banner ──────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${TEAL}${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "  ${TEAL}${BOLD}║                                      ║${RESET}"
echo -e "  ${TEAL}${BOLD}║       ◎  S A M V A D                ║${RESET}"
if [ "$OS" = "Darwin" ]; then
  echo -e "  ${TEAL}${BOLD}║       Voice → Text for macOS         ║${RESET}"
else
  echo -e "  ${TEAL}${BOLD}║       Voice → Text for Linux         ║${RESET}"
fi
echo -e "  ${TEAL}${BOLD}║                                      ║${RESET}"
echo -e "  ${TEAL}${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""
echo -e "  ${DIM}Installing to ~/.samvad${RESET}"
echo ""

# ── Step 0 (Linux only): Install system dependencies ─────────────────────
if [ "$OS" = "Linux" ]; then
  echo -e "  ${BOLD}[0/4]${RESET} ${GRAY}Installing system dependencies...${RESET}"

  # Common packages + display-server-specific tools
  if command -v apt-get &>/dev/null; then
    sudo apt-get update -qq
    # Core audio + GTK
    sudo apt-get install -y -qq \
      portaudio19-dev \
      libgirepository1.0-dev \
      gir1.2-gtk-3.0 \
      python3-gi \
      python3-gi-cairo \
      gir1.2-gdk-3.0 2>/dev/null
    if [ "$DISPLAY_SERVER" = "wayland" ]; then
      sudo apt-get install -y -qq wl-clipboard wtype 2>/dev/null || true
      # xdotool as fallback (works via XWayland)
      sudo apt-get install -y -qq xdotool 2>/dev/null || true
    else
      sudo apt-get install -y -qq xclip xdotool 2>/dev/null
    fi
    pass "System packages installed (apt)"

  elif command -v dnf &>/dev/null; then
    sudo dnf install -y -q \
      portaudio-devel \
      gobject-introspection-devel \
      gtk3 \
      python3-gobject 2>/dev/null
    if [ "$DISPLAY_SERVER" = "wayland" ]; then
      sudo dnf install -y -q wl-clipboard wtype 2>/dev/null || true
      sudo dnf install -y -q xdotool 2>/dev/null || true
    else
      sudo dnf install -y -q xclip xdotool 2>/dev/null
    fi
    pass "System packages installed (dnf)"

  elif command -v pacman &>/dev/null; then
    sudo pacman -S --noconfirm --needed \
      portaudio \
      gobject-introspection \
      gtk3 \
      python-gobject 2>/dev/null
    if [ "$DISPLAY_SERVER" = "wayland" ]; then
      sudo pacman -S --noconfirm --needed wl-clipboard wtype 2>/dev/null || true
      sudo pacman -S --noconfirm --needed xdotool 2>/dev/null || true
    else
      sudo pacman -S --noconfirm --needed xclip xdotool 2>/dev/null
    fi
    pass "System packages installed (pacman)"

  elif command -v zypper &>/dev/null; then
    sudo zypper install -y \
      portaudio-devel \
      gobject-introspection-devel \
      gtk3-devel \
      python3-gobject 2>/dev/null
    if [ "$DISPLAY_SERVER" = "wayland" ]; then
      sudo zypper install -y wl-clipboard wtype 2>/dev/null || true
      sudo zypper install -y xdotool 2>/dev/null || true
    else
      sudo zypper install -y xclip xdotool 2>/dev/null
    fi
    pass "System packages installed (zypper)"

  elif command -v apk &>/dev/null; then
    sudo apk add \
      portaudio-dev \
      gobject-introspection-dev \
      gtk+3.0-dev \
      py3-gobject3 2>/dev/null
    if [ "$DISPLAY_SERVER" = "wayland" ]; then
      sudo apk add wl-clipboard wtype 2>/dev/null || true
      sudo apk add xdotool 2>/dev/null || true
    else
      sudo apk add xclip xdotool 2>/dev/null
    fi
    pass "System packages installed (apk)"

  else
    info "Could not detect package manager."
    info "Please install manually: portaudio, gtk3, python-gobject"
    if [ "$DISPLAY_SERVER" = "wayland" ]; then
      info "Wayland tools: wl-clipboard, wtype (or ydotool)"
    else
      info "X11 tools: xclip, xdotool"
    fi
  fi

  # Ensure user is in 'input' group (needed for pynput key capture)
  if ! groups | grep -qw input; then
    info "Adding $USER to 'input' group (needed for key capture)..."
    sudo usermod -aG input "$USER" 2>/dev/null || \
      info "Could not add to input group — you may need: sudo usermod -aG input \$USER"
  fi
fi

# ── Step 1: Download ────────────────────────────────────────────────────────
echo -e "  ${BOLD}[1/4]${RESET} ${GRAY}Downloading core files...${RESET}"
mkdir -p "$INSTALL_DIR"
curl -fsSL "$REPO_RAW/samvad-core.py"    -o "$INSTALL_DIR/samvad-core.py"
curl -fsSL "$REPO_RAW/samvad-ui.py"     -o "$INSTALL_DIR/samvad-ui.py"
curl -fsSL "$REPO_RAW/daemon.sh"        -o "$INSTALL_DIR/daemon.sh"
chmod +x "$INSTALL_DIR/daemon.sh"

if [ "$OS" = "Darwin" ]; then
  curl -fsSL "$REPO_RAW/samvad-overlay.py" -o "$INSTALL_DIR/samvad-overlay.py"
  pass "Downloaded samvad-core, samvad-ui, overlay, daemon"
else
  curl -fsSL "$REPO_RAW/samvad-overlay-linux.py" -o "$INSTALL_DIR/samvad-overlay-linux.py"
  pass "Downloaded samvad-core, samvad-ui, overlay, daemon"
fi

# ── Step 2: API key ────────────────────────────────────────────────────────
echo -e "  ${BOLD}[2/4]${RESET} ${GRAY}Configuring API key...${RESET}"
if [ -n "$SARVAM_API_KEY" ]; then
  echo "SARVAM_API_KEY=$SARVAM_API_KEY" > "$INSTALL_DIR/.env"
  chmod 600 "$INSTALL_DIR/.env"
  pass "API key written to ~/.samvad/.env"
elif [ -f "$HOME/.samvad/.env" ]; then
  pass "Existing ~/.samvad/.env preserved"
else
  echo "# Get your key at https://www.sarvam.ai" > "$INSTALL_DIR/.env"
  echo "SARVAM_API_KEY=" >> "$INSTALL_DIR/.env"
  chmod 600 "$INSTALL_DIR/.env"
  info "No API key found — edit ~/.samvad/.env with your SARVAM_API_KEY"
fi

# ── Step 3: Python runtime ─────────────────────────────────────────────────
echo -e "  ${BOLD}[3/4]${RESET} ${GRAY}Checking Python runtime (uv)...${RESET}"
if command -v uv &>/dev/null; then
  pass "uv already installed"
else
  info "Installing uv (fast Python manager)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
  pass "uv installed"
fi

# ── Step 4: Create command ──────────────────────────────────────────────────
echo -e "  ${BOLD}[4/4]${RESET} ${GRAY}Creating 'samvad' command...${RESET}"
cat > /tmp/samvad_cmd << 'EOF'
#!/bin/bash
export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
bash "$HOME/.samvad/daemon.sh" "$@"
EOF

if [ "$NEEDS_SUDO" = true ]; then
  sudo mv /tmp/samvad_cmd "$BIN_PATH"
  sudo chmod +x "$BIN_PATH"
else
  mv /tmp/samvad_cmd "$BIN_PATH"
  chmod +x "$BIN_PATH"
fi
pass "Command installed at $BIN_PATH"

# ── Done ────────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "  ${GREEN}${BOLD}  Installation complete!${RESET}"
echo -e "  ${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "  ${BOLD}Get started:${RESET}"
echo ""
echo -e "    ${TEAL}\$ samvad${RESET}"
echo ""

if [ "$OS" = "Darwin" ]; then
  echo -e "  ${BOLD}First run on macOS:${RESET}"
  echo -e "  ${GRAY}macOS will ask for two permissions —${RESET}"
  echo -e "  ${GRAY}go to ${BOLD}System Settings → Privacy & Security${RESET}${GRAY} and enable:${RESET}"
  echo ""
  echo -e "    ${DIM}1.${RESET} Accessibility"
  echo -e "    ${DIM}2.${RESET} Input Monitoring"
  echo ""
  echo -e "  ${GRAY}Then run ${TEAL}samvad${GRAY} again.${RESET}"
  echo ""
  echo -e "  ${BOLD}How it works:${RESET}"
  echo -e "  ${GRAY}Switch to any app → hold ${TEAL}[fn]${GRAY} → speak → release${RESET}"
else
  echo -e "  ${BOLD}First run on Linux:${RESET}"
  echo -e "  ${GRAY}If key listening fails, make sure your user is in the ${BOLD}input${RESET}${GRAY} group:${RESET}"
  echo ""
  echo -e "    ${TEAL}sudo usermod -aG input \$USER${RESET}"
  echo -e "    ${GRAY}Then log out and back in.${RESET}"
  echo ""
  if [ "$DISPLAY_SERVER" = "wayland" ]; then
    echo -e "  ${GRAY}Detected: ${BOLD}Wayland${RESET}${GRAY} session${RESET}"
    echo -e "  ${GRAY}Using: wl-clipboard + wtype for paste${RESET}"
  else
    echo -e "  ${GRAY}Detected: ${BOLD}X11${RESET}${GRAY} session${RESET}"
    echo -e "  ${GRAY}Using: xclip + xdotool for paste${RESET}"
  fi
  echo ""
  echo -e "  ${BOLD}How it works:${RESET}"
  echo -e "  ${GRAY}Switch to any app → hold ${TEAL}[Right Ctrl]${GRAY} → speak → release${RESET}"
fi
echo -e "  ${GRAY}Text appears at your cursor instantly.${RESET}"
echo ""
echo -e "  ${GRAY}A floating indicator appears while listening,${RESET}"
echo -e "  ${GRAY}even when the terminal is minimized.${RESET}"
echo ""
