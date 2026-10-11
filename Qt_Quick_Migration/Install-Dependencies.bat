@echo off
setlocal
cd /d "%~dp0"
title Install YouTube Toolkit Qt Quick Dependencies
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Dependencies.ps1"
set "RESULT=%ERRORLEVEL%"
if /I not "%~1"=="/nopause" (
    echo.
    if "%RESULT%"=="0" (
        echo Dependencies are ready. Run Build-Prototype-EXE.bat to build the standalone EXE.
    ) else (
        echo Dependency installation failed. Read the error above.
    )
    pause
)
exit /b %RESULT%
