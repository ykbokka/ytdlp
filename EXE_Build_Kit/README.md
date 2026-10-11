# YTM Music Toolkit — One-File EXE Build Kit

This kit builds a **single-file Windows GUI executable** at `dist\\YTM Music Toolkit.exe`. The intended end-user machine does not need Python, pip, Deno, yt-dlp, FFmpeg, or FFprobe installed separately.

## What the EXE bundles

- The Python interpreter/runtime and the application source.
- The Python standard-library modules required by the application.
- Third-party packages, their collected package data, native extensions, and hidden imports.
- Explicit `ytmusicapi` locale files required by gettext translations.
- `yt-dlp.exe`, including the EJS scripts shipped in the official standalone build.
- Deno, the JavaScript runtime used by yt-dlp.
- FFmpeg and FFprobe for media processing.

The spec intentionally fails the build if required helper executables or the expected `ytmusicapi` locale directory are missing.

## Build

1. Download the repository ZIP and extract it.
2. Run `EXE_Build_Kit\\Build.bat`.
3. Wait for the builder to download its build-time assets and create the isolated build environment.
4. Find the result at `EXE_Build_Kit\\dist\\YTM Music Toolkit.exe`.

The **build machine** needs a supported Python 3.10–3.14 installation and internet access. That is only for compiling the EXE; the **end-user machine** does not need Python installed.

## What "standalone" means — and what it cannot mean

The application is packaged to run on a fresh, supported Windows 11 installation without separately installing its software dependencies. The EXE still needs:

- Internet access for YouTube / YouTube Music and other online services.
- A valid user session or authentication when a feature accesses account-specific content such as Liked Music. A Windows reset removes browser sessions and local authentication files; the EXE cannot recreate or preserve those credentials.
- Normal Windows facilities and permissions, including access to a writable temporary directory and a destination for downloads.

User-specific settings, authentication files, downloads, and failure logs are intentionally kept outside the EXE. They are created or supplied at runtime and are not build dependencies. Do not embed personal cookies or account credentials in a distributable EXE.

## One-file behavior

PyInstaller extracts bundled files into a temporary runtime directory when the EXE starts. That is normal and does not mean the user needs to install those components. The EXE may be large because it contains the Python runtime, libraries, and media tools.

## Validation before release

A successful build alone does not prove portability. Test the resulting EXE on a clean Windows 11 VM or another Windows installation without Python, Deno, yt-dlp, or FFmpeg installed. Verify launch, YouTube Music Liked Music access after authentication, a download, metadata, cover art, and media merging. Also check that no dependency is accidentally being loaded from the build folder or system PATH.

The script has not itself run a clean-machine validation. Do not call the build fully verified until that test passes.

## Licensing and security

- The FFmpeg package is sourced from Gyan's Windows builds. Review applicable licensing terms before redistribution.
- yt-dlp, Deno, Python, and bundled libraries have their own licensing terms.
- Windows Defender or other antivirus software may scrutinize unsigned PyInstaller executables. Test the output before distributing it.

## Files

- `Build.bat` — double-click entry point.
- `Build-EXE.ps1` — downloads build assets and invokes PyInstaller.
- `YTM_Music_Toolkit.spec` — defines the one-file executable and collected resources.
- `requirements-build.txt` — dependencies used only to build the EXE.
