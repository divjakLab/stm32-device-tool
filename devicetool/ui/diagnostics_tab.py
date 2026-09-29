"""Diagnostics tab: status, reset reason, crash report, .elf symbols."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QFileDialog, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
                               QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from .. import config
from ..core.fault import FaultSnapshot, format_report
from ..core.probe import BoardInfo, Health
from ..core.reset_reason import describe_reset
from ..core.storage import Settings
from ..core.symbols import Symbolizer
from . import style

_STATES = {
    "running": ("ok", "Running"),
    "sleeping": ("ok", "Running (CPU sleeping)"),
    "halted": ("busy", "Halted by a debugger"),
    "faulted": ("error", "Crashed"),
    "lockup": ("error", "Crashed (CPU locked up)"),
    "no_response": ("busy", "Not responding (held in reset?)"),
}


class DiagnosticsTab(QWidget):
    resetRequested = Signal()
    checkRequested = Signal()
    crashStateChanged = Signal(bool)

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        self._board: Optional[BoardInfo] = None
        self._snapshot: Optional[FaultSnapshot] = None
        self._symbols: Optional[Symbolizer] = None
        self._hex: Optional[str] = None
        self._crashed = False
        self._chip_reset = "—"
        self._fw_reset = "—"

        self.status = QLabel()
        self.checked = QLabel()
        self.chip_reset = QLabel("—")
        self.fw_reset = QLabel("—")
        self.symbols_label = QLabel("Symbols: none (load the .elf for function names)")
        grid = QGridLayout()
        grid.addWidget(QLabel("<b>Status</b>"), 0, 0)
        grid.addWidget(self.status, 0, 1)
        grid.addWidget(self.checked, 0, 2)
        grid.addWidget(QLabel("<b>Last reset (chip)</b>"), 1, 0)
        grid.addWidget(self.chip_reset, 1, 1, 1, 2)
        grid.addWidget(QLabel("<b>Last reset (reported by firmware)</b>"), 2, 0)
        grid.addWidget(self.fw_reset, 2, 1, 1, 2)
        grid.setColumnStretch(2, 1)

        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        self.report.setFont(style.mono_font())
        self.report.setPlaceholderText("No crash detected.")

        def btn(text, slot):
            b = QPushButton(text)
            b.clicked.connect(slot)
            return b

        row = QHBoxLayout()
        row.addWidget(btn("Load .elf…", self._load_elf))
        row.addWidget(self.symbols_label, 1)
        row.addWidget(btn("Copy report", self._copy))
        row.addWidget(btn("Save report…", self._save))
        row.addWidget(btn("Reset board", self.resetRequested.emit))
        row.addWidget(btn("Check now", self.checkRequested.emit))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 16)
        lay.addLayout(grid)
        lay.addSpacing(8)
        lay.addWidget(QLabel("<b>Crash report</b>"))
        lay.addWidget(self.report, 1)
        lay.addLayout(row)
        self.on_disconnected()

    # -- inputs from the workers -------------------------------------------------

    def set_board(self, info: BoardInfo) -> None:
        self._board = info

    def _set_status(self, kind: str, text: str) -> None:
        self.status.setText(f"{style.dot(style.colors()[kind])} <b>{text}</b>")

    def on_health(self, h: Health) -> None:
        kind, text = _STATES.get(h.state, ("idle", h.state))
        self._set_status(kind, text)
        self.checked.setText(f"<small>checked {datetime.now():%H:%M:%S}</small>")
        if self._crashed and not h.faulted and h.state != "no_response":
            self.clear_crash()

    def on_crash(self, snap: FaultSnapshot) -> None:
        self._snapshot = snap
        self._crashed = True
        self._render()
        self.crashStateChanged.emit(True)

    def clear_crash(self) -> None:
        if self._crashed:
            self._crashed = False
            self._render()
            self.crashStateChanged.emit(False)

    def on_disconnected(self) -> None:
        self._set_status("idle", "No board")
        self.checked.setText("")

    def on_reset_flags(self, csr: int) -> None:
        self._chip_reset = describe_reset(csr)
        self.chip_reset.setText(self._chip_reset)

    def set_firmware_reset(self, csr: int) -> None:
        self._fw_reset = f"{describe_reset(csr)}  (RCC->CSR = 0x{csr:08X}, " \
                         f"at {datetime.now():%H:%M:%S})"
        self.fw_reset.setText(self._fw_reset)

    def set_hex(self, path: str) -> None:
        self._hex = path
        elf = self._settings.get("elf_for_hex", {}).get(path)
        if elf and Path(elf).is_file():
            self._use_elf(elf, quiet=True)

    # -- report ------------------------------------------------------------------

    def _render(self) -> None:
        if self._snapshot is None:
            self.report.setPlainText("")
            return
        text = format_report(self._snapshot,
                             self._symbols.describe if self._symbols else None)
        if not self._crashed:
            text = "PREVIOUS CRASH (the device has restarted since)\n\n" + text
        self.report.setPlainText(text)

    def report_text(self) -> str:
        board = f"{config.TARGET_DISPLAY_NAME} · {self._board.device}" if self._board else "—"
        head = [f"{config.APP_NAME} {config.APP_VERSION} — {datetime.now():%Y-%m-%d %H:%M:%S}",
                f"Board: {board}",
                f"Firmware file: {self._hex or '—'}",
                f"Symbols: {self._symbols.path if self._symbols else 'none'}",
                f"Last reset (chip): {self._chip_reset}",
                f"Last reset (firmware): {self._fw_reset}", ""]
        return "\n".join(head) + (self.report.toPlainText() or "No crash detected.")

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.report_text())

    def _save(self) -> None:
        name = datetime.now().strftime("crash-report_%Y-%m-%d_%H-%M-%S.txt")
        path, _ = QFileDialog.getSaveFileName(self, "Save report",
                                              str(Path.home() / "Desktop" / name), "Text (*.txt)")
        if path:
            try:
                Path(path).write_text(self.report_text(), encoding="utf-8")
            except OSError as exc:
                QMessageBox.warning(self, "Save report", str(exc))

    def _load_elf(self) -> None:
        start = str(Path(self._hex).parent) if self._hex else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Load .elf", start, "ELF (*.elf *.axf *.out);;All files (*)")
        if path:
            self._use_elf(path, quiet=False)

    def _use_elf(self, path: str, quiet: bool) -> None:
        try:
            self._symbols = Symbolizer(Path(path))
        except ValueError as exc:
            if not quiet:
                QMessageBox.warning(self, "Load .elf", str(exc))
            return
        self.symbols_label.setText(f"Symbols: {Path(path).name}")
        if self._hex:
            mapping = dict(self._settings.get("elf_for_hex", {}))
            mapping[self._hex] = path
            self._settings.set("elf_for_hex", mapping)
        self._render()
