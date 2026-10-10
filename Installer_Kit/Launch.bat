@echo off
setlocal
set "APP_DIR=%~dp0"
set "PATH=%APP_DIR%venv\Scripts;%APP_DIR%tools;%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
if not exist "%APP_DIR%venv\Scripts\pythonw.exe" (
    echo YTM Music Toolkit is not installed correctly.
    echo Run Install.bat from the Installer_Kit folder.
    pause
    exit /b 1
)
start "" "%APP_DIR%venv\Scripts\pythonw.exe" "%APP_DIR%YTM_Music_Toolkit.pyw"
endlocal
