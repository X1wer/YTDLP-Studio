"""Valós hálózati ellenőrzés a csomagolt yt-dlp/FFmpeg eszközökkel (kézzel futtatandó).

    python tests/live_check.py [célmappa]

Jogszerűen használható tesztanyagok: Big Buck Bunny (Blender Foundation, CC BY 3.0),
„Me at the zoo” (az első YouTube-videó, rövid nyilvános tesztanyag). A többnyelvű
hangsáv ellenőrzéséhez egy 3 másodperces részlet készül, amelyet a szkript utána töröl.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import _support  # noqa: F401
from _support import bin_tool

from ytstudio import engine, updater
from ytstudio.core import DownloadOptions, PlaylistInfo, Subtitle, VideoInfo

BBB = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
ZOO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
MULTI = "https://www.youtube.com/watch?v=0e3GPea1Tyg"
results: list[tuple[str, str, str]] = []
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class External(Exception):
    """Külső szolgáltatás korlátozása (nem a program hibája)."""


def probe(path: Path) -> dict:
    out = subprocess.run([str(bin_tool("ffprobe")), "-v", "error", "-show_entries",
                          "format=duration,format_name:stream=codec_type,codec_name,height:stream_disposition=attached_pic:stream_tags=language",
                          "-of", "json", str(path)], capture_output=True, text=True, encoding="utf-8")
    return json.loads(out.stdout)


def check(name: str):
    def wrap(func):
        started = time.monotonic()
        try:
            detail = func() or ""
            results.append((name, "OK", f"{detail} ({time.monotonic() - started:.0f} s)"))
            print(f"[OK]   {name}: {detail}", flush=True)
        except External as exc:
            results.append((name, "KÜLSŐ", str(exc)))
            print(f"[KÜLSŐ] {name}: {exc}", flush=True)
        except Exception as exc:  # noqa: BLE001
            results.append((name, "HIBA", f"{type(exc).__name__}: {exc}"))
            print(f"[HIBA] {name}: {exc}", flush=True)
        return func
    return wrap


def run(dest: Path) -> None:
    @check("Elemzés (Big Buck Bunny)")
    def _():
        info = engine.analyze(BBB)
        assert isinstance(info, VideoInfo) and 2160 in info.heights, info
        return f"{info.title}, {info.duration:.0f} s, max {info.heights[0]}p"

    @check("Videórészlet MP4 360p (01:00–01:10)")
    def _():
        opts = DownloadOptions(url=BBB, dest=str(dest), quality="360", start=60, end=70, duration=635)
        f = engine.DownloadTask(opts, "live1").run().main_file
        p = probe(f)
        dur = float(p["format"]["duration"])
        heights = [s.get("height") for s in p["streams"] if s["codec_type"] == "video"
                   and not s.get("disposition", {}).get("attached_pic")]
        assert f.suffix == ".mp4" and abs(dur - 10) < 1.5 and heights == [360], (dur, heights)
        return f"{f.name}, {dur:.2f} s, {heights[0]}p, {f.stat().st_size // 1024} KB"

    @check("Formátum érvényesül: WebM (VP9/AV1 + Opus), 240p")
    def _():
        opts = DownloadOptions(url=BBB, dest=str(dest), container="webm", quality="240", start=5, end=12, duration=635)
        f = engine.DownloadTask(opts, "live2").run().main_file
        codecs = sorted(s["codec_name"] for s in probe(f)["streams"])
        assert f.suffix == ".webm" and ("vp9" in codecs or "av1" in codecs) and "opus" in codecs, codecs
        return f"{f.name}: {codecs}"

    @check("Csak hang: MP3 (30 s részlet)")
    def _():
        opts = DownloadOptions(url=BBB, dest=str(dest), mode="audio", audio_format="mp3", start=100, end=130, duration=635)
        f = engine.DownloadTask(opts, "live3").run().main_file
        p = probe(f)
        dur = float(p["format"]["duration"])
        assert f.suffix == ".mp3" and abs(dur - 30) < 1.5, dur
        return f"{f.name}, {dur:.1f} s"

    @check("Feliratok beágyazva MKV-ba (Me at the zoo, en + de)")
    def _():
        info = engine.analyze(ZOO)
        subs = [s for s in info.subtitles if s.language in ("en", "de")]
        opts = DownloadOptions(url=ZOO, dest=str(dest), container="mkv", subtitles=subs, embed_subtitles=True,
                               subtitle_format="srt", duration=info.duration)
        f = engine.DownloadTask(opts, "live4").run().main_file
        langs = sorted(s.get("tags", {}).get("language") for s in probe(f)["streams"] if s["codec_type"] == "subtitle")
        assert langs == ["deu", "eng"], langs
        return f"{f.name}: feliratsávok {langs}"

    @check("Vágott részlet + felirat igazítása (zoo 00:05–00:12, külön SRT)")
    def _():
        opts = DownloadOptions(url=ZOO, dest=str(dest), container="mp4", subtitles=[Subtitle("en", "manual")],
                               start=5, end=12, duration=19)
        files = engine.DownloadTask(opts, "live5").run().files
        srt = next(f for f in files if f.suffix == ".srt")
        first = next(line for line in srt.read_text(encoding="utf-8").splitlines() if "-->" in line)
        assert first.startswith("00:00:0"), first
        return f"{srt.name}: első felirat {first}"

    @check("Csak felirat: YouTube automatikus magyar fordítás (SRT)")
    def _():
        opts = DownloadOptions(url=MULTI, dest=str(dest), mode="subtitles",
                               subtitles=[Subtitle("hu", "translated", "Hungarian", "en")])
        try:
            files = engine.DownloadTask(opts, "live6").run().files
        except engine.OperationError as exc:
            if "429" in exc.details:
                raise External("a YouTube 429-cel elutasítja a fordított feliratot; a program ezt érthetően jelzi: "
                               + exc.details.splitlines()[-1][:160])
            raise
        f = files[0]
        text = f.read_text(encoding="utf-8")
        assert f.name.endswith(".hu.srt") and text.count("-->") > 50
        return f"{f.name}, {text.count('-->')} felirat"

    @check("Több hangsáv egy MKV-ban, nyelvi címkével (3 s, utána törölve)")
    def _():
        info = engine.analyze(MULTI)
        tracks = {t.language: t for t in info.audio_tracks}
        opts = DownloadOptions(url=MULTI, dest=str(dest), quality="144", start=10, end=13, duration=info.duration,
                               audio_selectors=[tracks["de"].selector, tracks["es"].selector],
                               audio_languages=["de", "es"], embed_thumbnail=False)
        f = engine.DownloadTask(opts, "live7").run().main_file
        langs = [s.get("tags", {}).get("language") for s in probe(f)["streams"] if s["codec_type"] == "audio"]
        f.unlink()
        assert f.suffix == ".mkv" and langs == ["deu", "spa"], langs
        return f"hangsávok: {langs}"

    @check("Csatornalink → Videók lista (flat)")
    def _():
        pl = engine.analyze("https://www.youtube.com/@jawed")
        assert isinstance(pl, PlaylistInfo) and pl.entries, pl
        return f"{pl.title}: {len(pl.entries)} videó"

    @check("Megszakítás 4K letöltés közben, folyamatok leállnak")
    def _():
        def count():
            out = subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower()
            return out.count("yt-dlp.exe"), out.count("ffmpeg.exe")
        before = count()
        task = engine.DownloadTask(DownloadOptions(url=BBB, dest=str(dest), quality="2160", container="mkv"), "live8")
        states = []
        thread = threading.Thread(target=lambda: states.append(_run_catch(task)))
        thread.start()
        deadline = time.time() + 60
        while time.time() < deadline and (task.progress.percent or 0) < 1:
            time.sleep(0.5)
        task.cancel()
        thread.join(15)
        time.sleep(1)
        after = count()
        engine.cleanup_workdir(dest, "live8")
        assert states == ["cancelled"] and after == before, (states, before, after)
        assert not (dest / engine.TEMP_DIR_NAME).exists()
        return "leállt, nincs árva yt-dlp/ffmpeg, ideiglenes fájlok törölve"

    @check("Unicode / ékezetes mentési mappa")
    def _():
        folder = dest / "Ékezetes ő ű mappa"
        opts = DownloadOptions(url=ZOO, dest=str(folder), mode="audio", audio_format="m4a")
        f = engine.DownloadTask(opts, "live9").run().main_file
        assert f.exists() and f.parent == folder
        return str(f.relative_to(dest))

    @check("yt-dlp frissítés: valós letöltés + SHA-256 + futtatás (ideiglenes mappába)")
    def _():
        rel = updater.fetch_latest("stable")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "yt-dlp.exe"
            shutil.copy2(bin_tool("yt-dlp"), target)
            version = updater.install_release(rel, target, "régi")
            assert updater.backup_path(target).exists()
        return f"telepítve {version} ({rel.channel}), előző verzió mentve"


def _run_catch(task):
    try:
        task.run()
        return "done"
    except engine.Cancelled:
        return "cancelled"


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="ytstudio-live-"))
    target.mkdir(parents=True, exist_ok=True)
    print("Célmappa:", target)
    run(target)
    ok = sum(1 for _, state, _ in results if state == "OK")
    failed = sum(1 for _, state, _ in results if state == "HIBA")
    print(f"\n{ok}/{len(results)} sikeres, {failed} hiba, {len(results) - ok - failed} külső korlátozás")
    (target / "live_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.exit(1 if failed else 0)
