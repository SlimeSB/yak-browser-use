@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ============================================
echo   Learning Browser-Use - 一键安装
echo ============================================
echo.

where uv > nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [错误] 未找到 uv，请先安装 uv（https://docs.astral.sh/uv/）
    echo        或运行: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    pause
    exit /b 1
)

echo [1/3] 安装 Python 依赖...
uv sync
if %ERRORLEVEL% neq 0 (
    echo Python 依赖安装失败
    pause
    exit /b 1
)
echo 已完成

echo [2/3] 安装 Playwright Chromium...
uv run playwright install chromium
if %ERRORLEVEL% neq 0 (
    echo Playwright 安装失败，隔离浏览器模式可能不可用
)

echo [3/3] 安装 Electron 前端依赖...
cd /d "%~dp0electron"
call npm install
if %ERRORLEVEL% neq 0 (
    echo npm 安装失败
    pause
    exit /b 1
)
echo 已完成

echo.
echo ============================================
echo   安装完成！
echo.
echo  启动 CLI: python __main__.py --help
echo  启动 Electron: cd electron ^&^& npm run electron:dev
echo  或直接双击 run.bat
echo ============================================
pause
