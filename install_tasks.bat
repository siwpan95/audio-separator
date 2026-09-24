@echo off
setlocal
:: 2026-09-23 去本地化：解释器与脚本按 %~dp0 解析（原路径已失效）
cd /d "%~dp0"
set "PY="
if exist "%~dp0venv\Scripts\python.exe" set "PY=%~dp0venv\Scripts\python.exe"
if not defined PY for /f "delims=" %%P in ('where python 2^>nul') do if not defined PY set "PY=%%P"
if not defined PY (
  echo [错误] 未找到 Python：请先运行 bootstrap.bat 建立本仓 venv，或把 python 加入 PATH。
  pause
  exit /b 1
)
title Register RadioMusicSeparator scheduled tasks
echo Registering scheduled tasks...
echo.
echo [1/2] RadioMusicSeparator  (on startup, loops until ALL_DONE)
schtasks /create /tn "RadioMusicSeparator" /tr "\"%PY%\" \"%~dp0run_until_done.py\" --batch 20 --cool-down 10" /sc onstart /rl highest /f
echo [2/2] RadioMusicSeparator_Hourly  (every 2 hours, fallback)
schtasks /create /tn "RadioMusicSeparator_Hourly" /tr "\"%PY%\" \"%~dp0run_until_done.py\" --batch 20 --cool-down 10" /sc hourly /mo 2 /rl highest /f
echo.
echo Done. Tasks registered.
echo run_until_done.py loops until all songs separated, then writes ALL_DONE.txt and exits.
echo To start now, run: schtasks /run /tn "RadioMusicSeparator"
echo To uninstall, run remove_tasks.bat
pause