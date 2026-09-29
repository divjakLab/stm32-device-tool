import sys

import pytest
from PySide6.QtCore import QCoreApplication

from devicetool.core.probe import BoardInfo, Health, ProbeError, ProbeGone, ProbeInfo
from devicetool.ui.workers import ProbeWorker, SerialWorker

UID = "0123456789ABCDEF01234567"


@pytest.fixture(scope="module", autouse=True)
def qapp():
    yield QCoreApplication.instance() or QCoreApplication(sys.argv)


class Rec:
    def __init__(self, *signals):
        self.events = []
        for name, sig in signals:
            sig.connect(lambda *a, n=name: self.events.append((n, a)))

    def names(self):
        return [n for n, _ in self.events]


class FakeProbe:
    def __init__(self, pack):
        self.connected, self.health_value, self.snaps = False, Health("running"), 0
        self.connect_error = None
        self.unique_id = None

    def connect(self, uid):
        if self.connect_error:
            raise self.connect_error
        self.connected, self.unique_id = True, uid
        return BoardInfo(uid, "STLINK-V3", "STM32U575, rev 0x3007")

    def disconnect(self): self.connected = False
    def health(self):
        if isinstance(self.health_value, Exception):
            self.connected = False
            raise self.health_value
        return self.health_value
    def snapshot(self):
        self.snaps += 1
        return "SNAP"
    def read_reset_flags(self): return 0x0C004400
    def reset(self): pass
    def flash(self, path, progress):
        progress("Programming", 0.5)
        if "bad" in path:
            raise ProbeError("Programming failed.", "detail")


def make_probe_worker(present=True):
    w = ProbeWorker("pack.pack", probe_factory=FakeProbe,
                    lister=lambda: [ProbeInfo(UID, "STLINK-V3")] if present else [])
    w._probe = FakeProbe("pack.pack")
    rec = Rec(("connected", w.connected), ("disconnected", w.disconnected), ("status", w.status),
              ("health", w.health), ("crash", w.crash), ("reset", w.resetFlags),
              ("progress", w.flashProgress), ("finished", w.flashFinished))
    return w, rec


def test_connects_and_reports_reset_and_health():
    w, rec = make_probe_worker()
    w.tick()
    assert rec.names()[:3] == ["connected", "reset", "health"]


def test_searching_status_is_not_repeated():
    w, rec = make_probe_worker(present=False)
    w.tick(); w.tick()
    assert rec.events == [("status", ("searching", "No board"))]


def test_busy_status():
    w, rec = make_probe_worker()
    w._probe.connect_error = ProbeError("Board busy or not responding.", "LIBUSB_ERROR_ACCESS")
    w.tick()
    assert rec.events[0][0] == "status" and rec.events[0][1][0] == "busy"


def test_crash_reported_once_until_recovered():
    w, rec = make_probe_worker()
    w.tick()
    w._probe.health_value = Health("faulted", 0x100000, 0x40000000)
    w.tick(); w.tick()
    assert rec.names().count("crash") == 1
    w._probe.health_value = Health("running")
    w.tick()
    w._probe.health_value = Health("faulted", 0x100000, 0x40000000)
    w.tick()
    assert rec.names().count("crash") == 2


def test_check_now_forces_new_snapshot():
    w, rec = make_probe_worker()
    w.tick()
    w._probe.health_value = Health("faulted", 0x100000, 0)
    w.tick()
    w.check_now()
    assert rec.names().count("crash") == 2


def test_unplug_emits_disconnected():
    w, rec = make_probe_worker()
    w.tick()
    w._probe.health_value = ProbeGone("The board was disconnected.")
    w.tick()
    assert "disconnected" in rec.names()


def test_flash_ok_and_error():
    w, rec = make_probe_worker()
    w.tick()
    w.flash("good.hex")
    w.flash("bad.hex")
    fin = [a for n, a in rec.events if n == "finished"]
    assert fin[0][0] is True and fin[1] == (False, "Programming failed.", "detail")
    assert ("progress", ("Programming", 0.5)) in rec.events


class FakeLink:
    def __init__(self):
        self.is_open, self.device, self.data, self.sent = False, None, [], b""
        self.busy = False
    def open(self, device, baud):
        from devicetool.core.serial_link import SerialBusy
        if self.busy:
            raise SerialBusy("busy")
        self.is_open, self.device = True, device
    def read(self):
        if self.data and isinstance(self.data[0], Exception):
            raise self.data.pop(0)
        return self.data.pop(0) if self.data else b""
    def write(self, d): self.sent += d
    def set_baud(self, b): pass
    def close(self): self.is_open = False


def make_serial_worker(tmp_path, link):
    from devicetool.core.serial_link import PortInfo
    w = SerialWorker(tmp_path, link_factory=lambda: link,
                     ports=lambda: [PortInfo("/dev/cu.usbmodem1", 0x0483, UID)])
    w._owner = lambda dev: "picocom"
    rec = Rec(("lines", w.lines), ("status", w.status))
    return w, rec


def test_serial_opens_reads_and_logs(tmp_path):
    link = FakeLink()
    w, rec = make_serial_worker(tmp_path, link)
    w.set_probe(UID)
    w.tick()
    assert rec.events[0] == ("status", ("open", "/dev/cu.usbmodem1 @ 921600"))
    link.data.append(b"hello\r\n")
    w.tick()
    lines = [l for n, a in rec.events if n == "lines" for l in a[0]]
    assert lines[-1].text == "hello"
    assert "hello" in next(tmp_path.glob("*.txt")).read_text()


def test_serial_busy_names_owner(tmp_path):
    link = FakeLink(); link.busy = True
    w, rec = make_serial_worker(tmp_path, link)
    w.tick()
    assert rec.events[0] == ("status", ("busy", "Serial port busy — close picocom"))


def test_serial_read_error_closes_with_marker(tmp_path):
    link = FakeLink()
    w, rec = make_serial_worker(tmp_path, link)
    w.tick()
    link.data.append(OSError("device gone"))
    w.tick()
    lines = [l for n, a in rec.events if n == "lines" for l in a[0]]
    assert lines[-1].text == "── serial disconnected ──"
    assert ("status", ("closed", "Serial disconnected")) in rec.events


def test_send_echoes_and_writes(tmp_path):
    link = FakeLink()
    w, rec = make_serial_worker(tmp_path, link)
    w.tick()
    w.send(b"version\n")
    assert link.sent == b"version\n"
    lines = [l for n, a in rec.events if n == "lines" for l in a[0]]
    assert lines[-1].text == "→ version"


def test_send_without_port(tmp_path):
    link = FakeLink()
    w, rec = make_serial_worker(tmp_path, link)
    w.send(b"x\n")
    lines = [l for n, a in rec.events if n == "lines" for l in a[0]]
    assert lines[-1].text == "── not sent: no serial connection ──"


def test_set_baud_failure_closes_port_instead_of_raising(tmp_path):
    link = FakeLink()
    def bad(b): raise OSError("IOSSIOSPEED failed")
    link.set_baud = bad
    w, rec = make_serial_worker(tmp_path, link)
    w.tick()
    w.set_baud(460800)
    assert not link.is_open
    assert ("status", ("closed", "Serial disconnected")) in rec.events


def test_serial_busy_without_owner_uses_platform_hint(tmp_path):
    from devicetool.core.serial_link import busy_hint
    link = FakeLink(); link.busy = True
    w, rec = make_serial_worker(tmp_path, link)
    w._owner = lambda dev: None
    w.tick()
    assert rec.events[0] == ("status", ("busy", busy_hint(None)))
