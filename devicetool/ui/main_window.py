"""Main window: status header + Flash / Logs / Diagnostics tabs. Owns the worker threads."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QMetaObject, Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMainWindow, QMessageBox, QTabWidget,
                               QVBoxLayout, QWidget)

from .. import config
from ..core.probe import BoardInfo
from ..core.reset_reason import parse_firmware_reset_line
from ..core.storage import Settings
from . import style
from .diagnostics_tab import DiagnosticsTab
from .flash_tab import FlashTab
from .logs_tab import LogsTab
from .workers import ProbeWorker, SerialWorker


class MainWindow(QMainWindow):
    _flash = Signal(str)
    _reset = Signal()
    _check = Signal()
    _send = Signal(bytes)
    _baud = Signal(int)
    _serial_probe = Signal(object)
    _marker = Signal(str)

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        self._flashing = ""
        self.setWindowTitle(config.APP_NAME)
        self.setMinimumSize(900, 600)
        self.setAcceptDrops(True)

        self.board_label = QLabel()
        self.serial_label = QLabel()
        header = QHBoxLayout()
        header.setContentsMargins(16, 10, 16, 4)
        header.addWidget(self.board_label)
        header.addStretch()
        header.addWidget(self.serial_label)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.flash_tab = FlashTab(settings)
        self.logs_tab = LogsTab(settings, config.support_dir())
        self.diag_tab = DiagnosticsTab(settings)
        self.tabs.addTab(self.flash_tab, "Flash")
        self.tabs.addTab(self.logs_tab, "Logs")
        self.tabs.addTab(self.diag_tab, "Diagnostics")

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(header)
        lay.addWidget(self.tabs)
        self.setCentralWidget(central)

        self._set_board_text("idle", "No board — connect the ST-LINK USB port (CN1)")
        self.serial_label.setText("")

        self._start_workers()
        self._wire()

        geo = settings.get("geometry")
        if geo:
            self.restoreGeometry(QByteArray.fromBase64(geo.encode()))
        else:
            self.resize(1100, 720)
        if self.flash_tab.hex_path:
            self.diag_tab.set_hex(self.flash_tab.hex_path)

    # -- setup -----------------------------------------------------------------

    def _start_workers(self) -> None:
        self.probe_thread = QThread(self)
        self.probe_worker = ProbeWorker(config.find_pack_file())
        self.probe_worker.moveToThread(self.probe_thread)
        self.probe_thread.started.connect(self.probe_worker.start)

        self.serial_thread = QThread(self)
        self.serial_worker = SerialWorker(config.logs_dir() / "sessions")
        self.serial_worker.moveToThread(self.serial_thread)
        self.serial_thread.started.connect(self.serial_worker.start)

        self.probe_thread.start()
        self.serial_thread.start()

    def _wire(self) -> None:
        pw, sw = self.probe_worker, self.serial_worker
        self._flash.connect(pw.flash)
        self._reset.connect(pw.reset_board)
        self._check.connect(pw.check_now)
        self._send.connect(sw.send)
        self._baud.connect(sw.set_baud)
        self._serial_probe.connect(sw.set_probe)
        self._marker.connect(sw.marker)

        pw.connected.connect(self._on_connected)
        pw.disconnected.connect(self._on_disconnected)
        pw.status.connect(self._on_probe_status)
        pw.health.connect(self.diag_tab.on_health)
        pw.crash.connect(self.diag_tab.on_crash)
        pw.resetFlags.connect(self.diag_tab.on_reset_flags)
        pw.flashProgress.connect(self.flash_tab.on_progress)
        pw.flashFinished.connect(self._on_flash_finished)
        pw.actionFailed.connect(self._on_action_failed)

        sw.lines.connect(self._on_lines)
        sw.status.connect(self._on_serial_status)

        self.flash_tab.flashRequested.connect(self._start_flash)
        self.logs_tab.sendRequested.connect(self._send)
        self.logs_tab.baudChanged.connect(self._baud)
        self.diag_tab.resetRequested.connect(self._reset_board)
        self.diag_tab.checkRequested.connect(self._check)
        self.diag_tab.crashStateChanged.connect(self._on_crash_state)
        self._baud.emit(self.logs_tab.baud)

    # -- header ----------------------------------------------------------------

    def _set_board_text(self, kind: str, text: str) -> None:
        c = style.colors()
        color = {"ok": c["ok"], "busy": c["busy"], "error": c["error"]}.get(kind, c["idle"])
        self.board_label.setText(f"{style.dot(color)} <b>{text}</b>")

    def _on_connected(self, info: BoardInfo) -> None:
        self._set_board_text("ok", f"{config.TARGET_DISPLAY_NAME} · {info.probe_name}")
        self.board_label.setToolTip(f"{info.device}\nProbe ID {info.unique_id}")
        self.flash_tab.set_board_available(True)
        self.diag_tab.set_board(info)
        self._serial_probe.emit(info.unique_id)

    def _on_disconnected(self, reason: str) -> None:
        self._set_board_text("idle", "No board — connect the ST-LINK USB port (CN1)")
        self.flash_tab.set_board_available(False)
        self.diag_tab.on_disconnected()

    def _on_probe_status(self, state: str, message: str) -> None:
        kind = {"busy": "busy", "error": "error"}.get(state, "idle")
        if state == "searching":
            message = "No board — connect the ST-LINK USB port (CN1)"
        self._set_board_text(kind, message)
        self.flash_tab.set_board_available(False)

    def _on_serial_status(self, state: str, message: str) -> None:
        c = style.colors()
        color = {"open": c["ok"], "busy": c["busy"], "error": c["error"]}.get(state, c["idle"])
        self.serial_label.setText(f"{style.dot(color)} Log: {message}")

    # -- actions ---------------------------------------------------------------

    def _start_flash(self, path: str) -> None:
        self._flashing = path
        self.diag_tab.set_hex(path)
        self._flash.emit(path)

    def _on_flash_finished(self, ok: bool, message: str, detail: str) -> None:
        self.flash_tab.on_finished(ok, message, detail)
        if ok:
            self.diag_tab.clear_crash()
            self._marker.emit(f"flashed {Path(self._flashing).name}")
            self.tabs.setCurrentWidget(self.logs_tab)

    def _reset_board(self) -> None:
        self._marker.emit("board reset")
        self._reset.emit()

    def _on_action_failed(self, message: str, detail: str) -> None:
        box = QMessageBox(QMessageBox.Icon.Warning, config.APP_NAME, message, parent=self)
        if detail:
            box.setDetailedText(detail)
        box.exec()

    def _on_lines(self, lines: list) -> None:
        self.logs_tab.add_lines(lines)
        for line in lines:
            csr = parse_firmware_reset_line(line.text)
            if csr is not None:
                self.diag_tab.set_firmware_reset(csr)

    def _on_crash_state(self, crashed: bool) -> None:
        i = self.tabs.indexOf(self.diag_tab)
        self.tabs.setTabText(i, "Diagnostics  ●" if crashed else "Diagnostics")
        # An invalid QColor means "no override": the style's normal tab color.
        self.tabs.tabBar().setTabTextColor(
            i, QColor(style.colors()["error"]) if crashed else QColor())

    # -- drag & drop, close ----------------------------------------------------

    def dragEnterEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if urls and urls[0].toLocalFile().lower().endswith(".hex"):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        if self.flash_tab.busy:
            return
        path = event.mimeData().urls()[0].toLocalFile()
        self.tabs.setCurrentWidget(self.flash_tab)
        if self.flash_tab.set_file(path):
            self.diag_tab.set_hex(path)

    def closeEvent(self, event) -> None:
        if self.flash_tab.busy:
            QMessageBox.information(self, config.APP_NAME,
                                    "Please wait until flashing has finished.")
            event.ignore()
            return
        self._settings.set("geometry", bytes(self.saveGeometry().toBase64()).decode())
        for worker, thread in ((self.probe_worker, self.probe_thread),
                               (self.serial_worker, self.serial_thread)):
            QMetaObject.invokeMethod(worker, "stop", Qt.ConnectionType.BlockingQueuedConnection)
            thread.quit()
            thread.wait(3000)
        event.accept()
