@echo off
title DreamLab OctoBot
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

:: Wait 2 seconds then open browser
start "" cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:7860"

:: Run the server (keeps terminal open)
python main.py

pause
