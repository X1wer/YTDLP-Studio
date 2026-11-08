import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import _support  # noqa: F401

from ytstudio.subtitles import ms_to_stamp, stamp_to_ms, trim_file, trim_subtitle_text

SRT = """1
00:00:05,000 --> 00:00:11,000
Első

2
00:00:12,000 --> 00:00:19,000
Második sor
Két soros

3
00:00:30,000 --> 00:00:40,000
Harmadik
"""


class SubtitlesTest(unittest.TestCase):
    def test_stamps(self):
        self.assertEqual(stamp_to_ms("00:01:04,200"), 64200)
        self.assertEqual(stamp_to_ms("01:04.2"), 64200)
        self.assertEqual(ms_to_stamp(64200, False), "00:01:04,200")
        self.assertEqual(ms_to_stamp(64200, True), "00:01:04.200")

    def test_srt_trim(self):
        result = trim_subtitle_text(SRT, 10, 32)
        self.assertIn("1\n00:00:00,000 --> 00:00:01,000\nElső", result)
        self.assertIn("00:00:02,000 --> 00:00:09,000\nMásodik sor\nKét soros", result)
        self.assertIn("3\n00:00:20,000 --> 00:00:22,000", result)

    def test_offset_for_keyframe_cut(self):
        # A gyors vágásnál a hang 1,6 mp-cel később indul: a felirat is eltolódik.
        result = trim_subtitle_text(SRT, 10, 32, offset=1.6)
        self.assertIn("00:00:01,600 --> 00:00:02,600", result)

    def test_vtt_header_and_inline_timestamps(self):
        text = ("WEBVTT\nKind: captions\nLanguage: hu\n\n"
                "00:00:05.000 --> 00:00:15.000 align:start position:0%\n<00:00:06.000><c>Szia</c> világ\n\n"
                "00:00:30.000 --> 00:00:31.000\nBye\n")
        result = trim_subtitle_text(text, 10, 25, True)
        self.assertTrue(result.startswith("WEBVTT\nKind: captions\nLanguage: hu"))
        self.assertIn("00:00:00.000 --> 00:00:05.000 align:start position:0%", result)
        self.assertIn("<00:00:00.000>", result)
        self.assertNotIn("Bye", result)

    def test_empty_result(self):
        self.assertEqual(trim_subtitle_text(SRT, 100, 200), "")
        self.assertEqual(trim_subtitle_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nx", 50, None, True), "WEBVTT\n")

    def test_atomic_file_trim_utf8(self):
        with TemporaryDirectory() as d:
            src = Path(d) / "példa ő.srt"
            src.write_bytes("﻿1\r\n00:00:09,000 --> 00:00:11,000\r\nÁrvíztűrő\r\n".encode("utf-8"))
            self.assertEqual(trim_file(src, 10, 15), 1)
            text = src.read_text(encoding="utf-8")
            self.assertIn("00:00:00,000 --> 00:00:01,000", text)
            self.assertIn("Árvíztűrő", text)
            self.assertFalse(src.with_suffix(".srt.tmp").exists())


if __name__ == "__main__":
    unittest.main()
