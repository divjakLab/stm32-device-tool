# STM32 Device Tool — Building & Maintaining

For whoever runs the app from source, builds the installers, or changes the
code. End-user instructions are in [USER_GUIDE.md](USER_GUIDE.md); the design
is in [spec.md](spec.md).

---

## 1. Run from source

Needs Python **3.13** (macOS: Homebrew `python@3.13` or python.org; Windows:
python.org 64-bit).

**macOS**
```bash
cd stm32-device-tool
python3.13 -m venv .venv
.venv/bin/pip install -r requirements-build.txt
.venv/bin/pytest -q                  # 101 tests, no board needed
.venv/bin/python run.py              # start the app
.venv/bin/python run.py --selftest   # check all components are present
```

**Windows** (Command Prompt in the folder)
```bat
py -3.13 -m venv .venv
.venv\Scripts\pip install -r requirements-build.txt
.venv\Scripts\pytest -q
.venv\Scripts\python run.py
```

`test_symbols.py` needs `clang` to build a small test `.elf`; it is skipped
automatically when clang is missing (normal on Windows).

---

## 2. Build the macOS app (`.dmg`)

On a Mac:
```bash
./build_macos.sh
```
It creates `.venv` if needed, runs the tests, creates the icon if it's missing,
builds `dist/STM32 Device Tool.app` with PyInstaller, runs `--selftest` on the
finished app (the build stops if anything is missing), signs it and makes
`output/STM32DeviceTool-1.0.0.dmg`.

The app is built for the build Mac's CPU (Apple Silicon → arm64 only).

**Signing (optional, removes the right-click → Open step):** with an Apple
Developer account, set before building:
```bash
export SIGN_IDENTITY="Developer ID Application: Your Company (TEAMID)"
export NOTARY_PROFILE="my-notary-profile"   # once: xcrun notarytool store-credentials ...
```
Without them the app is ad-hoc signed (required on Apple Silicon) and users
right-click → Open the first time.

---

## 3. Build the Windows installer (`Setup.exe`)

A Windows `.exe` can only be built **on Windows** (PyInstaller does not
cross-compile).

1. On the Mac, pack the sources:
   ```bash
   ./make_windows_kit.sh      # -> output/STM32DeviceTool-windows-build-kit.zip
   ```
   (Or copy the folder without `.venv`, `build`, `dist`, `output`.)
2. On the Windows PC, install once:
   - Python 3.13 **64-bit (x64)** from python.org, with **"Add python.exe to PATH"**
   - Inno Setup 6.3+ (default location)
3. Unzip, double-click **`build_windows.bat`**. It creates `.venv`, installs
   everything, runs the tests, builds `dist\STM32DeviceTool\` with PyInstaller,
   runs `--selftest` on the result and packs it with Inno Setup into
   **`output\STM32DeviceTool-Setup-1.0.0.exe`**.

If the build stops, the window stays open with the error; `selftest.log`
contains the self-test output.

Windows needs ST's **STSW-LINK009** driver on every PC that uses the board
(the installer's last page links to it). The Windows installer is not
code-signed, so SmartScreen shows "More info → Run anyway".

---

## 4. Releasing a new version

1. Change the version in: `devicetool/config.py` (`APP_VERSION`),
   `device_tool.spec` (`VERSION`), `build_macos.sh` (`VERSION`),
   `installer_windows.iss` (`AppVersion`), and the file names in
   `build_windows.bat` / docs.
2. Never change `AppId` in `installer_windows.iss` — it lets new versions
   upgrade the old one in place.
3. Build on both platforms, then test on a board: flash, boot log, reset
   button, unplug/replug, crash report (see *Hardware test checklist* below).

---

## 5. How the code is organised

```
run.py                  entry point (also PyInstaller's)
devicetool/
  config.py             target MCU, baud rates, timings, file locations
  main.py               startup, logging, hidapi init, error dialog
  selftest.py           --selftest checks
  core/                 no Qt — unit-tested without hardware
    probe.py            the pyOCD session: flash+verify, health, crash snapshot, reset
    hexfile.py          .hex loading/validation
    serial_link.py      ST-LINK serial port: find, open, busy detection
    logbuffer.py        bytes → timestamped, colored lines; session files
    fault.py            Cortex-M33 fault register decoding + report text
    reset_reason.py     RCC_CSR reset flags
    symbols.py          .elf → function+offset (file:line)
    commands.py         command library, {placeholders}, send history
    storage.py          JSON files, settings
  ui/                   PySide6
    main_window.py      header, tabs, owns the two worker threads
    workers.py          ProbeWorker, SerialWorker (each in its own QThread)
    flash_tab.py, logs_tab.py, log_view.py, command_panel.py, diagnostics_tab.py
    style.py            colors (light/dark), fonts
tests/                  pytest
tools/make_icon.py      draws icon.png / icon.ico / icon.icns
resources/              icons + the STM32U5 CMSIS pack
```

**Rules that keep it stable:**
- Only `ProbeWorker`'s thread talks to the debugger, only `SerialWorker`'s
  thread to the serial port, only the GUI thread to widgets. They talk only
  through Qt signals.
- On macOS `hid.enumerate()` must run on the main thread before any worker
  starts (`main._init_hid_on_main_thread`) — otherwise the app crashes with
  "trace trap" on the first board scan. Same fix as in the old updater.
- Crash detection reads DHCSR/CFSR/HFSR while the CPU runs; it only halts the
  CPU (for milliseconds) after a fault has already happened.

---

## 6. Changing things

| Want to… | Change |
|---|---|
| Support another STM32 | `config.py` target block (`PYOCD_TARGET`, `EXPECTED_DEV_ID`, `DEVICE_NAME`, `TARGET_DISPLAY_NAME`, `RCC_CSR_ADDR`) + replace the `.pack` in `resources/packs/`. Find the target name with `pyocd list --targets --pack <file>`. |
| Change the default baud rate | `config.DEFAULT_BAUD` (users' saved choice still wins) |
| Change the example commands | `EXAMPLES` in `core/commands.py` (only used when a user has no library yet) |
| Change log colors / keywords | `_ERROR_RE` / `_WARN_RE` in `core/logbuffer.py`, colors in `ui/style.py` |
| Change the icon | edit `tools/make_icon.py`, run it, rebuild |

Run `pytest -q` after every change; `build_*` scripts refuse to build when a
test fails.

---

## 7. Hardware test checklist

Run before each release, on a real board, with the packaged app:

1. **Start:** app opens from Applications / Start menu; header turns green
   within ~2 s; the log header shows the port and baud rate.
2. **Crash detection:** with firmware that crashes, Diagnostics gets a red dot
   and a sensible summary; *Copy report* pastes header + report.
3. **Flash:** all stages run, `✓ Update successful`, the app switches to Logs,
   a `── flashed … ──` marker appears and the boot log follows.
4. **Reset reason:** reset button → "Reset pin"; unplug/replug → power-on
   (chip or firmware-reported line).
5. **Unplug/replug:** during logging → `── serial disconnected ──`, "No board",
   reconnects by itself; during flashing → clear error, flashing again works.
6. **Busy port:** open the port in picocom / PuTTY first → "Serial port busy";
   close it → log connects within ~1 s.
7. **Logs:** filter, Pause/Resume counter, Clear, Save… (timestamps), baud
   change marker.
8. **Commands:** click → input, double-click → send (`→ …` echo),
   placeholder form, New/Edit/Duplicate/Delete, drag between groups,
   Export → Import (no duplicates), ↑/↓ history.
