"""A felület nyelve: magyar (a forráskód nyelve) vagy angol.

A felhasználónak szóló szövegek a kódban magyarul szerepelnek, és a ``tr()``
függvényen mennek át; angol nyelv esetén az ``i18n_en.CATALOG`` szótárból jön a
fordítás. Az import idején kiértékelt szövegeket (modulszintű állandók,
alapértelmezett paraméterek) az ``N_()`` csak megjelöli, a fordítás a
felhasználás helyén, ``tr()``-rel történik.
"""
from __future__ import annotations

import locale
import sys

LANGUAGES = ("auto", "hu", "en")
_current = "hu"


def system_language() -> str:
    """A Windows felhasználói felületének nyelve: magyar, egyébként angol."""
    if sys.platform == "win32":
        try:
            import ctypes
            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "hu" if (langid & 0x3FF) == 0x0E else "en"  # LANG_HUNGARIAN
        except (OSError, AttributeError):
            pass
    name = (locale.getlocale()[0] or "").lower()
    return "hu" if name.startswith(("hu", "hungarian")) else "en"


def resolve(setting: str) -> str:
    return system_language() if setting not in ("hu", "en") else setting


def set_language(setting: str) -> str:
    global _current
    _current = resolve(setting)
    return _current


def current() -> str:
    return _current


def tr(text: str) -> str:
    if _current == "hu" or not text:
        return text
    from .i18n_en import CATALOG
    return CATALOG.get(text, text)


def N_(text: str) -> str:  # noqa: N802 - a gettext-hagyomány szerinti név
    """Fordítandónak jelöl, de nem fordít (import idején kiértékelt szövegekhez)."""
    return text
