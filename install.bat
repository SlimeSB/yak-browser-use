@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ============================================
echo   Learning Browser-Use - Setup
echo ============================================
echo.

where uv > nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] uv not found. Install it first: https://docs.astral.sh/uv/
    echo        Or run: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    pause
    exit /b 1
)

echo [1/3] Installing Python dependencies...
uv sync
if %ERRORLEVEL% neq 0 (
    echo Python dependency installation failed
    pause
    exit /b 1
)
echo Done

echo [2/3] Installing Playwright Chromium...
uv run playwright install chromium
if %ERRORLEVEL% neq 0 (
    echo Playwright installation failed. Isolated browser mode may be unavailable.
)

echo [3/3] Installing Electron frontend dependencies...
cd /d "%~dp0electron"
call npm install
if %ERRORLEVEL% neq 0 (
    echo npm install failed
    pause
    exit /b 1
)
echo Done

echo.
echo ============================================
echo   Setup complete!
echo.
echo  Run CLI: python __main__.py --help
echo  Run Electron: cd electron ^&^& npm run electron:dev
echo  Or double-click run.bat
echo ============================================
pause
