# Samvad Windows installer
# Usage: iwr -useb https://raw.githubusercontent.com/mrunalpendem123/samvad-terminal/main/install.ps1 | iex

$ErrorActionPreference = "Stop"

$INSTALL_DIR = "$env:USERPROFILE\.samvad"
$REPO_RAW    = "https://raw.githubusercontent.com/mrunalpendem123/samvad-terminal/main"

Write-Host ""
Write-Host "  +----------------------------------+"
Write-Host "  |   Installing Samvad             |"
Write-Host "  |   Voice -> Text for Windows     |"
Write-Host "  +----------------------------------+"
Write-Host ""

# ── Download files ────────────────────────────────────────────────────────────
Write-Host "-> Downloading Samvad..."
New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null

Invoke-WebRequest "$REPO_RAW/samvad-core.py" -OutFile "$INSTALL_DIR\samvad-core.py"
Invoke-WebRequest "$REPO_RAW/samvad-ui.py"   -OutFile "$INSTALL_DIR\samvad-ui.py"
Invoke-WebRequest "$REPO_RAW/daemon.bat"     -OutFile "$INSTALL_DIR\samvad.bat"

# ── API key (pre-configured) ──────────────────────────────────────────────────
Write-Host "-> Writing API key..."
"SARVAM_API_KEY=sk_b4nkb7vl_0BGkC05zj0buoUXEBK6cy0hk" | Out-File -FilePath "$INSTALL_DIR\.env" -Encoding utf8

# ── Ensure uv is installed ────────────────────────────────────────────────────
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "-> Installing uv (Python manager)..."
    irm https://astral.sh/uv/install.ps1 | iex
}

# ── Add install dir to user PATH (so you can type 'samvad' anywhere) ─────────
Write-Host "-> Adding samvad to PATH..."
$UserPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($UserPath -notlike "*$INSTALL_DIR*") {
    [Environment]::SetEnvironmentVariable("PATH", "$UserPath;$INSTALL_DIR", "User")
    Write-Host "   (close and reopen your terminal for PATH to take effect)"
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  +-------------------------------------------------+"
Write-Host "  |  Done!  Open a NEW terminal and run:  samvad   |"
Write-Host "  |                                                 |"
Write-Host "  |  First run: Windows may ask for permissions.    |"
Write-Host "  |  Allow access when prompted.                    |"
Write-Host "  +-------------------------------------------------+"
Write-Host ""
Write-Host "  HOW TO USE:"
Write-Host "  Switch to any app, hold [Right Ctrl], speak, release."
Write-Host "  Text appears at your cursor instantly."
Write-Host ""
