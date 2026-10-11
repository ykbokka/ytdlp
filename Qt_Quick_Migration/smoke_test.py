from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from backend import ToolkitBackend


def main() -> int:
    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    backend = ToolkitBackend()
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("bridge", backend)
    warnings: list[str] = []
    engine.warnings.connect(lambda entries: warnings.extend(str(entry.toString()) for entry in entries))

    qml_file = Path(__file__).resolve().parent / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))
    app.processEvents()

    if not engine.rootObjects():
        print(f"FAIL: QML did not load: {qml_file}", file=sys.stderr)
        return 1
    if warnings:
        print("QML warnings/errors:")
        for warning in warnings:
            print(warning, file=sys.stderr)
        return 2
    print("PASS: Python syntax and Qt Quick QML load succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
