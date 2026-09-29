import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from devicetool.core.fault import FaultSnapshot  # noqa: E402
from devicetool.core.logbuffer import Level, LogLine  # noqa: E402
from devicetool.core.probe import BoardInfo, Health  # noqa: E402
from devicetool.core.storage import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication(sys.argv)


def test_logs_tab_filter_pause_send(app, tmp_path):
    from devicetool.ui.logs_tab import LogsTab
    tab = LogsTab(Settings(tmp_path / "s.json"), tmp_path)
    sent = []
    tab.sendRequested.connect(sent.append)
    tab.add_lines([LogLine(1.0, "BLE ok", Level.NORMAL), LogLine(1.0, "wifi fail", Level.ERROR)])
    assert tab.view.document().blockCount() == 2
    tab.filter.setText("wifi")
    assert tab.view.toPlainText().endswith("wifi fail")
    tab.filter.setText("")
    tab.pause_btn.setChecked(True)
    tab.add_lines([LogLine(2.0, "new", Level.NORMAL)])
    assert tab.pause_btn.text() == "Resume (1 new)"
    tab.pause_btn.setChecked(False)
    assert tab.view.document().blockCount() == 3
    tab.input.setText("version")
    tab._send_input()
    assert sent == [b"version\n"] and tab.history.items == ["version"]


def test_diagnostics_crash_flow(app, tmp_path):
    from devicetool.ui.diagnostics_tab import DiagnosticsTab
    tab = DiagnosticsTab(Settings(tmp_path / "s.json"))
    states = []
    tab.crashStateChanged.connect(states.append)
    tab.set_board(BoardInfo("id", "STLINK-V3", "STM32U575, rev 0x3007"))
    regs = {"lr": 0xFFFFFFBC, "xpsr": 0x21000003, "pc": 0x0800715E}
    tab.on_crash(FaultSnapshot(0x100000, 0x40000000, 0, 0, regs, None))
    assert "Stack overflow in an RTOS task" in tab.report_text()
    tab.on_health(Health("running"))
    assert states == [True, False]
    assert "PREVIOUS CRASH" in tab.report.toPlainText()
    tab.set_firmware_reset(0x14004400)          # SFTRSTF + PINRSTF
    assert "Software reset" in tab.report_text()


def test_flash_tab_validates_file(app, tmp_path):
    from intelhex import IntelHex
    from devicetool.ui.flash_tab import FlashTab
    tab = FlashTab(Settings(tmp_path / "s.json"))
    bad = tmp_path / "bad.hex"
    bad.write_text("x")
    assert not tab.set_file(str(bad)) and not tab.flash_btn.isEnabled()
    good = tmp_path / "good.hex"
    ih = IntelHex(); ih.puts(0x08000000, b"\x01\x02"); ih.write_hex_file(str(good))
    assert tab.set_file(str(good))
    assert not tab.flash_btn.isEnabled()        # no board yet
    tab.set_board_available(True)
    assert tab.flash_btn.isEnabled()


def test_diagnostics_tab_color_restored_after_crash_clears(app, tmp_path, monkeypatch):
    from devicetool import config
    from devicetool.ui import main_window
    monkeypatch.setattr(config, "support_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_workers", lambda self: None)
    monkeypatch.setattr(main_window.MainWindow, "_wire", lambda self: None)
    w = main_window.MainWindow(Settings(tmp_path / "s.json"))
    bar = w.tabs.tabBar()
    i = w.tabs.indexOf(w.diag_tab)
    before = bar.tabTextColor(i)
    w._on_crash_state(True)
    assert bar.tabTextColor(i) != before
    w._on_crash_state(False)
    assert bar.tabTextColor(i) == before and w.tabs.tabText(i) == "Diagnostics"


def test_flash_tab_shows_absolute_folder(app, tmp_path, monkeypatch):
    from intelhex import IntelHex
    from devicetool.ui.flash_tab import FlashTab
    good = tmp_path / "good.hex"
    ih = IntelHex(); ih.puts(0x08000000, b"\x01"); ih.write_hex_file(str(good))
    monkeypatch.chdir(tmp_path)
    tab = FlashTab(Settings(tmp_path / "s.json"))
    assert tab.set_file("good.hex")
    assert tab.hex_path == str(good.resolve())


def test_excepthook_from_worker_thread_shows_dialog_on_gui_thread(app):
    import threading
    from PySide6.QtCore import QThread
    from devicetool.main import make_excepthook
    shown = []
    hook = make_excepthook(app, lambda text: shown.append(QThread.currentThread()))
    t = threading.Thread(target=lambda: hook(ValueError, ValueError("x"), None))
    t.start(); t.join()
    assert shown == []                       # not shown on the worker thread
    for _ in range(20):
        app.processEvents()
    assert shown == [app.thread()]


def test_file_cannot_change_while_flashing(app, tmp_path):
    from intelhex import IntelHex
    from devicetool.ui.flash_tab import FlashTab
    a, b = tmp_path / "a.hex", tmp_path / "b.hex"
    for p in (a, b):
        ih = IntelHex(); ih.puts(0x08000000, b"\x01"); ih.write_hex_file(str(p))
    tab = FlashTab(Settings(tmp_path / "s.json"))
    tab.set_file(str(a)); tab.set_board_available(True)
    tab._flash()
    assert tab.busy
    assert not tab.set_file(str(b)) and not tab.set_file(str(tmp_path / "bad.hex"))
    assert tab.hex_path == str(a)


def test_flash_marker_uses_flashed_file(app, tmp_path, monkeypatch):
    from devicetool import config
    from devicetool.ui import main_window
    monkeypatch.setattr(config, "support_dir", lambda: tmp_path)
    monkeypatch.setattr(main_window.MainWindow, "_start_workers", lambda self: None)
    monkeypatch.setattr(main_window.MainWindow, "_wire", lambda self: None)
    w = main_window.MainWindow(Settings(tmp_path / "s.json"))
    markers = []
    w._marker.connect(markers.append)
    w._start_flash(str(tmp_path / "fw.hex"))
    w.flash_tab._path = None                 # whatever happens to the tab meanwhile
    w._on_flash_finished(True, "ok", "")
    assert markers == ["flashed fw.hex"]
