@echo off
title DreamLab OctoBot - Server
color 0D
cd /d "D:\VS Code Projects\Octobot"

echo.
echo   ____  _                  _          _
echo  ^|  _ \^| ^|_ ___ __ _ _ __ ^| ^|     __ ^| ^|__
echo  ^| ^| ^| ^| __/ _ / _` ^| '_ \^| ^|    / _` ^| '_ \
echo  ^| ^|_^| ^| ^|^|  __/ (_^| ^| ^| ^| ^| ^|___^| (_^| ^| ^|_) ^|
echo  ^|____/ \__\___\__,_^|_^| ^|_^|______\__,_^|_.__/
echo                   OctoBot
echo.
echo  Starting server on http://localhost:7860 ...
echo.

:: Open loading screen immediately
start "" "%cd%\loading.html"

:: Launch the progress monitor
start "DreamLab OctoBot - Progress Monitor" python progress_monitor.py

:: Launch the live viewer in a separate CMD window
start "DreamLab OctoBot - Live Viewer" cmd /k "color 0D & cd /d "D:\VS Code Projects\Octobot" & python viewer.py"

:: Run the server in this window (keeps it open)
python main.py

pause
