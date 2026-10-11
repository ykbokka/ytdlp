# YTM Music Toolkit — One-File EXE Build Kit

This kit builds a **single-file Windows GUI executable** at `EXE_Build_Kit\dist\YTM Music Toolkit.exe`. The target PC should not need Python, pip, Deno, yt-dlp, FFmpeg, or FFprobe installed separately.

## Two-step build workflow

### Step 1 — Download and prepare everything

Double-click `Download-Requirements.bat`.

It downloads the app source and helper tools, creates an isolated 64-bit Python build environment, installs the build/runtime Python packages, runs startup/import checks, and writes a build manifest containing the tool/package versions and SHA-256 hashes of the main build inputs. Large downloads suppress Windows PowerShell's expensive per-transfer progress redraws, report measured MiB/s after each file, and use longer timeouts with retries. pip's own progress bar is disabled to reduce console overhead, and compatible wheels are preferred.

The build PC must be 64-bit Windows with 64-bit Python 3.11–3.14 and internet access. The current build workspace stores the exact tools and Python environment prepared for that build. Run preparation again only when refreshing the source/tools or recreating the build environment.

### Step 2 — Assemble the EXE

Double-click `Build.bat`.

This step only validates the prepared files and runs PyInstaller. It does not download anything, install packages, or create a virtual environment. It runs offline preflight checks, confirms the helper tools launch, checks Python imports and package consistency, performs a clean PyInstaller assembly, and prints the final EXE size and SHA-256 hash.

The output is `EXE_Build_Kit\dist\YTM Music Toolkit.exe`. If a requirement is missing or broken, the builder stops instead of accidentally treating an older EXE as a successful new build.

Keep the `build_workspace` folder intact between preparation and assembly.

## Optional GitHub Actions build

The repository also includes a manually triggered Windows x64 build workflow at `.github/workflows/build-exe.yml`. In GitHub, open Actions, select **Build YTM Music Toolkit EXE**, then choose **Run workflow**. If the run succeeds, it uploads the EXE and build manifest as an artifact for 14 days. This workflow is manual-only; ordinary commits do not automatically start a CI build.

## What the EXE is configured to bundle

- The Python interpreter/runtime and the application.
- Standard-library functionality required by the app; PyInstaller's Windows hooks handle Tcl/Tk resources for the GUI.
- Third-party packages and collected submodules, package data, native extensions, and package metadata.
- psutil, which is used by the download pause/resume feature.
- The CustomTkinter theme resources and its companion packages.
- ytmusicapi's locale files at the package-relative path expected by gettext.
- The certifi root CA bundle used for HTTPS requests.
- yt-dlp, Deno, FFmpeg, FFprobe, and aria2c as bundled helper executables in the one-file payload.
- aria2's GPL license text, copied into the EXE payload under the `licenses` folder.

The official yt-dlp standalone executable includes its EJS challenge-solver scripts; those do not need to be installed separately. See the [official yt-dlp EJS guide](https://github.com/yt-dlp/yt-dlp/wiki/ejs).

### Download-speed strategy

The downloader's **Performance** selector now tunes the whole transfer strategy rather than only the fragment count. Conservative uses 4 aria2 connections / 4 native fragments, Balanced uses 8 / 12, and Aggressive uses 16 / 24. Aggressive is the default for new installs, and older installs whose saved setting is Balanced are migrated to Aggressive once. After this update, any manually selected preset is saved and preserved.

When aria2c is present, direct HTTP/HTTPS media downloads use the bundled executable with the selected connection count, split into byte ranges (1 MiB pieces in Aggressive mode), and skip slow file preallocation on Windows. The yt-dlp adaptive read buffer also scales from 1 MiB to 4 MiB. If aria2c is absent when running the source directly, the app falls back to yt-dlp's chunked HTTP option (5 MiB / 10 MiB / 16 MiB by preset).

DASH and HLS/M3U8 manifest downloads are deliberately kept on yt-dlp's native downloader for compatibility. If yt-dlp reports an aria2c-specific failure, the app retries that stage once with the native downloader. These settings can improve throughput when the server and connection support parallel/range downloads, but no client-side setting can exceed the source server's limits, and excessive parallelism can sometimes trigger throttling; use Conservative or Balanced if Aggressive performs worse on a particular connection.

The spec intentionally fails if required helper executables, ytmusicapi locale data, or the certificate bundle are missing.

## What standalone means

The target PC should not need a separate Python, Deno, yt-dlp, FFmpeg, FFprobe, or aria2c installation. PyInstaller extracts its embedded one-file payload into a temporary runtime directory when the EXE launches; that is normal and does not mean the user must install the bundled parts.

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
- aria2 is GPL-2.0. The build includes its license text; review the corresponding-source and redistribution requirements before distributing the EXE. The upstream source is available at [aria2 on GitHub](https://github.com/aria2/aria2/tree/release-1.37.0).
- yt-dlp, Deno, Python, and the bundled Python libraries have their own license terms.
- Unsigned PyInstaller executables may be flagged for inspection by Windows Defender or other antivirus software. Test the output before distributing it.

## Files

- `Download-Requirements.bat` — one-click download/setup and validation of build requirements.
- `Download-Requirements.ps1` — downloads tools, prepares the build virtual environment, smoke-tests dependencies, and records a manifest.
- `Build.bat` — one-click entry point for assembling the EXE only.
- `Build-EXE.ps1` — offline preflight checks and PyInstaller assembly.
- `YTM_Music_Toolkit.spec` — high-coverage package/data/native-binary collection rules, including aria2c and its license.
- `requirements-build.txt` — packages needed by the build environment and runtime collection.
