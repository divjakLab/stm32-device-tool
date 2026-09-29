"""Background workers. Each lives in its own QThread; talk to them only via signals."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from .. import config
from ..core.logbuffer import LineAssembler, LogLine, Level, SessionLog, make_marker
from ..core.probe import Probe, ProbeError, ProbeGone, list_probes
from ..core.serial_link import (SerialBusy, SerialLink, available_ports, busy_hint, pick_port,
                                port_owner)

log = logging.getLogger(__name__)


class ProbeWorker(QObject):
    connected = Signal(object)
    disconnected = Signal(str)
    status = Signal(str, str)
    health = Signal(object)
    crash = Signal(object)
    resetFlags = Signal(int)
    flashProgress = Signal(str, float)
    flashFinished = Signal(bool, str, str)
    actionFailed = Signal(str, str)

    def __init__(self, pack: Optional[Path], probe_factory=Probe, lister=list_probes) -> None:
        super().__init__()
        self._pack = pack
        self._factory = probe_factory
        self._list = lister
        self._probe = None
        self._timer: Optional[QTimer] = None
        self._busy = False
        self._crash_reported = False
        self._last_status: Optional[tuple[str, str]] = None

    @Slot()
    def start(self) -> None:
        if self._pack is not None and self._probe is None:
            self._probe = self._factory(self._pack)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.tick)
        self._timer.start(config.HEALTH_INTERVAL_MS)
        self.tick()

    @Slot()
    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        if self._probe is not None:
            self._probe.disconnect()

    def _set_status(self, state: str, message: str) -> None:
        if self._last_status != (state, message):
            self._last_status = (state, message)
            self.status.emit(state, message)

    @Slot()
    def tick(self) -> None:
        if self._busy:
            return
        if self._probe is None:
            self._set_status("error", "Device support file (.pack) is missing from the app.")
            return
        try:
            if not self._probe.connected:
                self._try_connect()
            else:
                self._check_health()
        except ProbeGone as exc:
            self._crash_reported = False
            self._last_status = None
            self.disconnected.emit(exc.message)
        except Exception:
            log.exception("probe tick failed")

    def _try_connect(self) -> None:
        probes = self._list()
        if not probes:
            self._set_status("searching", "No board")
            return
        try:
            info = self._probe.connect(probes[0].unique_id)
        except ProbeGone:
            raise
        except ProbeError as exc:
            self._set_status("busy", "Board busy — close STM32CubeIDE / CubeProgrammer "
                                     f"and other debug tools ({exc.detail})")
            return
        self._last_status = None
        self.connected.emit(info)
        self._emit_reset_flags()
        self._check_health()

    def _emit_reset_flags(self) -> None:
        try:
            self.resetFlags.emit(self._probe.read_reset_flags())
        except Exception as exc:
            log.info("reset flags not readable: %s", exc)

    def _check_health(self) -> None:
        h = self._probe.health()
        self.health.emit(h)
        if h.faulted and not self._crash_reported:
            self._crash_reported = True
            try:
                self.crash.emit(self._probe.snapshot())
            except ProbeError as exc:
                self.actionFailed.emit(exc.message, exc.detail)
        elif not h.faulted and h.state != "no_response":
            self._crash_reported = False

    @Slot(str)
    def flash(self, path: str) -> None:
        if self._probe is None:
            self.flashFinished.emit(False, "Device support file (.pack) is missing.", "")
            return
        self._busy = True
        try:
            self._probe.flash(path, lambda stage, f: self.flashProgress.emit(stage, f))
        except ProbeError as exc:
            self.flashFinished.emit(False, exc.message, exc.detail)
        except Exception as exc:
            log.exception("flash failed")
            self.flashFinished.emit(False, "Unexpected error while flashing.",
                                    f"{type(exc).__name__}: {exc}")
        else:
            self.flashFinished.emit(True, "Update successful. The board is running the new "
                                          "firmware.", "")
        finally:
            self._busy = False
            self._crash_reported = False
        if self._probe.connected:
            self._emit_reset_flags()
        self.tick()

    @Slot()
    def reset_board(self) -> None:
        try:
            self._probe.reset()
            self._crash_reported = False
        except ProbeError as exc:
            self.actionFailed.emit(exc.message, exc.detail)
        except Exception as exc:
            self.actionFailed.emit("Could not reset the board.", str(exc))

    @Slot()
    def check_now(self) -> None:
        self._crash_reported = False
        self.tick()


class SerialWorker(QObject):
    lines = Signal(list)
    status = Signal(str, str)

    def __init__(self, sessions_dir: Path, link_factory=SerialLink, ports=available_ports) -> None:
        super().__init__()
        self._sessions_dir = Path(sessions_dir)
        self._link = link_factory()
        self._ports = ports
        self._owner = port_owner
        self._asm = LineAssembler()
        self._baud = config.DEFAULT_BAUD
        self._probe_serial: Optional[str] = None
        self._session: Optional[SessionLog] = None
        self._next_try = 0.0
        self._timer: Optional[QTimer] = None
        self._last_status: Optional[tuple[str, str]] = None

    @Slot()
    def start(self) -> None:
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.tick)
        self._timer.start(config.SERIAL_POLL_MS)

    @Slot()
    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        self._close(None)

    def _set_status(self, state: str, message: str) -> None:
        if self._last_status != (state, message):
            self._last_status = (state, message)
            self.status.emit(state, message)

    def _emit(self, lines: list[LogLine]) -> None:
        if self._session is not None:
            try:
                self._session.write(lines)
            except OSError:
                pass
        self.lines.emit(lines)

    @Slot(str)
    def marker(self, text: str) -> None:
        self._emit([make_marker(text, time.time())])

    @Slot(object)
    def set_probe(self, uid: Optional[str]) -> None:
        self._probe_serial = uid
        self._next_try = 0.0

    @Slot(int)
    def set_baud(self, baud: int) -> None:
        self._baud = baud
        if self._link.is_open:
            try:
                self._link.set_baud(baud)
            except Exception as exc:
                log.info("baud change failed: %s", exc)
                self._close("serial disconnected")
                return
            self._set_status("open", f"{self._link.device} @ {baud}")
            self.marker(f"baud rate {baud}")

    @Slot(bytes)
    def send(self, data: bytes) -> None:
        if not self._link.is_open:
            self.marker("not sent: no serial connection")
            return
        try:
            self._link.write(data)
        except Exception as exc:
            self.marker(f"not sent: {exc}")
            return
        shown = data.decode("utf-8", errors="replace").rstrip("\r\n")
        self._emit([LogLine(time.time(), f"→ {shown}", Level.MARKER)])

    def _close(self, reason: Optional[str]) -> None:
        was_open = self._link.is_open
        self._link.close()
        if was_open and reason:
            self.marker(reason)
            self._set_status("closed", reason[0].upper() + reason[1:])
        if self._session is not None:
            self._session.close()
            self._session = None
        self._next_try = time.time() + config.SERIAL_RETRY_S

    @Slot()
    def tick(self) -> None:
        now = time.time()
        if not self._link.is_open:
            if now < self._next_try:
                return
            self._next_try = now + config.SERIAL_RETRY_S
            device = pick_port(self._ports(), self._probe_serial)
            if device is None:
                self._set_status("none", "No serial port")
                return
            try:
                self._link.open(device, self._baud)
            except SerialBusy:
                if not self._last_status or self._last_status[0] != "busy":
                    owner = self._owner(device)
                    self._set_status("busy", busy_hint(owner))
                return
            except Exception as exc:
                self._set_status("error", f"Serial port error: {exc}")
                return
            try:
                self._session = SessionLog(self._sessions_dir)
            except OSError:
                self._session = None
            self._set_status("open", f"{device} @ {self._baud}")
            return
        try:
            data = self._link.read()
        except Exception as exc:
            log.info("serial read failed: %s", exc)
            self._close("serial disconnected")
            return
        out = self._asm.feed(data, now) if data else []
        out += self._asm.flush_if_idle(now)
        if out:
            self._emit(out)
