@echo off
title DreamLab OctoBot — Server
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

:: Open browser after a short delay
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:7860"

:: Launch the live viewer in a separate CMD window
start "DreamLab OctoBot — Live Viewer" cmd /k "color 0D & cd /d "D:\VS Code Projects\Octobot" & python viewer.py"

:: Run the server in this window (keeps it open)
python main.py

pause
