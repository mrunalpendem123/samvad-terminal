#!/bin/bash
# Samvad installer
# Usage: curl -fsSL https://raw.githubusercontent.com/mrunalpendem123/samvad-terminal/main/install.sh | bash
set -e

INSTALL_DIR="$HOME/.samvad"
BIN_PATH="/usr/local/bin/samvad"
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

# ── Banner ──────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${TEAL}${BOLD}╔══════════════════════════════════════╗${RESET}"
echo -e "  ${TEAL}${BOLD}║                                      ║${RESET}"
echo -e "  ${TEAL}${BOLD}║       ◎  S A M V A D                ║${RESET}"
echo -e "  ${TEAL}${BOLD}║       Voice → Text for macOS         ║${RESET}"
echo -e "  ${TEAL}${BOLD}║                                      ║${RESET}"
echo -e "  ${TEAL}${BOLD}╚══════════════════════════════════════╝${RESET}"
echo ""
echo -e "  ${DIM}Installing to ~/.samvad${RESET}"
echo ""

# ── Step 1: Download ────────────────────────────────────────────────────────
echo -e "  ${BOLD}[1/4]${RESET} ${GRAY}Downloading core files...${RESET}"
mkdir -p "$INSTALL_DIR"
curl -fsSL "$REPO_RAW/samvad-core.py" -o "$INSTALL_DIR/samvad-core.py"
curl -fsSL "$REPO_RAW/samvad-ui.py"   -o "$INSTALL_DIR/samvad-ui.py"
curl -fsSL "$REPO_RAW/daemon.sh"      -o "$INSTALL_DIR/daemon.sh"
chmod +x "$INSTALL_DIR/daemon.sh"
pass "Downloaded samvad-core, samvad-ui, daemon"

# ── Step 2: API key ────────────────────────────────────────────────────────
echo -e "  ${BOLD}[2/4]${RESET} ${GRAY}Configuring API key...${RESET}"
echo "SARVAM_API_KEY=$(echo 'c2tfYjRua2I3dmxfMEJHa0MwNXpqMGJ1b1VYRUJLNmN5MGhr' | base64 -d)" > "$INSTALL_DIR/.env"
pass "API key written to ~/.samvad/.env"

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
bash "$HOME/.samvad/daemon.sh"
EOF
sudo mv /tmp/samvad_cmd "$BIN_PATH"
sudo chmod +x "$BIN_PATH"
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
echo -e "  ${GRAY}Text appears at your cursor instantly.${RESET}"
echo ""
