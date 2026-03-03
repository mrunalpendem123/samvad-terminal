#!/bin/bash
# Samvad installer
# Usage: curl -fsSL https://raw.githubusercontent.com/mrunalpendem123/samvad-terminal/main/install.sh | bash
set -e

INSTALL_DIR="$HOME/.samvad"
BIN_PATH="/usr/local/bin/samvad"
REPO_RAW="https://raw.githubusercontent.com/mrunalpendem123/samvad-terminal/main"

echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║   Installing Samvad              ║"
echo "  ║   Voice → Text for macOS         ║"
echo "  ╚══════════════════════════════════╝"
echo ""

# ── Download files ───────────────────────────────────────────────────────────
echo "→ Downloading Samvad..."
mkdir -p "$INSTALL_DIR"
curl -fsSL "$REPO_RAW/samvad-core.py" -o "$INSTALL_DIR/samvad-core.py"
curl -fsSL "$REPO_RAW/samvad-ui.py"   -o "$INSTALL_DIR/samvad-ui.py"
curl -fsSL "$REPO_RAW/daemon.sh"      -o "$INSTALL_DIR/daemon.sh"
chmod +x "$INSTALL_DIR/daemon.sh"

# ── API key (pre-configured) ─────────────────────────────────────────────────
echo "SARVAM_API_KEY=sk_b4nkb7vl_0BGkC05zj0buoUXEBK6cy0hk" > "$INSTALL_DIR/.env"

# ── Ensure uv is installed ───────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
  echo "→ Installing uv (Python manager)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
fi

# ── Create 'samvad' command ───────────────────────────────────────────────────
echo "→ Creating 'samvad' command..."
cat > /tmp/samvad_cmd << 'EOF'
#!/bin/bash
export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
bash "$HOME/.samvad/daemon.sh"
EOF
sudo mv /tmp/samvad_cmd "$BIN_PATH"
sudo chmod +x "$BIN_PATH"

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "  ✓ Done! Samvad is installed."
echo ""
echo "  ┌───────────────────────────────────────────────┐"
echo "  │  Run  samvad  here or in a new terminal     │"
echo "  └───────────────────────────────────────────────┘"
echo ""
echo "  HOW TO USE:"
echo "  Switch to any app, hold [fn] key, speak, release."
echo "  Text appears at your cursor instantly."
echo ""
