@echo off
setlocal
title YTM Music Toolkit - Download Build Requirements
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Download-Requirements.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" (
  echo Requirement download/setup failed. Copy the error above before closing this window.
) else (
  echo All build requirements are ready. Run Build.bat when you want to assemble the EXE.
)
pause
exit /b %RESULT%
