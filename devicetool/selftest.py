"""--selftest: checks that a (frozen) build contains everything. No board needed."""

from __future__ import annotations

import sys
from pathlib import Path

from . import config


def qt_platform_plugin() -> str:
    return "qwindows.dll" if sys.platform == "win32" else "libqcocoa.dylib"


def run() -> int:
    ok = True

    def check(name: str, passed: bool, info: str = "") -> None:
        nonlocal ok
        ok &= passed
        print(f"[{'ok' if passed else 'FAIL'}] {name} {info}")

    pack = config.find_pack_file()
    check("pack file", pack is not None, str(pack))

    from pyocd.probe.aggregator import PROBE_CLASSES
    check("probe drivers", "stlink" in PROBE_CLASSES, str(sorted(PROBE_CLASSES)))

    import libusb_package
    lib = libusb_package.get_library_path()
    check("libusb", lib is not None, str(lib))

    if pack is not None:
        from pyocd.target.pack.cmsis_pack import CmsisPack
        try:
            names = [d.part_number.lower() for d in CmsisPack(str(pack)).devices]
        except Exception as exc:
            names = []
            print(f"pack could not be read: {exc}")
        check(f"target '{config.PYOCD_TARGET}' in pack", config.PYOCD_TARGET in names)

    from serial.tools import list_ports
    check("pyserial", callable(list_ports.comports))

    import elftools  # noqa: F401
    import intelhex  # noqa: F401
    import hid  # noqa: F401
    check("elftools / intelhex / hid", True)

    from PySide6.QtCore import QLibraryInfo
    plugins = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
    plugin = plugins / "platforms" / qt_platform_plugin()
    check("Qt platform plugin", plugin.exists(), str(plugin))

    print("SELFTEST", "PASSED" if ok else "FAILED")
    return 0 if ok else 1
