from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from backend import ToolkitBackend, write_failure_log


def main() -> int:
    app = QGuiApplication(sys.argv)
    app.setApplicationName("YouTube Toolkit")
    app.setOrganizationName("YouTube Toolkit")

    engine = QQmlApplicationEngine()
    backend = ToolkitBackend()
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("bridge", backend)

    qml_file = Path(__file__).resolve().parent / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not engine.rootObjects():
        message = f"Could not load the Qt Quick interface: {qml_file}"
        log_path = write_failure_log("qt_qml_startup", RuntimeError(message))
        if log_path:
            message += f"\\n\\nDiagnostic log: {log_path}"
        print(message, file=sys.stderr)
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, message, "YouTube Toolkit — Startup Error", 0x10)
            except Exception:
                pass
        return 1

    app.aboutToQuit.connect(backend.stopDownload)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
