"""The single pyOCD session. Not thread-safe: use from one thread only."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .. import config
from .fault import (BFAR_ADDR, CFSR_ADDR, CORE_REGS, DHCSR_ADDR, DHCSR_S_HALT, DHCSR_S_LOCKUP,
                    DHCSR_S_SLEEP, HFSR_ADDR, MMFAR_ADDR, STACKED_NAMES, FaultSnapshot,
                    decode_exc_return, is_faulted)
from .hexfile import HexFileError, load_hex

log = logging.getLogger(__name__)

Progress = Callable[[str, float], None]

# Consecutive failed health reads before the session is treated as dead.
NO_RESPONSE_LIMIT = 3


class ProbeError(Exception):
    """An error with a message suitable for the user, plus technical detail."""

    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class ProbeGone(ProbeError):
    """The probe disappeared (USB unplugged)."""


@dataclass(frozen=True)
class ProbeInfo:
    unique_id: str
    description: str


@dataclass(frozen=True)
class BoardInfo:
    unique_id: str
    probe_name: str
    device: str


@dataclass(frozen=True)
class Health:
    state: str
    cfsr: int = 0
    hfsr: int = 0
    dhcsr: int = 0

    @property
    def faulted(self) -> bool:
        return self.state in ("faulted", "lockup")


def list_probes() -> list[ProbeInfo]:
    from pyocd.core.helpers import ConnectHelper
    return [ProbeInfo(p.unique_id, p.description) for p in
            ConnectHelper.get_all_connected_probes(blocking=False, print_wait_message=False)]


def _safe_close(session) -> None:
    try:
        session.close()
    except Exception:
        pass


class Probe:
    def __init__(self, pack: Path, session_factory=None, probe_lister=list_probes) -> None:
        self._pack = Path(pack)
        self._factory = session_factory or self._default_factory
        self._list = probe_lister
        self._session = None
        self._uid: Optional[str] = None
        self._no_response = 0

    # -- session handling ------------------------------------------------------

    def _default_factory(self, uid: str, connect_mode: str):
        from pyocd.core.helpers import ConnectHelper
        return ConnectHelper.session_with_chosen_probe(
            unique_id=uid, blocking=False,
            options={
                "target_override": config.PYOCD_TARGET,
                "pack": str(self._pack),
                "frequency": config.SWD_FREQUENCY_HZ,
                "connect_mode": connect_mode,
                "no_config": True,
                "resume_on_disconnect": True,
            })

    @property
    def connected(self) -> bool:
        return self._session is not None

    @property
    def unique_id(self) -> Optional[str]:
        return self._uid

    def connect(self, uid: str) -> BoardInfo:
        """Attach without halting or resetting the running firmware."""
        self.disconnect()
        session = self._factory(uid, "attach")
        if session is None:
            raise ProbeGone("The board was disconnected.")
        try:
            session.open()
        except Exception as exc:
            _safe_close(session)
            raise ProbeError("Board busy or not responding.",
                             f"{type(exc).__name__}: {exc}") from exc
        self._session, self._uid = session, uid
        self._no_response = 0
        return BoardInfo(uid, session.probe.description, self._device_description())

    def disconnect(self) -> None:
        if self._session is not None:
            _safe_close(self._session)
        self._session = None

    def _target(self):
        if self._session is None:
            raise ProbeGone("No board connected.")
        return self._session.target

    def _device_description(self) -> str:
        try:
            idcode = self._target().read32(config.DBGMCU_IDCODE_ADDR)
        except Exception:
            return "Unknown device"
        dev_id, rev_id = idcode & 0xFFF, (idcode >> 16) & 0xFFFF
        if dev_id != config.EXPECTED_DEV_ID:
            return f"Unknown device (ID 0x{dev_id:03X})"
        return f"{config.DEVICE_NAME}, rev 0x{rev_id:04X}"

    def _probe_present(self) -> bool:
        try:
            return any(p.unique_id == self._uid for p in self._list())
        except Exception:
            return False

    # -- monitoring ------------------------------------------------------------

    def health(self) -> Health:
        """Reads debug/fault registers without halting the CPU."""
        t = self._target()
        try:
            dhcsr = t.read32(DHCSR_ADDR)
            cfsr = t.read32(CFSR_ADDR)
            hfsr = t.read32(HFSR_ADDR)
        except Exception as exc:
            if not self._probe_present():
                self.disconnect()
                raise ProbeGone("The board was disconnected.", str(exc)) from exc
            # The probe is listed but reads keep failing: after a quick
            # unplug/replug the old USB handle is dead. Drop the session so the
            # next check reconnects (attach mode, harmless to the firmware).
            self._no_response += 1
            if self._no_response >= NO_RESPONSE_LIMIT:
                self.disconnect()
                raise ProbeGone("Lost contact with the board — reconnecting.", str(exc)) from exc
            return Health("no_response")
        self._no_response = 0
        if dhcsr & DHCSR_S_LOCKUP:
            state = "lockup"
        elif is_faulted(cfsr, hfsr, 0):
            state = "faulted"
        elif dhcsr & DHCSR_S_HALT:
            state = "halted"
        elif dhcsr & DHCSR_S_SLEEP:
            state = "sleeping"
        else:
            state = "running"
        return Health(state, cfsr, hfsr, dhcsr)

    def snapshot(self) -> FaultSnapshot:
        """Halts the CPU for a moment, reads the fault state, resumes."""
        t = self._target()
        try:
            t.halt()
            regs = {n: t.read_core_register(n) for n in CORE_REGS}
            cfsr, hfsr, mmfar, bfar = (t.read32(a) for a in
                                       (CFSR_ADDR, HFSR_ADDR, MMFAR_ADDR, BFAR_ADDR))
            stacked = None
            exc = decode_exc_return(regs["lr"])
            if exc is not None and regs["xpsr"] & 0x1FF:
                sp = regs["psp"] if exc.uses_psp else regs["msp"]
                try:
                    stacked = dict(zip(STACKED_NAMES, t.read_memory_block32(sp, 8)))
                except Exception:
                    stacked = None
        except Exception as exc:
            raise ProbeError("Could not read the crash details.",
                             f"{type(exc).__name__}: {exc}") from exc
        finally:
            try:
                t.resume()
            except Exception:
                pass
        return FaultSnapshot(cfsr, hfsr, mmfar, bfar, regs, stacked)

    def read_reset_flags(self) -> int:
        return self._target().read32(config.RCC_CSR_ADDR)

    def reset(self) -> None:
        try:
            self._target().reset()
        except ProbeError:
            raise
        except Exception as exc:
            raise ProbeError("Could not reset the board.", str(exc)) from exc

    # -- flashing --------------------------------------------------------------

    def _open_for_flash(self, uid: str):
        last: Optional[Exception] = None
        for mode in ("halt", "under-reset"):
            session = self._factory(uid, mode)
            if session is None:
                raise ProbeGone("The board was disconnected. Please reconnect it.")
            try:
                session.open()
                return session
            except Exception as exc:
                last = exc
                log.info("connect mode %s failed: %s", mode, exc)
                _safe_close(session)
        raise ProbeError(
            "The board was found but the microcontroller does not respond.\n"
            "Unplug the USB cable, wait 5 seconds, plug it back in and try again.",
            f"{type(last).__name__}: {last}")

    def flash(self, hex_path, progress: Progress) -> None:
        """Program, verify and restart. Reconnects the monitoring session after."""
        uid = self._uid
        if uid is None or self._session is None:
            raise ProbeError("No board connected.")
        try:
            image, info = load_hex(hex_path)
        except HexFileError as exc:
            raise ProbeError(str(exc)) from exc

        from pyocd.flash.file_programmer import FileProgrammer

        progress("Connecting", 0.0)
        self.disconnect()
        try:
            session = self._open_for_flash(uid)
            try:
                progress("Programming", 0.0)
                FileProgrammer(session,
                               progress=lambda f: progress("Programming", f * config.PROGRAM_SHARE)
                               ).program(str(info.path), file_format="hex")
                progress("Verifying", config.PROGRAM_SHARE)
                self._verify(session, image, progress)
                progress("Restarting", 1.0)
                session.target.reset()
            except ProbeError:
                raise
            except Exception as exc:
                if not self._probe_present():
                    raise ProbeGone("Board disconnected during the update. "
                                    "Reconnect it and flash again.", str(exc)) from exc
                raise ProbeError("Programming failed.", f"{type(exc).__name__}: {exc}") from exc
            finally:
                _safe_close(session)
        finally:
            try:
                self.connect(uid)
            except ProbeError as exc:
                log.info("reconnect after flash failed: %s", exc)
        progress("Done", 1.0)

    @staticmethod
    def _verify(session, image, progress: Progress) -> None:
        memory_map = session.target.memory_map
        segments = []
        for start, end in image.segments():
            region = memory_map.get_region_for_address(start)
            if region is not None and region.is_flash:
                segments.append((start, end))
        total = sum(e - s for s, e in segments) or 1
        done, chunk = 0, 32 * 1024
        for start, end in segments:
            address = start
            while address < end:
                size = min(chunk, end - address)
                expected = image.tobinarray(start=address, size=size).tolist()
                actual = session.target.read_memory_block8(address, size)
                if actual != expected:
                    offset = next(i for i, (a, e) in enumerate(zip(actual, expected)) if a != e)
                    raise ProbeError(
                        f"Verification failed: the board's memory does not match the file "
                        f"(first difference at 0x{address + offset:08X}).\nPlease flash again.")
                address += size
                done += size
                progress("Verifying",
                         config.PROGRAM_SHARE + (1 - config.PROGRAM_SHARE) * done / total)
