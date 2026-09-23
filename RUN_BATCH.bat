@echo off
setlocal
:: 自动循环拆解 — 持续跑直到全部完成（双击启动，可直接关窗，下次自动继续）
:: 2026-09-23 去本地化：解释器与脚本一律按本文件所在目录解析，不再写死 G:\tools\audio\audio_separator
cd /d "%~dp0"
set "PY="
if exist "%~dp0venv\Scripts\python.exe" set "PY=%~dp0venv\Scripts\python.exe"
if not defined PY for /f "delims=" %%P in ('where python 2^>nul') do if not defined PY set "PY=%%P"
if not defined PY (
  echo [错误] 未找到 Python：请先运行 bootstrap.bat 建立本仓 venv，或把 python 加入 PATH。
  pause
  exit /b 1
)
title Radio Music Separator — 自动拆解中...
echo [启动] %PY%
"%PY%" "%~dp0run_until_done.py" --batch 20 --cool-down 10
pause