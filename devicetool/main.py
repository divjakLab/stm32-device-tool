"""App startup."""

from __future__ import annotations

import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler

from . import config


def _setup_logging() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    try:
        d = config.logs_dir()
        d.mkdir(parents=True, exist_ok=True)
        h = RotatingFileHandler(d / "app.log", maxBytes=1_000_000, backupCount=4,
                                encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(h)
    except OSError:
        pass
    logging.getLogger("pyocd").setLevel(logging.WARNING)


def _init_hid_on_main_thread() -> None:
    # hidapi binds its USB manager to the run loop of the first thread that
    # uses it; a worker thread's run loop dies with the thread and the app
    # later crashes with "trace trap". Initialise it on the main thread.
    if sys.platform != "darwin":
        return
    try:
        import hid
        hid.enumerate()
    except Exception:
        logging.getLogger(__name__).info("hidapi init skipped", exc_info=True)


def make_excepthook(app, show):
    """Log unhandled exceptions and show them with show(text) on the GUI thread.

    PySide6 calls sys.excepthook on the thread where a slot raised; building a
    dialog on a worker thread aborts the app on macOS, so the dialog is posted
    to the application's thread instead.
    """
    from PySide6.QtCore import QThread, QTimer

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        logging.getLogger(__name__).error("unhandled exception\n%s", text)
        if QThread.currentThread() is app.thread():
            show(text)
        else:
            QTimer.singleShot(0, app, lambda: show(text))

    return hook


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--selftest" in argv:
        from .selftest import run
        return run()

    _setup_logging()
    _init_hid_on_main_thread()

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox

    from .core.storage import Settings
    from .ui.main_window import MainWindow

    app = QApplication(argv)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationVersion(config.APP_VERSION)
    icon = config.resource_dir() / "icon.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    def show(text: str) -> None:
        box = QMessageBox(QMessageBox.Icon.Critical, config.APP_NAME,
                          "Unexpected error: " + text.strip().splitlines()[-1])
        box.setDetailedText(text)
        box.exec()

    sys.excepthook = make_excepthook(app, show)
    window = MainWindow(Settings(config.support_dir() / "settings.json"))
    window.show()
    return app.exec()
