"""Világos és sötét téma: színtokenek, Qt-stíluslap és a Windows-címsor színe."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from . import icons
from ..settings import data_dir

LIGHT = {
    "bg": "#f3f4f7", "surface": "#ffffff", "surface2": "#f6f7f9", "hover": "#eef0f4",
    "border": "#e2e5ea", "border_strong": "#c9ced6", "text": "#151922", "muted": "#5d6574",
    "faint": "#8b93a1", "accent": "#4f46e5", "accent_hover": "#4338ca", "accent_soft": "#eceafe",
    "accent_text": "#ffffff", "success": "#15803d", "success_soft": "#e6f6ec",
    "warning": "#b45309", "warning_soft": "#fdf3e1", "danger": "#c62828", "danger_soft": "#fdecec",
    "track": "#e4e7ec", "shadow": "#1a000000", "selection": "#dcdafe",
}

DARK = {
    "bg": "#0f1116", "surface": "#171a21", "surface2": "#1d2129", "hover": "#242934",
    "border": "#2a2f3a", "border_strong": "#3a414f", "text": "#e9ebf0", "muted": "#a3aab7",
    "faint": "#6f7785", "accent": "#7c7ff7", "accent_hover": "#9093fa", "accent_soft": "#25264a",
    "accent_text": "#ffffff", "success": "#4ade80", "success_soft": "#173025",
    "warning": "#fbbf24", "warning_soft": "#33280f", "danger": "#f87171", "danger_soft": "#3a1d1f",
    "track": "#2b303b", "shadow": "#40000000", "selection": "#2e3060",
}

FONT_FAMILY = "Segoe UI Variable Text, Segoe UI, Arial"


class ThemeManager(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.mode = "system"
        self.colors = dict(LIGHT)
        self.dark = False

    def c(self, name: str) -> str:
        return self.colors[name]

    def qc(self, name: str, alpha: int | None = None) -> QColor:
        color = QColor(self.colors[name])
        if alpha is not None:
            color.setAlpha(alpha)
        return color

    def system_is_dark(self) -> bool:
        hints = QGuiApplication.styleHints()
        try:
            return hints.colorScheme() == Qt.ColorScheme.Dark
        except AttributeError:
            return False

    def apply(self, mode: str | None = None) -> None:
        if mode:
            self.mode = mode
        self.dark = self.system_is_dark() if self.mode == "system" else self.mode == "dark"
        self.colors = dict(DARK if self.dark else LIGHT)
        app = QApplication.instance()
        if app is None:
            return
        app.setPalette(self._palette())
        app.setStyleSheet(stylesheet(self.colors, self._indicator_dir()))
        for widget in app.topLevelWidgets():
            set_dark_title_bar(widget, self.dark)
        self.changed.emit()

    def _palette(self) -> QPalette:
        c = self.colors
        p = QPalette()
        roles = {
            QPalette.ColorRole.Window: c["bg"], QPalette.ColorRole.WindowText: c["text"],
            QPalette.ColorRole.Base: c["surface"], QPalette.ColorRole.AlternateBase: c["surface2"],
            QPalette.ColorRole.Text: c["text"], QPalette.ColorRole.Button: c["surface"],
            QPalette.ColorRole.ButtonText: c["text"], QPalette.ColorRole.Highlight: c["accent"],
            QPalette.ColorRole.HighlightedText: c["accent_text"], QPalette.ColorRole.ToolTipBase: c["surface"],
            QPalette.ColorRole.ToolTipText: c["text"], QPalette.ColorRole.PlaceholderText: c["faint"],
            QPalette.ColorRole.Link: c["accent"], QPalette.ColorRole.Mid: c["border"],
            QPalette.ColorRole.Light: c["surface2"], QPalette.ColorRole.Dark: c["border_strong"],
        }
        for role, value in roles.items():
            p.setColor(role, QColor(value))
        for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
            p.setColor(QPalette.ColorGroup.Disabled, role, QColor(c["faint"]))
        return p

    def _indicator_dir(self) -> str:
        folder = data_dir() / "cache" / "theme" / ("dark" if self.dark else "light")
        try:
            folder.mkdir(parents=True, exist_ok=True)
            icons.write_svg(folder / "check.svg", "check", self.colors["accent_text"])
            icons.write_svg(folder / "chevron.svg", "chevron-down", self.colors["muted"], 2.0)
            icons.write_svg(folder / "chevron-disabled.svg", "chevron-down", self.colors["faint"], 2.0)
        except OSError:
            pass
        return folder.as_posix()


manager = ThemeManager()


def c(name: str) -> str:
    return manager.c(name)


def qc(name: str, alpha: int | None = None) -> QColor:
    return manager.qc(name, alpha)


def set_dark_title_bar(widget: QWidget, dark: bool) -> None:
    """Windows 10/11: a natív címsor a témához igazodik (DWMWA_USE_IMMERSIVE_DARK_MODE)."""
    if sys.platform != "win32" or not widget.isWindow():
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        value = ctypes.c_int(1 if dark else 0)
        for attribute in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value),
                                                          ctypes.sizeof(value)) == 0:
                break
    except (OSError, AttributeError, ValueError):
        pass


def stylesheet(c: dict[str, str], indicator_dir: str) -> str:
    return f"""
* {{ font-family: {FONT_FAMILY}; font-size: 10pt; }}
QWidget {{ color: {c['text']}; }}
QMainWindow, QDialog, QWidget#root {{ background: {c['bg']}; }}
QWidget#transparent, QScrollArea#workspaceScroll, QWidget#workspace {{ background: transparent; }}
QScrollArea {{ border: none; background: transparent; }}
QToolTip {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border_strong']};
            padding: 6px 8px; border-radius: 6px; }}

QFrame#card {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px; }}
QFrame#subtle {{ background: {c['surface2']}; border: 1px solid {c['border']}; border-radius: 10px; }}
QFrame#actionBar {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px; }}
QFrame#header {{ background: transparent; }}
QFrame#divider {{ background: {c['border']}; max-height: 1px; min-height: 1px; border: none; }}

QLabel {{ background: transparent; }}
QLabel[role="appTitle"] {{ font-size: 15pt; font-weight: 600; }}
QLabel[role="h1"] {{ font-size: 15pt; font-weight: 600; }}
QLabel[role="h2"] {{ font-size: 11.5pt; font-weight: 600; }}
QLabel[role="muted"] {{ color: {c['muted']}; }}
QLabel[role="faint"] {{ color: {c['faint']}; font-size: 9pt; }}
QLabel[role="caption"] {{ color: {c['muted']}; font-size: 9pt; }}
QLabel[role="chip"] {{ background: {c['surface2']}; border: 1px solid {c['border']}; border-radius: 9px;
                       padding: 1px 8px; color: {c['muted']}; font-size: 9pt; }}
QLabel[role="accentChip"] {{ background: {c['accent_soft']}; border-radius: 9px; padding: 1px 8px;
                             color: {c['accent']}; font-size: 9pt; font-weight: 600; }}
QLabel[role="warnText"] {{ color: {c['warning']}; font-size: 9pt; }}
QLabel[role="emptyTitle"] {{ font-size: 16pt; font-weight: 600; }}
QLabel[role="step"] {{ background: {c['accent_soft']}; color: {c['accent']}; border-radius: 13px;
                       font-weight: 700; min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px; }}

QPushButton {{ background: {c['surface']}; border: 1px solid {c['border_strong']}; border-radius: 8px;
               padding: 6px 14px; min-height: 22px; }}
QPushButton:hover {{ background: {c['hover']}; }}
QPushButton:pressed {{ background: {c['border']}; }}
QPushButton:disabled {{ color: {c['faint']}; border-color: {c['border']}; background: {c['surface2']}; }}
QPushButton:focus {{ outline: none; border-color: {c['accent']}; }}
QPushButton[variant="primary"] {{ background: {c['accent']}; color: {c['accent_text']}; border: 1px solid {c['accent']};
                                  font-weight: 600; }}
QPushButton[variant="primary"]:hover {{ background: {c['accent_hover']}; border-color: {c['accent_hover']}; }}
QPushButton[variant="primary"]:disabled {{ background: {c['border']}; border-color: {c['border']}; color: {c['faint']}; }}
QPushButton[size="large"] {{ padding: 9px 20px; font-size: 10.5pt; }}
QPushButton[variant="ghost"] {{ background: transparent; border: 1px solid transparent; padding: 6px 10px; }}
QPushButton[variant="ghost"]:hover {{ background: {c['hover']}; }}
QPushButton[variant="ghost"]:checked {{ background: {c['accent_soft']}; color: {c['accent']}; }}
QPushButton[variant="link"] {{ background: transparent; border: none; color: {c['accent']}; padding: 2px 4px; }}
QPushButton[variant="link"]:hover {{ text-decoration: underline; }}
QPushButton[variant="danger"] {{ color: {c['danger']}; }}

QWidget#segmented {{ background: {c['surface2']}; border: 1px solid {c['border']}; border-radius: 9px; }}
QPushButton[segment="true"] {{ background: transparent; border: 1px solid transparent; border-radius: 7px;
                               padding: 5px 12px; color: {c['muted']}; min-height: 20px; }}
QPushButton[segment="true"]:hover {{ background: {c['hover']}; color: {c['text']}; }}
QPushButton[segment="true"]:checked {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border_strong']};
                                       font-weight: 600; }}
QPushButton[segment="true"]:disabled {{ color: {c['faint']}; }}
QPushButton[segment="true"][large="true"] {{ padding: 8px 16px; font-size: 10.5pt; }}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox {{ background: {c['surface']}; border: 1px solid {c['border_strong']};
               border-radius: 8px; padding: 6px 10px; selection-background-color: {c['accent']};
               selection-color: {c['accent_text']}; }}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {{ border: 1px solid {c['accent']}; }}
QLineEdit:disabled {{ color: {c['faint']}; background: {c['surface2']}; }}
QLineEdit[size="large"] {{ padding: 9px 12px; font-size: 10.5pt; border-radius: 10px; }}
QLineEdit[invalid="true"] {{ border: 1px solid {c['danger']}; }}
QPlainTextEdit#log {{ font-family: Cascadia Mono, Consolas, monospace; font-size: 9pt; }}

QComboBox {{ background: {c['surface']}; border: 1px solid {c['border_strong']}; border-radius: 8px;
             padding: 6px 30px 6px 10px; min-height: 20px; }}
QComboBox:hover {{ background: {c['hover']}; }}
QComboBox:focus {{ border-color: {c['accent']}; }}
QComboBox:disabled {{ color: {c['faint']}; background: {c['surface2']}; border-color: {c['border']}; }}
QComboBox::drop-down {{ border: none; width: 26px; subcontrol-origin: padding; subcontrol-position: center right; }}
QComboBox::down-arrow {{ image: url({indicator_dir}/chevron.svg); width: 14px; height: 14px; }}
QComboBox::down-arrow:disabled {{ image: url({indicator_dir}/chevron-disabled.svg); }}
QComboBox QAbstractItemView {{ background: {c['surface']}; border: 1px solid {c['border_strong']};
             border-radius: 8px; padding: 4px; outline: none; selection-background-color: {c['accent_soft']};
             selection-color: {c['text']}; }}
QComboBox QAbstractItemView::item {{ min-height: 28px; padding: 2px 8px; border-radius: 6px; }}

QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1.5px solid {c['border_strong']};
                        background: {c['surface']}; }}
QCheckBox::indicator:hover {{ border-color: {c['accent']}; }}
QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']};
                                image: url({indicator_dir}/check.svg); }}
QCheckBox::indicator:disabled {{ background: {c['surface2']}; border-color: {c['border']}; }}
QCheckBox:disabled {{ color: {c['faint']}; }}
QRadioButton::indicator {{ width: 16px; height: 16px; border-radius: 9px; border: 1.5px solid {c['border_strong']};
                           background: {c['surface']}; }}
QRadioButton::indicator:checked {{ border: 5px solid {c['accent']}; background: {c['surface']}; }}

QProgressBar {{ background: {c['track']}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px;
                text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 3px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border_strong']}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['faint']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c['border_strong']}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QListView, QTreeView, QTableView {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px;
                                   outline: none; selection-background-color: {c['selection']};
                                   selection-color: {c['text']}; alternate-background-color: {c['surface2']}; }}
QListView#queueList {{ border: none; background: transparent; }}
QHeaderView::section {{ background: {c['surface2']}; color: {c['muted']}; border: none;
                        border-bottom: 1px solid {c['border']}; padding: 6px 8px; font-weight: 600; }}
QTableView::item {{ padding: 4px; }}

QMenu {{ background: {c['surface']}; border: 1px solid {c['border_strong']}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['accent_soft']}; color: {c['text']}; }}
QMenu::item:disabled {{ color: {c['faint']}; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 8px; }}

QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: 12px; }}

QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 10px; background: {c['surface']}; top: -1px; }}
QTabBar::tab {{ background: transparent; padding: 8px 14px; border: none; color: {c['muted']}; }}
QTabBar::tab:selected {{ color: {c['text']}; border-bottom: 2px solid {c['accent']}; font-weight: 600; }}

QFrame#banner[kind="error"] {{ background: {c['danger_soft']}; border: 1px solid {c['danger']}; border-radius: 10px; }}
QFrame#banner[kind="warning"] {{ background: {c['warning_soft']}; border: 1px solid {c['warning']}; border-radius: 10px; }}
QFrame#banner[kind="info"] {{ background: {c['accent_soft']}; border: 1px solid {c['accent']}; border-radius: 10px; }}
QFrame#banner[kind="success"] {{ background: {c['success_soft']}; border: 1px solid {c['success']}; border-radius: 10px; }}
QFrame#banner QLabel[role="bannerTitle"] {{ font-weight: 600; }}
"""


def refresh_style(widget: QWidget) -> None:
    """Dinamikus tulajdonság (pl. ``invalid``) változása után újrastílusoz."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def theme_cache_path() -> Path:
    return data_dir() / "cache" / "theme"
