# YouTube Toolkit — Qt Quick migration branch

This is the **future-interface test build** for migrating from CustomTkinter to **PySide6 + Qt Quick/QML**. The current production application on `main` is left untouched.

## Easiest way to test on Windows

1. Open the repository's [draft pull request](https://github.com/ykbokka/ytdlp/pull/7).
2. Use **Code → Download ZIP** on the `qt-quick-migration` branch, then extract it. Alternatively, clone the repo and check out that branch.
3. Open the extracted `Qt_Quick_Migration` folder.
4. Double-click `Run-Prototype.bat`. The first run creates a separate `.venv`, installs the listed dependencies, and launches the Qt Quick UI. It does not touch your current app or its environment.

If the launcher fails, keep the console open and copy the error text. Please do not replace or delete the current app files while testing this branch.

## What works in this migration build

- Qt Quick/QML owns the interface, animated navigation, theme colors, page entrances, hover feedback, and progress display.
- Python operations run through a worker pool rather than being intentionally run on the GUI thread.
- Direct yt-dlp downloads with video quality ceilings, MKV/MP4 output options, audio-only conversion options, optional subtitle downloads, cookie-file support, download directory setting, performance preset, and existing-file policy.
- Playlist/source expansion into a sequential queue, with per-item status, remove/clear controls, and queue stop support.
- Read/write common media metadata, embed supported artwork into FLAC/MP3/M4A audio and attach JPEG artwork to MKV videos, crop a source image to a square JPEG, scan a library, and optionally rewrite titles from filenames/remove album-artist tags.

## Important known scope limits

This is a **real working migration foundation, not yet a feature-for-feature replacement** for the current application. The existing CustomTkinter app includes specialized YT Music metadata matching, multi-language audio-track handling, bespoke lossless video/FLAC workflows, additional queue/download states, and more elaborate post-processing. Those workflows still need to be ported and regression-tested against the existing source before this branch can replace it.

The new downloader currently uses a simpler yt-dlp command path. In particular, choosing FLAC means yt-dlp converts the best available audio stream to FLAC; it does not magically restore quality lost in a lossy source. Do not treat converted FLAC as proof of lossless source audio.

Use test files and a temporary output folder first. Bulk library operations change tags on the files you select. The prototype has not yet been run and validated on every Windows setup, and the EXE builder has not yet been migrated to Qt.

## Files

- `main.py`: Qt Quick launcher and Python-to-QML bridge.
- `qml/Main.qml`: interface, UI animation, navigation, and forms.
- `backend.py`: asynchronous download, queue, tag, artwork, crop, and library operations.
- `requirements.txt`: isolated prototype dependencies.
- `Run-Prototype.bat`: first-run setup and launcher.

## Next migration stages

1. Run the QML load/syntax checks and test on Windows.
2. Compare each operation against the current app and fix behavioral differences.
3. Port the specialized YT Music resolver, multi-audio/FLAC workflow, queue controls and history, and existing settings semantics.
4. Only after feature parity, adapt the PyInstaller build kit so the shipped EXE bundles QML resources, Qt plugins, helper executables, and Python dependencies.
