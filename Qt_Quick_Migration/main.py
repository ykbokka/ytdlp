from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine


class UiBridge(QObject):
    """Small Python/QML bridge; real downloader services are not attached yet."""

    statusChanged = Signal(str)

    @Slot(str, str)
    def previewAction(self, url: str, quality: str) -> None:
        url = (url or "").strip()
        if not url:
            self.statusChanged.emit("Enter a YouTube URL to preview the UI action.")
            return
        self.statusChanged.emit(
            f"UI bridge works — requested {quality} for {url}. Downloader integration is the next phase."
        )

    @Slot(str)
    def reportStatus(self, message: str) -> None:
        self.statusChanged.emit(message)


def main() -> int:
    app = QGuiApplication(sys.argv)
    app.setApplicationName("YouTube Toolkit — Qt Quick Preview")
    app.setOrganizationName("YouTube Toolkit")

    engine = QQmlApplicationEngine()
    bridge = UiBridge()
    engine.rootContext().setContextProperty("bridge", bridge)

    qml_file = Path(__file__).resolve().parent / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not engine.rootObjects():
        print(f"Could not load Qt Quick UI: {qml_file}", file=sys.stderr)
        return 1

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
