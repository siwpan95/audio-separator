@echo off
title Register RadioMusicSeparator scheduled tasks
echo Registering scheduled tasks...
echo.
echo [1/2] RadioMusicSeparator  (on startup, loops until ALL_DONE)
schtasks /create /tn "RadioMusicSeparator" /tr "G:\tools\audio\audio_separator\venv\Scripts\python.exe G:\tools\audio\audio_separator\run_until_done.py --batch 20 --cool-down 10" /sc onstart /rl highest /f
echo [2/2] RadioMusicSeparator_Hourly  (every 2 hours, fallback)
schtasks /create /tn "RadioMusicSeparator_Hourly" /tr "G:\tools\audio\audio_separator\venv\Scripts\python.exe G:\tools\audio\audio_separator\run_until_done.py --batch 20 --cool-down 10" /sc hourly /mo 2 /rl highest /f
echo.
echo Done. Tasks registered.
echo run_until_done.py loops until all songs separated, then writes ALL_DONE.txt and exits.
echo To start now, run: schtasks /run /tn "RadioMusicSeparator"
echo To uninstall, run remove_tasks.bat
pause
