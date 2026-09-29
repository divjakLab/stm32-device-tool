import errno

import pytest
import serial

from devicetool.core import serial_link
from devicetool.core.serial_link import PortInfo, SerialBusy, SerialLink, parse_lsof, pick_port

UID = "0123456789ABCDEF01234567"
PORTS = [
    PortInfo("/dev/cu.Bluetooth-Incoming-Port", None, None),
    PortInfo("/dev/cu.usbmodem99", 0x0483, "OTHERBOARD"),
    PortInfo("/dev/cu.usbmodem1101", 0x0483, UID),
    PortInfo("/dev/tty.usbmodem1101", 0x0483, UID),
]


def test_pick_matching_serial_prefers_cu():
    assert pick_port(PORTS, UID) == "/dev/cu.usbmodem1101"
    assert pick_port(PORTS, UID.lower()) == "/dev/cu.usbmodem1101"


def test_pick_falls_back_to_first_stlink():
    assert pick_port(PORTS, "UNKNOWN") == "/dev/cu.usbmodem1101"
    assert pick_port(PORTS, None) == "/dev/cu.usbmodem1101"


def test_pick_none_without_stlink():
    assert pick_port(PORTS[:1], UID) is None


def test_parse_lsof():
    assert parse_lsof("p42910\ncpicocom\nf3\n") == "picocom"
    assert parse_lsof("") is None


def test_busy_port_raises_serialbusy(monkeypatch):
    def fake_serial(*a, **k):
        raise serial.SerialException(errno.EBUSY, "could not open port: [Errno 16] Resource busy")
    monkeypatch.setattr(serial_link.serial, "Serial", fake_serial)
    with pytest.raises(SerialBusy):
        SerialLink().open("/dev/cu.x", 115200)


def test_link_reads_and_writes(monkeypatch):
    class Fake:
        in_waiting = 3
        def __init__(self, *a, **k): self.written = b""; self.baudrate = k["baudrate"]
        def read(self, n): return b"abc"[:n]
        def write(self, d): self.written += d
        def close(self): pass
    monkeypatch.setattr(serial_link.serial, "Serial", Fake)
    link = SerialLink()
    link.open("/dev/cu.x", 115200)
    assert link.is_open and link.device == "/dev/cu.x"
    assert link.read() == b"abc"
    link.write(b"hi\n")
    link.set_baud(921600)
    assert link._s.baudrate == 921600 and link._s.written == b"hi\n"
    link.close()
    assert not link.is_open


def test_flock_held_port_is_busy(monkeypatch):
    # picocom / a second app instance holds the flock: pyserial raises errno 35.
    def fake_serial(*a, **k):
        raise serial.SerialException(
            errno.EAGAIN, "Could not exclusively lock port /dev/cu.x: [Errno 35] "
                          "Resource temporarily unavailable")
    monkeypatch.setattr(serial_link.serial, "Serial", fake_serial)
    with pytest.raises(SerialBusy):
        SerialLink().open("/dev/cu.x", 115200)


def test_windows_access_denied_is_busy(monkeypatch):
    # Windows reports a port held by PuTTY/Tera Term as "Access is denied".
    def fake_serial(*a, **k):
        raise serial.SerialException("could not open port 'COM5': PermissionError(13, "
                                     "'Access is denied.', None, 5)")
    monkeypatch.setattr(serial_link.serial, "Serial", fake_serial)
    with pytest.raises(SerialBusy):
        SerialLink().open("COM5", 921600)


def test_pick_port_on_windows_com_names():
    ports = [PortInfo("COM3", 0x0483, UID), PortInfo("COM1", None, None)]
    assert pick_port(ports, UID) == "COM3"


def test_port_owner_only_uses_lsof_on_macos(monkeypatch):
    monkeypatch.setattr(serial_link.sys, "platform", "win32")
    def boom(*a, **k):
        raise AssertionError("lsof must not run on Windows")
    monkeypatch.setattr(serial_link.subprocess, "run", boom)
    assert serial_link.port_owner("COM3") is None


def test_busy_hint(monkeypatch):
    assert serial_link.busy_hint("picocom") == "Serial port busy — close picocom"
    monkeypatch.setattr(serial_link.sys, "platform", "darwin")
    assert serial_link.busy_hint(None) == "Serial port busy — close picocom / CubeIDE"
    monkeypatch.setattr(serial_link.sys, "platform", "win32")
    assert serial_link.busy_hint(None) == \
        "Serial port busy — close PuTTY / Tera Term / CubeIDE"
