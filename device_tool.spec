# -*- mode: python ; coding: utf-8 -*-
# PyInstaller recipe:  pyinstaller --noconfirm device_tool.spec
# pyOCD loads probe drivers via entry points and ships native libraries, so
# its packages are collected explicitly (same as the old updater).

import sys

from PyInstaller.utils.hooks import collect_all

APP_NAME = "STM32DeviceTool"
DISPLAY_NAME = "STM32 Device Tool"
VERSION = "1.0.0"
ICON = "resources/icon.ico" if sys.platform == "win32" else "resources/icon.icns"

datas, binaries, hiddenimports = [], [], ["hid"]
for package in ("pyocd", "libusb_package", "cmsis_pack_manager", "capstone", "pylink"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

datas += [("resources/packs/*.pack", "packs"), ("resources/icon.png", ".")]

a = Analysis(
    ["run.py"],
    pathex=["."],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "numpy", "PyQt5", "PyQt6"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=APP_NAME, console=False,
          icon=ICON)
coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{DISPLAY_NAME}.app",
        icon=ICON,
        bundle_identifier="com.divjaklab.stm32devicetool",
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            "NSRequiresAquaSystemAppearance": False,
        },
    )
