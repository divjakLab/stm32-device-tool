"""Constants and paths. To support another MCU, change the target block."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

APP_NAME = "STM32 Device Tool"
APP_VERSION = "1.0.0"

# --- Target ---------------------------------------------------------------
PYOCD_TARGET = "stm32u575zitxq"
TARGET_DISPLAY_NAME = "NUCLEO-U575ZI-Q"
DBGMCU_IDCODE_ADDR = 0xE0044000
EXPECTED_DEV_ID = 0x482          # STM32U575/585
DEVICE_NAME = "STM32U575"
SWD_FREQUENCY_HZ = 4_000_000
PROGRAM_SHARE = 0.85             # progress bar: programming share, rest = verify

# RCC_CSR (reset flags). RM0456: RCC base 0x46020C00 (non-secure) + 0xF4.
RCC_CSR_ADDR = 0x46020CF4

# --- Serial -----------------------------------------------------------------
STLINK_VID = 0x0483
DEFAULT_BAUD = 921600          # the firmware this was built for logs at 921600
BAUD_RATES = (9600, 57600, 115200, 230400, 460800, 921600)
LINE_ENDINGS = {"LF": "\n", "CR": "\r", "CR+LF": "\r\n", "None": ""}
DEFAULT_LINE_ENDING = "LF"

# --- Timing and limits -------------------------------------------------------
HEALTH_INTERVAL_MS = 1500
SERIAL_POLL_MS = 20
SERIAL_RETRY_S = 1.0
LINE_IDLE_FLUSH_S = 0.2
MAX_LINE_BYTES = 4096
MAX_LOG_LINES = 100_000
MAX_SESSION_LOGS = 50
MAX_HISTORY = 100


def resource_dir() -> Path:
    """Bundled files: sys._MEIPASS when frozen, else ./resources."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent / "resources"


def find_pack_file() -> Optional[Path]:
    packs = sorted((resource_dir() / "packs").glob("*.pack"))
    return packs[-1] if packs else None


def _windows_dir(env: str, fallback: str) -> Path:
    value = os.environ.get(env)
    return Path(value) if value else Path.home() / "AppData" / fallback


def support_dir() -> Path:
    """Settings, commands, history."""
    if sys.platform == "win32":
        return _windows_dir("APPDATA", "Roaming") / APP_NAME
    return Path.home() / "Library" / "Application Support" / APP_NAME


def logs_dir() -> Path:
    """app.log and the sessions/ folder."""
    if sys.platform == "win32":
        return _windows_dir("LOCALAPPDATA", "Local") / APP_NAME / "Logs"
    return Path.home() / "Library" / "Logs" / APP_NAME
