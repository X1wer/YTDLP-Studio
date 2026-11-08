"""Folyamatkezelés: elemzés, letöltés, haladás, feliratok, vágás és véglegesítés.

Minden külső program ellenőrzött argumentumlistával indul (shell nélkül).
Windows alatt minden gyerekfolyamat egy saját Job Objectbe kerül, így
megszakításkor vagy az alkalmazás (akár hibás) leállásakor a yt-dlp által
indított FFmpeg-folyamatok sem maradnak futva.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

from .core import (DownloadOptions, PlaylistInfo, Subtitle, Tools, VideoInfo, media_args,
                   metadata_args, subtitle_args, subtitle_plan, youtube_playlist_context)
from .errors import FriendlyError, explain
from .langs import to_iso639_2
from .settings import command_env, data_dir, find_exe
from .subtitles import trim_file

LogCallback = Callable[[str], None]
TEMP_DIR_NAME = ".ytdlp-studio-temp"
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class Cancelled(Exception):
    """A felhasználó megszakította a műveletet."""


class OperationError(Exception):
    def __init__(self, friendly: FriendlyError, details: str = ""):
        super().__init__(friendly.message)
        self.friendly = friendly
        self.details = details


def tools() -> Tools:
    ffmpeg = find_exe("ffmpeg")
    cache = data_dir() / "cache" / "yt-dlp"
    return Tools(ffmpeg.parent if ffmpeg else None, find_exe("deno"), cache)


def tool_cmd(name: str) -> list[str]:
    """A külső eszköz indítóparancsa (tesztekben helyettesíthető)."""
    return [str(require(name))]


def require(name: str) -> Path:
    path = find_exe(name)
    if path is None:
        raise OperationError(FriendlyError(
            f"Hiányzik: {name}",
            f"A program mappájából hiányzik a bin\\{name}.exe. Csomagold ki újra a teljes "
            f"portable ZIP-et, vagy forrásból futtatva tedd a bin mappába.", False))
    return path


# --------------------------------------------------------------------------- #
# Folyamatkezelés (Windows Job Object)
# --------------------------------------------------------------------------- #

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _BasicLimit(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _ExtendedLimit(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _BasicLimit), ("IoInfo", _IoCounters),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]

    def _create_job(proc: subprocess.Popen):
        job = _kernel32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = _ExtendedLimit()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = _kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
        if not ok or not _kernel32.AssignProcessToJobObject(job, int(proc._handle)):  # type: ignore[attr-defined]
            _kernel32.CloseHandle(job)
            return None
        return job

    def _terminate_job(job) -> None:
        _kernel32.TerminateJobObject(job, 1)

    def _close_job(job) -> None:
        _kernel32.CloseHandle(job)

    def _hide(path: Path) -> None:
        _kernel32.SetFileAttributesW(str(path), 0x2)  # FILE_ATTRIBUTE_HIDDEN
else:  # pragma: no cover - a célplatform Windows
    def _create_job(proc):
        return None

    def _terminate_job(job) -> None:
        pass

    def _close_job(job) -> None:
        pass

    def _hide(path: Path) -> None:
        pass


class Process:
    """Egy külső program futtatása soronkénti, nem blokkoló kimenetolvasással."""

    def __init__(self, cmd: list[str], *, cwd: Path | None = None, merge_stderr: bool = True):
        self.cmd = cmd
        self.popen = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
            env=command_env(), cwd=str(cwd) if cwd else None, creationflags=_NO_WINDOW)
        self._job = _create_job(self.popen)
        self._killed = False

    def lines(self):
        """Sorok a kimenetből; a ``\\r``-rel frissített FFmpeg-állapotsorokat is szétválasztja."""
        stream = self.popen.stdout
        assert stream is not None
        buffer = b""
        while True:
            chunk = stream.read1(65536) if hasattr(stream, "read1") else stream.read(4096)
            if not chunk:
                break
            buffer += chunk
            parts = re.split(rb"\r\n|\r|\n", buffer)
            buffer = parts.pop()
            for part in parts:
                if part.strip():
                    yield part.decode("utf-8", errors="replace")
        if buffer.strip():
            yield buffer.decode("utf-8", errors="replace")

    def communicate(self, cancel: threading.Event | None, timeout: float | None = None) -> tuple[bytes, bytes]:
        started = time.monotonic()
        while True:
            try:
                return self.popen.communicate(timeout=0.2)
            except subprocess.TimeoutExpired:
                if cancel is not None and cancel.is_set():
                    self.kill()
                    raise Cancelled() from None
                if timeout is not None and time.monotonic() - started > timeout:
                    self.kill()
                    raise OperationError(FriendlyError(
                        "Időtúllépés", "A művelet túl sokáig tartott, ezért leállítottam.")) from None

    def kill(self) -> None:
        self._killed = True
        if self.popen.poll() is not None:
            return
        if self._job is not None:
            _terminate_job(self._job)
        else:
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/PID", str(self.popen.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=_NO_WINDOW, timeout=10)
                else:
                    self.popen.terminate()
            except (OSError, subprocess.TimeoutExpired):
                pass
        try:
            self.popen.kill()
        except OSError:
            pass

    def wait(self) -> int:
        return self.popen.wait()

    def close(self) -> None:
        for stream in (self.popen.stdout, self.popen.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        if self.popen.poll() is None:
            self.kill()
            try:
                self.popen.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        if self._job is not None:
            _close_job(self._job)
            self._job = None


def run_quiet(cmd: list[str], timeout: float = 20) -> tuple[int, str]:
    try:
        result = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, env=command_env(), timeout=timeout,
                                creationflags=_NO_WINDOW)
        return result.returncode, result.stdout.decode("utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, str(exc)


# --------------------------------------------------------------------------- #
# Eszközverziók
# --------------------------------------------------------------------------- #

def tool_version(name: str) -> str:
    path = find_exe(name)
    if path is None:
        return ""
    flag = "--version" if name in ("yt-dlp", "deno") else "-version"
    code, out = run_quiet([str(path), flag], timeout=25)
    if code != 0 or not out.strip():
        return "ismeretlen"
    first = out.strip().splitlines()[0]
    if name in ("ffmpeg", "ffprobe"):
        match = re.search(r"version\s+(\S+)", first)
        return match.group(1) if match else first
    if name == "deno":
        match = re.search(r"deno\s+(\S+)", first)
        return match.group(1) if match else first
    return first.strip()


# --------------------------------------------------------------------------- #
# Elemzés
# --------------------------------------------------------------------------- #

def analyze(url: str, *, cancel: threading.Event | None = None, allow_playlist: bool = True,
            cookies_browser: str = "", on_log: LogCallback = lambda _: None,
            _depth: int = 0) -> VideoInfo | PlaylistInfo:
    cmd = tool_cmd("yt-dlp") + metadata_args(url, tools(), allow_playlist=allow_playlist,
                                    cookies_browser=cookies_browser)
    on_log("Elemzés: " + url)
    proc = Process(cmd, cwd=data_dir(), merge_stderr=False)
    try:
        out, err = proc.communicate(cancel, timeout=600)
    finally:
        proc.close()
    errors = err.decode("utf-8", errors="replace")
    for line in errors.splitlines():
        if line.strip():
            on_log(line)
    if proc.popen.returncode != 0:
        details = errors.strip() or out.decode("utf-8", errors="replace")[-2000:].strip()
        raise OperationError(explain(details), details)
    try:
        data = json.loads(out.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise OperationError(FriendlyError(
            "Értelmezhetetlen válasz",
            "A yt-dlp válasza nem értelmezhető. Frissítsd a yt-dlp-t az Eszközök menüben."),
            errors.strip()) from exc
    if not isinstance(data, dict):
        raise OperationError(FriendlyError("Értelmezhetetlen válasz", "Üres válasz érkezett."))
    entries = data.get("entries")
    if data.get("_type") in ("playlist", "multi_video") or isinstance(entries, list):
        entries = [e for e in entries or [] if isinstance(e, dict)]
        if len(entries) == 1 and entries[0].get("formats"):
            data = entries[0]
        elif (entries and allow_playlist and all(str(e.get("ie_key")) == "YoutubeTab" for e in entries)
              and str(entries[0].get("url") or "").startswith("https://") and _depth == 0):
            # Csatornalink: a fülek (Videók, Shorts, Élő) közül a Videók listáját nyitja meg.
            on_log("Csatorna: a „Videók” fül betöltése.")
            return analyze(str(entries[0]["url"]), cancel=cancel, allow_playlist=True,
                           cookies_browser=cookies_browser, on_log=on_log, _depth=1)
        else:
            playlist = PlaylistInfo.from_json(data, url)
            if not playlist.entries:
                raise OperationError(FriendlyError("Üres lista", "A lejátszási lista nem tartalmaz elérhető videót.", False))
            return playlist
    info = VideoInfo.from_json(data, url)
    has_video, has_list = youtube_playlist_context(url)
    info.playlist_hint = has_video and has_list
    if info.has_drm:
        raise OperationError(FriendlyError(
            "DRM-védett tartalom",
            "A tartalom másolásvédelemmel (DRM) rendelkezik, ezért a program nem tölti le.", False))
    return info


# --------------------------------------------------------------------------- #
# Letöltés
# --------------------------------------------------------------------------- #

PP_LABELS = {
    "Merger": "Sávok összefűzése", "ExtractAudio": "Hang átalakítása",
    "VideoRemuxer": "Konténer átalakítása", "VideoConvertor": "Videó átkódolása",
    "Metadata": "Metaadatok írása", "EmbedThumbnail": "Borítókép beágyazása",
    "ThumbnailsConvertor": "Borítókép átalakítása", "SubtitlesConvertor": "Felirat átalakítása",
    "MoveFiles": "Fájlok áthelyezése", "FixupM3u8": "Fájl javítása", "FixupM4a": "Fájl javítása",
    "FixupStretched": "Fájl javítása", "FixupDuplicateMoov": "Fájl javítása",
    "FixupTimestamp": "Fájl javítása", "FixupDuration": "Fájl javítása",
    "ModifyChapters": "Fejezetek kezelése", "SplitChapters": "Fejezetek kezelése",
    "FFmpegConcat": "Összefűzés",
}


@dataclass
class Progress:
    stage: str = "queued"          # queued|starting|downloading|processing|subtitles|finishing
    text: str = ""
    percent: float | None = None   # None = határozatlan
    speed: float | None = None     # bájt/s
    eta: float | None = None       # másodperc
    downloaded: float | None = None
    total: float | None = None


@dataclass
class DownloadResult:
    files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def main_file(self) -> Path | None:
        return self.files[0] if self.files else None


def _num(value: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number >= 0 else None


def job_workdir(dest: Path, key: str) -> Path:
    return dest / TEMP_DIR_NAME / key


def cleanup_workdir(dest: Path, key: str) -> None:
    work = job_workdir(dest, key)
    shutil.rmtree(work, ignore_errors=True)
    try:
        (dest / TEMP_DIR_NAME).rmdir()  # csak ha üres
    except OSError:
        pass


class DownloadTask:
    """Egy letöltési feladat teljes végrehajtása egy saját munkamappában."""

    def __init__(self, opts: DownloadOptions, key: str, *,
                 on_progress: Callable[[Progress], None] = lambda _: None,
                 on_log: LogCallback = lambda _: None):
        self.opts = opts
        self.key = key
        self.on_progress = on_progress
        self.on_log = on_log
        self.cancel_event = threading.Event()
        self._proc: Process | None = None
        self._lock = threading.Lock()
        self.progress = Progress()

    # -- vezérlés ---------------------------------------------------------- #
    def cancel(self) -> None:
        self.cancel_event.set()
        with self._lock:
            proc = self._proc
        if proc is not None:
            proc.kill()

    def _check(self) -> None:
        if self.cancel_event.is_set():
            raise Cancelled()

    def _emit(self, **changes) -> None:
        for key, value in changes.items():
            setattr(self.progress, key, value)
        self.on_progress(Progress(**vars(self.progress)))

    # -- futtatás ------------------------------------------------------------ #
    def run(self) -> DownloadResult:
        opts = self.opts
        opts.validate()
        tool_cmd("yt-dlp")
        require("ffmpeg")
        dest = Path(opts.dest)
        work = job_workdir(dest, self.key)
        work.mkdir(parents=True, exist_ok=True)
        _hide(dest / TEMP_DIR_NAME)
        result = DownloadResult()
        self._emit(stage="starting", text="Videóadatok lekérése…", percent=None)
        media: list[Path] = []
        if opts.mode != "subtitles":
            media = self._download_media(work)
            self._check()
            if opts.is_clip and opts.cut_method == "full":
                media = [self._local_cut(path) for path in media]
        subs: list[tuple[Path, Subtitle | None, str]] = []
        if opts.wants_subtitles:
            subs = self._download_subtitles(work, result)
            if opts.mode == "subtitles" and not subs:
                raise OperationError(FriendlyError(
                    "Nem sikerült feliratot letölteni",
                    "A kijelölt feliratok egyike sem volt letölthető. Lásd a naplót."),
                    "\n".join(result.warnings))
        self._check()
        if subs and opts.is_clip:
            self._emit(stage="finishing", text="Feliratok időzítésének igazítása…", percent=None)
            offset = self._probe_offset(media[0]) if media and opts.mode == "video" else 0.0
            if offset:
                self.on_log(f"A gyors vágás miatt a hang {offset:.3f} mp-cel később indul; a feliratok ehhez igazodnak.")
            for path, _, _ in subs:
                kept = trim_file(path, opts.start or 0.0, opts.end, offset)
                self.on_log(f"Felirat igazítva ({kept} sor maradt): {path.name}")
        if subs and opts.embed_subtitles and opts.mode == "video" and media:
            self._emit(stage="finishing", text="Feliratok beágyazása…", percent=None)
            try:
                for video in media:
                    self._mux_subtitles(video, subs)
                for path, _, _ in subs:
                    path.unlink(missing_ok=True)
                self.on_log("A feliratok a videófájlba kerültek.")
            except Cancelled:
                raise
            except Exception as exc:  # noqa: BLE001 - a videó ettől még használható
                message = f"A feliratokat nem sikerült beágyazni, külön fájlként mentettem őket ({exc})."
                result.warnings.append(message)
                self.on_log("FIGYELEM: " + message)
        self._check()
        self._emit(stage="finishing", text="Fájlok áthelyezése…", percent=None)
        result.files = self._finalize(work, dest, media, [p for p, _, _ in subs])
        cleanup_workdir(dest, self.key)
        self._emit(stage="done", text="Kész", percent=100.0, speed=None, eta=None)
        return result

    def _spawn(self, cmd: list[str], cwd: Path) -> Process:
        self._check()
        proc = Process(cmd, cwd=cwd)
        with self._lock:
            self._proc = proc
        if self.cancel_event.is_set():
            proc.kill()
        return proc

    def _release(self, proc: Process) -> None:
        with self._lock:
            if self._proc is proc:
                self._proc = None
        proc.close()

    # -- médialetöltés --------------------------------------------------------- #
    def _download_media(self, work: Path) -> list[Path]:
        opts = self.opts
        cmd = tool_cmd("yt-dlp") + media_args(opts, work, tools())
        self.on_log("Letöltés indítása: " + (opts.title or opts.url))
        proc = self._spawn(cmd, work)
        outputs: list[Path] = []
        errors: list[str] = []
        streams: dict[str, list[float]] = {}   # format_id -> [letöltve, teljes]
        clip_len = None
        if opts.is_clip and opts.cut_method == "sections":
            end = opts.end if opts.end is not None else opts.duration
            if end:
                clip_len = max(0.5, end - (opts.start or 0))
        last_log = 0.0
        try:
            for line in proc.lines():
                if self.cancel_event.is_set():
                    break
                if line.startswith("__YTS_P__"):
                    self._on_progress_line(line[9:], streams)
                    now = time.monotonic()
                    if now - last_log > 5:
                        last_log = now
                        self.on_log(self._progress_summary())
                    continue
                if line.startswith("__YTS_REQ__"):
                    self._on_requested(line[11:], streams)
                    continue
                if line.startswith("__YTS_PP__"):
                    name, _, status = line[10:].partition("|")
                    if status == "started":
                        label = PP_LABELS.get(name, "Utófeldolgozás")
                        self._emit(stage="processing", text=label + "…", percent=None, speed=None, eta=None)
                    continue
                if line.startswith("__YTS_OUT__"):
                    path = Path(line[11:].strip())
                    outputs.append(path)
                    self.on_log("Elkészült: " + path.name)
                    continue
                if clip_len and "time=" in line and line.lstrip().startswith(("frame=", "size=")):
                    self._on_ffmpeg_line(line, clip_len)
                    continue
                if line.startswith("[download]") and "%" in line and " of " in line:
                    continue  # a sablonos haladásjelzés már feldolgozta
                if line.startswith("ERROR:"):
                    errors.append(line)
                elif line.startswith(("[youtube]", "[info]", "[generic]")) and self.progress.stage == "starting":
                    self._emit(text="Videóadatok lekérése…")
                self.on_log(line)
            code = proc.wait()
        finally:
            self._release(proc)
        self._check()
        if code != 0:
            details = "\n".join(errors) or f"A yt-dlp hibakóddal ({code}) állt le."
            raise OperationError(explain(details), details)
        outputs = [p for p in outputs if p.is_file()]
        if not outputs:
            outputs = self._scan_media(work)
        if not outputs:
            raise OperationError(FriendlyError("Nem készült fájl",
                                               "A yt-dlp nem hozott létre kimeneti fájlt. Lásd a naplót."))
        return outputs

    def _on_requested(self, payload: str, streams: dict[str, list[float]]) -> None:
        try:
            ids_raw, sizes_raw, approx_raw, single_raw = payload.split("|", 3)
            ids = json.loads(ids_raw) if ids_raw not in ("NA", "null") else None
            sizes = json.loads(sizes_raw) if sizes_raw not in ("NA", "null") else None
            approx = json.loads(approx_raw) if approx_raw not in ("NA", "null") else None
        except (ValueError, json.JSONDecodeError):
            return
        if isinstance(ids, list):
            for i, fid in enumerate(ids):
                size = None
                for source in (sizes, approx):
                    if isinstance(source, list) and i < len(source) and source[i]:
                        size = float(source[i])
                        break
                streams.setdefault(str(fid), [0.0, size or 0.0])

    def _on_progress_line(self, payload: str, streams: dict[str, list[float]]) -> None:
        parts = payload.split("|")
        if len(parts) < 7:
            return
        status, downloaded, total, estimate, speed, eta, fid = parts[:7]
        done = _num(downloaded)
        size = _num(total) or _num(estimate)
        entry = streams.setdefault(fid, [0.0, 0.0])
        if done is not None:
            entry[0] = done
        if size:
            entry[1] = size
        if status == "finished" and entry[1]:
            entry[0] = entry[1]
        totals = [v[1] for v in streams.values()]
        if totals and all(totals):
            percent = min(100.0, 100.0 * sum(v[0] for v in streams.values()) / sum(totals))
        elif entry[1]:
            percent = min(100.0, 100.0 * entry[0] / entry[1])
        else:
            percent = None
        index = list(streams).index(fid) + 1
        count = len(streams)
        label = "Letöltés"
        if count > 1:
            label += f" ({index}/{count}. sáv)"
        self._emit(stage="downloading", text=label, percent=percent, speed=_num(speed), eta=_num(eta),
                   downloaded=sum(v[0] for v in streams.values()),
                   total=sum(totals) if totals and all(totals) else None)

    def _on_ffmpeg_line(self, line: str, clip_len: float) -> None:
        match = re.search(r"time=(-?)(\d+):(\d{2}):(\d{2}(?:\.\d+)?)", line)
        if not match:
            return
        seconds = 0.0 if match.group(1) else int(match.group(2)) * 3600 + int(match.group(3)) * 60 + float(match.group(4))
        speed = re.search(r"speed=\s*([\d.]+)x", line)
        factor = float(speed.group(1)) if speed else None
        size = re.search(r"size=\s*(\d+)\s*(KiB|kB|MiB|MB)", line)
        downloaded = None
        if size:
            downloaded = int(size.group(1)) * (1024 if size.group(2) in ("KiB", "kB") else 1024 * 1024)
        eta = (clip_len - seconds) / factor if factor else None
        self._emit(stage="downloading", text="Szakasz letöltése", percent=min(100.0, 100 * seconds / clip_len),
                   speed=None, eta=eta, downloaded=downloaded, total=None)

    def _progress_summary(self) -> str:
        p = self.progress
        text = f"{p.text}: {p.percent:.1f}%" if p.percent is not None else p.text
        if p.speed:
            text += f", {p.speed / 1048576:.2f} MB/s"
        return text

    def _scan_media(self, work: Path) -> list[Path]:
        skip = {".part", ".ytdl", ".srt", ".vtt", ".json", ".jpg", ".png", ".webp", ".tmp", ".ass", ".lrc"}
        return sorted((p for p in work.iterdir() if p.is_file() and p.suffix.lower() not in skip
                       and ".part-Frag" not in p.name and not re.search(r"\.f\d+[\w-]*\.\w+$", p.name)),
                      key=lambda p: p.stat().st_size, reverse=True)

    # -- feliratok ------------------------------------------------------------- #
    def _download_subtitles(self, work: Path, result: DownloadResult) -> list[tuple[Path, Subtitle | None, str]]:
        opts = self.opts
        found: list[tuple[Path, Subtitle | None, str]] = []
        plan = subtitle_plan(opts)
        for step in plan:
            self._check()
            self._emit(stage="subtitles", text="Feliratok letöltése…", percent=None, speed=None, eta=None)
            before = {p.name for p in work.iterdir()}
            cmd = tool_cmd("yt-dlp") + subtitle_args(
                opts, work, tools(), langs=step["langs"], manual=step["manual"], auto=step["auto"],
                suffix=step["suffix"])
            proc = self._spawn(cmd, work)
            messages: list[str] = []
            try:
                for line in proc.lines():
                    if self.cancel_event.is_set():
                        break
                    if line.startswith(("ERROR:", "WARNING:")):
                        messages.append(line)
                    self.on_log(line)
                code = proc.wait()
            finally:
                self._release(proc)
            self._check()
            new_files = [p for p in work.iterdir() if p.is_file() and p.name not in before
                         and p.suffix.lower() in (".srt", ".vtt", ".ass", ".ttml", ".json3", ".srv3")]
            manual_langs = {s.language for s in opts.subtitles if s.group == "manual"}
            for path in sorted(new_files):
                lang = self._lang_of(path, step["langs"], step["suffix"])
                group = "auto" if step["suffix"] or lang not in manual_langs else "manual"
                sub = next((s for s in opts.subtitles if s.language == lang and s.group == group), None)
                found.append((path, sub, lang))
            got = {self._lang_of(p, step["langs"], step["suffix"]) for p in new_files}
            missing = [l for l in step["langs"] if l not in got]
            if opts.sub_langs:
                missing = []  # lejátszási listánál a preferált nyelvek opcionálisak
            if code != 0 or missing:
                detail = explain("\n".join(messages)).message if messages else ""
                names = ", ".join(missing) if missing else "egyes feliratok"
                message = f"Nem sikerült letölteni: {names}. {detail}".strip()
                result.warnings.append(message)
                self.on_log("FIGYELEM: " + message)
        return found

    @staticmethod
    def _lang_of(path: Path, langs: list[str], suffix: str) -> str:
        stem = path.name[: -len(path.suffix)]
        for lang in sorted(langs, key=len, reverse=True):
            if stem.endswith("." + lang):
                return lang
        return stem.rsplit(".", 1)[-1] if "." in stem else ""

    def _probe_offset(self, media: Path) -> float:
        ffprobe = find_exe("ffprobe")
        if ffprobe is None:
            return 0.0
        code, out = run_quiet([str(ffprobe), "-v", "error", "-show_entries",
                               "format=start_time:stream=codec_type,start_time", "-of", "json", str(media)])
        if code != 0:
            return 0.0
        try:
            data = json.loads(out)
            fmt_start = float(data.get("format", {}).get("start_time") or 0)
            starts = [float(s["start_time"]) for s in data.get("streams", [])
                      if s.get("codec_type") == "audio" and s.get("start_time") not in (None, "N/A")]
        except (ValueError, KeyError, TypeError):
            return 0.0
        if not starts:
            return 0.0
        offset = min(starts) - fmt_start
        return offset if 0.02 < offset < 30 else 0.0

    def _mux_subtitles(self, video: Path, subs: list[tuple[Path, Subtitle | None, str]]) -> None:
        ffmpeg = require("ffmpeg")
        ext = video.suffix.lower()
        if ext not in (".mp4", ".m4v", ".mkv", ".webm", ".mov"):
            raise ValueError("ebben a formátumban nem támogatott a beágyazás")
        existing = 0
        ffprobe = find_exe("ffprobe")
        if ffprobe:
            code, out = run_quiet([str(ffprobe), "-v", "error", "-select_streams", "s",
                                   "-show_entries", "stream=index", "-of", "csv=p=0", str(video)])
            if code == 0:
                existing = len([l for l in out.splitlines() if l.strip()])
        codec = {".mp4": "mov_text", ".m4v": "mov_text", ".mov": "mov_text", ".webm": "webvtt"}.get(ext, "copy")
        temp = video.with_name(video.stem + ".subs-tmp" + video.suffix)
        cmd = [str(ffmpeg), "-hide_banner", "-nostdin", "-y", "-i", str(video)]
        for path, _, _ in subs:
            cmd += ["-i", str(path)]
        cmd += ["-map", "0"]
        for i in range(len(subs)):
            cmd += ["-map", f"{i + 1}:0"]
        cmd += ["-c", "copy", "-c:s", codec]
        for i, (_, sub, lang) in enumerate(subs):
            index = existing + i
            iso = to_iso639_2(lang)
            if iso:
                cmd += [f"-metadata:s:s:{index}", f"language={iso}"]
            title = sub.label if sub else lang
            cmd += [f"-metadata:s:s:{index}", f"title={title}"]
        if ext in (".mp4", ".m4v", ".mov"):
            cmd += ["-movflags", "+faststart"]
        cmd.append(str(temp))
        proc = self._spawn(cmd, video.parent)
        tail: list[str] = []
        try:
            for line in proc.lines():
                tail = (tail + [line])[-6:]
            code = proc.wait()
        finally:
            self._release(proc)
        self._check()
        if code != 0 or not temp.is_file() or temp.stat().st_size == 0:
            temp.unlink(missing_ok=True)
            raise RuntimeError(" ".join(tail[-2:]) or "FFmpeg-hiba")
        os.replace(temp, video)

    # -- helyi vágás ----------------------------------------------------------- #
    def _local_cut(self, src: Path) -> Path:
        opts = self.opts
        ffmpeg = require("ffmpeg")
        start = opts.start or 0.0
        end = opts.end if opts.end is not None else opts.duration
        self._emit(stage="processing", text="Vágás…" if not opts.accurate_cut else "Pontos vágás (újrakódolás)…",
                   percent=None, speed=None, eta=None)
        temp = src.with_name(src.stem + ".cut-tmp" + src.suffix)
        cmd = [str(ffmpeg), "-hide_banner", "-nostdin", "-y", "-ss", f"{start:.3f}", "-i", str(src)]
        if end:
            cmd += ["-t", f"{max(0.1, end - start):.3f}"]
        ext = src.suffix.lower()
        if not opts.accurate_cut:
            cmd += ["-map", "0", "-c", "copy", "-avoid_negative_ts", "make_zero"]
        elif opts.mode == "audio":
            codec = {".mp3": ["-c:a", "libmp3lame", "-q:a", "0"], ".m4a": ["-c:a", "aac", "-b:a", "256k"],
                     ".aac": ["-c:a", "aac", "-b:a", "256k"], ".opus": ["-c:a", "libopus", "-b:a", "160k"],
                     ".ogg": ["-c:a", "libopus", "-b:a", "160k"], ".flac": ["-c:a", "flac"],
                     ".wav": ["-c:a", "pcm_s16le"]}.get(ext, ["-c:a", "copy"])
            cmd += ["-map", "0:a"] + codec
        elif ext == ".webm":
            cmd += ["-map", "0:v:0", "-map", "0:a", "-c:v", "libvpx-vp9", "-crf", "31", "-b:v", "0",
                    "-row-mt", "1", "-cpu-used", "4", "-c:a", "libopus", "-b:a", "160k"]
        else:
            cmd += ["-map", "0:v:0", "-map", "0:a", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                    "-c:a", "aac", "-b:a", "192k"]
        if ext in (".mp4", ".m4a", ".mov"):
            cmd += ["-movflags", "+faststart"]
        cmd += ["-map_metadata", "0", "-map_chapters", "-1", str(temp)]
        proc = self._spawn(cmd, src.parent)
        tail: list[str] = []
        try:
            for line in proc.lines():
                tail = (tail + [line])[-6:]
                if "time=" in line and end:
                    self._on_ffmpeg_line(line, max(0.5, end - start))
            code = proc.wait()
        finally:
            self._release(proc)
        self._check()
        if code != 0 or not temp.is_file():
            temp.unlink(missing_ok=True)
            details = "\n".join(tail)
            raise OperationError(explain("Postprocessing: Conversion failed " + details), details)
        os.replace(temp, src)
        return src

    # -- véglegesítés ---------------------------------------------------------- #
    def _finalize(self, work: Path, dest: Path, media: list[Path], subs: list[Path]) -> list[Path]:
        """A kész fájlokat ütközésmentes névvel a célmappába mozgatja.

        Ha már létezik azonos nevű fájl, „(2)”, „(3)” … utótag kerül a névbe, a
        videó és a hozzá tartozó feliratfájlok egységesen, így a lejátszók
        továbbra is automatikusan felismerik a feliratokat.
        """
        groups: list[tuple[str, list[Path]]] = []
        used: set[Path] = set()
        for path in media:
            base = path.name[: -len(path.suffix)] if path.suffix else path.name
            members = [path] + [s for s in subs if s.name.startswith(base + ".") and s not in used]
            used.update(members)
            groups.append((base, members))
        langs = [s.language for s in self.opts.subtitles] + list(self.opts.sub_langs)
        for sub in subs:
            if sub in used or not sub.exists():
                continue
            lang = self._lang_of(sub, langs, "")
            stem = sub.name[: -len(sub.suffix)]
            base = stem[: -(len(lang) + 1)] if lang and stem.endswith("." + lang) else stem
            if base.endswith(".auto"):
                base = base[:-5]
            existing = next((g for g in groups if g[0] == base), None)
            if existing:
                existing[1].append(sub)
            else:
                groups.append((base, [sub]))
            used.add(sub)
        final: list[Path] = []
        for base, members in groups:
            members = [m for m in members if m.exists()]
            n = 1
            while True:
                new_base = base if n == 1 else f"{base} ({n})"
                targets = [dest / (new_base + m.name[len(base):]) for m in members]
                if not any(t.exists() for t in targets):
                    break
                n += 1
            for member, target in zip(members, targets):
                shutil.move(str(member), str(target))
                final.append(target)
            if n > 1:
                self.on_log(f"Azonos nevű fájl már létezett, az új fájl neve: {new_base}")
        return final
