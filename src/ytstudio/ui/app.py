"""Az alkalmazás indítása: DPI, betűtípus, téma, hibakezelés."""
from __future__ import annotations

import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from .. import APP_ID, APP_NAME, __version__
from ..settings import Settings
from . import theme
from .logbus import log


def _excepthook(exc_type, exc, tb) -> None:
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    log("VÁRATLAN HIBA:\n" + text)
    app = QApplication.instance()
    if app is not None:
        QMessageBox.critical(None, APP_NAME, "Váratlan hiba történt. A program tovább használható, "
                             "a részleteket a Napló ablakban és a data/logs mappában találod.\n\n"
                             f"{exc_type.__name__}: {exc}")


def create_app(argv: list[str] | None = None) -> QApplication:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_ID}.App")
        except (OSError, AttributeError):
            pass
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_ID)
    app.setStyle("Fusion")
    font = QFont("Segoe UI Variable Text")
    if not font.exactMatch():
        font = QFont("Segoe UI")
    font.setPointSizeF(10)
    app.setFont(font)
    return app


def run() -> int:
    app = create_app()
    sys.excepthook = _excepthook
    settings = Settings.load()
    theme.manager.apply(settings.theme)
    try:
        hints = QGuiApplication.styleHints()
        hints.colorSchemeChanged.connect(lambda _s: theme.manager.mode == "system" and theme.manager.apply())
    except AttributeError:
        pass
    from .main_window import MainWindow
    window = MainWindow(settings)
    log(f"{APP_NAME} {__version__} elindult.")
    window.show()
    theme.set_dark_title_bar(window, theme.manager.dark)
    return app.exec()
