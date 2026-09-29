"""Generates resources/icon.png, icon.ico (Windows) and icon.icns (macOS only)."""

import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 1024
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#1f2a44"))
    p.drawRoundedRect(QRectF(100 * s, 100 * s, 824 * s, 824 * s), 180 * s, 180 * s)
    p.setBrush(QColor("#c9d1d9"))
    for i in range(5):
        o = (322 + i * 85) * s
        for rect in ((o, 190 * s, 40 * s, 110 * s), (o, 724 * s, 40 * s, 110 * s),
                     (190 * s, o, 110 * s, 40 * s), (724 * s, o, 110 * s, 40 * s)):
            p.drawRoundedRect(QRectF(*rect), 8 * s, 8 * s)
    p.setBrush(QColor("#2f6fed"))
    p.drawRoundedRect(QRectF(290 * s, 290 * s, 444 * s, 444 * s), 50 * s, 50 * s)
    p.setPen(QPen(QColor("#ffffff"), 34 * s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(390 * s, 390 * s, 70 * s, 70 * s))
    p.end()
    return img


def png_bytes(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def write_ico(path: Path, pngs: dict) -> None:
    """ICO file with PNG-compressed entries (supported since Windows Vista)."""
    sizes = sorted(pngs)
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries, blobs = b"", b""
    for size in sizes:
        data = pngs[size]
        dim = 0 if size >= 256 else size          # 0 means 256 in the ICO format
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    Path(path).write_bytes(header + entries + blobs)


def main() -> int:
    QGuiApplication(sys.argv)
    res = ROOT / "resources"
    draw(512).save(str(res / "icon.png"))
    write_ico(res / "icon.ico", {s: png_bytes(draw(s)) for s in (16, 24, 32, 48, 64, 128, 256)})
    print("wrote", res / "icon.png", res / "icon.ico")
    if sys.platform != "darwin":
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "icon.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            draw(size).save(str(iconset / f"icon_{size}x{size}.png"))
            draw(size * 2).save(str(iconset / f"icon_{size}x{size}@2x.png"))
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(res / "icon.icns")],
                       check=True)
    print("wrote", res / "icon.icns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
