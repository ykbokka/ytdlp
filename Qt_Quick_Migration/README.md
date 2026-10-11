# YouTube Toolkit — Qt Quick migration branch

This is the **future-interface test build** for migrating from CustomTkinter to **PySide6 + Qt Quick/QML**. The production app on `main` is unchanged.

## Easiest way to test on Windows

1. Open the [draft pull request](https://github.com/ykbokka/ytdlp/pull/7).
2. Use **Code → Download ZIP** for the `qt-quick-migration` branch, then extract it. Alternatively, clone the repository and check out that branch.
3. Open the extracted `Qt_Quick_Migration` folder.
4. Double-click `Run-Prototype.bat`. The first run creates a separate `.venv`, installs its dependencies, runs a QML smoke test, and then starts the new interface. It does not replace the existing app or modify the old source.

Keep the current EXE/source you saved. For the first download test, use a temporary output folder and a nonessential public video. Bulk tag operations modify the selected files.

## Included in this migration build

- Qt Quick/QML interface with animated navigation/page entrances, animated dark/light palette, hover/press feedback, and progress display.
- A Python worker pool so yt-dlp extraction, downloads, and media operations don't intentionally run on the GUI thread.
- Single-video downloads, height-ceiling format selection, MKV/MP4 video modes, audio-only FLAC/MP3/M4A/Opus options, optional subtitles, a cookie-file path, configurable output folder, performance presets, and existing-file policies.
- Playlist expansion and sequential queue, persistent pending queue entries, per-item status, pause/resume via process suspension, stop/cancel, and queue removal/clear.
- An MKV path that downloads the video-only stream, selects a highest-quality audio stream per language, converts each selected stream to a FLAC file, then muxes them into one MKV with language-labelled audio tracks and an optional cover attachment.
- Read/write common media tags; a YouTube Music metadata lookup using artist/title/album text; artwork embedding in FLAC/MP3/M4A and selected video containers; square image cropping; a folder scan with optional title rewrite and album-artist tag removal.
- Settings stored alongside the same user config file used by the existing app, so unrelated existing preferences are preserved.

## Important limitations

This is a working migration foundation, **not yet a feature-for-feature replacement**. The specialised resolver and edge cases in the existing app need regression testing against the old source. This branch's YT Music lookup is a new simplified match rather than a verified port of every old matching rule. Liked Music authentication workflows, full queue history, all legacy post-processing rules, and exact feature parity are not yet confirmed.

The FLAC tracks are created by converting the best available source audio stream. FLAC is a lossless *container/codec*, but converting a lossy YouTube stream to FLAC cannot restore information already lost in the source.

The QML interface, multistream mux path, artwork embedding, and EXE packaging still need real Windows runtime tests. A passing QML smoke test only proves that Python syntax/QML loading succeeds; it doesn't prove every download format works across all sources.

## Files

- `main.py`: Qt Quick launcher and Python-to-QML connection.
- `qml/Main.qml`: entire visible interface, layouts, and animations.
- `backend.py`: asynchronous download, queue, metadata, artwork, crop, and library operations.
- `requirements.txt`: isolated dependencies.
- `Run-Prototype.bat`: one-click Windows setup and launcher.
- `smoke_test.py`: offscreen QML loading check.

## Next migration stages

1. Run the smoke test and inspect the actual interface on Windows.
2. Compare core download/metadata/cover/crop flows to the saved current version; fix behavioral differences.
3. Port the remaining old-app behaviours and test multi-audio merging, cancellation, cookies, subtitles, and existing-file handling with real media.
4. Adapt the PyInstaller build kit to include QML assets, Qt plugins, Python dependencies, yt-dlp, FFmpeg, Deno, and aria2c.
5. Only then consider replacing the current EXE.
