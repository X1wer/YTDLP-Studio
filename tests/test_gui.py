"""Actual Tk GUI regressions; run using xvfb-run on Linux, or a Windows desktop."""
import os
import sys
import tempfile
import tkinter as tk
import unittest

from ytstudio.core import AudioTrack, Subtitle, VideoInfo
from ytstudio.gui import App


@unittest.skipUnless(sys.platform == 'win32' or os.environ.get('DISPLAY'),
                     'GUI requires an active display server')
class GuiTest(unittest.TestCase):
    def setUp(self):
        try:
            self.app = App()
        except tk.TclError as exc:
            self.skipTest(f'Tk unavailable: {exc}')
        self.app.withdraw()
        self.app.update_idletasks()

    def tearDown(self):
        if hasattr(self, 'app'):
            self.app.destroy()

    def test_options_are_native_menus_and_change_selection(self):
        app = self.app
        self.assertEqual(type(app.quality_cb).__name__, 'OptionMenu')
        # The new native menu must contain actual radio choices, not a dummy.
        menu = app.quality_cb['menu']
        self.assertGreater(menu.index('end'), 2)
        menu.invoke(1)
        self.assertEqual(app.quality.get(), '2160p')
        for control, variable, item_index, expected in [
            (app.mode_cb, app.mode, 1, 'Csak hang'),
            (app.container_cb, app.container, 1, 'mkv'),
            (app.audio_format_cb, app.audio_format, 2, 'aac'),
            (app.subtitle_format_cb, app.subtitle_format, 1, 'vtt'),
        ]:
            self.assertEqual(type(control).__name__, 'OptionMenu')
            control['menu'].invoke(item_index)
            self.assertEqual(variable.get(), expected)

    def test_checkbox_selection_survives_filtering(self):
        app = self.app
        app.sub_list.set_items([
            ('manual:hu', 'Magyar (hu) — kézi'),
            ('automatic:hu', 'Magyar (hu) — automatikus'),
            ('automatic:en', 'Angol (en) — automatikus'),
        ])
        app.sub_list.vars['automatic:en'].set(True)
        app.sub_list.search.set('magyar')
        self.assertEqual(len(app.sub_list._filtered_items()), 2)
        self.assertEqual(app.sub_list.selected_keys(), ['automatic:en'])
        app.sub_list.select_visible()
        self.assertEqual(len(app.sub_list.selected_keys()), 3)
        app.sub_list.clear_selection()
        self.assertFalse(app.sub_list.selected_keys())
        self.assertTrue(any(isinstance(w, tk.Checkbutton)
                            for w in app.sub_list.inner.winfo_children()))

    def test_metadata_checkbox_keys_and_download(self):
        app = self.app
        url = 'https://www.youtube.com/watch?v=abc123xyz00'
        info = VideoInfo(url=url, title='Teszt', duration=100,
                         uploader='Creator', thumbnail='', video_id='abc123xyz00',
                         original_language='en',
                         audio_tracks=[AudioTrack('a_en', 'en', 'opus', 120, '', 'webm'),
                                       AudioTrack('a_hu', 'hu', 'opus', 120, '', 'webm')],
                         subtitles=[Subtitle('hu', 'manual', 'Hungarian'),
                                    Subtitle('hu', 'automatic', 'Hungarian')],
                         resolutions=[1080, 720])
        with tempfile.TemporaryDirectory() as directory:
            app.destination.set(directory)
            app.url.set(url)
            app._metadata_ready(info)
            app.audio_list.vars['a_hu'].set(True)
            app.sub_list.vars['automatic:hu'].set(True)
            self.assertIn('1080p', [app.quality_cb['menu'].entrycget(i, 'label')
                                    for i in range(app.quality_cb['menu'].index('end') + 1)])
            opts = app._make_opts()
            self.assertEqual(opts.audio_track_ids, ['a_hu'])
            self.assertEqual([(s.kind, s.language) for s in opts.subtitles],
                             [('automatic', 'hu')])
            self.assertEqual(str(app.open_video.cget('state')), 'normal')

    def test_two_column_layout_and_preview_area(self):
        app = self.app
        app.deiconify()
        app.update_idletasks()
        self.assertGreater(app.preview_area.winfo_width(), 200)
        self.assertGreater(app.preview_area.winfo_height(), 100)
        self.assertNotEqual(str(app.audio_list.master), str(app.sub_list.master))
        self.assertLess(abs(app.audio_list.winfo_rootx() - app.sub_list.winfo_rootx()), 650)


if __name__ == '__main__':
    unittest.main()
