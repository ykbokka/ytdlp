@echo off
setlocal
cd /d "%~dp0"
title YouTube Toolkit - Qt Quick Prototype

where py >nul 2>nul
if errorlevel 1 (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python was not found. Install Python 3.11 or newer, then run this file again.
        pause
        exit /b 1
    )
    set "PYTHON=python"
) else (
    set "PYTHON=py"
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating an isolated environment for the Qt Quick prototype...
    %PYTHON% -m venv .venv
    if errorlevel 1 goto :failed
)

echo Installing or validating prototype dependencies...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :failed

echo.
echo Checking Python syntax...
".venv\Scripts\python.exe" -m compileall -q backend.py main.py smoke_test.py
if errorlevel 1 goto :failed

echo Running an offscreen Qt Quick load test...
".venv\Scripts\python.exe" smoke_test.py
if errorlevel 1 goto :failed

echo.
echo Launching the Qt Quick version...
".venv\Scripts\python.exe" main.py
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo The prototype could not start. Copy the error above before changing anything.
pause
exit /b 1
