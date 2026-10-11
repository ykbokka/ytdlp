from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from backend import ToolkitBackend


def main() -> int:
    app = QGuiApplication(sys.argv)
    app.setApplicationName("YouTube Toolkit")
    app.setOrganizationName("YouTube Toolkit")

    engine = QQmlApplicationEngine()
    backend = ToolkitBackend()
    engine.rootContext().setContextProperty("backend", backend)
    # Kept as a compatibility alias for any shared QML helper that still uses it.
    engine.rootContext().setContextProperty("bridge", backend)

    qml_file = Path(__file__).resolve().parent / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not engine.rootObjects():
        print(f"Could not load Qt Quick interface: {qml_file}", file=sys.stderr)
        return 1

    app.aboutToQuit.connect(backend.stopDownload)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
