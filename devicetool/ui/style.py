"""Shared colors and fonts; adapts to macOS light/dark mode."""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QPalette


def is_dark() -> bool:
    app = QGuiApplication.instance()
    return bool(app) and app.palette().color(QPalette.ColorRole.Window).lightness() < 128


def colors() -> dict:
    if is_dark():
        return {"error": "#ff6b6b", "warn": "#e5c07b", "marker": "#8b949e", "ts": "#6e7681",
                "ok": "#3fb950", "busy": "#d29922", "idle": "#8b949e"}
    return {"error": "#cf222e", "warn": "#9a6700", "marker": "#6e7781", "ts": "#8c959f",
            "ok": "#1a7f37", "busy": "#bc4c00", "idle": "#6e7781"}


def dot(color: str) -> str:
    return f'<span style="color:{color}">●</span>'


def mono_font() -> QFont:
    f = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    f.setPointSize(12)
    return f
