"""Metadata normalization and safe yt-dlp argument construction.

No shell command strings are constructed. All user input is passed as process
arguments to a verified local executable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse
import re


LANG_NAMES = {
    "hu": "Magyar", "en": "Angol", "de": "Német", "fr": "Francia",
    "es": "Spanyol", "it": "Olasz", "pt": "Portugál", "ja": "Japán",
    "ko": "Koreai", "ru": "Orosz", "zh": "Kínai", "und": "Ismeretlen",
}


def language_name(code: str) -> str:
    key = (code or "und").lower().split("-")[0]
    return LANG_NAMES.get(key, code or "Ismeretlen")


def validate_url(url: str) -> str:
    url = url.strip()
    value = urlparse(url)
    if value.scheme not in {"https", "http"} or not value.netloc:
        raise ValueError("Adj meg egy érvényes http(s) videó-URL-t.")
    if value.username or value.password:
        raise ValueError("Felhasználónevet vagy jelszót tartalmazó URL nem támogatott.")
    if any(c in url for c in "\n\r\0"):
        raise ValueError("Érvénytelen karakter az URL-ben.")
    return url


def parse_time(value: str) -> float | None:
    """Accept HH:MM:SS, MM:SS or plain seconds. Empty is unspecified."""
    value = value.strip()
    if not value:
        return None
    parts = value.split(":")
    if not (1 <= len(parts) <= 3):
        raise ValueError("Az idő formátuma: ÓÓ:PP:MM vagy PP:MM.")
    try:
        nums = [float(p) for p in parts]
    except ValueError as exc:
        raise ValueError("Az időpont csak számokat tartalmazhat.") from exc
    if any(not (0 <= n < 1e8) for n in nums):
        raise ValueError("Az időpont nem lehet negatív vagy érvénytelen.")
    if len(nums) > 1 and any(n >= 60 for n in nums[1:]):
        raise ValueError("A perc és másodperc értéke 60-nál kisebb legyen.")
    return sum(n * 60 ** i for i, n in enumerate(reversed(nums)))


def fmt_time(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 3600:02d}:{whole // 60 % 60:02d}:{whole % 60:02d}"


@dataclass(frozen=True)
class AudioTrack:
    format_id: str
    language: str
    codec: str
    abr: float
    note: str
    ext: str
    original: bool = False

    @property
    def label(self) -> str:
        desc = f"{language_name(self.language)} ({self.language}) | {self.codec}"
        if self.abr:
            desc += f" | {self.abr:g} kb/s"
        if self.note:
            desc += f" | {self.note}"
        return desc


@dataclass(frozen=True)
class Subtitle:
    language: str
    kind: str  # 'manual' or 'automatic' (incl. auto translated)
    name: str

    @property
    def label(self) -> str:
        extra = "kézi" if self.kind == "manual" else "automatikus / fordított"
        return f"{language_name(self.language)} ({self.language}) — {extra}" + (f" — {self.name}" if self.name else "")


@dataclass
class VideoInfo:
    url: str
    title: str
    duration: float | None
    uploader: str
    thumbnail: str
    video_id: str
    original_language: str
    audio_tracks: list[AudioTrack] = field(default_factory=list)
    subtitles: list[Subtitle] = field(default_factory=list)
    resolutions: list[int] = field(default_factory=list)

    @classmethod
    def from_json(cls, raw: dict, url: str) -> "VideoInfo":
        original_language = str(raw.get("original_language") or "").lower()
        audio: list[AudioTrack] = []
        resolutions: set[int] = set()
        for f in raw.get("formats") or []:
            if not isinstance(f, dict):
                continue
            fid = str(f.get("format_id") or "")
            if not fid:
                continue
            if f.get("vcodec") not in (None, "none"):
                h = f.get("height")
                if isinstance(h, (int, float)) and h > 0:
                    resolutions.add(int(h))
            if f.get("acodec") in (None, "none") or f.get("vcodec") not in (None, "none"):
                # Only audio-only formats can reliably be combined with an
                # independently selected video stream.
                continue
            lang = str(f.get("language") or "und")
            abr = f.get("abr") or f.get("tbr") or 0
            try:
                abr = float(abr)
            except (ValueError, TypeError):
                abr = 0
            note = str(f.get("format_note") or "")
            audio.append(AudioTrack(fid, lang, str(f.get("acodec")), abr,
                                    note, str(f.get("ext") or ""),
                                    original=bool(original_language and lang.lower().startswith(original_language))))
        # Show one sensible audio choice per language. Prefer audio-only to
        # muxed formats and higher bitrate for the same language.
        best: dict[str, AudioTrack] = {}
        for a in audio:
            lang = a.language.lower()
            current = best.get(lang)
            if current is None or a.abr > current.abr:
                best[lang] = a
        subs = []
        for key, kind in (("subtitles", "manual"), ("automatic_captions", "automatic")):
            for code, options in (raw.get(key) or {}).items():
                if not options:
                    continue
                name = str(next((v.get("name") for v in options if isinstance(v, dict) and v.get("name")), ""))
                subs.append(Subtitle(str(code), kind, name))
        try:
            duration = float(raw["duration"]) if raw.get("duration") is not None else None
        except (ValueError, TypeError):
            duration = None
        return cls(url, str(raw.get("title") or "Ismeretlen cím"), duration,
                   str(raw.get("uploader") or raw.get("channel") or ""),
                   str(raw.get("thumbnail") or ""), str(raw.get("id") or ""),
                   original_language, sorted(best.values(), key=lambda a: (not a.original, a.language)),
                   sorted(subs, key=lambda s: (s.language != "hu", s.language != "en", s.language, s.kind)),
                   sorted(resolutions, reverse=True))


@dataclass
class DownloadOptions:
    url: str
    dest: str
    mode: str = "video"  # video | audio | subtitles
    container: str = "mp4"
    quality: str = "Legjobb"
    audio_format: str = "mp3"
    audio_track_ids: list[str] = field(default_factory=list)
    subtitles: list[Subtitle] = field(default_factory=list)
    embed_subtitles: bool = False
    subtitle_format: str = "srt"
    start: float | None = None
    end: float | None = None
    accurate_cut: bool = False
    playlist: bool = False

    def validate(self) -> None:
        validate_url(self.url)
        if self.mode not in {"video", "audio", "subtitles"}:
            raise ValueError("Ismeretlen letöltési mód.")
        if self.container not in {"mp4", "mkv", "webm"}:
            raise ValueError("Nem támogatott videókonténer.")
        if self.audio_format not in {"mp3", "m4a", "aac", "opus", "flac", "wav"}:
            raise ValueError("Nem támogatott hangformátum.")
        if self.subtitle_format not in {"srt", "vtt"}:
            raise ValueError("Nem támogatott feliratformátum.")
        if self.start is not None and self.start < 0:
            raise ValueError("A kezdőpont nem lehet negatív.")
        if self.end is not None and self.end <= 0:
            raise ValueError("A végpontnak pozitívnak kell lennie.")
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise ValueError("A végpont később legyen a kezdőpontnál.")
        if len(self.audio_track_ids) > 1 and self.container != "mkv" and self.mode == "video":
            raise ValueError("Több hangsáv egy fájlba csak MKV formátumban támogatott.")
        if self.mode == "subtitles" and not self.subtitles:
            raise ValueError("Válassz legalább egy feliratot.")
        Path(self.dest).mkdir(parents=True, exist_ok=True)


def _base_args(ffmpeg_path: Path | None) -> list[str]:
    args = ["--ignore-config", "--no-warnings", "--newline", "--no-overwrites",
            "--windows-filenames", "--trim-filenames", "160", "--retries", "3",
            "--fragment-retries", "3", "--socket-timeout", "20"]
    if ffmpeg_path:
        args.extend(["--ffmpeg-location", str(ffmpeg_path)])
    return args


def metadata_args(url: str, ffmpeg_path: Path | None = None, playlist: bool = False) -> list[str]:
    args = _base_args(ffmpeg_path) + ["--dump-single-json", "--skip-download"]
    if not playlist:
        args.append("--no-playlist")
    return args + [validate_url(url)]


def media_args(opts: DownloadOptions, ffmpeg_path: Path | None = None) -> list[str]:
    opts.validate()
    args = _base_args(ffmpeg_path) + ["-P", str(Path(opts.dest)),
                                    "-o", "%(title).150B [%(id)s].%(ext)s",
                                    "--print", "after_move:__YTDLPSTUDIO_OUTPUT__%(filepath)s"]
    if not opts.playlist:
        args.append("--no-playlist")
    if opts.start is not None or opts.end is not None:
        args += ["--download-sections", f"*{fmt_time(opts.start or 0)}-{fmt_time(opts.end) if opts.end is not None else 'inf'}"]
        if opts.accurate_cut:
            args.append("--force-keyframes-at-cuts")
    if opts.mode == "subtitles":
        raise ValueError("A feliratok letöltése külön folyamatban történik.")
    if opts.mode == "audio":
        if opts.audio_track_ids:
            args += ["-f", opts.audio_track_ids[0]]
        else:
            args += ["-f", "bestaudio/best"]
        args += ["--extract-audio", "--audio-format", opts.audio_format, "--audio-quality", "0"]
    else:
        max_height = None
        match = re.search(r"(\d{3,4})", opts.quality)
        if match:
            max_height = int(match.group(1))
        constraint = f"[height<={max_height}]" if max_height else ""
        if opts.audio_track_ids:
            audio_ids = "+".join(opts.audio_track_ids)
            # The video stream must be video-only to avoid accidental extra audio.
            selector = f"bv{constraint}+{audio_ids}"
        else:
            selector = f"bv{constraint}+ba/b{constraint}/best"
        args += ["-f", selector, "--merge-output-format", opts.container,
                 "--remux-video", opts.container]
        if len(opts.audio_track_ids) > 1:
            args.append("--audio-multistreams")
    return args + [validate_url(opts.url)]


def subtitles_args(opts: DownloadOptions, ffmpeg_path: Path | None = None,
                   subtitles: list[Subtitle] | None = None) -> list[str]:
    opts.validate()
    selections = subtitles if subtitles is not None else opts.subtitles
    if not selections:
        return []
    args = _base_args(ffmpeg_path) + ["--no-playlist", "-P", str(Path(opts.dest)),
                                    "-o", "%(title).150B [%(id)s].%(ext)s", "--skip-download"]
    if any(s.kind == "manual" for s in selections):
        args.append("--write-subs")
    if any(s.kind == "automatic" for s in selections):
        args.append("--write-auto-subs")
    # Individual language codes come from yt-dlp JSON, never user regex.
    langs = [s.language for s in selections]
    if any(not re.fullmatch(r"[a-zA-Z0-9_-]{1,32}", lang) for lang in langs):
        raise ValueError("A felirat nyelvkódja nem támogatott.")
    args += ["--sub-langs", ",".join(sorted(set(langs))), "--sub-format", "vtt/srt/best" if opts.subtitle_format == "vtt" else "srt/vtt/best"]
    if opts.subtitle_format == "srt":
        args += ["--convert-subs", "srt"]
    return args + [validate_url(opts.url)]
