from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def render_icon(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"SVG app icon was not found: {source}")

    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        raise RuntimeError(f"Could not parse SVG app icon: {source}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(1024, 1024, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()

    with tempfile.TemporaryDirectory(prefix="ytm_icon_") as temporary:
        png_path = Path(temporary) / "app_icon.png"
        if not image.save(str(png_path), "PNG"):
            raise RuntimeError("Qt could not render the SVG app icon to PNG.")
        with Image.open(png_path) as rendered:
            rgba = rendered.convert("RGBA")
            rgba.save(
                destination,
                format="ICO",
                sizes=[
                    (16, 16),
                    (24, 24),
                    (32, 32),
                    (48, 48),
                    (64, 64),
                    (128, 128),
                    (256, 256),
                ],
            )

    if not destination.is_file() or destination.stat().st_size < 1024:
        raise RuntimeError(f"ICO output is missing or unexpectedly small: {destination}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Windows ICO from the toolkit's SVG artwork.")
    parser.add_argument("source", type=Path, help="Source SVG icon")
    parser.add_argument("destination", type=Path, help="Output ICO path")
    args = parser.parse_args()
    render_icon(args.source.resolve(), args.destination.resolve())
    print(f"App icon generated: {args.destination.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
