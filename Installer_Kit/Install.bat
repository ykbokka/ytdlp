@echo off
setlocal
title YTM Music Toolkit Installer
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" (
    echo Installer exited with code %RESULT%.
    echo If an error was reported, copy the message before closing this window.
) else (
    echo Installer finished.
)
echo.
pause
exit /b %RESULT%
