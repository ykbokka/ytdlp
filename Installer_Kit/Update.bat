@echo off
setlocal
title YTM Music Toolkit Updater
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Update.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" echo Update failed with exit code %RESULT%.
pause
exit /b %RESULT%
