"""Flash tab: choose a .hex, flash it, see progress."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
                               QPushButton, QVBoxLayout, QWidget)

from ..core.hexfile import HexFileError, load_hex
from ..core.storage import Settings
from . import style


class FlashTab(QWidget):
    flashRequested = Signal(str)

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        self._path: Optional[str] = None
        self._board = False
        self._busy = False
        self._detail = ""

        title = QLabel("<h2>Firmware</h2>")
        self.file_label = QLabel("No file selected")
        self.file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.info_label = QLabel("Choose a .hex file or drag it onto this window.")
        self.info_label.setWordWrap(True)
        choose = QPushButton("Choose…")
        choose.clicked.connect(self._choose)
        self.flash_btn = QPushButton("Flash")
        self.flash_btn.setDefault(True)
        self.flash_btn.setMinimumWidth(140)
        self.flash_btn.clicked.connect(self._flash)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.stage_label = QLabel("")
        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.details_btn = QPushButton("Details…")
        self.details_btn.setVisible(False)
        self.details_btn.clicked.connect(self._show_details)

        buttons = QHBoxLayout()
        buttons.addWidget(choose)
        buttons.addStretch()
        buttons.addWidget(self.flash_btn)
        result = QHBoxLayout()
        result.addWidget(self.result_label, 1)
        result.addWidget(self.details_btn)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 16, 24, 24)
        for w in (title, self.file_label, self.info_label):
            lay.addWidget(w)
        lay.addSpacing(12)
        lay.addLayout(buttons)
        lay.addSpacing(12)
        lay.addWidget(self.progress)
        lay.addWidget(self.stage_label)
        lay.addLayout(result)
        lay.addStretch()

        last = settings.get("last_hex")
        if last and Path(last).is_file():
            self.set_file(last)
        self._update()

    @property
    def hex_path(self) -> Optional[str]:
        return self._path

    @property
    def busy(self) -> bool:
        return self._busy

    def set_file(self, path: str) -> bool:
        if self._busy:
            return False
        path = str(Path(path).expanduser().resolve())
        try:
            _, info = load_hex(path)
        except HexFileError as exc:
            self._path = None
            self.file_label.setText(f"<b>{Path(path).name}</b>")
            self.info_label.setText(f'<span style="color:{style.colors()["error"]}">'
                                    f'{str(exc).splitlines()[0]}</span>')
            self._update()
            return False
        self._path = str(info.path)
        mtime = datetime.fromtimestamp(info.path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        self.file_label.setText(f"<b>{info.path.name}</b>")
        self.info_label.setText(f"{info.size:,} bytes · 0x{info.start:08X}–0x{info.end - 1:08X}"
                                f" · modified {mtime}<br><small>{info.path.parent}</small>")
        self._settings.set("last_hex", self._path)
        self._settings.set("last_folder", str(info.path.parent))
        self.result_label.setText("")
        self.details_btn.setVisible(False)
        self._update()
        return True

    def set_board_available(self, available: bool) -> None:
        self._board = available
        self._update()

    def _update(self) -> None:
        self.flash_btn.setEnabled(self._board and self._path is not None and not self._busy)
        if not self._board and not self._busy:
            self.stage_label.setText("Connect the board to flash.")
        elif not self._busy and self.stage_label.text() == "Connect the board to flash.":
            self.stage_label.setText("")

    def _choose(self) -> None:
        if self._busy:
            return
        folder = self._settings.get("last_folder") or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Choose firmware", folder,
                                              "Intel HEX (*.hex);;All files (*)")
        if path:
            self.set_file(path)

    def _flash(self) -> None:
        if self._path is None:
            return
        self._busy = True
        self.progress.setValue(0)
        self.result_label.setText("")
        self.details_btn.setVisible(False)
        self._update()
        self.flashRequested.emit(self._path)

    def on_progress(self, stage: str, fraction: float) -> None:
        self.progress.setValue(int(fraction * 1000))
        text = {"Programming": "Programming… do not unplug the board."}.get(stage, f"{stage}…")
        self.stage_label.setText(text if stage != "Done" else "")

    def on_finished(self, ok: bool, message: str, detail: str) -> None:
        self._busy = False
        self._detail = detail
        c = style.colors()
        color = c["ok"] if ok else c["error"]
        mark = "✓" if ok else "✕"
        self.result_label.setText(f'<span style="color:{color}"><b>{mark}</b> '
                                  f'{message.replace(chr(10), "<br>")}</span>')
        self.details_btn.setVisible(bool(detail))
        if ok:
            self.progress.setValue(1000)
        self.stage_label.setText("")
        self._update()

    def _show_details(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Details")
        box.setText(self.result_label.text())
        box.setDetailedText(self._detail)
        box.exec()
