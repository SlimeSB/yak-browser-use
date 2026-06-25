@echo off
chcp 65001 > nul
cd /d "%~dp0electron"
:: Electron 会自动启动 Python 后端 (uv run python __main__.py serve)
npm start
