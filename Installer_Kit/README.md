# YTM Music Toolkit — Windows Installer Kit

A dedicated installer for the **released, working `YTM_Music_Toolkit.pyw`** in this repository. It installs the Python dependencies and the external tools needed by the raw `.pyw` app, creates Start Menu/Desktop shortcuts, and keeps the app's own config and selected cookie path in the current Windows user profile.

> This kit installs and launches the raw Python app. It does **not** build an EXE and does not use or modify a PyInstaller `.spec` file.

## What the installer does

- Downloads the current released `YTM_Music_Toolkit.pyw` from this repository's `main` branch.
- Creates an isolated Python virtual environment inside the app folder.
- Installs the app's Python dependencies, including `yt-dlp` and `ytmusicapi`.
- Checks for Python, Deno, and FFmpeg. If a required tool is missing, it asks before using WinGet to install it.
- Creates Start Menu and Desktop shortcuts.
- Adds local `venv\Scripts`, `tools`, and WinGet's executable-link directory to the launcher's PATH.
- Keeps cookies, configuration, and downloaded media out of the repository and installer kit.

## Requirements

- Windows 10/11 x64.
- Internet access during installation and when using online services.
- WinGet if Python, Deno, or FFmpeg needs to be installed automatically.
- A signed-in YouTube/YouTube Music browser session and a fresh Netscape-format `cookies.txt` file when using features that require account authentication. The app asks you to select your own file; **the installer never downloads, requests, or uploads your cookies**.

## Install

1. Download this repository as a ZIP, or open the `Installer_Kit` folder on GitHub.
2. Keep the whole `Installer_Kit` folder together.
3. Right-click `Install.bat` and choose **Run as administrator only if Windows asks for it**. Normally, installation is per-user and does not require administrator rights.
4. Read the PowerShell prompts. The installer asks before installing missing WinGet packages.
5. When installation finishes, launch **YTM Music Toolkit** from the Desktop or Start Menu shortcut.

If Windows blocks scripts, launch `Install.bat` normally first; it invokes the included PowerShell script with a process-scoped execution-policy bypass. This does not change the system execution policy.

## Update

Run `Update.bat` from the same kit. It replaces the installed app source with the current `main` version and updates Python packages in the app's virtual environment. Your user config and selected cookie-file path are stored separately and are not removed.

## Uninstall

Run `Uninstall.bat`. It removes the installed program folder and the shortcuts created by this kit. It deliberately leaves these user data items alone:

- `%USERPROFILE%\.ytm_music_toolkit.json`
- `%USERPROFILE%\Documents\YTDLP\` (failure logs)
- Your cookies file and downloaded media

Delete those separately yourself if you no longer need them.

## Troubleshooting

- **Python not found:** the installer checks for an already-installed Python 3.14, 3.13, 3.12, 3.11, or 3.10 before offering to install Python 3.12 through WinGet. If you just installed Python, close the installer window and run `Install.bat` again.
- **Deno / JavaScript challenge errors:** make sure Deno is installed, then close and relaunch the toolkit. The launcher adds WinGet's standard executable-link directory to PATH.
- **FFmpeg not found:** install FFmpeg using WinGet, then rerun the installer. The app needs FFmpeg for operations such as merging separate audio/video streams and conversions.
- **Cookies/authentication:** choose a fresh Netscape-format cookies file from the app's Browse button. Never share or commit cookies; they can grant access to your account.
- **Failure logs:** the app writes logs under `%USERPROFILE%\Documents\YTDLP\`. Inspect them before changing settings.

## Files

- `Install.bat` / `Install.ps1` — first-time setup.
- `Update.bat` / `Update.ps1` — refresh app source and dependencies.
- `Uninstall.bat` / `Uninstall.ps1` — remove installed program and shortcuts.
- `Launch.bat` — launch the installed raw `.pyw`.
- `requirements.txt` — Python runtime dependencies.

This kit is intentionally separate from the application source. It does not change the released `.pyw`, the repository's packaging spec, or the user's download/configuration data.
