# Qt Quick UI Migration Prototype

This directory is an isolated prototype for migrating YouTube Toolkit's interface from CustomTkinter to **PySide6 + Qt Quick/QML**. It intentionally does not replace or modify the existing application entry point or downloader engine.

## Why this exists

Qt Quick provides built-in declarative transitions and animations. The UI can animate opacity, position, scale, color, state changes, and coordinated sequences in QML while Python continues to own application logic and media processing.

## Run the prototype

Use Python 3.12+ in a fresh virtual environment and install the dependency:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r Qt_Quick_Migration\requirements.txt
.\.venv\Scripts\python.exe Qt_Quick_Migration\main.py
```

If your existing source environment uses a different Python version, use a version supported by the PySide6 wheel available for that interpreter. Keep this prototype's environment separate from the current app while we validate compatibility.

## Current scope

- Animated Qt Quick/QML navigation shell with six sections matching the current app's main areas.
- Dark/light palette changes using Qt Quick property animations.
- Animated page entrance, navigation selection, hover/press feedback, and a responsive layout.
- Python/QML bridge with a **demo-only** action so we can test event wiring before connecting real downloader functions.

## Not wired yet

The downloader, queue, metadata, cover art, crop tools, configuration, cookie status, and media pipeline are **not connected** to this prototype yet. Existing production code remains unchanged on `main`. The next phase is to map the current app's Python operations behind a small backend/service API, then connect the QML controls without blocking the GUI thread.

## Migration plan

1. Validate startup, QML loading, visual behavior, and resizing on Windows.
2. Profile animation smoothness and confirm the actual renderer/frame pacing rather than assuming a framework switch guarantees performance.
3. Extract backend operations from the old GUI into UI-independent services.
4. Port one feature at a time and compare behavior against the existing app.
5. Update the PyInstaller build kit only after the prototype and backend integration are stable.

**Do not use this preview as the production downloader.** It is an isolated UI prototype, not a complete port.
