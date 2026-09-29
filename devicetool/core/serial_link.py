"""The ST-LINK virtual COM port: discovery, open/read/write, busy detection."""

from __future__ import annotations

import errno
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

import serial
from serial.tools import list_ports

from .. import config


@dataclass(frozen=True)
class PortInfo:
    device: str
    vid: Optional[int]
    serial_number: Optional[str]
    description: str = ""


def available_ports() -> list[PortInfo]:
    return [PortInfo(p.device, p.vid, p.serial_number, p.description or "")
            for p in list_ports.comports()]


def _cu_first(ports: list[PortInfo]) -> list[PortInfo]:
    return sorted(ports, key=lambda p: (not p.device.startswith("/dev/cu."), p.device))


def pick_port(ports: list[PortInfo], probe_serial: Optional[str]) -> Optional[str]:
    """The ST-LINK VCP whose USB serial equals the probe ID, else the first ST-LINK."""
    st = [p for p in ports if p.vid == config.STLINK_VID]
    if probe_serial:
        same = [p for p in st if (p.serial_number or "").lower() == probe_serial.lower()]
        if same:
            return _cu_first(same)[0].device
    return _cu_first(st)[0].device if st else None


class SerialBusy(Exception):
    """Another program has the port open."""


def _is_busy(exc: Exception) -> bool:
    # macOS: EBUSY = TIOCEXCL (e.g. picocom's tty); EAGAIN = another process
    # holds the flock that pyserial's exclusive=True takes.
    # Windows: a port open in another program gives "Access is denied".
    text = str(exc).lower()
    return (getattr(exc, "errno", None) in (errno.EBUSY, errno.EAGAIN, errno.EACCES)
            or any(word in text for word in ("busy", "lock", "access is denied",
                                             "permissionerror")))


class SerialLink:
    def __init__(self) -> None:
        self._s = None
        self.device: Optional[str] = None

    @property
    def is_open(self) -> bool:
        return self._s is not None

    def open(self, device: str, baud: int) -> None:
        self.close()
        try:
            self._s = serial.Serial(device, baudrate=baud, timeout=0, write_timeout=1,
                                    exclusive=True)
        except serial.SerialException as exc:
            if _is_busy(exc):
                raise SerialBusy(str(exc)) from exc
            raise
        self.device = device

    def set_baud(self, baud: int) -> None:
        if self._s is not None:
            self._s.baudrate = baud

    def read(self) -> bytes:
        """Non-blocking: returns whatever has arrived (possibly b'')."""
        return self._s.read(max(1, self._s.in_waiting))

    def write(self, data: bytes) -> None:
        self._s.write(data)

    def close(self) -> None:
        if self._s is not None:
            try:
                self._s.close()
            except Exception:
                pass
        self._s = None
        self.device = None


def parse_lsof(output: str) -> Optional[str]:
    for line in output.splitlines():
        if line.startswith("c"):
            return line[1:]
    return None


def busy_hint(owner: Optional[str]) -> str:
    """Status text for a busy port, naming the owner when it is known."""
    if owner:
        return f"Serial port busy — close {owner}"
    if sys.platform == "win32":
        return "Serial port busy — close PuTTY / Tera Term / CubeIDE"
    return "Serial port busy — close picocom / CubeIDE"


def port_owner(device: str) -> Optional[str]:
    """Name of the program holding the port (macOS only: checks the cu./tty. twins)."""
    if sys.platform != "darwin":
        return None
    paths = [device]
    if device.startswith("/dev/cu."):
        paths.append("/dev/tty." + device[len("/dev/cu."):])
    try:
        out = subprocess.run(["lsof", "-Fc", *paths], capture_output=True, text=True,
                             timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_lsof(out)
