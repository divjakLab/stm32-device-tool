"""Logs tab: live log with filter/pause/save, send line with history, command library."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QSplitter, QVBoxLayout, QWidget)

from .. import config
from ..core.commands import Command, History, fill, placeholders
from ..core.logbuffer import LogStore, make_marker, matches
from ..core.storage import Settings
from .command_panel import CommandPanel, PlaceholderDialog
from .log_view import LogView


class _HistoryKeys(QObject):
    def __init__(self, edit: QLineEdit, history: History) -> None:
        super().__init__(edit)
        self._edit, self._history = edit, history

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Up:
                text = self._history.previous()
                if text is not None:
                    self._edit.setText(text)
                return True
            if event.key() == Qt.Key.Key_Down:
                self._edit.setText(self._history.next())
                return True
        return False


class LogsTab(QWidget):
    sendRequested = Signal(bytes)
    baudChanged = Signal(int)

    def __init__(self, settings: Settings, support_dir: Path) -> None:
        super().__init__()
        self._settings = settings
        self._history_path = support_dir / "history.json"
        self.history = History.load(self._history_path)
        self.store = LogStore()
        self._query = ""
        self._paused = False
        self._pending = 0

        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter…")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._on_filter)
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setCheckable(True)
        self.pause_btn.toggled.connect(self._on_pause)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear)
        save_btn = QPushButton("Save…")
        save_btn.clicked.connect(self._save)
        self.baud_box = QComboBox()
        for b in config.BAUD_RATES:
            self.baud_box.addItem(f"{b} baud", b)
        saved = settings.get("baud", config.DEFAULT_BAUD)
        self.baud_box.setCurrentIndex(max(0, list(config.BAUD_RATES).index(saved)
                                          if saved in config.BAUD_RATES else 2))
        self.baud_box.currentIndexChanged.connect(self._on_baud)
        self.cmd_toggle = QPushButton("Commands ▸")
        self.cmd_toggle.setCheckable(True)
        self.cmd_toggle.setChecked(settings.get("commands_visible", True))

        bar = QHBoxLayout()
        bar.addWidget(self.filter, 1)
        for w in (self.pause_btn, clear_btn, save_btn, self.baud_box, self.cmd_toggle):
            bar.addWidget(w)

        self.view = LogView()
        self.commands = CommandPanel(support_dir / "commands.json", settings)
        self.commands.commandPicked.connect(self._use_command)
        self.commands.setVisible(self.cmd_toggle.isChecked())
        self.cmd_toggle.toggled.connect(self._toggle_commands)
        split = QSplitter()
        split.addWidget(self.view)
        split.addWidget(self.commands)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Send to device…  (↑/↓ history)")
        self.input.returnPressed.connect(self._send_input)
        self.input.installEventFilter(_HistoryKeys(self.input, self.history))
        self.ending = QComboBox()
        self.ending.addItems(list(config.LINE_ENDINGS))
        self.ending.setCurrentText(settings.get("line_ending", config.DEFAULT_LINE_ENDING))
        self.ending.currentTextChanged.connect(lambda t: settings.set("line_ending", t))
        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self._send_input)
        send_row = QHBoxLayout()
        send_row.addWidget(self.input, 1)
        send_row.addWidget(QLabel("Line end"))
        send_row.addWidget(self.ending)
        send_row.addWidget(send_btn)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 12)
        lay.addLayout(bar)
        lay.addWidget(split, 1)
        lay.addLayout(send_row)

    @property
    def baud(self) -> int:
        return int(self.baud_box.currentData())

    # -- incoming lines ----------------------------------------------------------

    def add_lines(self, lines: list) -> None:
        self.store.extend(lines)
        visible = [l for l in lines if matches(l, self._query)]
        if not visible:
            return
        if self._paused:
            self._pending += len(visible)
            self.pause_btn.setText(f"Resume ({self._pending} new)")
            return
        self.view.append_lines(visible)

    def add_marker(self, text: str) -> None:
        self.add_lines([make_marker(text, time.time())])

    def _rebuild(self) -> None:
        self.view.reset()
        self.view.append_lines(self.store.filtered(self._query))

    # -- toolbar -------------------------------------------------------------------

    def _on_filter(self, text: str) -> None:
        self._query = text
        self._rebuild()

    def _on_pause(self, paused: bool) -> None:
        self._paused = paused
        if not paused:
            self._pending = 0
            self.pause_btn.setText("Pause")
            self._rebuild()

    def _clear(self) -> None:
        self.store.clear()
        self.view.reset()

    def _save(self) -> None:
        name = datetime.now().strftime("device-log_%Y-%m-%d_%H-%M-%S.txt")
        folder = self._settings.get("last_log_folder") or str(Path.home() / "Desktop")
        path, _ = QFileDialog.getSaveFileName(self, "Save log", str(Path(folder) / name),
                                              "Text (*.txt)")
        if not path:
            return
        try:
            self.store.save(Path(path))
            self._settings.set("last_log_folder", str(Path(path).parent))
        except OSError as exc:
            QMessageBox.warning(self, "Save log", f"Could not save the log:\n{exc}")

    def _on_baud(self) -> None:
        self._settings.set("baud", self.baud)
        self.baudChanged.emit(self.baud)

    def _toggle_commands(self, visible: bool) -> None:
        self.commands.setVisible(visible)
        self.cmd_toggle.setText("Commands ▸" if visible else "Commands ◂")
        self._settings.set("commands_visible", visible)

    # -- sending -------------------------------------------------------------------

    def _send_text(self, text: str) -> None:
        ending = config.LINE_ENDINGS[self.ending.currentText()]
        if not text and not ending:
            return
        self.sendRequested.emit((text + ending).encode("utf-8"))
        self.history.add(text)
        self.history.save(self._history_path)

    def _send_input(self) -> None:
        self._send_text(self.input.text())
        self.input.clear()

    def _use_command(self, cmd: Command, send_now: bool) -> None:
        if not send_now:
            self.input.setText(cmd.text)
            self.input.setFocus()
            return
        text = cmd.text
        if placeholders(text):
            remembered = self._settings.get("placeholder_values", {})
            dlg = PlaceholderDialog(self, cmd, remembered)
            if not dlg.exec():
                return
            values = dlg.values()
            self._settings.set("placeholder_values", {**remembered, **values})
            text = fill(text, values)
        self._send_text(text)
