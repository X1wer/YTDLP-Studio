import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from ytstudio.subtitles import stamp_to_ms, ms_to_stamp, trim_file, trim_subtitle_text


class SubtitlesTest(unittest.TestCase):
    def test_stamps(self):
        self.assertEqual(stamp_to_ms("00:01:04,200"), 64200)
        self.assertEqual(ms_to_stamp(64200, False), "00:01:04,200")
        self.assertEqual(ms_to_stamp(64200, True), "00:01:04.200")

    def test_srt_trim(self):
        content = """1
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
        result = trim_subtitle_text(content, 10, 32)
        self.assertIn("00:00:00,000 --> 00:00:01,000", result)
        self.assertIn("00:00:02,000 --> 00:00:09,000", result)
        self.assertIn("00:00:20,000 --> 00:00:22,000", result)
        self.assertIn("Két soros", result)
        self.assertNotIn("00:00:30,000 --> 00:00:40,000", result)

    def test_vtt_trim(self):
        text = "WEBVTT\n\n00:00:05.000 --> 00:00:15.000\nHello world!\n\n00:00:30.000 --> 00:00:31.000\nBye\n"
        result = trim_subtitle_text(text, 10, 25, True)
        self.assertTrue(result.startswith("WEBVTT"))
        self.assertIn("00:00:00.000 --> 00:00:05.000", result)
        self.assertNotIn("Bye", result)

    def test_atomic_file_trim(self):
        with TemporaryDirectory() as d:
            src = Path(d) / "example.srt"
            src.write_text("1\n00:00:09,000 --> 00:00:11,000\nHello\n", encoding="utf8")
            trim_file(src, 10, 15)
            self.assertIn("00:00:00,000 --> 00:00:01,000", src.read_text())
            self.assertFalse(src.with_suffix(".srt.tmp").exists())


if __name__ == "__main__":
    unittest.main()
