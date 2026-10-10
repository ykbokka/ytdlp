@echo off
setlocal
title YTM Music Toolkit — One-File EXE Builder
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build-EXE.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" (
  echo Build failed. Copy the error above before closing this window.
) else (
  echo Build finished. Check the dist folder for YTM Music Toolkit.exe.
)
pause
exit /b %RESULT%
