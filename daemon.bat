@echo off
:: Samvad Daemon — Windows
:: Hold [Right Ctrl] anywhere → speak → release → auto-pastes at cursor
setlocal

set "DIR=%~dp0"

:: ── Load API key from .env ──────────────────────────────────────────────────
if exist "%DIR%.env" (
    for /f "usebackq tokens=1* delims==" %%A in ("%DIR%.env") do (
        if not "%%A"=="" (
            set "FIRST=%%A"
            if not "!FIRST:~0,1!"=="#" set "%%A=%%B"
        )
    )
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
