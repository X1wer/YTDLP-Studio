"""Az alkalmazás indítása: DPI, betűtípus, téma, hibakezelés."""
from __future__ import annotations

import sys
import traceback

from PySide6.QtCore import QLibraryInfo, QLocale, Qt, QTranslator
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
    # A Qt saját feliratai (pl. Igen/Nem gombok, szövegmező helyi menüje) magyarul.
    translator = QTranslator(app)
    if translator.load(QLocale(QLocale.Language.Hungarian), "qtbase", "_",
                       QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
    font = QFont("Segoe UI Variable Text")
    if not font.exactMatch():
        font = QFont("Segoe UI")
    font.setPointSizeF(10)
    app.setFont(font)
    return app


def selftest(output: str) -> int:
    """Indítási önellenőrzés (pl. tiszta Windows-környezetben): ablak + összetevők."""
    import json
    import platform
    from pathlib import Path
    from PySide6.QtCore import QTimer
    from .. import engine
    from ..settings import app_dir, data_dir
    result: dict = {"version": __version__, "python": platform.python_version(),
                    "frozen": bool(getattr(sys, "frozen", False)), "app_dir": str(app_dir())}
    code = 1
    try:
        app = create_app([sys.argv[0]])
        settings = Settings.load()
        theme.manager.apply(settings.theme)
        from .main_window import MainWindow
        window = MainWindow(settings)
        window.show()
        QTimer.singleShot(1500, app.quit)
        app.exec()
        result["window"] = {"shown": True, "width": window.width(), "height": window.height(),
                            "dpr": window.devicePixelRatioF()}
        result["tools"] = {name: engine.tool_version(name) for name in ("yt-dlp", "ffmpeg", "ffprobe", "deno")}
        try:
            from PySide6 import QtMultimedia  # noqa: F401
            result["multimedia"] = True
        except Exception as exc:  # noqa: BLE001
            result["multimedia"] = f"hiba: {exc}"
        result["data_dir"] = str(data_dir())
        result["ok"] = all(result["tools"].values())
        code = 0 if result["ok"] else 2
        window.close()
    except Exception:  # noqa: BLE001
        result["error"] = traceback.format_exc()
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return code


def run() -> int:
    if "--selftest" in sys.argv:
        index = sys.argv.index("--selftest")
        target = sys.argv[index + 1] if len(sys.argv) > index + 1 else "selftest.json"
        return selftest(target)
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
