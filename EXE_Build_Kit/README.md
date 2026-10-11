# YTM Music Toolkit — One-File EXE Build Kit

This kit builds a **single-file Windows GUI executable** at `EXE_Build_Kit\dist\YTM Music Toolkit.exe`. The target PC should not need Python, pip, Deno, yt-dlp, FFmpeg, or FFprobe installed separately.

## Two-step build workflow

### Step 1 — Download and prepare everything

Double-click `Download-Requirements.bat`.

It downloads the app source and helper tools, creates an isolated 64-bit Python build environment, installs the build/runtime Python packages, runs startup/import checks, and writes a build manifest containing the tool/package versions and SHA-256 hashes of the main build inputs.

The build PC must be 64-bit Windows with 64-bit Python 3.11–3.14 and internet access. The current build workspace stores the exact tools and Python environment prepared for that build. Run preparation again only when refreshing the source/tools or recreating the build environment.

### Step 2 — Assemble the EXE

Double-click `Build.bat`.

This step only validates the prepared files and runs PyInstaller. It does not download anything, install packages, or create a virtual environment. It runs offline preflight checks, confirms the helper tools launch, checks Python imports and package consistency, performs a clean PyInstaller assembly, and prints the final EXE size and SHA-256 hash.

The output is `EXE_Build_Kit\dist\YTM Music Toolkit.exe`. If a requirement is missing or broken, the builder stops instead of accidentally treating an older EXE as a successful new build.

Keep the `build_workspace` folder intact between preparation and assembly.

## What the EXE is configured to bundle

- The Python interpreter/runtime and the application.
- Standard-library functionality required by the app; PyInstaller's Windows hooks handle Tcl/Tk resources for the GUI.
- Third-party packages and collected submodules, package data, native extensions, and package metadata.
- psutil, which is used by the download pause/resume feature.
- The CustomTkinter theme resources and its companion packages.
- ytmusicapi's locale files at the package-relative path expected by gettext.
- The certifi root CA bundle used for HTTPS requests.
- yt-dlp, Deno, FFmpeg, and FFprobe as bundled helper executables in the one-file payload.

The official yt-dlp standalone executable includes its EJS challenge-solver scripts; those do not need to be installed separately. See the [official yt-dlp EJS guide](https://github.com/yt-dlp/yt-dlp/wiki/ejs).

The spec intentionally fails if required helper executables, ytmusicapi locale data, or the certificate bundle are missing.

## What standalone means

The target PC should not need a separate Python, Deno, yt-dlp, FFmpeg, or FFprobe installation. PyInstaller extracts its embedded one-file payload into a temporary runtime directory when the EXE launches; that is normal and does not mean the user must install the bundled parts.

The app still needs:
- Internet access for YouTube / YouTube Music and other online services.
- A valid user session or authentication for account-specific features such as Liked Music. A Windows reset removes local browser sessions and user authentication files, so the EXE cannot recreate those credentials.
- Normal Windows permissions and a writable temporary directory and download destination.

Personal settings, authentication files, downloads, and failure logs intentionally remain outside the EXE. Never embed personal cookies or account credentials in a public distributable.

## Stability and verification

A successful build and preflight checks are useful, but they **do not prove** the EXE works on every clean Windows installation. Test it in a clean Windows 11 VM or another Windows installation without Python, Deno, yt-dlp, or FFmpeg installed. Verify first launch, authenticated Liked Music access, downloads, metadata, cover art, and media merging. Also verify that the app does not accidentally load dependencies from the build folder or system PATH.

The project has not yet been validated on a clean Windows machine as part of these scripts. Do not call it fully verified until that test passes.

## Licensing and security

- FFmpeg is sourced from Gyan's Windows builds. Review the applicable license terms before redistributing the EXE.
- yt-dlp, Deno, Python, and the bundled Python libraries have their own license terms.
- Unsigned PyInstaller executables may be flagged for inspection by Windows Defender or other antivirus software. Test the output before distributing it.

## Files

- `Download-Requirements.bat` — one-click download/setup and validation of build requirements.
- `Download-Requirements.ps1` — downloads tools, prepares the build virtual environment, smoke-tests dependencies, and records a manifest.
- `Build.bat` — one-click entry point for assembling the EXE only.
- `Build-EXE.ps1` — offline preflight checks and PyInstaller assembly.
- `YTM_Music_Toolkit.spec` — high-coverage package/data/native-binary collection rules.
- `requirements-build.txt` — packages needed by the build environment and runtime collection.
