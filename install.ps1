# Samvad Windows installer
# Usage: iwr -useb https://raw.githubusercontent.com/mrunalpendem123/samvad-terminal/main/install.ps1 | iex

$ErrorActionPreference = "Stop"

# ── Fix execution policy so uv installer can run ──────────────────────────────
$policy = Get-ExecutionPolicy -Scope CurrentUser
if ($policy -notin @("Unrestricted", "RemoteSigned", "Bypass")) {
    Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
}

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
$k = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String("c2tfYjRua2I3dmxfMEJHa0MwNXpqMGJ1b1VYRUJLNmN5MGhr"))
[System.IO.File]::WriteAllText("$INSTALL_DIR\.env", "SARVAM_API_KEY=$k`n")

# ── Ensure uv is installed ────────────────────────────────────────────────────
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "-> Installing uv (Python manager)..."
    & powershell -ExecutionPolicy Bypass -NoProfile -c "irm https://astral.sh/uv/install.ps1 | iex"
    # Refresh PATH for this session so uv is found immediately
    $env:PATH = "$env:USERPROFILE\.local\bin;$env:USERPROFILE\.cargo\bin;$env:PATH"
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
