"""Valódi Qt-felülettesztek: a vezérlőkre kattintva ellenőrzi a működést."""
import os
import sys
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from _support import fixture

from PySide6.QtCore import QEvent, QModelIndex, QPoint, Qt
from PySide6.QtGui import QHelpEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QStyleOptionViewItem

from ytstudio.engine import OperationError
from ytstudio.errors import explain

from ytstudio.core import DownloadOptions, PlaylistEntry, PlaylistInfo, VideoInfo
from ytstudio.engine import Progress
from ytstudio.settings import Settings
from ytstudio.ui import theme
from ytstudio.ui.app import create_app
from ytstudio.ui.main_window import MainWindow
from ytstudio.ui.queue import Job
from ytstudio.ui.widgets import KEY_ROLE

URL = "https://www.youtube.com/watch?v=0e3GPea1Tyg"
app = create_app([])
theme.manager.apply("light")


def click_row(checklist, key: str) -> None:
    """A lista adott sorára kattint (az egész sor vált, nem csak a négyzet)."""
    view = checklist.view
    for row in range(checklist.proxy.rowCount()):
        index = checklist.proxy.index(row, 0)
        if index.data(KEY_ROLE) == key:
            view.scrollTo(index)
            rect = view.visualRect(index)
            QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                             QPoint(rect.center().x() + 60, rect.center().y()))
            return
    raise AssertionError(f"nem látható sor: {key}")


class GuiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.settings = Settings(destination=self.tmp.name)
        self.settings.save = lambda: True
        self.window = MainWindow(self.settings)
        self.window.resize(1300, 860)
        self.window.show()
        QTest.qWaitForWindowExposed(self.window)
        self.window._load_thumbnail = lambda *a, **k: None

    def tearDown(self):
        self.window.manager.jobs.clear()
        self.window.close()
        self.window.deleteLater()
        app.processEvents()
        self.tmp.cleanup()

    def show_video(self):
        info = VideoInfo.from_json(fixture("youtube_multi_audio.json"), URL)
        self.window._show_video(info)
        app.processEvents()
        return info

    def test_starts_with_empty_state(self):
        w = self.window
        self.assertEqual(w.stack.currentIndex(), 0)
        self.assertFalse(w.action_bar.isVisible())

    def test_invalid_url_shows_hungarian_message(self):
        w = self.window
        w.url_edit.setText("ez nem link")
        QTest.mouseClick(w.analyze_button, Qt.MouseButton.LeftButton)
        self.assertIn("http", w.status_label.text())
        self.assertIsNone(w._cancel)

    def test_quality_dropdown_opens_and_changes(self):
        w = self.window
        self.show_video()
        labels = [w.quality.itemText(i) for i in range(w.quality.count())]
        self.assertIn("1080p (Full HD)", labels)
        w.quality.showPopup()
        QTest.qWait(150)
        self.assertTrue(w.quality.view().isVisible(), "a legördülő lista nem nyílt meg")
        w.quality.hidePopup()
        w.quality.set_value("720")
        self.assertEqual(w._single_options().quality, "720")

    def test_mode_switch_shows_relevant_controls(self):
        w = self.window
        self.show_video()
        QTest.mouseClick(w.mode.button("audio"), Qt.MouseButton.LeftButton)
        self.assertEqual(w.mode.value(), "audio")
        self.assertTrue(w.audio_format.isVisible())
        self.assertFalse(w.quality.isVisible())
        QTest.mouseClick(w.audio_format.button("flac"), Qt.MouseButton.LeftButton)
        self.assertFalse(w.audio_quality.isVisible())  # veszteségmentesnél nincs bitráta
        opts = w._single_options()
        self.assertEqual((opts.mode, opts.audio_format), ("audio", "flac"))
        QTest.mouseClick(w.mode.button("subtitles"), Qt.MouseButton.LeftButton)
        self.assertFalse(w.audio_card.isVisible())
        self.assertFalse(w.trim_card.isVisible())
        QTest.mouseClick(w.mode.button("video"), Qt.MouseButton.LeftButton)
        self.assertTrue(w.quality.isVisible())

    def test_audio_checkboxes_and_search_keep_selection(self):
        w = self.window
        self.show_video()
        click_row(w.audio_list, "de|dubbed")
        click_row(w.audio_list, "es|dubbed")
        self.assertEqual(w.audio_list.checked_keys(), ["de|dubbed", "es|dubbed"])
        # Több hangsáv: MKV-ra vált, az MP4 nem választható.
        self.assertEqual(w.container.value(), "mkv")
        self.assertFalse(w.container.button("mp4").isEnabled())
        QTest.keyClicks(w.audio_list.search, "spany")
        self.assertEqual(w.audio_list.visible_keys(), ["es|dubbed"])
        self.assertEqual(w.audio_list.checked_keys(), ["de|dubbed", "es|dubbed"])
        click_row(w.audio_list, "es|dubbed")  # szűrt nézetben kijelölés megszüntetése
        w.audio_list.search.clear()
        self.assertEqual(w.audio_list.checked_keys(), ["de|dubbed"])
        w.audio_list.only_checked.setChecked(True)
        self.assertEqual(w.audio_list.visible_keys(), ["de|dubbed"])
        opts = w._single_options()
        self.assertEqual(opts.audio_selectors, ["ba[language=de]"])
        self.assertTrue(w.container.button("mp4").isEnabled())

    def test_subtitle_type_filter_and_options(self):
        w = self.window
        self.show_video()
        w.sub_list.kind_box.set_value("translated")
        keys = w.sub_list.visible_keys()
        self.assertTrue(keys and all(k.startswith("auto:") for k in keys))
        click_row(w.sub_list, "auto:hu")
        w.sub_list.kind_box.set_value("manual")
        click_row(w.sub_list, "manual:en")
        w.sub_list.kind_box.set_value("")
        QTest.mouseClick(w.sub_format.button("vtt"), Qt.MouseButton.LeftButton)
        w.embed_subs.setChecked(True)
        opts = w._single_options()
        self.assertEqual(sorted(s.key for s in opts.subtitles), ["auto:hu", "manual:en"])
        self.assertEqual(opts.subtitle_format, "vtt")
        self.assertTrue(opts.embed_subtitles)
        w.sub_list.clear_selection()
        self.assertEqual(w.sub_list.checked_keys(), [])

    def test_trim_timeline_and_time_fields(self):
        w = self.window
        info = self.show_video()
        self.assertEqual(w._single_options().start, None)
        w.trim_switch.click()
        self.assertTrue(w.trim_body.isVisible())
        w.start_edit.setText("00:15:30")
        w.start_edit.editingFinished.emit()
        w.end_edit.setText("20:00")
        w.end_edit.editingFinished.emit()
        self.assertEqual((w.range.start, w.range.end), (930, 1200))
        opts = w._single_options()
        self.assertEqual((opts.start, opts.end), (930, 1200))
        self.assertIn("4:30", w.clip_length.text())
        w.range.set_range(10, info.duration, emit=True)
        self.assertEqual(w.start_edit.text(), "00:00:10")
        self.assertEqual(w._single_options().end, None)  # a vége a videó vége
        w.end_edit.setText("hibás")
        w.end_edit.editingFinished.emit()
        self.assertEqual(w.end_edit.property("invalid"), "true")
        w.chapter_box.setCurrentIndex(2)
        self.assertEqual(w.range.start, info.chapters[1].start)

    def test_download_now_creates_job_with_selected_options(self):
        w = self.window
        self.show_video()
        click_row(w.audio_list, "de|dubbed")
        with patch.object(w.manager, "_start") as start:
            QTest.mouseClick(w.download_button, Qt.MouseButton.LeftButton)
            self.assertEqual(len(w.manager.jobs), 1)
            job = w.manager.jobs[0]
            start.assert_called_once()
            self.assertTrue(job.immediate)
            self.assertEqual(job.options.audio_selectors, ["ba[language=de]"])
            self.assertEqual(job.options.dest, self.tmp.name)
            QTest.mouseClick(w.queue_button, Qt.MouseButton.LeftButton)
            self.assertEqual(len(w.manager.jobs), 2)
            self.assertFalse(w.manager.jobs[1].immediate)

    def test_playlist_selection_and_naming(self):
        w = self.window
        pl = PlaylistInfo("https://www.youtube.com/playlist?list=PL", "Saját: lista", "U", [
            PlaylistEntry(i, f"id{i}", f"https://www.youtube.com/watch?v=id{i:09d}", f"Videó {i}", 60.0)
            for i in range(1, 13)])
        w._show_playlist(pl)
        app.processEvents()
        self.assertEqual(len(w.pl_list.checked_keys()), 12)
        click_row(w.pl_list, w.pl_list.checked_keys()[0])
        self.assertIn("11 videó", w.download_button.text())
        w.pl_subs.setChecked(True)
        jobs = w._playlist_options()
        self.assertEqual(len(jobs), 11)
        first, _ = jobs[0]
        self.assertTrue(first.dest.endswith("Saját_ lista"))
        self.assertEqual(first.filename_prefix, "02 - ")
        self.assertEqual(first.sub_langs, ["hu", "en"])

    def test_queue_cards_and_actions(self):
        w = self.window
        manager = w.manager
        with patch.object(manager, "_start"):
            job = manager.add(DownloadOptions(url=URL, dest=self.tmp.name), "Teszt videó")
        job.status, job.progress = "running", Progress(stage="downloading", text="Letöltés", percent=40, speed=2e6, eta=30)
        manager.jobChanged.emit(job)
        self.assertIn("40%", job.status_line())
        self.assertIn("van hátra", job.status_line())
        job.status = "error"
        manager.jobChanged.emit(job)
        with patch.object(manager, "_start") as start:
            w._job_action("retry", job)
            start.assert_called_once()
        job.status = "done"
        w._job_action("remove", job)
        self.assertEqual(manager.jobs, [])
        self.assertTrue(w.queue.empty.isVisible())

    def test_tooltip_over_empty_list_area_does_not_crash(self):
        # Regresszió (0.2.0): a lista üres része fölötti buboréksúgó AttributeError-t dobott.
        w = self.window
        with patch.object(w.manager, "_start"):
            w.manager.add(DownloadOptions(url=URL, dest=self.tmp.name), "Teszt")
        for view in (w.queue.view, w.audio_list.view):
            event = QHelpEvent(QEvent.Type.ToolTip, QPoint(5, 5000), view.viewport().mapToGlobal(QPoint(5, 5000)))
            option = QStyleOptionViewItem()
            self.assertTrue(view.itemDelegate().helpEvent(event, view, option, QModelIndex()))

    def test_rate_limit_pauses_queue_and_retries_once(self):
        w = self.window
        manager = w.manager
        def fake_start(job):
            job.status = "running"
        with patch.object(manager, "_start", side_effect=fake_start) as start:
            first = manager.add(DownloadOptions(url=URL, dest=self.tmp.name), "Első")
            second = manager.add(DownloadOptions(url=URL, dest=self.tmp.name), "Második")
            self.assertEqual((first.status, second.status), ("running", "queued"))
            start.reset_mock()
            bot = OperationError(explain("ERROR: [youtube] x: Sign in to confirm you're not a bot"), "bot")
            manager._on_finished(first, "error", bot)
            self.assertTrue(manager.in_cooldown())
            self.assertEqual((first.status, first.auto_retries), ("queued", 1))
            self.assertIn("automatikusan újrapróbálja", first.status_line())
            start.assert_not_called()  # várakozás alatt nem indul új letöltés
            app.processEvents()
            self.assertTrue(w.queue.cooldown.isVisible())
            self.assertIn("Folytatás most", [b.text() for b in w.queue.cooldown.findChildren(QPushButton)])
            manager.resume_now()
            self.assertFalse(manager.in_cooldown())
            self.assertEqual([c.args[0] for c in start.call_args_list], [first])  # az újrapróbálás indul
            # Második korlátozás ugyanannál a feladatnál: már nem próbálja újra automatikusan.
            manager._on_finished(first, "error", bot)
            self.assertEqual(first.status, "error")
            self.assertEqual(second.status, "queued")
            manager.resume_now()
            self.assertFalse(w.queue.cooldown.isVisible())
            self.assertEqual(second.status, "running")

    def test_theme_switch_at_runtime(self):
        w = self.window
        theme.manager.apply("dark")
        self.assertTrue(theme.manager.dark)
        self.assertIn(theme.DARK["bg"], app.styleSheet())
        w._cycle_theme()
        self.assertEqual(theme.manager.mode, "system")
        theme.manager.apply("light")


if __name__ == "__main__":
    unittest.main()
