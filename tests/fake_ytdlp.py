"""A yt-dlp parancssorát utánzó tesztprogram (hálózat nélkül).

Valódi FFmpeg-gel készít rövid tesztvideót, így a felirat-beágyazás, a vágás
és a fájlkezelés valódi médiafájlon ellenőrizhető. Viselkedés környezeti
változókkal: FAKE_JSON (elemzés), FAKE_FAIL (hibaüzenet), FAKE_SLOW (lassú
letöltés a megszakítás teszteléséhez), FAKE_TITLE (cím).
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
args = sys.argv[1:]
TITLE = os.environ.get("FAKE_TITLE", "Teszt videó ékezetekkel ő ű 𝕐")
VID = "vid12345678"


def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default


def fill(template: str, ext: str, lang: str = "") -> str:
    name = template.replace("%(title).120B", TITLE).replace("%(id)s", VID)
    name = name.replace("%(language|hang)s", lang or "hang").replace("%%", "%")
    return name.replace("%(ext)s", ext)


if os.environ.get("FAKE_FAIL"):
    print("ERROR: [youtube] " + VID + ": " + os.environ["FAKE_FAIL"], file=sys.stderr, flush=True)
    sys.exit(1)

if "--dump-single-json" in args:
    print(Path(os.environ["FAKE_JSON"]).read_text(encoding="utf-8"))
    sys.exit(0)

# Mentett elemzés használata: naplózza, és szükség esetén lejárt linket szimulál.
if "--load-info-json" in args:
    log = os.environ.get("FAKE_CALLS")
    if log:
        with open(log, "a", encoding="utf-8") as handle:
            handle.write("load-info-json\n")
    if os.environ.get("FAKE_STALE"):
        print("ERROR: unable to download video data: HTTP Error 403: Forbidden", flush=True)
        sys.exit(1)
elif os.environ.get("FAKE_CALLS"):
    with open(os.environ["FAKE_CALLS"], "a", encoding="utf-8") as handle:
        handle.write("fresh\n")

work = Path(opt("-P"))
templates = [args[i + 1] for i, a in enumerate(args) if a == "-o"]
media_template = next(t for t in templates if not t.startswith("subtitle:"))
ffmpeg_dir = Path(opt("--ffmpeg-location"))
ffmpeg = ffmpeg_dir / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
print("[youtube] Extracting URL: " + args[-1], flush=True)

if "--skip-download" in args:
    sub_template = next((t[9:] for t in templates if t.startswith("subtitle:")), media_template)
    fmt = "vtt" if (opt("--convert-subs") == "vtt") else "srt"
    for lang in opt("--sub-langs").split(","):
        lang = lang.replace("\\", "")
        if lang == "xx":
            print("WARNING: Unable to download video subtitles for 'xx': HTTP Error 429: Too Many Requests")
            continue
        path = work / fill(sub_template, f"{lang}.{fmt}")
        if fmt == "srt":
            body = "".join(f"{i}\n00:00:0{i},000 --> 00:00:0{i},800\n{lang} felirat {i}\n\n" for i in range(1, 6))
        else:
            body = "WEBVTT\n\n" + "".join(f"00:00:0{i}.000 --> 00:00:0{i}.800\n{lang} felirat {i}\n\n" for i in range(1, 6))
        path.write_text(body, encoding="utf-8")
        print(f"[info] Writing video subtitles to: {path}", flush=True)
    sys.exit(0)

audio = "--extract-audio" in args
container = opt("--merge-output-format", "mp4").split("/")[0]
ext = (opt("--audio-format") or "opus") if audio else container
selectors = opt("-f", "")
languages = list(dict.fromkeys(re.findall(r"ba\[language=([\w-]+)\]", selectors))) if audio and "," in selectors else [""]
print('__YTS_REQ__["137", "140"]|[300000, 100000]|NA|NA', flush=True)
for fid, size in (("137", 300000), ("140", 100000)):
    steps = 30 if os.environ.get("FAKE_SLOW") else 3
    for i in range(1, steps + 1):
        done = size * i // steps
        print(f"__YTS_P__downloading|{done}|{size}|NA|1048576.0|{steps - i}|{fid}", flush=True)
        time.sleep(0.5 if os.environ.get("FAKE_SLOW") else 0.01)
    print(f"__YTS_P__finished|{size}|{size}|NA|NA|NA|{fid}", flush=True)
print("__YTS_PP__Merger|started", flush=True)
duration = "8"
for lang in languages:
    out = work / fill(media_template, ext, lang)
    if audio:
        cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
               f"sine=frequency=440:duration={duration}", str(out)]
    else:
        cmd = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
               f"testsrc=size=160x90:rate=10:duration={duration}", "-f", "lavfi", "-i",
               f"sine=frequency=440:duration={duration}", "-c:v", "libx264" if ext != "webm" else "libvpx-vp9",
               "-c:a", "aac" if ext != "webm" else "libopus", "-shortest", str(out)]
    subprocess.run(cmd, check=True)
    print("__YTS_PP__Merger|finished", flush=True)
    print("__YTS_OUT__" + str(out), flush=True)
sys.exit(0)
