# YouTube Toolkit — Qt Quick migration branch

This is the **future-interface test build** for migrating YouTube Toolkit from CustomTkinter to **PySide6 + Qt Quick/QML**. The existing `YTM_Music_Toolkit.pyw` entry point and downloader implementation remain unchanged. All new UI/backend work is isolated under `Qt_Quick_Migration/` until feature parity is demonstrated.

## Test the new app on Windows

1. Open the [Qt Quick migration branch](https://github.com/ykbokka/ytdlp/tree/qt-quick-migration/Qt_Quick_Migration).
2. Download the repository ZIP from the branch dropdown, then extract it.
3. Open `Qt_Quick_Migration`.
4. Double-click `Run-Prototype.bat`. The first run creates a separate `.venv`, installs dependencies, runs Python syntax/QML-load checks, and launches the new UI.

This keeps the saved current version and its Python environment separate. You do not need to install Qt or manually manage QML files outside the extracted folder. If startup fails, copy the console error before editing anything.

The GitHub Actions smoke test has successfully loaded the QML interface offscreen and compiled the Python modules. This is a syntax/startup check, **not proof that every UI flow or media format has passed end-to-end testing**.

## Build a self-contained Windows EXE

1. Double-click `Install-Dependencies.bat` in this folder. It creates/uses the isolated `.venv`, installs Python and PyInstaller packages, and downloads helper tools into `build_assets\`.
2. Double-click `Build-Prototype-EXE.bat`. It checks the prerequisites, runs Python/backend/QML smoke tests, and builds the one-file app.
3. Find the result at `dist\YouTube Toolkit Qt Preview.exe`.

The EXE bundles the Python runtime, Python packages, Qt/QML UI, backend and YouTube Music resolver modules, `yt-dlp.exe`, `ffmpeg.exe`, `ffprobe.exe`, `deno.exe`, `aria2c.exe`, and helper DLLs. The EXE should not require a separate Python installation or separate copies of these tools on the target PC.

The first install/build needs internet and can download several large files. Already-valid tool downloads are reused later. The build targets 64-bit Windows. Personal cookies and user settings intentionally remain outside the EXE; cookie files are private credentials, not application dependencies. The build does not overwrite the existing production EXE.

## Included in this migration build

- An animated Qt Quick/QML interface: navigation/page transitions, dark/light theme animations, hover/press feedback, progress, eight sections, and a separate Activity log.
- A Python worker pool for yt-dlp extraction, downloads, and file operations so those jobs do not intentionally block QML's GUI thread.
- Single video downloads, quality ceilings, MKV/MP4 options, audio-only FLAC/MP3/M4A/Opus, optional subtitles, cookie-file support, the existing performance presets, and rename/skip/replace policies.
- Playlist expansion into a sequential queue, persistent queue entries, per-item states, queue remove/clear, pause/resume, cancellation, and `tempytm` workspace cleanup after items / queue completion.
- The specialist MKV path: video-only stream plus the best available separate audio rendition per exposed language, converted to FLAC, then muxed as named/language-tagged tracks with an optional attached cover.
- Core YouTube Music matching policy: songs results first, exact contributing-artist match, title/album scoring, then the YouTube Music videos fallback. Matching metadata/artwork is accepted only when it belongs to the exact source video ID; mismatched search results never replace a user-supplied playlist item.
- Authenticated Liked Music enumeration via a temporary ytmusicapi auth file derived from the selected Netscape cookies, with a yt-dlp cookie fallback if ytmusicapi cannot enumerate the shelf. No cookie values are logged or embedded in the app.
- Common tag read/write, YT Music metadata lookup, batch FLAC metadata + artwork rewrite, batch cover upgrades, artwork embedding, square image cropping, and a library scan/apply workflow.
- Reuse of `~/.ytm_music_toolkit.json`, including the existing folder paths, cookie-file path, appearance/performance settings, and the new saved download options. Personal cookies remain external to the EXE.

## Known limits — don't skip this

This is a substantial migration foundation, **not yet a feature-for-feature replacement**. It still needs comparison against the saved current build for edge cases in playlist/queue behavior, every audio/container format, pause/stop timing, unusual metadata tags, and full YT Music account workflows. The original code has years of special cases; they should only be removed after equivalent behavior is tested, not just because the new interface loads.

FLAC is a lossless *container/codec*, but converting a lossy source stream to FLAC cannot restore audio information that was already lost upstream.

Use a temporary output folder and disposable test media first. Batch tag changes modify the selected files. The UI has been smoke-tested for QML loading, but the actual Windows UI, multistream muxing, cover embedding, Liked Music authentication, and standalone EXE still need end-to-end tests.

## Files

- `main.py`: Qt Quick launcher and Python/QML bridge.
- `qml/Main.qml`: interface, layouts, controls, and animations.
- `backend.py`: asynchronous downloader, queue, settings, metadata, artwork, crop, and library operations.
- `ytmusic_resolver.py`: exact contributing-artist search and authenticated Liked Music resolver.
- `requirements.txt` / `requirements-build.txt`: prototype and packaging dependencies.
- `Run-Prototype.bat`: one-click Python setup, QML smoke test, and launch.
- `Install-Dependencies.bat` / `Install-Dependencies.ps1`: install packaging dependencies and download helper tools.
- `Build-Prototype-EXE.bat` / `Build-Prototype-EXE.ps1`: test and build the self-contained one-file EXE.
- `smoke_test.py`: headless QML-load check.

## Next migration stages

1. Run the prototype on Windows and check visual responsiveness/resizing.
2. Test a single public download, subtitles, each audio output option, and the multiaudio MKV path.
3. Test queue and playlist flows, cancellation/cleanup, cookies, Liked Music, metadata matching, cover binding, and batch tools against the saved current app.
4. Fix behavioral differences, then build and test a standalone EXE.
5. Only after feature parity and real Windows testing should the Qt Quick version replace the current production EXE.
