@echo off
setlocal
cd /d "%~dp0"
title Build YouTube Toolkit Qt Preview EXE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build-Prototype-EXE.ps1"
if errorlevel 1 (
    echo.
    echo Qt Quick EXE build failed. Read the error above.
    pause
    exit /b 1
)
echo.
pause
