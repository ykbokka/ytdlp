@echo off
setlocal
title YTM Music Toolkit Uninstaller
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Uninstall.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %RESULT%
