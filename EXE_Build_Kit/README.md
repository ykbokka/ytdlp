# YTM Music Toolkit — One-File EXE Build Kit

This kit builds a **single-file Windows GUI executable** at `dist\YTM Music Toolkit.exe`. The intended end-user machine does not need Python, pip, Deno, yt-dlp, FFmpeg, or FFprobe installed separately.

## Two-step build workflow

### Step 1 — Download and prepare everything

Double-click `Download-Requirements.bat`.

It downloads the app source, yt-dlp, Deno, FFmpeg/FFprobe, creates the isolated build virtual environment, and installs the Python build dependencies listed in `requirements-build.txt`. It also checks that the files needed for building are present.

Run this again only when you want to refresh the downloaded source/tools or prepare a new build environment. It needs internet access and a supported Python 3.10–3.14 installation on the build PC.

### Step 2 — Assemble the EXE

Double-click `Build.bat`.

This step **only invokes PyInstaller using the already-prepared files**. It does not download the source, download media tools, create a virtual environment, or install Python packages. If something is missing, it stops and tells you to run `Download-Requirements.bat` first.

The finished file is placed at `EXE_Build_Kit\dist\YTM Music Toolkit.exe`.

Keep the `build_workspace` folder intact between preparation and assembly.

## What the EXE bundles

- The Python interpreter/runtime and the application source.
- The Python standard-library modules required by the application.
- Third-party packages, their collected package data, native extensions, and hidden imports.
- Explicit `ytmusicapi` locale files required by gettext translations.
- `yt-dlp.exe`, including the EJS scripts shipped in the official standalone build.
- Deno, the JavaScript runtime used by yt-dlp.
- FFmpeg and FFprobe for media processing.

The spec intentionally fails the build if required helper executables or the expected `ytmusicapi` locale directory are missing.

## Build-machine vs. end-user requirements

The **build machine** needs internet access and Python 3.10–3.14 to prepare and compile the EXE. The **end-user machine** does not need Python installed separately.

The application still needs:
- Internet access for YouTube / YouTube Music and other online services.
- A valid user session or authentication when a feature accesses account-specific content such as Liked Music. A Windows reset removes browser sessions and local authentication files; the EXE cannot recreate or preserve those credentials.
- Normal Windows facilities and permissions, including access to a writable temporary directory and a destination for downloads.

User-specific settings, authentication files, downloads, and failure logs are intentionally kept outside the EXE. Do not embed personal cookies or account credentials in a distributable EXE.

## One-file behavior

PyInstaller extracts bundled files into a temporary runtime directory when the EXE starts. That is normal and does not mean the user needs to install those components. The EXE may be large because it contains the Python runtime, libraries, and media tools.

## Validation before release

A successful build alone does not prove portability. Test the resulting EXE on a clean Windows 11 VM or another Windows installation without Python, Deno, yt-dlp, or FFmpeg installed. Verify launch, YouTube Music Liked Music access after authentication, a download, metadata, cover art, and media merging. Also check that no dependency is accidentally being loaded from the build folder or system PATH.

The scripts have not themselves run a clean-machine validation. Do not call the build fully verified until that test passes.

## Licensing and security

- The FFmpeg package is sourced from Gyan's Windows builds. Review applicable licensing terms before redistribution.
- yt-dlp, Deno, Python, and bundled libraries have their own licensing terms.
- Windows Defender or other antivirus software may scrutinize unsigned PyInstaller executables. Test the output before distributing it.

## Files

- `Download-Requirements.bat` — one-click download and setup of all build requirements.
- `Download-Requirements.ps1` — downloads tools, prepares the build virtual environment, and installs dependencies.
- `Build.bat` — one-click entry point for assembling the EXE only.
- `Build-EXE.ps1` — runs PyInstaller using the prepared files only.
- `YTM_Music_Toolkit.spec` — defines the one-file executable and collected resources.
- `requirements-build.txt` — dependencies used only to build the EXE.
