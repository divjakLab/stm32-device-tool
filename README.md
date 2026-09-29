# STM32 Device Tool

Desktop app (macOS and Windows) for the NUCLEO-U575ZI-Q: flash a `.hex`,
watch the live UART log, send commands, and see crash reports and reset
reasons.

| Document | For |
|---|---|
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | Everyone using the app: install on Mac/Windows, flashing, logs, commands, diagnostics, troubleshooting, file locations |
| [docs/BUILDING.md](docs/BUILDING.md) | Building the `.dmg` / `Setup.exe`, running from source, releasing, code layout, changing the target MCU |
| [docs/spec.md](docs/spec.md) | Design: what the app does and why |

## Quick start

**Use it:** macOS → open the `.dmg`, drag the app to Applications,
right-click → Open the first time. Windows → run `Setup.exe`, then install
ST's ST-LINK driver (STSW-LINK009) once. Plug the board into the ST-LINK
port (CN1).

**Build it:** macOS → `./build_macos.sh`. Windows → `./make_windows_kit.sh`
on the Mac, then `build_windows.bat` on a Windows PC.

**Develop:**
```bash
python3.13 -m venv .venv && .venv/bin/pip install -r requirements-build.txt
.venv/bin/pytest -q && .venv/bin/python run.py
```

## License

MIT — see [LICENSE](LICENSE).

The bundled device pack `resources/packs/Keil.STM32U5xx_DFP.3.2.0.pack` is by
Arm Keil / STMicroelectronics under Apache-2.0 and BSD-3-Clause; its license
text is in [resources/packs/LICENSES-Keil.STM32U5xx_DFP.txt](resources/packs/LICENSES-Keil.STM32U5xx_DFP.txt).
Runtime dependencies (pyOCD, PySide6/Qt under LGPLv3, pyserial, pyelftools,
intelhex, hidapi, libusb) keep their own licenses.
