# STM32 Device Tool — User Guide

For flashing firmware to a **NUCLEO-U575ZI-Q** board, watching its live log,
sending commands and seeing why the device crashed or restarted.
Works on macOS and Windows. No other software needed.

---

## 1. Install

### macOS
1. Open `STM32DeviceTool-1.0.0.dmg`.
2. Drag **STM32 Device Tool** onto the **Applications** folder.
3. First start only: in Applications, **right-click** the app → **Open** →
   **Open**. (macOS asks this once because the app is not signed by the Apple
   App Store.) After that, start it normally.

No driver is needed on a Mac.

### Windows
1. Run `STM32DeviceTool-Setup-1.0.0.exe` and click through the installer.
   If Windows shows "Windows protected your PC", click **More info** →
   **Run anyway**.
2. **Once per PC: install ST's ST-LINK USB driver (STSW-LINK009).** The last
   installer page has a checkbox that opens the download page, or get it at
   <https://www.st.com/en/development-tools/stsw-link009.html>.
   Without this driver the app shows "No board" and no log.
3. Start the app from the Start menu or the desktop shortcut.

---

## 2. Connect the board

1. Plug a USB **data** cable (not a charge-only cable) into the board's
   **ST-LINK** USB port (CN1, next to the ST-LINK chip).
2. **Close other programs that use the board**: STM32CubeIDE,
   STM32CubeProgrammer, picocom, PuTTY, Tera Term, or a second copy of this app.
   Only one program at a time can use the board.

The top-left of the window shows the board state:

| Header | Meaning |
|---|---|
| 🟢 **NUCLEO-U575ZI-Q · STLINK-V3** | Connected, ready |
| ⚪ **No board — connect the ST-LINK USB port (CN1)** | Nothing plugged in (or, on Windows, driver missing) |
| 🟠 **Board busy — close STM32CubeIDE / CubeProgrammer…** | Another program is using the debugger |

The top-right shows the log connection, e.g. `🟢 Log: /dev/cu.usbmodem1101 @ 921600`
(macOS) or `🟢 Log: COM5 @ 921600` (Windows). 🟠 *Serial port busy — close …*
means another terminal program has the log port open.

The app connects by itself whenever a board is plugged in — no Connect button.

---

## 3. Flash firmware (Flash tab)

1. Click **Choose…** and pick the `.hex` file — or drag the `.hex` file onto
   the window. The app shows its size, address range and date. The last file
   is remembered.
2. Click **Flash**. Progress: *Connecting → Programming → Verifying →
   Restarting*. **Don't unplug the board while it says Programming.**
3. When it shows **✓ Update successful**, the app switches to the **Logs**
   tab so you can see the new firmware start.

If something goes wrong, the message says what to do; **Details…** shows the
technical text to send to the developer. The board is only restarted after
the whole file has been written and verified.

---

## 4. Live log (Logs tab)

Everything the firmware prints over the ST-LINK serial port, each line with
the time it arrived (`HH:MM:SS.mmm`).

- **Colors:** red = lines with *error / fail / fault / assert*, yellow = *warn*,
  grey italics = notes from the app itself, e.g. `── flashed firmware.hex ──`,
  `── board reset ──`, `── serial disconnected ──`.
- **Filter…** — shows only lines that contain the text you type (not case
  sensitive). Clear it to see everything again.
- **Pause** — freezes the view so you can read; logging continues in the
  background. The button shows how many new lines arrived; click it again to
  resume.
- **Clear** — empties the view.
- **Save…** — saves the whole log (not only the filtered lines) as a `.txt`.
- **Baud rate** — **921600** for the current firmware (the default). If you
  see nothing or only garbage with a different firmware, try another rate;
  the choice is remembered.

Logs are also **saved automatically**, one file per connection (the last 50
are kept) — see *Where are my files?* below.

---

## 5. Send commands to the device

At the bottom of the Logs tab:

- Type in **Send to device…** and press **Enter** (or **Send**).
- **Line end** — what's added after your text: `LF` (default), `CR`,
  `CR+LF` or `None`. Use what the firmware expects.
- **↑ / ↓** in the input box — previous commands, like in a terminal.
- Sent text appears in the log as `→ your command`.

> If your firmware does not read commands from the serial port, sending
> does nothing — commands only do something once the developer adds a serial
> command handler. The feature is ready for that.

### Command library (right-hand panel, **Commands ▸** to show/hide)

- **Click** a command → it is put into the input box, so you can edit it
  before pressing Enter.
- **Double-click** → sends it immediately.
- Commands with fill-in fields, e.g. `wifi set {ssid} {password}`: on
  double-click a small form asks for each value (the last value is
  remembered), then **Send**.
- **➕ New / Edit / Duplicate / Delete** — manage your own commands. A command
  has a name, a group (e.g. "Wi-Fi", "Debug") and the text. Write
  `{something}` for a value you want to fill in when sending.
- **Drag** commands to reorder them or move them to another group.
- **Export… / Import…** — save the library as a `.json` file to share with
  colleagues; importing adds new commands and skips ones you already have.

The **Examples** group (`help`, `version`, `reboot`, `set {key} {value}`,
`get {key}`) only shows how it works — the real command names depend on the
firmware.

---

## 6. Crashes and restarts (Diagnostics tab)

- **Status:** *Running*, *Crashed*, *Halted by a debugger*,
  *Not responding*, or *No board*. The app checks every 1.5 s **without
  stopping the firmware**.
- **Last reset (chip)** — why the board last restarted: power-on / brown-out,
  reset pin (button or debugger), independent or window watchdog, software
  reset, low-power reset, option-byte load. With the current firmware this
  usually says *Unknown (reset flags already cleared by the firmware)*,
  because the firmware reads and clears them at start-up.
- **Last reset (reported by firmware)** — the same information decoded from
  the firmware's own start-up line `Reset cause: … (RCC->CSR = 0x…)`.

### When the device crashes
The **Diagnostics** tab label turns red with a ● and the **Crash report**
shows:
- a plain-language summary, e.g.
  *Stack overflow in an RTOS task (UsageFault → HardFault)*,
- the fault registers and where the CPU was when it crashed.

Buttons:
- **Load .elf…** — pick the `.elf` file from the **same build** as the `.hex`
  (the developer has it). Addresses then show function names and source lines,
  e.g. `BLE_Task+0x10 (main_app_BLE.c:120)`. The app remembers which `.elf`
  belongs to which `.hex`.
- **Copy report** — copies everything (board, file, reset reason, report) to
  the clipboard, ready to paste into a message to the developer.
- **Save report…** — the same as a `.txt` file.
- **Reset board** — restarts the firmware.
- **Check now** — reads the crash state again immediately.

After the board restarts, the red dot goes away and the old report stays
visible, marked *PREVIOUS CRASH*.

---

## 7. Troubleshooting

| Problem | What to do |
|---|---|
| **No board** | Use the ST-LINK USB port (CN1) and a data cable. Windows: install the ST-LINK driver (STSW-LINK009). Try another USB port. |
| **Board busy** | Close STM32CubeIDE, STM32CubeProgrammer or another copy of this app, then wait a second. |
| **Serial port busy** | Close picocom / screen (macOS) or PuTTY / Tera Term (Windows). The log reconnects within a second. |
| **Log is empty** | Check the baud rate (921600 for the current firmware). If the device crashed right away there may be nothing to print — look at Diagnostics. Press **Reset board** to see the start-up log. |
| **Log shows garbage** | Wrong baud rate — pick the one the firmware uses. |
| **"Microcontroller does not respond"** | Unplug the USB cable, wait 5 seconds, plug it back in, flash again. Check the board's jumpers are in their default position. |
| **Verification failed** | Flash again. If it keeps failing, send the Details text to the developer. |
| **macOS: "can't be opened"** | Right-click the app → Open → Open (first time only). |
| **Windows: "Windows protected your PC"** | More info → Run anyway. |
| **The app closed unexpectedly** | Send `app.log` (see below) to the developer. |

---

## 8. Where are my files?

| | macOS | Windows |
|---|---|---|
| Settings, command library, send history | `~/Library/Application Support/STM32 Device Tool/` | `%APPDATA%\STM32 Device Tool\` |
| Automatic session logs (last 50) | `~/Library/Logs/STM32 Device Tool/sessions/` | `%LOCALAPPDATA%\STM32 Device Tool\Logs\sessions\` |
| App log (`app.log`, for bug reports) | `~/Library/Logs/STM32 Device Tool/` | `%LOCALAPPDATA%\STM32 Device Tool\Logs\` |

macOS: in Finder press **⇧⌘G** and paste the path. Windows: paste the path
into the Explorer address bar.

Deleting the settings folder resets the app to defaults (your own commands
are in `commands.json` there — export them first if you want to keep them).
