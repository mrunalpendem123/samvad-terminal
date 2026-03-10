# Samvad Windows installer
# Usage: iwr -useb https://raw.githubusercontent.com/mrunalpendem123/samvad-terminal/main/install.ps1 | iex

$ErrorActionPreference = "Stop"

# ── Helpers ──────────────────────────────────────────────────────────────────
function Write-Pass  { param($msg) Write-Host "  " -NoNewline; Write-Host "OK" -ForegroundColor Green -NoNewline; Write-Host "  $msg" }
function Write-Step  { param($n, $total, $msg) Write-Host "  [$n/$total] " -NoNewline -ForegroundColor White; Write-Host $msg -ForegroundColor DarkGray }
function Write-Info  { param($msg) Write-Host "  ->  $msg" -ForegroundColor DarkCyan }

# ── Fix execution policy ────────────────────────────────────────────────────
$policy = Get-ExecutionPolicy -Scope CurrentUser
if ($policy -notin @("Unrestricted", "RemoteSigned", "Bypass")) {
    Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
}

$INSTALL_DIR = "$env:USERPROFILE\.samvad"
$REPO_RAW    = "https://raw.githubusercontent.com/mrunalpendem123/samvad-terminal/main"

# ── Banner ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  +========================================+" -ForegroundColor Cyan
Write-Host "  |                                        |" -ForegroundColor Cyan
Write-Host "  |       o  S A M V A D                   |" -ForegroundColor Cyan
Write-Host "  |       Voice -> Text for Windows        |" -ForegroundColor Cyan
Write-Host "  |                                        |" -ForegroundColor Cyan
Write-Host "  +========================================+" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Installing to ~\.samvad" -ForegroundColor DarkGray
Write-Host ""

# ── Step 1: Download ────────────────────────────────────────────────────────
Write-Step 1 5 "Downloading core files..."
New-Item -ItemType Directory -Force -Path $INSTALL_DIR | Out-Null
Invoke-WebRequest "$REPO_RAW/samvad-core.py" -OutFile "$INSTALL_DIR\samvad-core.py"
Invoke-WebRequest "$REPO_RAW/samvad-ui.py"   -OutFile "$INSTALL_DIR\samvad-ui.py"
Invoke-WebRequest "$REPO_RAW/daemon.bat"     -OutFile "$INSTALL_DIR\samvad.bat"
Write-Pass "Downloaded samvad-core, samvad-ui, daemon"

# ── Step 2: API key ─────────────────────────────────────────────────────────
Write-Step 2 5 "Configuring API key..."
$envFile = "$INSTALL_DIR\.env"
if ($env:SARVAM_API_KEY) {
    [System.IO.File]::WriteAllText($envFile, "SARVAM_API_KEY=$($env:SARVAM_API_KEY)`n")
    Write-Pass "API key written to ~\.samvad\.env"
} elseif (Test-Path $envFile) {
    Write-Pass "Existing ~\.samvad\.env preserved"
} else {
    [System.IO.File]::WriteAllText($envFile, "# Get your key at https://www.sarvam.ai`nSARVAM_API_KEY=`n")
    Write-Info "No API key found - edit ~\.samvad\.env with your SARVAM_API_KEY"
}

# ── Step 3: Python runtime ──────────────────────────────────────────────────
Write-Step 3 5 "Checking Python runtime (uv)..."
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Pass "uv already installed"
} else {
    Write-Info "Installing uv (fast Python manager)..."
    & powershell -ExecutionPolicy Bypass -NoProfile -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:PATH = "$env:USERPROFILE\.local\bin;$env:USERPROFILE\.cargo\bin;$env:PATH"
    Write-Pass "uv installed"
}

# ── Step 4: Add to PATH ─────────────────────────────────────────────────────
Write-Step 4 5 "Adding samvad to PATH..."
$UserPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($UserPath -notlike "*$INSTALL_DIR*") {
    [Environment]::SetEnvironmentVariable("PATH", "$UserPath;$INSTALL_DIR", "User")
    Write-Pass "Added to PATH (restart terminal to take effect)"
} else {
    Write-Pass "Already in PATH"
}

# ── Step 5: Verify ──────────────────────────────────────────────────────────
Write-Step 5 5 "Verifying installation..."
if (Test-Path "$INSTALL_DIR\samvad-core.py") {
    Write-Pass "All files in place"
} else {
    Write-Host "  X  Installation may be incomplete" -ForegroundColor Red
}

# ── Done ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ========================================" -ForegroundColor Green
Write-Host "    Installation complete!" -ForegroundColor Green
Write-Host "  ========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Get started:" -ForegroundColor White
Write-Host ""
Write-Host "    Open a NEW terminal and run:" -ForegroundColor DarkGray
Write-Host "    > samvad" -ForegroundColor Cyan
Write-Host ""
Write-Host "  First run on Windows:" -ForegroundColor White
Write-Host "    Windows may ask for input-monitoring permissions." -ForegroundColor DarkGray
Write-Host "    Allow access when prompted." -ForegroundColor DarkGray
Write-Host ""
Write-Host "  How it works:" -ForegroundColor White
Write-Host "    Switch to any app -> hold [Right Ctrl] -> speak -> release" -ForegroundColor DarkGray
Write-Host "    Text appears at your cursor instantly." -ForegroundColor DarkGray
Write-Host ""
