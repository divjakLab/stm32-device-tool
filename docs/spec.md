# STM32 Device Tool — Design Spec

Date: 2026-09-29
Status: draft, awaiting review

## 1. Purpose

A small macOS app that lets colleagues who don't use a terminal:

1. flash a `.hex` into the STM32U575 on a NUCLEO-U575ZI-Q (on-board ST-LINK/V3),
2. watch the device's live UART log,
3. send commands to the device,
4. see when the device has crashed and why, and why it last reset.

Success: a colleague opens `STM32 Device Tool.app` from a `.dmg`, plugs in the
board, flashes a file, and reads the log, without installing anything else
and without a terminal.

Out of scope for v1: Windows build, RTT/SWO logging (needs firmware changes),
FreeRTOS task-list awareness, other MCUs (target is a config constant, so it
can be changed later).

## 2. Platform and packaging

- Python 3.13 + PySide6 (Qt 6) + pyOCD 0.45.1 (pinned, same as the existing
  updater) + pyserial + pyelftools.
- Packaged with PyInstaller into `STM32 Device Tool.app`, wrapped in a `.dmg`
  by `build_macos.sh` (based on `stm32-updater/build_macos.sh`). Optional
  Developer ID signing + notarization through environment variables; without
  them the app is ad-hoc signed and users right-click → Open once.
- The STM32U5 CMSIS pack (`Keil.STM32U5xx_DFP.3.2.0.pack`) is bundled inside
  the app.
- The build runs `--selftest` on the finished `.app` and fails if anything is
  missing (pack, probe drivers, libusb, Qt plugins, pyserial).
- Lives in `stm32-device-tool/` beside `stm32-updater/`. The old updater is
  not changed.

## 3. User interface

One window, minimum about 900×600, follows macOS light/dark mode.

**Header bar (always visible):** connection state, for example
`● NUCLEO-U575ZI-Q · STLINK-V3` (green), `● No board` (grey), or
`● Board busy` (orange). The app connects automatically when a board is
plugged in. Below it are three tabs: **Flash · Logs · Diagnostics**. The
Diagnostics tab shows a red dot while a crash is detected.

### 3.1 Flash tab
- File picker plus drag-and-drop of a `.hex` onto the window. The last file
  and folder are remembered.
- File info: name, size, address range, modified time.
- **Flash** button. Steps shown with a progress bar: Connecting → Programming
  → Verifying → Restarting.
- On success the app shows a green confirmation and switches to **Logs**.
- On failure it shows a plain-language message with a "Details" disclosure.
- The Flash button is disabled while there's no board or a flash is running.

### 3.2 Logs tab
- Live UART text. Every line is prefixed with a local timestamp
  `HH:MM:SS.mmm`. Incomplete lines are flushed after 200 ms of silence so a
  prompt without a newline still appears.
- Colors: lines matching `error|fail|fault|assert` (case-insensitive) in red,
  `warn` in yellow. App-generated markers such as
  `── flashed firmware.hex ──` and `── board reset ──` in grey italics.
- Toolbar: Filter box (plain substring, case-insensitive, live), Pause
  (freezes the view; recording continues; a counter shows how many new lines
  arrived), Clear, Save… (a `.txt` of all recorded lines, not only the
  filtered ones), baud-rate selector (default 115200; 9600, 57600, 230400,
  460800, 921600).
- Buffer: the last 100,000 lines in memory; older lines are dropped from the
  view but kept in the auto-saved session log (§5).
- The serial port stays open during flashing and resets. It belongs to the
  ST-LINK, not the target, so boot output after a flash is captured.

### 3.3 Send area (bottom of the Logs tab)
- Input line + **Send** button. Enter sends. Line ending selector: `LF`
  (default), `CR`, `CR+LF`, `None`.
- ↑ / ↓ goes through the send history (last 100 entries, kept across
  restarts).
- **Command library** panel (collapsible, to the right of or above the input):
  - Commands grouped in folders (for example "Examples", "Wi-Fi", "Debug").
  - Clicking a command puts its text into the input so it can be edited
    before sending. Double-click sends it directly.
  - Placeholders `{name}` in a command: picking it opens a small form with
    one field per placeholder (the field remembers its last value); OK sends
    the filled-in text.
  - ➕ New, Edit, Duplicate, Delete, drag to reorder or regroup.
  - Import / Export as `.json` to share with colleagues.
  - Ships with an "Examples" group, clearly labelled as examples:
    `help`, `version`, `reboot`, `set {key} {value}`, `get {key}`.
    (The current firmware reads no UART commands; the examples show how it
    works.)
- Storage: `~/Library/Application Support/STM32 Device Tool/commands.json`.

### 3.4 Diagnostics tab
- **Status:** Running / Crashed / Halted / In reset / No board, with the time
  of the last check.
- **Last reset reason:** decoded from the RCC reset-flag register (power-on /
  brown-out, reset pin, independent watchdog, window watchdog, software reset,
  low-power, option-byte load). Refreshed on connect and after every flash.
  If the firmware clears the flags, the app shows "unknown (flags cleared by
  firmware)". The current firmware does clear them (register read
  0x00004400 on 2026-09-29) but prints
  `Reset cause: … (RCC->CSR = 0x…)` at boot; the app decodes that log line
  too and shows it as "Reported by firmware".
- **Crash report**, filled in when a fault is detected:
  - summary in plain words, for example
    "Stack overflow in an RTOS task (UsageFault → HardFault)",
  - decoded fault flags (CFSR, HFSR; MMFAR/BFAR when valid),
  - active exception, EXC_RETURN decoded (thread/handler, PSP/MSP),
  - core registers and the stacked frame (R0–R3, R12, LR, PC, xPSR), with a
    note that the frame may be unreliable after a stack overflow,
  - **with an `.elf` loaded:** PC and LR shown as `function+offset (file:line)`.
- Buttons: **Load .elf…** (remembered per `.hex` file path), **Copy report**
  (plain text to the clipboard), **Save report…**, **Reset board**,
  **Check now**.

## 4. Architecture

```
stm32-device-tool/
  run.py               entry point used by PyInstaller
  devicetool/          (the Python package)
    main.py            startup, hidapi main-thread init
    selftest.py        --selftest checks
    config.py          target, pack name, device ID, RCC addresses, defaults
    core/              no Qt imports; unit-testable
      probe.py         the one pyOCD session: flash, verify, reset,
                       reset reason, fault snapshot
      serial_link.py   port discovery + reader + writer
      fault.py         pure decoding of fault registers / EXC_RETURN
      reset_reason.py  pure decoding of RCC reset flags
      symbols.py       .elf address → function/file:line (pyelftools)
      commands.py      command library model, placeholders, JSON I/O
      logbuffer.py     line assembly, timestamps, classification, filtering
    ui/
      main_window.py   header + tabs
      flash_tab.py
      logs_tab.py      log view + send area + command library
      diagnostics_tab.py
      workers.py       QThread workers bridging core → Qt signals
  resources/           icon, bundled pack
  tests/               pytest, no hardware needed
  build_macos.sh, device_tool.spec, entitlements.plist, requirements*.txt
```

**Threads.** The GUI thread only touches widgets. Three workers:
1. **ProbeWorker** owns the single pyOCD session and runs a queue of jobs
   (connect, flash, health check, reset, fault snapshot). Only this thread
   talks SWD.
2. **SerialWorker** reads the port and emits text chunks; writes are queued
   into it.
3. **Board watcher** (a timer in ProbeWorker, every 1.5 s) checks probe
   presence and health.

Workers talk to the UI only through Qt signals. `hidapi` is initialised on the
main thread before any worker starts (the macOS trace-trap fix from the
existing updater).

**Serial port discovery.** Using pyserial `list_ports`: the ST-LINK VCP whose
USB serial number equals the pyOCD probe's `unique_id`. Fallback: the first
port with VID 0x0483. If the port is busy, the header shows
"Serial port busy — close picocom/CubeIDE", naming the process when `lsof`
finds it.

**Health check without disturbing the firmware.** While the target runs, the
app reads over the debug port, without halting:
- `DHCSR` (0xE000EDF0): `S_LOCKUP`, `S_HALT`, `S_RESET_ST`,
- `HFSR` (0xE000ED2C) and `CFSR` (0xE000ED28).
A crash counts as detected when HFSR/CFSR are non-zero or the core is locked
up. Only then does the app halt the core once (a few ms) to take the
register snapshot, and then resumes it: the target stays in its fault
handler, as it would anyway. The session connects with `connect_mode=attach`,
so connecting never resets or halts the board. Flashing uses
`halt` → `under-reset` fallback, like the existing updater.

**Flashing** reuses the existing, proven logic (`stm32_updater.py`
`Flasher.download`): parse the hex first, program with pyOCD `FileProgrammer`
(smart flash), read back and compare every flash segment, reset. After a
flash the fault state is cleared and the reset reason is re-read.

## 5. Error handling

Every error shown to the user has a plain one-line message, an action to take,
and a "Details" disclosure with the technical text.

| Situation | Message / behaviour |
|---|---|
| No probe | "No board found" + cable / ST-LINK port / close other tools hints. Keeps watching and connects automatically when a board appears. |
| Probe or port in use | "Board busy: <program> is using it." |
| Target doesn't respond | Automatic retry under reset, then "Unplug the board, wait 5 s, plug back in." |
| Invalid / empty hex | Refused before anything is erased. |
| Verify mismatch | "Verification failed at 0x…; flash again." Board is not reset. |
| Unplug during flash | "Board disconnected during update — reconnect and flash again." |
| Unplug during logging | Log marker `── disconnected ──`; reconnects automatically. |
| Unexpected exception | Dialog with the message; full traceback written to the app log. |

App log: `~/Library/Logs/STM32 Device Tool/app.log`, rotated at 5 × 1 MB.
Session UART logs: `~/Library/Logs/STM32 Device Tool/sessions/` (one file per
connection, last 50 kept).

## 6. Persistence

`~/Library/Application Support/STM32 Device Tool/`:
`settings.json` (last hex, last folder, baud rate, line ending, window size,
elf per hex), `commands.json`, `history.json`.

## 7. Testing

**Unit tests (pytest, no hardware):**
- `fault.py`: the real values captured on 2026-09-29
  (CFSR 0x00100000, HFSR 0x40000000, EXC_RETURN 0xFFFFFFBC, IPSR 3) →
  "stack overflow, thread mode, PSP"; plus the MemManage, BusFault, UsageFault
  and forced-HardFault cases.
- `reset_reason.py`: each flag and combinations.
- `commands.py`: placeholder parsing and filling, JSON round-trip, import of
  malformed files.
- `logbuffer.py`: line assembly across chunk boundaries, the 200 ms flush,
  classification, filtering, CR/LF handling.
- `serial_link.py`: port matching logic with fake port lists.
- `symbols.py`: lookup against a small test ELF.

**Hardware checks (NUCLEO-U575ZI-Q):** flash + verify; boot log captured
after flash; crash detection against the current firmware (a real stack
overflow); reset reason after power-on vs. the reset button; unplug/replug
during logging and during flashing; port-busy detection with picocom running.

**Packaged app:** `--selftest` on the built `.app`; manual launch from the
mounted `.dmg`.

## 8. Open points

- RCC reset-flag register address and bit layout for STM32U575 are taken
  from RM0456 (RCC_CSR at RCC base + 0xF4, flags in bits 25–31) and must be
  confirmed on hardware during implementation.
- App name and icon: "STM32 Device Tool" with a generic chip icon unless you
  want something else.
