import pytest

from devicetool.core import fault
from devicetool.core.probe import BoardInfo, Probe, ProbeError, ProbeGone, ProbeInfo

UID = "0123456789ABCDEF01234567"


class FakeTarget:
    def __init__(self):
        self.mem = {0xE0044000: 0x30070482, fault.DHCSR_ADDR: 0x01000001,
                    fault.CFSR_ADDR: 0, fault.HFSR_ADDR: 0, fault.MMFAR_ADDR: 0,
                    fault.BFAR_ADDR: 0, 0x46020CF4: 0x0C004400}
        self.regs = {n: 0 for n in fault.CORE_REGS}
        self.halted = self.resumed = self.resets = 0
        self.fail = None

    def read32(self, addr):
        if self.fail:
            raise self.fail
        return self.mem[addr]

    def read_core_register(self, name):
        return self.regs[name]

    def read_memory_block32(self, addr, n):
        return [addr + i for i in range(n)]

    def halt(self): self.halted += 1
    def resume(self): self.resumed += 1
    def reset(self): self.resets += 1


class FakeProbeObj:
    description = "STLINK-V3"


class FakeSession:
    def __init__(self, target, fail_open=None):
        self.target, self.probe = target, FakeProbeObj()
        self.fail_open, self.closed = fail_open, False

    def open(self):
        if self.fail_open:
            raise self.fail_open

    def close(self):
        self.closed = True


def make(target=None, present=True, fail_open=None):
    target = target or FakeTarget()
    sessions = []

    def factory(uid, mode):
        s = FakeSession(target, fail_open)
        sessions.append((mode, s))
        return s

    lister = lambda: [ProbeInfo(UID, "STLINK-V3")] if present else []
    return Probe("pack.pack", session_factory=factory, probe_lister=lister), target, sessions


def test_connect_reads_device():
    p, _, sessions = make()
    info = p.connect(UID)
    assert info == BoardInfo(UID, "STLINK-V3", "STM32U575, rev 0x3007")
    assert sessions[0][0] == "attach" and p.connected


def test_connect_failure_is_busy_error():
    p, _, sessions = make(fail_open=RuntimeError("LIBUSB_ERROR_ACCESS"))
    with pytest.raises(ProbeError) as e:
        p.connect(UID)
    assert "LIBUSB_ERROR_ACCESS" in e.value.detail
    assert sessions[0][1].closed and not p.connected


def test_health_states():
    p, t, _ = make()
    p.connect(UID)
    assert p.health().state == "running"
    t.mem[fault.DHCSR_ADDR] = 0x01000001 | fault.DHCSR_S_SLEEP
    assert p.health().state == "sleeping"
    t.mem[fault.DHCSR_ADDR] = 0x01000001 | fault.DHCSR_S_HALT
    assert p.health().state == "halted"
    t.mem[fault.DHCSR_ADDR] = 0x01000001
    t.mem[fault.CFSR_ADDR] = 0x100000
    h = p.health()
    assert h.state == "faulted" and h.faulted and h.cfsr == 0x100000
    t.mem[fault.DHCSR_ADDR] = fault.DHCSR_S_LOCKUP
    assert p.health().state == "lockup"


def test_health_when_unplugged_raises_gone_and_disconnects():
    p, t, sessions = make()
    p.connect(UID)
    p._list = lambda: []
    t.fail = OSError("USB gone")
    with pytest.raises(ProbeGone):
        p.health()
    assert not p.connected and sessions[0][1].closed


def test_health_when_unresponsive_but_present():
    p, t, _ = make()
    p.connect(UID)
    t.fail = RuntimeError("no ack")
    assert p.health().state == "no_response"
    assert p.connected


def test_snapshot_reads_stacked_frame_from_psp_and_resumes():
    p, t, _ = make()
    p.connect(UID)
    t.regs.update(lr=0xFFFFFFBC, psp=0x2000C090, msp=0x200BFF90, xpsr=0x21000003)
    t.mem[fault.CFSR_ADDR] = 0x100000
    snap = p.snapshot()
    assert snap.cfsr == 0x100000 and snap.ipsr == 3
    assert snap.stacked["r0"] == 0x2000C090 and snap.stacked["xpsr"] == 0x2000C090 + 7
    assert t.halted == 1 and t.resumed == 1


def test_snapshot_resumes_even_on_error():
    p, t, _ = make()
    p.connect(UID)
    t.fail = RuntimeError("boom")
    with pytest.raises(ProbeError):
        p.snapshot()
    assert t.resumed == 1


def test_reset_flags_and_reset():
    p, t, _ = make()
    p.connect(UID)
    assert p.read_reset_flags() == 0x0C004400
    p.reset()
    assert t.resets == 1


def test_flash_rejects_bad_hex_without_touching_board(tmp_path):
    p, _, sessions = make()
    p.connect(UID)
    bad = tmp_path / "bad.hex"
    bad.write_text("nope")
    with pytest.raises(ProbeError, match="not a valid"):
        p.flash(bad, lambda s, f: None)
    assert p.connected and len(sessions) == 1


def test_flash_without_board():
    p, _, _ = make()
    with pytest.raises(ProbeError, match="No board"):
        p.flash("x.hex", lambda s, f: None)


def test_repeated_no_response_drops_dead_session_so_it_reconnects():
    # Quick unplug/replug: the probe is listed again but the old USB handle is dead.
    p, t, sessions = make()
    p.connect(UID)
    t.fail = RuntimeError("stale handle")
    assert p.health().state == "no_response"
    assert p.health().state == "no_response"
    with pytest.raises(ProbeGone):
        p.health()
    assert not p.connected and sessions[0][1].closed


def test_no_response_counter_resets_after_good_read():
    p, t, _ = make()
    p.connect(UID)
    t.fail = RuntimeError("x")
    p.health(); p.health()
    t.fail = None
    assert p.health().state == "running"
    t.fail = RuntimeError("x")
    assert p.health().state == "no_response"
    assert p.connected
