"""Fast colored log view (one text block per line, capped)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit

from .. import config
from ..core.logbuffer import Level, LogLine, format_ts
from . import style


class LogView(QPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setMaximumBlockCount(config.MAX_LOG_LINES)
        self.setFont(style.mono_font())
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setUndoRedoEnabled(False)
        self._empty = True
        self._formats = {}
        self._build_formats()

    def _build_formats(self) -> None:
        c = style.colors()

        def fmt(color=None, italic=False):
            f = QTextCharFormat()
            if color:
                f.setForeground(QColor(color))
            f.setFontItalic(italic)
            return f

        self._formats = {Level.NORMAL: fmt(), Level.WARN: fmt(c["warn"]),
                         Level.ERROR: fmt(c["error"]), Level.MARKER: fmt(c["marker"], True),
                         "ts": fmt(c["ts"])}

    @property
    def auto_scroll(self) -> bool:
        bar = self.verticalScrollBar()
        return bar.value() >= bar.maximum() - 4

    def reset(self) -> None:
        self.clear()
        self._empty = True

    def append_lines(self, lines: list[LogLine]) -> None:
        if not lines:
            return
        stick = self.auto_scroll
        cur = QTextCursor(self.document())
        cur.movePosition(QTextCursor.MoveOperation.End)
        cur.beginEditBlock()
        for line in lines:
            if not self._empty:
                cur.insertBlock()
            self._empty = False
            cur.insertText(format_ts(line.ts) + "  ", self._formats["ts"])
            cur.insertText(line.text, self._formats[line.level])
        cur.endEditBlock()
        if stick:
            bar = self.verticalScrollBar()
            bar.setValue(bar.maximum())
