"""Pure decoding of Cortex-M33 (ARMv8-M) fault state. No hardware access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

CFSR_ADDR = 0xE000ED28
HFSR_ADDR = 0xE000ED2C
MMFAR_ADDR = 0xE000ED34
BFAR_ADDR = 0xE000ED38
DHCSR_ADDR = 0xE000EDF0

DHCSR_S_HALT = 1 << 17
DHCSR_S_SLEEP = 1 << 18
DHCSR_S_LOCKUP = 1 << 19

CORE_REGS = tuple(f"r{i}" for i in range(13)) + ("sp", "lr", "pc", "xpsr", "msp", "psp", "control")
STACKED_NAMES = ("r0", "r1", "r2", "r3", "r12", "lr", "pc", "xpsr")

# bit -> (flag name, fault class)
_CFSR_BITS = {
    0: ("IACCVIOL", "MemManage"), 1: ("DACCVIOL", "MemManage"), 3: ("MUNSTKERR", "MemManage"),
    4: ("MSTKERR", "MemManage"), 5: ("MLSPERR", "MemManage"), 7: ("MMARVALID", "MemManage"),
    8: ("IBUSERR", "BusFault"), 9: ("PRECISERR", "BusFault"), 10: ("IMPRECISERR", "BusFault"),
    11: ("UNSTKERR", "BusFault"), 12: ("STKERR", "BusFault"), 13: ("LSPERR", "BusFault"),
    15: ("BFARVALID", "BusFault"),
    16: ("UNDEFINSTR", "UsageFault"), 17: ("INVSTATE", "UsageFault"), 18: ("INVPC", "UsageFault"),
    19: ("NOCP", "UsageFault"), 20: ("STKOF", "UsageFault"), 24: ("UNALIGNED", "UsageFault"),
    25: ("DIVBYZERO", "UsageFault"),
}
_HFSR_BITS = {1: "VECTTBL", 30: "FORCED", 31: "DEBUGEVT"}

_EXCEPTION_NAMES = {0: "Thread mode", 1: "Reset", 2: "NMI", 3: "HardFault", 4: "MemManage",
                    5: "BusFault", 6: "UsageFault", 7: "SecureFault", 11: "SVCall",
                    12: "DebugMonitor", 14: "PendSV", 15: "SysTick"}

_STACK_ENTRY = "Stack overflow or corrupted stack pointer (while entering an exception)"
_STACK_EXIT = "Corrupted stack (while returning from an exception)"
# First matching flag wins.
_REASONS = (
    ("STKOF", "Stack overflow"),
    ("MSTKERR", _STACK_ENTRY), ("STKERR", _STACK_ENTRY),
    ("MUNSTKERR", _STACK_EXIT), ("UNSTKERR", _STACK_EXIT),
    ("DIVBYZERO", "Division by zero"),
    ("UNALIGNED", "Unaligned memory access"),
    ("UNDEFINSTR", "Undefined instruction (corrupted code or a bad function pointer)"),
    ("INVSTATE", "Invalid CPU state (usually a bad function pointer)"),
    ("INVPC", "Invalid exception return (corrupted stack or LR)"),
    ("NOCP", "FPU used before it was enabled"),
    ("DACCVIOL", "Invalid memory access (memory protection)"),
    ("IACCVIOL", "Tried to run code from a forbidden address"),
    ("PRECISERR", "Bus error on a memory access"),
    ("IMPRECISERR", "Bus error on a memory write (reported late)"),
    ("IBUSERR", "Bus error while fetching an instruction (bad jump address)"),
    ("LSPERR", "Fault while saving FPU state"), ("MLSPERR", "Fault while saving FPU state"),
)


def decode_cfsr(cfsr: int) -> list[str]:
    return [name for bit, (name, _) in sorted(_CFSR_BITS.items()) if cfsr & (1 << bit)]


def decode_hfsr(hfsr: int) -> list[str]:
    return [name for bit, name in sorted(_HFSR_BITS.items()) if hfsr & (1 << bit)]


def fault_classes(cfsr: int) -> list[str]:
    out: list[str] = []
    for bit, (name, cls) in sorted(_CFSR_BITS.items()):
        if cfsr & (1 << bit) and not name.endswith("VALID") and cls not in out:
            out.append(cls)
    return out


def exception_name(ipsr: int) -> str:
    if ipsr in _EXCEPTION_NAMES:
        return _EXCEPTION_NAMES[ipsr]
    return f"IRQ {ipsr - 16}" if ipsr >= 16 else f"Exception {ipsr}"


@dataclass(frozen=True)
class ExcReturn:
    thread_mode: bool
    uses_psp: bool
    secure_stack: bool
    fp_frame: bool


def decode_exc_return(value: int) -> Optional[ExcReturn]:
    if (value >> 24) != 0xFF:
        return None
    return ExcReturn(thread_mode=bool(value & 0x08), uses_psp=bool(value & 0x04),
                     secure_stack=bool(value & 0x40), fp_frame=not (value & 0x10))


@dataclass
class FaultSnapshot:
    cfsr: int
    hfsr: int
    mmfar: int
    bfar: int
    registers: dict[str, int]
    stacked: Optional[dict[str, int]] = None

    @property
    def ipsr(self) -> int:
        return self.registers.get("xpsr", 0) & 0x1FF


def is_faulted(cfsr: int, hfsr: int, dhcsr: int) -> bool:
    return bool(cfsr or hfsr or (dhcsr & DHCSR_S_LOCKUP))


def summarize(snap: FaultSnapshot) -> str:
    flags = set(decode_cfsr(snap.cfsr))
    reason = next((text for flag, text in _REASONS if flag in flags), None)
    if reason is None:
        if snap.hfsr & (1 << 1):
            reason = "Vector table read error"
        elif snap.cfsr == 0 and snap.hfsr == 0:
            reason = "CPU locked up"
        else:
            reason = "HardFault"
    if "MMARVALID" in flags:
        reason += f" at address 0x{snap.mmfar:08X}"
    elif "BFARVALID" in flags:
        reason += f" at address 0x{snap.bfar:08X}"

    exc = decode_exc_return(snap.registers.get("lr", 0))
    if exc is not None:
        if exc.thread_mode and exc.uses_psp:
            reason += " in an RTOS task"
        elif exc.thread_mode:
            reason += " in main code"
        else:
            reason += " in an interrupt handler"

    classes = fault_classes(snap.cfsr)
    if snap.hfsr & (1 << 30) and classes:
        reason += f" ({classes[0]} → HardFault)"
    return reason


def _describe_exc_return(value: int) -> str:
    exc = decode_exc_return(value)
    if exc is None:
        return f"0x{value:08X} (LR is not an exception-return value)"
    mode = "thread mode" if exc.thread_mode else "handler mode"
    stack = "process stack (PSP)" if exc.uses_psp else "main stack (MSP)"
    fp = "FPU frame" if exc.fp_frame else "no FPU frame"
    return f"0x{value:08X} → {mode}, {stack}, {fp}"


def format_report(snap: FaultSnapshot,
                  symbolize: Optional[Callable[[int], Optional[str]]] = None) -> str:
    def sym(addr: int) -> str:
        if symbolize is None:
            return ""
        name = symbolize(addr)
        return f"  {name}" if name else ""

    flags = set(decode_cfsr(snap.cfsr))
    regs = snap.registers
    lines = [f"Summary: {summarize(snap)}", ""]
    if snap.ipsr == 0:
        lines += ["Note: the CPU is running again; these fault flags are from an earlier fault.", ""]
    lines.append(f"Active exception: {exception_name(snap.ipsr)} (IPSR {snap.ipsr})")
    lines += [
        "",
        "Fault status:",
        f"  CFSR   0x{snap.cfsr:08X}  {' '.join(decode_cfsr(snap.cfsr)) or '-'}",
        f"  HFSR   0x{snap.hfsr:08X}  {' '.join(decode_hfsr(snap.hfsr)) or '-'}",
        f"  MMFAR  0x{snap.mmfar:08X}  {'valid' if 'MMARVALID' in flags else 'not valid'}",
        f"  BFAR   0x{snap.bfar:08X}  {'valid' if 'BFARVALID' in flags else 'not valid'}",
        "",
        f"Exception return: {_describe_exc_return(regs.get('lr', 0))}",
    ]
    if snap.stacked:
        lines += ["", "Registers at the moment of the fault (stacked frame):"]
        for name in ("pc", "lr", "r0", "r1", "r2", "r3", "r12", "xpsr"):
            value = snap.stacked[name]
            extra = sym(value) if name in ("pc", "lr") else ""
            lines.append(f"  {name.upper():<5}  0x{value:08X}{extra}")
        if "STKOF" in flags or flags & {"MSTKERR", "STKERR"}:
            lines.append("  Note: after a stack overflow this frame may be unreliable.")
    lines += ["", "Core registers now:"]
    for name in ("pc", "lr", "sp", "msp", "psp", "control", "xpsr"):
        if name in regs:
            extra = sym(regs[name]) if name == "pc" else ""
            lines.append(f"  {name.upper():<7}  0x{regs[name]:08X}{extra}")
    general = [f"R{i}=0x{regs[f'r{i}']:08X}" for i in range(13) if f"r{i}" in regs]
    for i in range(0, len(general), 4):
        lines.append("  " + "  ".join(general[i:i + 4]))
    return "\n".join(lines)
