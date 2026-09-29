"""Decoding of the STM32U5 RCC_CSR reset flags (RM0456)."""

from __future__ import annotations

import re
from typing import Optional

_PIN = "reset pin (button or debugger)"
_FLAGS = (
    (31, "low-power mode reset"),
    (30, "window watchdog"),
    (29, "independent watchdog"),
    (28, "software reset"),
    (27, "power-on / brown-out"),
    (26, _PIN),
    (25, "option-byte load"),
)
_FIRMWARE_LINE = re.compile(r"Reset cause:.*\(RCC->CSR = 0x([0-9A-Fa-f]{1,8})\)")


def decode_reset_flags(csr: int) -> list[str]:
    names = [text for bit, text in _FLAGS if csr & (1 << bit)]
    # Every reset also drives the NRST pin, so the pin flag only means
    # "reset pin" when it is the only flag set.
    if len(names) > 1 and _PIN in names:
        names.remove(_PIN)
    return names


def describe_reset(csr: int) -> str:
    names = decode_reset_flags(csr)
    if not names:
        return "Unknown (reset flags already cleared by the firmware)"
    return ", ".join(n[0].upper() + n[1:] for n in names)


def parse_firmware_reset_line(text: str) -> Optional[int]:
    """The firmware prints '##### Reset cause: ... (RCC->CSR = 0x....)' at boot."""
    m = _FIRMWARE_LINE.search(text)
    return int(m.group(1), 16) if m else None
