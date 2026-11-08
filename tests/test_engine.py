"""A letöltőmotor végponttól végpontig, szimulált yt-dlp-vel és valódi FFmpeg-gel."""
import json
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from _support import FIXTURES, bin_tool

from ytstudio import engine
from ytstudio.core import DownloadOptions, PlaylistInfo, Subtitle, VideoInfo

FAKE = Path(__file__).resolve().parent / "fake_ytdlp.py"
URL = "https://www.youtube.com/watch?v=vid12345678"


def fake_cmd(name):
    return [sys.executable, str(FAKE)]


@unittest.skipUnless(bin_tool("ffmpeg") and bin_tool("ffprobe"), "bin/ffmpeg.exe és ffprobe.exe szükséges")
class EngineTest(unittest.TestCase):
    def setUp(self):
        self.patch = patch("ytstudio.engine.tool_cmd", side_effect=fake_cmd)
        self.patch.start()
        self.env = dict(os.environ)

    def tearDown(self):
        self.patch.stop()
        os.environ.clear()
        os.environ.update(self.env)

    def probe(self, path: Path) -> dict:
        code, out = engine.run_quiet([str(bin_tool("ffprobe")), "-v", "error", "-show_entries",
                                      "stream=codec_type,codec_name:stream_tags=language,title:format=duration",
                                      "-of", "json", str(path)])
        self.assertEqual(code, 0, out)
        return json.loads(out)

    def test_analyze_video_and_playlist(self):
        os.environ["FAKE_JSON"] = str(FIXTURES / "youtube_multi_audio.json")
        info = engine.analyze(URL)
        self.assertIsInstance(info, VideoInfo)
        self.assertEqual([t.language for t in info.audio_tracks][0], "en-US")
        self.assertEqual(len(info.audio_tracks), 3)
        with TemporaryDirectory() as d:
            path = Path(d) / "pl.json"
            path.write_text(json.dumps({"_type": "playlist", "title": "L", "entries": [
                {"id": "a1", "title": "A", "url": "https://www.youtube.com/watch?v=a1", "ie_key": "Youtube"},
                {"id": "b2", "title": "B", "url": "https://www.youtube.com/watch?v=b2", "ie_key": "Youtube"}]}),
                encoding="utf-8")
            os.environ["FAKE_JSON"] = str(path)
            result = engine.analyze("https://www.youtube.com/playlist?list=PL1")
        self.assertIsInstance(result, PlaylistInfo)
        self.assertEqual(len(result.entries), 2)

    def test_friendly_error(self):
        os.environ["FAKE_FAIL"] = "Unable to download webpage: HTTP Error 403: Forbidden"
        with self.assertRaises(engine.OperationError) as ctx:
            engine.analyze(URL)
        self.assertEqual(ctx.exception.friendly.title, "Hozzáférés megtagadva (403)")
        with TemporaryDirectory() as d:
            task = engine.DownloadTask(DownloadOptions(url=URL, dest=d), "k1")
            with self.assertRaises(engine.OperationError):
                task.run()

    def test_video_clip_with_embedded_subtitles_and_collision(self):
        with TemporaryDirectory() as d:
            subs = [Subtitle("hu", "translated", "Hungarian", "en"), Subtitle("en", "manual", "English")]
            opts = DownloadOptions(url=URL, dest=d, container="mkv", subtitles=subs, embed_subtitles=True,
                                   start=2, end=6, duration=8, title="Teszt")
            progress = []
            result = engine.DownloadTask(opts, "k2", on_progress=progress.append).run()
            video = result.main_file
            self.assertTrue(video.name.startswith("Teszt videó ékezetekkel ő ű 𝕐 [vid12345678] (00.00.02–00.00.06)"))
            self.assertEqual(video.suffix, ".mkv")
            streams = self.probe(video)["streams"]
            subs_in_file = [s for s in streams if s["codec_type"] == "subtitle"]
            self.assertEqual(sorted(s["tags"]["language"] for s in subs_in_file), ["eng", "hun"])
            self.assertEqual(list(Path(d).glob("*.srt")), [])  # beágyazás után nincs külön fájl
            self.assertFalse((Path(d) / engine.TEMP_DIR_NAME).exists())
            percents = [p.percent for p in progress if p.stage == "downloading" and p.percent is not None]
            self.assertEqual(percents[-1], 100.0)
            self.assertTrue(all(b >= a for a, b in zip(percents, percents[1:])))
            # Második letöltés: ütközésmentes név, a feliratok is követik.
            opts2 = opts.with_changes(embed_subtitles=False)
            second = engine.DownloadTask(opts2, "k3").run()
            names = sorted(p.name for p in second.files)
            self.assertTrue(all(" (2)" in n for n in names), names)
            self.assertEqual(len(names), 3)
            srt = next(p for p in second.files if p.name.endswith(".hu.srt"))
            text = srt.read_text(encoding="utf-8")
            self.assertIn("00:00:00,000 --> 00:00:00,800\nhu felirat 2", text)  # 2 mp-től igazítva

    def test_audio_tracks_to_separate_files_and_subtitle_failure_is_warning(self):
        with TemporaryDirectory() as d:
            opts = DownloadOptions(url=URL, dest=d, mode="audio", audio_format="mp3",
                                   audio_selectors=["ba[language=de]", "ba[language=es]"], audio_languages=["de", "es"],
                                   subtitles=[Subtitle("xx", "manual")])
            result = engine.DownloadTask(opts, "k4").run()
            names = sorted(p.name for p in result.files)
            self.assertEqual([n[-7:] for n in names], [".de.mp3", ".es.mp3"])
            self.assertTrue(result.warnings and "xx" in result.warnings[0])

    def test_subtitles_only_vtt(self):
        with TemporaryDirectory() as d:
            opts = DownloadOptions(url=URL, dest=d, mode="subtitles", subtitle_format="vtt",
                                   subtitles=[Subtitle("de", "manual"), Subtitle("de", "auto")])
            result = engine.DownloadTask(opts, "k5").run()
            names = sorted(p.name for p in result.files)
            self.assertEqual([n.split("]")[-1] for n in names], [".auto.de.vtt", ".de.vtt"])

    def test_cancel_stops_process_quickly(self):
        os.environ["FAKE_SLOW"] = "1"
        with TemporaryDirectory() as d:
            task = engine.DownloadTask(DownloadOptions(url=URL, dest=d), "k6")
            errors = []

            def run():
                try:
                    task.run()
                except engine.Cancelled:
                    errors.append("cancelled")

            thread = threading.Thread(target=run)
            thread.start()
            time.sleep(2.0)
            started = time.monotonic()
            task.cancel()
            thread.join(10)
            self.assertFalse(thread.is_alive())
            self.assertLess(time.monotonic() - started, 5)
            self.assertEqual(errors, ["cancelled"])
            engine.cleanup_workdir(Path(d), "k6")
            self.assertFalse((Path(d) / engine.TEMP_DIR_NAME).exists())

    def test_local_cut_method(self):
        with TemporaryDirectory() as d:
            opts = DownloadOptions(url=URL, dest=d, container="mp4", start=1, end=4, cut_method="full",
                                   accurate_cut=True, duration=8)
            video = engine.DownloadTask(opts, "k7").run().main_file
            duration = float(self.probe(video)["format"]["duration"])
            self.assertAlmostEqual(duration, 3.0, delta=0.3)

    def test_analysis_is_reused_without_new_youtube_request(self):
        os.environ["FAKE_JSON"] = str(FIXTURES / "youtube_multi_audio.json")
        with TemporaryDirectory() as d:
            calls = Path(d) / "calls.txt"
            info = engine.analyze(URL)
            # Hamarosan lejáró linkeket nem szabad újrahasznosítani.
            self.assertTrue(Path(info.info_json).is_file())
            info.info_expires = time.time() + 600
            self.assertEqual(engine.reusable_info_json(info), "")
            info.info_expires = time.time() + 3 * 3600
            reuse = engine.reusable_info_json(info)
            self.assertEqual(reuse, info.info_json)
            os.environ["FAKE_CALLS"] = str(calls)
            opts = DownloadOptions(url=URL, dest=d, subtitles=[Subtitle("en", "manual")], info_json=reuse)
            engine.DownloadTask(opts, "k8").run()
            self.assertEqual(calls.read_text().split(), ["load-info-json", "load-info-json"])

    def test_stale_analysis_falls_back_to_fresh_request(self):
        with TemporaryDirectory() as d:
            stale = Path(d) / "info.json"
            stale.write_text("{}", encoding="utf-8")
            calls = Path(d) / "calls.txt"
            os.environ.update(FAKE_STALE="1", FAKE_CALLS=str(calls))
            log = []
            result = engine.DownloadTask(DownloadOptions(url=URL, dest=d, info_json=str(stale)), "k9",
                                         on_log=log.append).run()
            self.assertTrue(result.main_file.exists())
            self.assertEqual(calls.read_text().split(), ["load-info-json", "fresh"])
            self.assertTrue(any("friss lekérés" in line for line in log))


if __name__ == "__main__":
    unittest.main()
