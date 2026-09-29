from devicetool.core import fault
from devicetool.core.fault import FaultSnapshot

# Values captured from the real board on 2026-09-29.
REAL_REGS = {"r0": 0, "r1": 0, "r2": 0, "r3": 0, "r4": 0, "r5": 0, "r6": 0, "r7": 0,
             "r8": 0, "r9": 0, "r10": 0, "r11": 0, "r12": 0,
             "sp": 0x200BFF90, "lr": 0xFFFFFFBC, "pc": 0x0800715E, "xpsr": 0x21000003,
             "msp": 0x200BFF90, "psp": 0x2000C090, "control": 0}
REAL_STACKED = {"r0": 0x20000560, "r1": 0x2000C0D0, "r2": 0x0804CF90, "r3": 0x208,
                "r12": 0x2000CBA8, "lr": 0x080484F1, "pc": 0x08049C28, "xpsr": 0x21000000}


def real_snapshot():
    return FaultSnapshot(cfsr=0x00100000, hfsr=0x40000000, mmfar=0x2000C0A4,
                         bfar=0x2000C0A4, registers=dict(REAL_REGS), stacked=dict(REAL_STACKED))


def test_decode_real_values():
    assert fault.decode_cfsr(0x00100000) == ["STKOF"]
    assert fault.decode_hfsr(0x40000000) == ["FORCED"]
    exc = fault.decode_exc_return(0xFFFFFFBC)
    assert exc.thread_mode and exc.uses_psp and not exc.secure_stack and not exc.fp_frame
    assert real_snapshot().ipsr == 3
    assert fault.exception_name(3) == "HardFault"


def test_summary_real_stack_overflow():
    assert fault.summarize(real_snapshot()) == \
        "Stack overflow in an RTOS task (UsageFault → HardFault)"


def test_summary_other_faults():
    base = dict(REAL_REGS, lr=0xFFFFFFF9)  # thread mode, MSP
    s = FaultSnapshot(0x00000082, 0x40000000, 0x20001234, 0, base, None)  # DACCVIOL+MMARVALID
    assert fault.summarize(s) == \
        "Invalid memory access (memory protection) at address 0x20001234 in main code (MemManage → HardFault)"
    s = FaultSnapshot(0x00008200, 0x40000000, 0, 0x40000000, dict(REAL_REGS, lr=0xFFFFFFF1), None)
    assert fault.summarize(s) == \
        "Bus error on a memory access at address 0x40000000 in an interrupt handler (BusFault → HardFault)"
    s = FaultSnapshot(0x02000000, 0x40000000, 0, 0, dict(REAL_REGS, lr=0x08001234), None)
    assert fault.summarize(s) == "Division by zero (UsageFault → HardFault)"
    s = FaultSnapshot(0, 0x00000002, 0, 0, dict(REAL_REGS), None)
    assert fault.summarize(s).startswith("Vector table read error")
    s = FaultSnapshot(0, 0, 0, 0, dict(REAL_REGS), None)
    assert fault.summarize(s).startswith("CPU locked up")


def test_exc_return_rejects_normal_address():
    assert fault.decode_exc_return(0x080484F1) is None


def test_exception_names():
    assert fault.exception_name(0) == "Thread mode"
    assert fault.exception_name(16) == "IRQ 0"
    assert fault.exception_name(58) == "IRQ 42"


def test_is_faulted():
    assert not fault.is_faulted(0, 0, 0x01000001)
    assert fault.is_faulted(0x100000, 0, 0)
    assert fault.is_faulted(0, 0x40000000, 0)
    assert fault.is_faulted(0, 0, fault.DHCSR_S_LOCKUP)


def test_report_contents_and_symbols():
    names = {0x08049C28: "BLE_Task+0x10 (main_app_BLE.c:120)"}
    text = fault.format_report(real_snapshot(), symbolize=lambda a: names.get(a & ~1))
    assert "Stack overflow in an RTOS task" in text
    assert "CFSR   0x00100000  STKOF" in text
    assert "HFSR   0x40000000  FORCED" in text
    assert "0xFFFFFFBC → thread mode, process stack (PSP), no FPU frame" in text
    assert "PC     0x08049C28  BLE_Task+0x10 (main_app_BLE.c:120)" in text
    assert "unreliable" in text          # stack-overflow warning
    assert "HardFault (IPSR 3)" in text


def test_report_when_running_again():
    s = FaultSnapshot(0x00000100, 0, 0, 0, dict(REAL_REGS, xpsr=0x01000000), None)
    assert "running again" in fault.format_report(s)
