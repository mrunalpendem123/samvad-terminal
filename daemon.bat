@echo off
:: Samvad Daemon — Windows
:: Hold [Right Ctrl] anywhere → speak → release → auto-pastes at cursor
setlocal

set "DIR=%~dp0"

:: ── Load API key from .env (use PowerShell to handle BOM correctly) ──────────
if exist "%DIR%.env" (
    for /f "usebackq delims=" %%A in (`powershell -NoProfile -c "([System.IO.File]::ReadAllLines('%DIR%.env') | Where-Object { $_ -match '^SARVAM_API_KEY=' }) -replace '^SARVAM_API_KEY=','' | Select-Object -First 1"`) do set "SARVAM_API_KEY=%%A"
)

:: ── Ensure uv is installed ─────────────────────────────────────────────────
where uv >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo uv not found -- installing...
    powershell -NoProfile -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
    :: Refresh PATH for this session
    set "PATH=%USERPROFILE%\.cargo\bin;%USERPROFILE%\.local\bin;%PATH%"
)

:: ── Launch ──────────────────────────────────────────────────────────────────
uv run ^
  --python 3.11 ^
  --no-project ^
  --with "textual>=0.70" ^
  --with "textual-plotext>=0.2" ^
  python "%DIR%samvad-ui.py"
