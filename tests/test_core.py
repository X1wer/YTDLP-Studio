import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from _support import fixture

from ytstudio.core import (DownloadOptions, PlaylistInfo, Subtitle, VideoInfo, audio_format_selector,
                           estimate_size, fmt_time, media_args, metadata_args, normalize_url, parse_time,
                           safe_component, section_arg, sort_subtitles, subtitle_args, subtitle_plan,
                           validate_url, video_format_selector, youtube_playlist_context)
from ytstudio.langs import language_name, to_iso639_2

URL = "https://www.youtube.com/watch?v=0e3GPea1Tyg"


def multi() -> VideoInfo:
    return VideoInfo.from_json(fixture("youtube_multi_audio.json"), URL)


class TimeAndUrlTest(unittest.TestCase):
    def test_time_parsing(self):
        self.assertEqual(parse_time("01:42:00"), 6120)
        self.assertEqual(parse_time("15:30"), 930)
        self.assertEqual(parse_time("2,5"), 2.5)
        self.assertIsNone(parse_time("  "))
        self.assertEqual(fmt_time(6120), "01:42:00")
        self.assertEqual(fmt_time(13.5), "00:00:13.5")
        for bad in ["2:99", "-1", "a", "12:0:0:1", "1:-5"]:
            with self.assertRaises(ValueError):
                parse_time(bad)

    def test_url_validation(self):
        for bad in ["file:///etc/passwd", "javascript:alert(1)", "no-url", "https://a.com\nfoo",
                    "https://user:pw@a.com/x", "ftp://a.com/v"]:
            with self.assertRaises(ValueError):
                validate_url(bad)
        self.assertEqual(normalize_url("nézd: https://youtu.be/abc?t=5 jó"), "https://youtu.be/abc?t=5")
        self.assertEqual(normalize_url("youtube.com/watch?v=x"), "https://youtube.com/watch?v=x")
        self.assertEqual(youtube_playlist_context("https://www.youtube.com/watch?v=a&list=PL1"), (True, True))
        self.assertEqual(youtube_playlist_context("https://www.youtube.com/playlist?list=PL1"), (False, True))

    def test_metadata_args_playlist_handling(self):
        args = metadata_args("https://www.youtube.com/watch?v=a&list=PL1")
        self.assertIn("--no-playlist", args)
        args = metadata_args("https://www.youtube.com/playlist?list=PL1")
        self.assertIn("--flat-playlist", args)
        self.assertEqual(args[-2:], ["--", "https://www.youtube.com/playlist?list=PL1"])
        self.assertIn("--encoding", args)

    def test_safe_component_and_languages(self):
        self.assertEqual(safe_component('Lista: "best" / 2024?'), "Lista_ _best_ _ 2024_")
        self.assertEqual(safe_component("CON"), "CON_")
        self.assertEqual(language_name("en-US"), "Angol (USA)")
        self.assertEqual(language_name("zh-Hans"), "Kínai (egyszerűsített)")
        self.assertEqual(language_name("hu"), "Magyar")
        self.assertEqual(to_iso639_2("hu"), "hun")
        self.assertEqual(to_iso639_2("de-DE"), "deu")


class MetadataTest(unittest.TestCase):
    def test_real_multi_audio_metadata(self):
        info = multi()
        self.assertEqual(info.title, "$456,000 Squid Game In Real Life!")
        self.assertEqual(info.heights[0], 1080)
        self.assertTrue(info.preview_url)
        self.assertEqual(len(info.chapters), 7)
        original = info.audio_tracks[0]
        self.assertEqual((original.language, original.kind), ("en-US", "original"))
        self.assertEqual(original.selector, "ba[language=en-US]")
        kinds = {t.language: t.kind for t in info.audio_tracks}
        self.assertEqual(kinds["de"], "dubbed")
        # Nem állítja, hogy AI-szinkron, ha a metaadat ezt nem jelzi.
        self.assertNotIn("dubbed-auto", kinds.values())

    def test_subtitle_kinds_from_real_metadata(self):
        info = multi()
        by_key = {s.key: s for s in info.subtitles}
        self.assertEqual(by_key["manual:en"].kind, "manual")
        self.assertEqual(by_key["auto:en-orig"].kind, "auto")
        self.assertEqual(by_key["auto:hu"].kind, "translated")
        self.assertEqual(by_key["auto:hu"].source, "en")
        self.assertIn("automatikus fordítás", by_key["auto:hu"].label)
        ordered = sort_subtitles(info.subtitles, ["hu", "en"])
        self.assertEqual(ordered[0].language, "hu")

    def test_hls_mirror_of_manual_subtitle_is_hidden(self):
        info = VideoInfo.from_json(fixture("youtube_zoo.json"), "https://www.youtube.com/watch?v=jNQXAC9IVRw")
        self.assertEqual(sorted(s.key for s in info.subtitles), ["manual:de", "manual:en"])
        self.assertEqual(len(info.audio_tracks), 1)
        self.assertEqual(info.audio_tracks[0].kind, "default")

    def test_ai_dub_only_when_marked(self):
        raw = {"id": "x", "title": "t", "formats": [
            {"format_id": "1", "vcodec": "none", "acodec": "opus", "language": "en", "language_preference": 10,
             "format_note": "English original (default)"},
            {"format_id": "2", "vcodec": "none", "acodec": "opus", "language": "hu", "format_note": "Hungarian (dubbed-auto)"},
            {"format_id": "3", "vcodec": "none", "acodec": "opus", "language": "en", "format_note": "English descriptive"},
        ]}
        tracks = {t.key: t for t in VideoInfo.from_json(raw, URL).audio_tracks}
        self.assertEqual(tracks["hu|dubbed-auto"].kind, "dubbed-auto")
        self.assertIn("[format_note*=descriptive]", tracks["en|descriptive"].selector)
        self.assertIn("[format_note!*=descriptive]", tracks["en|original"].selector)

    def test_playlist_parsing(self):
        raw = {"_type": "playlist", "title": "Lista", "uploader": "U", "entries": [
            {"id": "aaaaaaaaaaa", "title": "Első", "duration": 60, "ie_key": "Youtube",
             "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa"},
            {"id": "bbbbbbbbbbb", "title": "[Private video]", "ie_key": "Youtube", "url": "https://www.youtube.com/watch?v=bbbbbbbbbbb"},
            {"id": "ccccccccccc", "title": "Harmadik", "ie_key": "Youtube"},
        ]}
        pl = PlaylistInfo.from_json(raw, "https://www.youtube.com/playlist?list=PL")
        self.assertEqual([e.available for e in pl.entries], [True, False, True])
        self.assertEqual(pl.entries[2].url, "https://www.youtube.com/watch?v=ccccccccccc")


class ArgumentTest(unittest.TestCase):
    def test_video_clip_multi_audio(self):
        info = multi()
        tracks = {t.language: t for t in info.audio_tracks}
        with TemporaryDirectory() as dest:
            opts = DownloadOptions(url=URL, dest=dest, container="mp4", quality="1080", start=930, end=6120.5,
                                   audio_selectors=[tracks["de"].selector, tracks["es"].selector],
                                   audio_languages=["de", "es"], accurate_cut=True, duration=7000)
            self.assertEqual(opts.effective_container, "mkv")
            args = media_args(opts, Path(dest))
        self.assertIn("*00:15:30-01:42:00.5", args)
        self.assertIn("--force-keyframes-at-cuts", args)
        self.assertIn("--audio-multistreams", args)
        self.assertIn("--no-embed-chapters", args)
        self.assertEqual(args[args.index("--merge-output-format") + 1], "mkv")
        self.assertTrue(args[args.index("-f") + 1].startswith("bv[height<=1080]+ba[language=de]+ba[language=es]"))
        # Ékezetes kimenet és működő haladásjelzés (v0.1.3 hibái):
        self.assertEqual(args[args.index("--encoding") + 1], "utf-8")
        self.assertIn("--no-quiet", args)
        self.assertIn("--progress", args)
        self.assertIn("(00.15.30–01.42.00,5)", args[args.index("-o") + 1])

    def test_default_video_selector_and_compatibility_sort(self):
        opts = DownloadOptions(url=URL, dest=".", quality="720")
        self.assertEqual(video_format_selector(opts).split("/")[0], "bv*[height<=720]+ba")
        args = media_args(opts, Path("."))
        self.assertIn("lang,res,fps,hdr:12,vcodec:h264,acodec:aac", args)
        webm = DownloadOptions(url=URL, dest=".", container="webm")
        self.assertIn("vcodec~=", video_format_selector(webm))
        self.assertIn("webm/mkv", media_args(webm, Path(".")))
        pref = DownloadOptions(url=URL, dest=".", preferred_audio_lang="hu")
        self.assertIn("ba[language^=hu]", video_format_selector(pref))

    def test_audio_modes(self):
        opts = DownloadOptions(url=URL, dest=".", mode="audio", audio_format="m4a",
                               audio_selectors=["ba[language=de]", "ba[language=es]"], audio_languages=["de", "es"])
        self.assertEqual(audio_format_selector(opts), "ba[language=de]/b[language=de],ba[language=es]/b[language=es]")
        args = media_args(opts, Path("."))
        self.assertIn("lang,acodec:aac", args)
        self.assertIn(".%(language|hang)s.%(ext)s", args[args.index("-o") + 1])
        original = media_args(DownloadOptions(url=URL, dest=".", mode="audio", audio_format="original"), Path("."))
        self.assertNotIn("--audio-format", original)
        mp3 = media_args(DownloadOptions(url=URL, dest=".", mode="audio", audio_quality="192"), Path("."))
        self.assertEqual(mp3[mp3.index("--audio-quality") + 1], "192K")

    def test_subtitle_plan_avoids_name_conflicts(self):
        subs = [Subtitle("en", "manual"), Subtitle("en", "auto"), Subtitle("hu", "translated", source="en")]
        opts = DownloadOptions(url=URL, dest=".", subtitles=subs)
        plan = subtitle_plan(opts)
        self.assertEqual(plan[0]["langs"], ["en", "hu"])
        self.assertTrue(plan[0]["manual"] and plan[0]["auto"])
        self.assertEqual(plan[1], {"langs": ["en"], "manual": False, "auto": True, "suffix": "auto"})
        args = subtitle_args(opts, Path("."), langs=["zh-Hans"], manual=False, auto=True, suffix="auto")
        self.assertEqual(args[args.index("--sub-langs") + 1], r"zh\-Hans")
        self.assertIn("--write-auto-subs", args)
        self.assertTrue(args[args.index("-o") + 1].endswith(".auto.%(ext)s"))

    def test_validation(self):
        with TemporaryDirectory() as dest:
            bad = [
                dict(mode="subtitles"),
                dict(start=10, end=10.2),
                dict(start=100, duration=50),
                dict(container="avi"),
                dict(audio_selectors=["ba[language=x];rm"], audio_languages=["x"]),
                dict(subtitles=[Subtitle("en$(x)", "manual")]),
                dict(rate_limit="gyors"),
            ]
            for kwargs in bad:
                with self.assertRaises(ValueError, msg=str(kwargs)):
                    DownloadOptions(url=URL, dest=dest, **kwargs).validate()
            DownloadOptions(url=URL, dest=dest, start=1, end=2).validate()

    def test_saved_analysis_and_polite_mode(self):
        with TemporaryDirectory() as d:
            info_json = Path(d) / "a.json"
            info_json.write_text("{}", encoding="utf-8")
            opts = DownloadOptions(url=URL, dest=d, info_json=str(info_json))
            args = media_args(opts, Path(d))
            self.assertEqual(args[-2:], ["--load-info-json", str(info_json)])
            self.assertNotIn(URL, args)
            subs = subtitle_args(opts.with_changes(subtitles=[Subtitle("en", "manual")]), Path(d),
                                 langs=["en"], manual=True, auto=False)
            self.assertIn("--load-info-json", subs)
            polite = media_args(DownloadOptions(url=URL, dest=d, polite=True), Path(d))
            self.assertIn("--sleep-requests", polite)
            self.assertNotIn("--sleep-requests", media_args(DownloadOptions(url=URL, dest=d), Path(d)))
            info_json.unlink()
            with self.assertRaises(ValueError):
                opts.validate()

    def test_rate_limit_errors_are_classified(self):
        from ytstudio.errors import explain
        bot = explain("ERROR: [youtube] x: Sign in to confirm you're not a bot. Use --cookies-from-browser "
                      "or --cookies for the authentication.")
        self.assertEqual(bot.kind, "bot_check")
        self.assertTrue(bot.throttled and bot.needs_browser)
        too_many = explain("HTTP Error 429: Too Many Requests")
        self.assertTrue(too_many.throttled and not too_many.needs_browser)
        age = explain("Sign in to confirm your age. This video may be inappropriate for some users.")
        self.assertEqual(age.kind, "login")
        self.assertFalse(age.throttled)
        self.assertEqual(explain("HTTP Error 403: Forbidden").kind, "")

    def test_section_open_end(self):
        self.assertEqual(section_arg(DownloadOptions(url=URL, dest=".", start=90)), "*00:01:30-inf")

    def test_size_estimate(self):
        info = multi()
        full = estimate_size(info, DownloadOptions(url=URL, dest=".", quality="1080"))
        clip = estimate_size(info, DownloadOptions(url=URL, dest=".", quality="1080", start=0, end=info.duration / 2))
        small = estimate_size(info, DownloadOptions(url=URL, dest=".", quality="360"))
        audio = estimate_size(info, DownloadOptions(url=URL, dest=".", mode="audio"))
        self.assertGreater(full, small)
        self.assertAlmostEqual(clip, full / 2, delta=full * 0.01)
        self.assertLess(audio, full)


if __name__ == "__main__":
    unittest.main()
