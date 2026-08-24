@echo off
title Unregister RadioMusicSeparator scheduled tasks
echo Removing scheduled tasks...
echo.
echo [1/2] delete RadioMusicSeparator
schtasks /delete /tn "RadioMusicSeparator" /f
echo [2/2] delete RadioMusicSeparator_Hourly
schtasks /delete /tn "RadioMusicSeparator_Hourly" /f
echo.
echo Done. Tasks removed.
pause
