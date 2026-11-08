import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from ytstudio.core import (
    VideoInfo, DownloadOptions, Subtitle, language_name,
    parse_time, fmt_time, metadata_args, media_args, subtitles_args,
    validate_url,
)

SAMPLE = {
    "id": "abc123", "title": "Teszt", "duration": 7200, "uploader": "Példa",
    "original_language": "en",
    "formats": [
        {"format_id": "v1080", "vcodec": "avc1", "acodec": "none", "height": 1080},
        {"format_id": "v720", "vcodec": "avc1", "acodec": "none", "height": 720},
        {"format_id": "aen", "vcodec": "none", "acodec": "opus", "abr": 135, "language": "en"},
        {"format_id": "ahu", "vcodec": "none", "acodec": "opus", "abr": 140, "language": "hu",
         "format_note": "dubbed"},
    ],
    "subtitles": {"en": [{"ext": "vtt", "name": "English"}]},
    "automatic_captions": {"hu": [{"ext": "vtt", "name": "Hungarian"}]},
}


class CoreTest(unittest.TestCase):
    def test_metadata(self):
        result = VideoInfo.from_json(SAMPLE, "https://example.com/watch?v=1")
        self.assertEqual(result.duration, 7200)
        self.assertEqual(result.resolutions, [1080, 720])
        self.assertEqual(len(result.audio_tracks), 2)
        self.assertTrue(any(a.original for a in result.audio_tracks))
        self.assertEqual({s.kind for s in result.subtitles}, {"manual", "automatic"})

    def test_time_parsing(self):
        self.assertEqual(parse_time("01:42:00"), 6120)
        self.assertEqual(parse_time("15:30"), 930)
        self.assertEqual(parse_time("2.5"), 2.5)
        self.assertEqual(fmt_time(6120), "01:42:00")
        self.assertIsNone(parse_time(""))
        for bad in ["2:99", "-1", "a", "12:0:0:1"]:
            with self.assertRaises(ValueError):
                parse_time(bad)

    def test_url(self):
        for bad in ["file:///etc/passwd", "javascript:alert(1)", "no-url", "https://a.com\nfoo"]:
            with self.assertRaises(ValueError):
                validate_url(bad)

    def test_video_args(self):
        with TemporaryDirectory() as dest:
            opts = DownloadOptions(url="https://example.org/video", dest=dest, container="mkv",
                                   quality="1080p", start=930, end=6120,
                                   audio_track_ids=["aen", "ahu"], accurate_cut=True)
            args = media_args(opts, Path("/tmp"))
            self.assertIn("--download-sections", args)
            self.assertIn("*00:15:30-01:42:00", args)
            self.assertIn("bv[height<=1080]+aen+ahu", args)
            self.assertIn("--audio-multistreams", args)
            self.assertIn("--force-keyframes-at-cuts", args)

    def test_audio_args(self):
        with TemporaryDirectory() as dest:
            opts = DownloadOptions(url="https://example.org/1", dest=dest,
                                   mode="audio", audio_format="flac", audio_track_ids=["aen"])
            args = media_args(opts)
            self.assertEqual(args[args.index("-f") + 1], "aen")
            self.assertIn("--extract-audio", args)
            self.assertIn("flac", args)

    def test_subtitle_args(self):
        with TemporaryDirectory() as dest:
            opts = DownloadOptions(url="https://example.org/1", dest=dest,
                                   mode="subtitles", subtitles=[Subtitle("hu", "automatic", "")])
            args = subtitles_args(opts)
            self.assertIn("--write-auto-subs", args)
            self.assertNotIn("--write-subs", args)
            self.assertEqual(args[args.index("--sub-langs") + 1], "hu")

    def test_invalid_multi_audio_mp4(self):
        with TemporaryDirectory() as dest:
            opts = DownloadOptions(url="https://example.org/1", dest=dest,
                                   audio_track_ids=["aen", "ahu"])
            with self.assertRaises(ValueError):
                opts.validate()


if __name__ == "__main__":
    unittest.main()
