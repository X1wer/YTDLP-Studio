"""Fordítás: teljesség, helyőrzők, és hogy angol módban ne maradjon magyar szöveg a felületen."""
import re
import string
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from _support import fixture
from i18n_keys import collect

from ytstudio import i18n
from ytstudio.core import PlaylistEntry, PlaylistInfo, VideoInfo, fmt_size
from ytstudio.i18n_en import CATALOG
from ytstudio.langs import language_name

HU = re.compile(r"[áéíóöőúüűÁÉÍÓÖŐÚÜŰ]|\b(és|vagy|nincs|Mégse|Letöltés|Felirat|Hangsáv|Beállítás)\b")
URL = "https://www.youtube.com/watch?v=0e3GPea1Tyg"


def fields(text: str) -> set[str]:
    return {name for _lit, name, _spec, _conv in string.Formatter().parse(text) if name}


class CatalogTest(unittest.TestCase):
    def test_every_source_string_has_english_translation(self):
        keys = collect()
        missing = sorted(k for k in keys if k not in CATALOG)
        self.assertEqual(missing, [], "Hiányzó angol fordítás")

    def test_no_mnemonic_ampersands(self):
        # A Qt a gombfeliratokban az „&” jelet gyorsbillentyűnek veszi („Tools _updates” hiba).
        self.assertEqual([v for v in CATALOG.values() if "&" in v.replace("&&", "")], [])

    def test_placeholders_match(self):
        wrong = {k: v for k, v in CATALOG.items() if fields(k) != fields(v)}
        self.assertEqual(wrong, {})

    def test_language_switch_and_formatting(self):
        try:
            i18n.set_language("en")
            self.assertEqual(i18n.tr("Letöltés most"), "Download now")
            self.assertEqual(language_name("en-US"), "English (US)")
            self.assertEqual(fmt_size(1.5 * 1024 * 1024), "1.5 MB")
            i18n.set_language("hu")
            self.assertEqual(i18n.tr("Letöltés most"), "Letöltés most")
            self.assertEqual(language_name("en-US"), "Angol (USA)")
            self.assertEqual(fmt_size(1.5 * 1024 * 1024), "1,5 MB")
            self.assertIn(i18n.resolve("auto"), ("hu", "en"))
        finally:
            i18n.set_language("hu")


class EnglishUiTest(unittest.TestCase):
    """A teljes felület angolul: minden látható szöveg, súgó és listaelem."""

    @classmethod
    def setUpClass(cls):
        from ytstudio.ui.app import create_app
        cls.app = create_app([])

    def setUp(self):
        i18n.set_language("en")
        self.addCleanup(i18n.set_language, "hu")

    def texts(self, root) -> list[str]:
        from PySide6.QtWidgets import (QAbstractButton, QComboBox, QLabel, QLineEdit, QListView,
                                       QWidget)
        found = []
        widgets = [root] + root.findChildren(QWidget)
        for w in widgets:
            if not w.isVisibleTo(root) and w is not root:
                continue
            if isinstance(w, (QLabel, QAbstractButton)):
                found.append(w.text())
            if isinstance(w, QLineEdit):
                found.append(w.placeholderText())
            if isinstance(w, QComboBox):
                found += [w.itemText(i) for i in range(w.count())]
            if isinstance(w, QListView) and w.model() is not None:
                model = w.model()
                for r in range(min(model.rowCount(), 60)):
                    index = model.index(r, 0)
                    found += [str(index.data() or ""), str(index.data(0x0101 + 1) or "")]
            found.append(w.toolTip())
            found.append(w.windowTitle())
        return [t for t in found if t]

    def assert_english(self, root, allowed=()):
        leftovers = []
        for text in self.texts(root):
            rest = text
            for part in allowed:  # pl. a videó címe – csak ezt a részt hagyja ki
                rest = rest.replace(part, "")
            if HU.search(rest):
                leftovers.append(text)
        self.assertEqual(leftovers, [], "Magyar szöveg maradt az angol felületen")

    def test_main_window_pages_and_dialogs(self):
        from ytstudio.settings import Settings
        from ytstudio.ui.dialogs import DetailsDialog, LogWindow, SettingsDialog, ToolsDialog
        from ytstudio.ui.main_window import MainWindow
        from ytstudio.core import DownloadOptions
        from ytstudio.errors import explain
        with TemporaryDirectory() as tmp:
            settings = Settings(destination=tmp, language="en")
            settings.save = lambda: True
            w = MainWindow(settings)
            w._load_thumbnail = lambda *a, **k: None
            w.show()
            self.app.processEvents()
            self.assertEqual(w.analyze_button.text(), "Analyze")
            self.assert_english(w)
            # Videó: a YouTube-cím és a csatornanév a videó saját adata, ezek maradhatnak.
            info = VideoInfo.from_json(fixture("youtube_multi_audio.json"), URL)
            w._show_video(info)
            self.app.processEvents()
            self.assert_english(w, allowed=(info.title,))
            for mode in ("audio", "subtitles", "video"):
                w.mode.set_value(mode, emit=True)
                w.trim_switch.setChecked(mode == "video")
                self.app.processEvents()
                self.assert_english(w, allowed=(info.title,))
            pl = PlaylistInfo("https://www.youtube.com/playlist?list=PL", "List", "U", [
                PlaylistEntry(1, "a", "https://www.youtube.com/watch?v=aaaaaaaaaaa", "First", 61.0)])
            w._show_playlist(pl)
            self.app.processEvents()
            self.assert_english(w)
            # Sorkártyák szövegei
            from ytstudio.ui.queue import job_detail_text
            with patch.object(w.manager, "_start"):
                job = w.manager.add(DownloadOptions(url=URL, dest=tmp), "Video")
            job.status, job.error = "error", explain("HTTP Error 429: Too Many Requests")
            self.assertFalse(HU.search(job.status_line() + job_detail_text(job)))
            w.manager.start_cooldown()
            self.app.processEvents()
            self.assert_english(w.queue)
            w.manager.resume_now()
            # Párbeszédablakok (a nyelvválasztó kétnyelvű címkéje és a „Magyar” név szándékos)
            for dialog in (SettingsDialog(settings, w), LogWindow(w),
                           DetailsDialog("Title", "Message", "details", ["warning"], w)):
                dialog.show()
                self.app.processEvents()
                self.assert_english(dialog, allowed=("Nyelv / Language", "Magyar"))
                dialog.close()
            with patch("ytstudio.ui.dialogs.tool_version", return_value="1.0"):
                tools = ToolsDialog(settings, lambda: True, w)
                tools.show()
                self.app.processEvents()
                self.assert_english(tools)
                tools.close()
            w.manager.jobs.clear()
            w.close()




class SettingsFileTest(unittest.TestCase):
    def test_settings_with_utf8_bom_are_read(self):
        # Regresszió: a Jegyzettömb/PowerShell BOM-mal menti a fájlt; korábban ez a beállítások
        # csendes elvesztését okozta (pl. a nyelv visszaállt).
        from pathlib import Path
        from ytstudio.settings import Settings
        with TemporaryDirectory() as tmp:
            with patch.object(Settings, "path", staticmethod(lambda: Path(tmp) / "settings.json")):
                (Path(tmp) / "settings.json").write_bytes('﻿{"language": "en", "theme": "dark"}'.encode("utf-8"))
                loaded = Settings.load()
        self.assertEqual((loaded.language, loaded.theme), ("en", "dark"))


if __name__ == "__main__":
    unittest.main()
