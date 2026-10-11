@echo off
setlocal
cd /d "%~dp0"
title Build YouTube Toolkit Qt Preview EXE

echo Preparing dependencies and bundled helper tools...
call "%~dp0Install-Dependencies.bat" /nopause
if errorlevel 1 (
    echo.
    echo Dependency preparation failed. Read the error above.
    pause
    exit /b 1
)

echo.
echo Building the self-contained Qt Quick EXE...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build-Prototype-EXE.ps1"
if errorlevel 1 (
    echo.
    echo Qt Quick EXE build failed. Read the error above.
    pause
    exit /b 1
)
echo.
echo The EXE is in the dist folder.
pause
