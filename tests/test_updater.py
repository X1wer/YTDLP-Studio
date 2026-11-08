import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import _support  # noqa: F401

from ytstudio import updater
from ytstudio.updater import Release

GOOD_URL = "https://github.com/yt-dlp/yt-dlp/releases/download/2026.10.26/yt-dlp.exe"


def release(sha="a" * 64, sums=None, url=GOOD_URL):
    return Release("stable", "2026.10.26", "2026-10-26", url, "yt-dlp.exe", sha, sums)


class UpdaterTest(unittest.TestCase):
    def test_parse_release_rejects_foreign_download(self):
        raw = {"tag_name": "1", "assets": [{"name": "yt-dlp.exe", "browser_download_url": "https://evil.example/yt-dlp.exe"}]}
        with self.assertRaises(RuntimeError):
            updater.parse_release(raw, "stable")
        raw["assets"][0]["browser_download_url"] = GOOD_URL
        raw["assets"][0]["digest"] = "sha256:" + "B" * 64
        self.assertEqual(updater.parse_release(raw, "stable").sha256, "b" * 64)

    def test_checksum_sources_must_agree(self):
        sums = ("1" * 64 + "  yt-dlp.exe\n").encode()
        with patch("ytstudio.updater._get_bytes", return_value=sums):
            self.assertEqual(updater.expected_checksum(release(None, "https://github.com/x/SHA2-256SUMS")), "1" * 64)
            with self.assertRaises(RuntimeError):
                updater.expected_checksum(release("2" * 64, "https://github.com/x/SHA2-256SUMS"))
        with self.assertRaises(RuntimeError):
            updater.expected_checksum(release(None, None))

    def test_version_compare(self):
        self.assertTrue(updater.is_newer("2026.11.04.232659", "2026.10.26"))
        self.assertFalse(updater.is_newer("2026.10.26", "2026.10.26"))
        self.assertTrue(updater.is_newer("2026.10.26", ""))

    def test_install_backup_and_rollback(self):
        with TemporaryDirectory() as d:
            exe = Path(d) / "yt-dlp.exe"
            exe.write_bytes(b"OLD")

            def fake_download(url, dest, sha, notify, limit=0):
                dest.write_bytes(b"NEW")

            with patch("ytstudio.updater._download_verified", side_effect=fake_download), \
                    patch("ytstudio.updater._run_version", return_value="2026.10.26"):
                self.assertEqual(updater.install_release(release(), exe, "2025.01.01"), "2026.10.26")
            self.assertEqual(exe.read_bytes(), b"NEW")
            self.assertEqual(updater.backup_path(exe).read_bytes(), b"OLD")
            self.assertEqual(updater.backup_version(exe), "2025.01.01")

            # Hibás új verzió: automatikus visszaállítás az előzőre.
            calls = {"n": 0}

            def flaky(path):
                calls["n"] += 1
                if calls["n"] == 2:
                    raise RuntimeError("nem indul")
                return "x"

            with patch("ytstudio.updater._download_verified", side_effect=lambda u, dest, s, n, limit=0: dest.write_bytes(b"BROKEN")), \
                    patch("ytstudio.updater._run_version", side_effect=flaky):
                with self.assertRaises(RuntimeError):
                    updater.install_release(release(), exe, "2026.10.26")
            self.assertEqual(exe.read_bytes(), b"NEW")
            self.assertFalse(exe.with_name("yt-dlp.exe.download").exists())

            # Kézi visszaállítás: a mentett verzió és a jelenlegi helyet cserél.
            with patch("ytstudio.updater._run_version", return_value="v"):
                updater.restore_backup(exe)
            self.assertEqual(exe.read_bytes(), b"OLD")
            self.assertEqual(updater.backup_path(exe).read_bytes(), b"NEW")


if __name__ == "__main__":
    unittest.main()
