# YTM Music Toolkit — One-File EXE Build Kit

This kit builds a **single Windows GUI executable** from the released `YTM_Music_Toolkit.pyw`. The output is `dist\YTM Music Toolkit.exe`.

## What the build bundles

- Python runtime and Python package dependencies via PyInstaller.
- `yt-dlp.exe`.
- Deno, used by yt-dlp for YouTube JavaScript challenge solving.
- FFmpeg and FFprobe, used for media merging and processing.

The resulting EXE is designed not to require the end user to separately install Python, Deno, yt-dlp, or FFmpeg. It still requires internet access for online services and may need the user's own cookies for account-specific features. Cookies and personal media are never downloaded or embedded by this builder.

## Build

1. Download the repository ZIP and extract it.
2. Keep the `EXE_Build_Kit` folder together.
3. Run `Build.bat`.
4. Let the builder download the app source and required external binaries, then install build dependencies.
5. Find the result at `EXE_Build_Kit\dist\YTM Music Toolkit.exe`.

The build machine needs a supported Python 3.10–3.14 installation and internet access. The script prefers an existing Python runtime; it does not silently install Python.

## Important

- This is a **one-file** PyInstaller build. On launch, bundled files are extracted to a temporary runtime directory; that is normal.
- The EXE may be large because it contains the media tools and JavaScript runtime.
- YouTube's EJS challenge components may still be fetched by yt-dlp at runtime, so internet access is still required.
- Windows Defender or other antivirus software may scrutinize unsigned PyInstaller executables. Do not distribute the build until you have tested it.
- This script has not been validated by a completed Windows build yet. Run it, test downloads, playlist handling, metadata, cover art, and media merging before releasing the EXE.
- The FFmpeg package is sourced from Gyan's Windows builds. Review the applicable FFmpeg/build licensing terms before redistributing a compiled EXE.
- Your config file (`%USERPROFILE%\.ytm_music_toolkit.json`), failure logs (`%USERPROFILE%\Documents\YTDLP\`), cookies, and downloaded media are outside the EXE and are not removed by the build.

## Files

- `Build.bat` — double-click entry point.
- `Build-EXE.ps1` — downloads build assets and invokes PyInstaller using the spec file.
- `YTM_Music_Toolkit.spec` — defines the one-file EXE, collected Python packages, and bundled media executables.
- `requirements-build.txt` — Python build dependencies.
