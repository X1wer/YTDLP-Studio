from unittest import TestCase
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
from ytstudio.updater import Release, _checksum_from_release, _download_and_verify
import hashlib


class UpdaterTest(TestCase):
    def test_known_digest(self):
        sha = "a" * 64
        rel = Release("2026.10.26", "2026-10-26", "https://github.com/yt-dlp/yt-dlp/releases/download/test/yt-dlp.exe",
                      "yt-dlp.exe", sha, None)
        self.assertEqual(_checksum_from_release(rel), sha)

    def test_checksum_list(self):
        sample = "1" * 64 + "  yt-dlp.exe\n"
        rel = Release("1", "", "https://github.com/x/y", "yt-dlp.exe", None, "https://github.com/example/SHASUMS")
        with patch("ytstudio.updater._get_bytes", return_value=sample.encode()):
            self.assertEqual(_checksum_from_release(rel), "1" * 64)

    def test_missing_checksum_rejected(self):
        rel = Release("1", "", "https://github.com/x/y", "yt-dlp.exe", None, None)
        with self.assertRaises(RuntimeError):
            _checksum_from_release(rel)
