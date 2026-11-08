"""Nonblocking subprocess orchestration, progress, subtitles and FFmpeg muxing."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import json
import os
import queue
import re
import subprocess
import sys
import threading

from .core import DownloadOptions, Subtitle, metadata_args, media_args, subtitles_args
from .settings import command_env, ffmpeg_location, find_exe
from .subtitles import trim_file

OutputCallback = Callable[[str], None]


class Cancelled(Exception):
    pass


@dataclass
class Job:
    id: int
    info_title: str
    options: DownloadOptions
    status: str = "Várakozik"
    output: str = ""


class Engine:
    def __init__(self):
        self.cancel_event = threading.Event()
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def tool_status(self) -> dict[str, str]:
        return {n: str(find_exe(n) or "HIÁNYZIK") for n in ("yt-dlp", "ffmpeg", "ffprobe", "deno")}

    def _start(self, cmd: list[str]) -> subprocess.Popen:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        # stdin DEVNULL prevents stdin prompt / interaction deadlock.
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                errors="replace", bufsize=1, env=command_env(),
                                creationflags=flags)
        with self._lock:
            self._process = proc
        return proc

    def stop(self) -> None:
        self.cancel_event.set()
        with self._lock:
            proc = self._process
        if proc and proc.poll() is None:
            try:
                if sys.platform == "win32":
                    # Kill the whole yt-dlp/ffmpeg tree, not only its parent.
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW, timeout=8)
                else:
                    proc.terminate()
            except (OSError, subprocess.TimeoutExpired):
                proc.terminate()

    def reset(self) -> None:
        self.cancel_event.clear()

    def _run(self, cmd: list[str], on_log: OutputCallback, capture_json: bool = False) -> tuple[str, str]:
        if self.cancel_event.is_set():
            raise Cancelled()
        proc = self._start(cmd)
        lines: list[str] = []
        output_path = ""
        try:
            assert proc.stdout
            for line in proc.stdout:
                if self.cancel_event.is_set():
                    proc.terminate()
                    break
                line = line.rstrip("\r\n")
                if line.startswith("__YTDLPSTUDIO_OUTPUT__"):
                    output_path = line.split("__YTDLPSTUDIO_OUTPUT__", 1)[1].strip()
                    on_log("Mentés: " + output_path)
                elif not capture_json:
                    on_log(line)
                if capture_json:
                    lines.append(line)
                else:
                    if line.startswith("ERROR:"):
                        lines.append(line)
            code = proc.wait(timeout=10 if self.cancel_event.is_set() else None)
            if self.cancel_event.is_set():
                raise Cancelled()
            if code:
                raise RuntimeError("\n".join(lines[-8:]) or f"A művelet hibával leállt (kód: {code}). Lásd a naplót.")
            return "\n".join(lines), output_path
        finally:
            if proc.stdout is not None:
                proc.stdout.close()
            with self._lock:
                if self._process is proc:
                    self._process = None
            if proc.poll() is None:
                proc.kill()
                proc.wait()

    def analyze(self, url: str) -> dict:
        yt = find_exe("yt-dlp")
        if not yt:
            raise FileNotFoundError("Hiányzik a yt-dlp. A kész Windows ZIP 'bin' mappájában kell lennie.")
        # Metadata writes only stdout JSON. stderr merged, so suppress regular warnings.
        raw, _ = self._run([str(yt)] + metadata_args(url, ffmpeg_location()), lambda _: None, True)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Nem értelmezhető a yt-dlp metaadat-válasza. Ellenőrizd a yt-dlp verzióját.") from exc

    def _mux_subtitles(self, video: Path, captions: list[tuple[Path, str]], on_log: OutputCallback) -> None:
        ffmpeg = find_exe("ffmpeg")
        if not ffmpeg:
            raise FileNotFoundError("Feliratbeágyazáshoz szükséges az FFmpeg.")
        if video.suffix.lower() not in {".mkv", ".mp4", ".webm"}:
            raise ValueError("Ebben a videóformátumban a felirat beágyazása nem támogatott.")
        # WebM supports WebVTT only. Simplify by explicitly rejecting SRT mux
        # rather than silently converting to an incompatible subtitle codec.
        if video.suffix.lower() == ".webm":
            raise ValueError("WebM-be automatikus feliratbeágyazás nem támogatott. A külső felirat megmarad.")
        temp = video.with_name(video.stem + ".with_subs" + video.suffix)
        args = [str(ffmpeg), "-hide_banner", "-y", "-i", str(video)]
        for subtitle, _ in captions:
            args.extend(["-i", str(subtitle)])
        args += ["-map", "0"]
        for i in range(len(captions)):
            args.extend(["-map", f"{i+1}:0"])
        args += ["-c", "copy", "-c:s", "mov_text" if video.suffix.lower() == ".mp4" else "srt"]
        # Added captions follow any embedded subtitle tracks in source; set
        # language metadata on incoming streams only if track counts are known.
        args += [str(temp)]
        try:
            self._run(args, on_log)
            if not temp.is_file() or temp.stat().st_size == 0:
                raise RuntimeError("Az FFmpeg nem hozott létre feliratos fájlt.")
            os.replace(temp, video)
        finally:
            temp.unlink(missing_ok=True)

    def download(self, options: DownloadOptions, on_log: OutputCallback) -> str:
        options.validate()
        yt = find_exe("yt-dlp")
        if not yt:
            raise FileNotFoundError("A yt-dlp nincs telepítve vagy nincs a bin mappában.")
        if not find_exe("ffmpeg"):
            raise FileNotFoundError("Hiányzik az FFmpeg (bin/ffmpeg.exe).")
        destination = Path(options.dest)
        output = ""
        if options.mode != "subtitles":
            _, output = self._run([str(yt)] + media_args(options, ffmpeg_location()), on_log)
        if options.subtitles:
            # Separate calls when manual/auto language overlaps avoid some
            # preference collisions. They may still share a file name for the
            # same language; select manual first and auto only for other langs.
            manual = [s for s in options.subtitles if s.kind == "manual"]
            auto = [s for s in options.subtitles if s.kind == "automatic" and s.language not in {m.language for m in manual}]
            before = {p.resolve() for p in destination.iterdir() if p.is_file()}
            for group in (manual, auto):
                if group:
                    on_log("Feliratok letöltése...")
                    self._run([str(yt)] + subtitles_args(options, ffmpeg_location(), group), on_log)
            after = [p for p in destination.iterdir()
                     if p.is_file() and p.suffix.lower() in {".srt", ".vtt"}
                     and p.resolve() not in before]
            # For matching only this video's captions, require the extractor ID
            # in output name. If no media (subtitles only), we keep new files.
            if output:
                match = re.search(r"\[([^\[\]]+)\]\.[^.]+$", Path(output).name)
                if match:
                    token = f"[{match.group(1)}]"
                    after = [p for p in after if token in p.name]
            if options.start is not None or options.end is not None:
                on_log("Feliratok időzítésének igazítása...")
                for path in after:
                    trim_file(path, options.start or 0.0, options.end)
            if options.embed_subtitles and output and after:
                try:
                    self._mux_subtitles(Path(output), [(p, "") for p in after], on_log)
                    on_log("Feliratok beágyazva.")
                except Exception as exc:
                    on_log(f"FIGYELEM: a feliratok külső fájlokban maradtak: {exc}")
        return output or str(destination)
