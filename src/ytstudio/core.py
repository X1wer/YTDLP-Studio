"""yt-dlp metaadatok értelmezése és biztonságos parancsargumentumok előállítása.

Parancssor-sztring sehol sem készül: minden érték külön folyamatargumentum,
a felhasználói bevitel pedig ellenőrzött (URL, időpontok, nyelvkódok).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import re

from .langs import base_code, is_valid_code, language_name, matches_preference

# --------------------------------------------------------------------------- #
# Általános segédfüggvények
# --------------------------------------------------------------------------- #

_WIN_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                 *(f"LPT{i}" for i in range(1, 10))}


def validate_url(url: str) -> str:
    url = (url or "").strip()
    if any(c in url for c in "\n\r\t\0 "):
        raise ValueError("Az URL nem tartalmazhat szóközt vagy vezérlőkaraktert.")
    value = urlparse(url)
    if value.scheme not in {"https", "http"} or not value.netloc:
        raise ValueError("Adj meg egy érvényes, http:// vagy https:// kezdetű linket.")
    if value.username or value.password:
        raise ValueError("Felhasználónevet vagy jelszót tartalmazó link nem támogatott.")
    if len(url) > 4096:
        raise ValueError("A link túl hosszú.")
    return url


def normalize_url(text: str) -> str:
    """Beillesztett szövegből kiemeli az első linket (pl. ha szöveg is van mellette)."""
    text = (text or "").strip()
    match = re.search(r"https?://[^\s<>\"']+", text)
    if match:
        return match.group(0).rstrip(").,;]")
    if re.fullmatch(r"(www\.)?(youtube\.com|youtu\.be)/\S+", text):
        return "https://" + text
    return text


def youtube_playlist_context(url: str) -> tuple[bool, bool]:
    """(videó-ID van benne, lista-ID van benne) YouTube-linkeknél."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not (host.endswith("youtube.com") or host == "youtu.be"):
        return False, False
    query = parse_qs(parsed.query)
    has_video = "v" in query or host == "youtu.be" or "/shorts/" in parsed.path or "/live/" in parsed.path
    return has_video, "list" in query


def parse_time(value: str) -> float | None:
    """ÓÓ:PP:MM(.mmm), PP:MM vagy másodperc. Üres érték = nincs megadva."""
    value = (value or "").strip().replace(",", ".")
    if not value:
        return None
    parts = value.split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError("Az idő formátuma: ÓÓ:PP:MM vagy PP:MM.")
    try:
        nums = [float(p) for p in parts]
    except ValueError as exc:
        raise ValueError("Az időpont csak számokat és kettőspontot tartalmazhat.") from exc
    if any(n < 0 or n != n or n > 1e7 for n in nums):
        raise ValueError("Az időpont nem lehet negatív vagy érvénytelen.")
    if len(nums) > 1 and any(n >= 60 for n in nums[1:]):
        raise ValueError("A perc és a másodperc értéke 60-nál kisebb legyen.")
    return sum(n * 60 ** i for i, n in enumerate(reversed(nums)))


def fmt_time(seconds: float | None, millis: bool = False) -> str:
    if seconds is None:
        return ""
    seconds = max(0.0, float(seconds))
    whole = int(seconds)
    text = f"{whole // 3600:02d}:{whole // 60 % 60:02d}:{whole % 60:02d}"
    frac = round((seconds - whole) * 1000)
    if millis or frac:
        if frac >= 1000:
            return fmt_time(whole + 1, millis)
        if frac:
            text += f".{frac:03d}".rstrip("0")
    return text


def fmt_duration(seconds: float | None) -> str:
    if not seconds:
        return "ismeretlen hossz"
    whole = int(round(seconds))
    h, rem = divmod(whole, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_size(num: float | None) -> str:
    if not num or num <= 0:
        return "–"
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit in ("B", "KB") else f"{num:.1f} {unit}".replace(".", ",")
        num /= 1024
    return "–"


def safe_component(name: str, limit: int = 120) -> str:
    """Windows-kompatibilis mappanév (pl. lejátszási lista almappájához)."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name or "").strip().rstrip(". ")
    name = re.sub(r"\s+", " ", name)[:limit].rstrip(". ")
    if not name or name.upper().split(".")[0] in _WIN_RESERVED:
        name = (name + "_") if name else "Lejátszási lista"
    return name


def _template_literal(text: str) -> str:
    return text.replace("%", "%%")


# --------------------------------------------------------------------------- #
# Metaadat-modellek
# --------------------------------------------------------------------------- #

AUDIO_KIND_LABELS = {
    "original": "eredeti hangsáv",
    "dubbed": "szinkron hangsáv",
    "dubbed-auto": "AI-szinkron (a YouTube jelölése szerint)",
    "descriptive": "narrált hangsáv (látássérülteknek)",
    "default": "alapértelmezett hang",
}

SUB_KIND_LABELS = {
    "manual": "eredeti felirat",
    "auto": "automatikus felirat",
    "translated": "automatikus fordítás",
}


@dataclass(frozen=True)
class AudioTrack:
    key: str
    language: str
    kind: str
    selector: str
    note: str = ""
    abr: float = 0.0
    codecs: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        return language_name(self.language, "Alapértelmezett hang") if self.language else "Alapértelmezett hang"

    @property
    def label(self) -> str:
        kind = AUDIO_KIND_LABELS.get(self.kind, "")
        if self.kind == "default" or not kind:
            return self.name
        return f"{self.name} – {kind}"

    @property
    def detail(self) -> str:
        parts = [c for c in self.codecs]
        if self.abr:
            parts.append(f"max. {self.abr:.0f} kb/s")
        return " · ".join(parts)


@dataclass(frozen=True)
class Subtitle:
    language: str
    kind: str            # manual | auto | translated
    name: str = ""
    source: str = ""     # fordításnál a forrásnyelv

    @property
    def group(self) -> str:
        """A yt-dlp csoport: kézi (subtitles) vagy automatikus (automatic_captions)."""
        return "manual" if self.kind == "manual" else "auto"

    @property
    def key(self) -> str:
        return f"{self.group}:{self.language}"

    @property
    def label(self) -> str:
        lang = self.language
        if lang.endswith("-orig"):
            lang = lang[:-5]
        name = language_name(lang, self.name or self.language)
        kind = SUB_KIND_LABELS.get(self.kind, self.kind)
        if self.kind == "auto" and self.language.endswith("-orig"):
            kind = "automatikus felirat (eredeti beszéd)"
        if self.kind == "translated" and self.source:
            kind += f" ({language_name(self.source).lower()} forrásból)"
        return f"{name} – {kind}"


@dataclass(frozen=True)
class Chapter:
    start: float
    end: float
    title: str


@dataclass
class VideoInfo:
    url: str
    title: str
    duration: float | None
    uploader: str
    thumbnail: str
    video_id: str
    extractor: str = ""
    webpage_url: str = ""
    upload_date: str = ""
    view_count: int | None = None
    is_live: bool = False
    has_drm: bool = False
    audio_tracks: list[AudioTrack] = field(default_factory=list)
    subtitles: list[Subtitle] = field(default_factory=list)
    heights: list[int] = field(default_factory=list)
    fps_by_height: dict[int, float] = field(default_factory=dict)
    chapters: list[Chapter] = field(default_factory=list)
    formats: list[dict] = field(default_factory=list)
    preview_url: str = ""
    playlist_hint: bool = False

    @property
    def is_youtube(self) -> bool:
        return self.extractor.lower().startswith("youtube")

    @property
    def multi_language_audio(self) -> bool:
        return len([t for t in self.audio_tracks if t.language]) > 1

    def quality_label(self, height: int) -> str:
        names = {4320: "8K", 2160: "4K", 1440: "QHD", 1080: "Full HD", 720: "HD"}
        text = f"{height}p"
        fps = self.fps_by_height.get(height, 0)
        if fps and fps > 31:
            text += f"{fps:.0f}"
        if height in names:
            text += f" ({names[height]})"
        return text

    @classmethod
    def from_json(cls, raw: dict, url: str) -> "VideoInfo":
        formats = [f for f in raw.get("formats") or [] if isinstance(f, dict) and f.get("format_id")]
        if not formats and raw.get("url"):
            formats = [raw]  # egyfájlos forrás (nem YouTube oldalak)
        compact: list[dict] = []
        heights: set[int] = set()
        fps_by_height: dict[int, float] = {}
        for f in formats:
            # A yt-dlp a hiányzó kodeket None-nal jelzi (ismeretlen), a "none" = nincs ilyen sáv.
            vcodec = str(f["vcodec"]) if f.get("vcodec") is not None else "unknown"
            acodec = str(f["acodec"]) if f.get("acodec") is not None else "unknown"
            if f.get("ext") == "mhtml" or "storyboard" in str(f.get("format_note") or ""):
                continue
            item = {
                "format_id": str(f.get("format_id")), "ext": str(f.get("ext") or ""),
                "vcodec": vcodec, "acodec": acodec,
                "height": _num(f.get("height")), "fps": _num(f.get("fps")),
                "tbr": _num(f.get("tbr")), "abr": _num(f.get("abr")),
                "filesize": _num(f.get("filesize")) or _num(f.get("filesize_approx")),
                "language": str(f.get("language") or ""),
                "language_preference": _num(f.get("language_preference")),
                "format_note": str(f.get("format_note") or ""),
                "protocol": str(f.get("protocol") or ""),
                "dynamic_range": str(f.get("dynamic_range") or ""),
            }
            compact.append(item)
            if vcodec != "none" and item["height"]:
                h = int(item["height"])
                heights.add(h)
                fps_by_height[h] = max(fps_by_height.get(h, 0), item["fps"] or 0)
        chapters = []
        for ch in raw.get("chapters") or []:
            try:
                chapters.append(Chapter(float(ch["start_time"]), float(ch["end_time"]),
                                        str(ch.get("title") or "")))
            except (KeyError, TypeError, ValueError):
                continue
        try:
            duration = float(raw["duration"]) if raw.get("duration") is not None else None
        except (TypeError, ValueError):
            duration = None
        preview = ""
        for f in sorted(formats, key=lambda x: _num(x.get("height")) or 0):
            if (f.get("vcodec") not in (None, "none") and f.get("acodec") not in (None, "none")
                    and str(f.get("protocol") or "").startswith("https") and f.get("url")
                    and str(f.get("ext")) in ("mp4", "webm") and (_num(f.get("height")) or 0) >= 240):
                preview = str(f["url"])
                if (_num(f.get("height")) or 0) >= 360:
                    break
        view_count = raw.get("view_count")
        return cls(
            url=url,
            title=str(raw.get("title") or raw.get("fulltitle") or "Ismeretlen cím"),
            duration=duration,
            uploader=str(raw.get("uploader") or raw.get("channel") or raw.get("creator") or ""),
            thumbnail=str(raw.get("thumbnail") or ""),
            video_id=str(raw.get("id") or ""),
            extractor=str(raw.get("extractor_key") or raw.get("extractor") or ""),
            webpage_url=str(raw.get("webpage_url") or url),
            upload_date=str(raw.get("upload_date") or ""),
            view_count=view_count if isinstance(view_count, int) else None,
            is_live=bool(raw.get("is_live")) or raw.get("live_status") in ("is_live", "is_upcoming"),
            has_drm=bool(raw.get("_has_drm")) or any(f.get("has_drm") for f in formats),
            audio_tracks=_audio_tracks(compact),
            subtitles=_subtitles(raw),
            heights=sorted(heights, reverse=True),
            fps_by_height=fps_by_height,
            chapters=chapters,
            formats=compact,
            preview_url=preview,
        )


def _num(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _audio_kind(note: str, preference: float | None, multi: bool) -> str:
    low = note.lower()
    if "descriptive" in low or "audio description" in low:
        return "descriptive"
    if "dubbed-auto" in low or "auto-dubbed" in low or "ai-dubbed" in low or "(ai)" in low:
        return "dubbed-auto"
    if "original" in low or (multi and preference is not None and preference >= 10):
        return "original"
    if "dubbed" in low:
        return "dubbed"
    return "dubbed" if multi else "default"


def _clean_note(note: str) -> str:
    words = [w.strip() for w in note.split(",")]
    noise = {"low", "medium", "high", "ultralow", "drc", "default", ""}
    return ", ".join(w for w in words if w.lower() not in noise)


def _audio_tracks(formats: list[dict]) -> list[AudioTrack]:
    """Hangsávok nyelv (és változat) szerint csoportosítva, választó-szűrővel."""
    audio = [f for f in formats if f["vcodec"] == "none" and f["acodec"] not in ("none", "unknown")]
    if not audio:
        return []
    languages = {f["language"] for f in audio if f["language"]}
    multi = len(languages) > 1
    groups: dict[tuple[str, str], list[dict]] = {}
    for f in audio:
        kind = _audio_kind(f["format_note"], f["language_preference"], multi)
        if not f["language"]:
            kind = "default"
        groups.setdefault((f["language"], kind), []).append(f)
    tracks = []
    for (language, kind), items in groups.items():
        if language and not is_valid_code(language):
            continue
        same_lang_kinds = {k for (lang, k) in groups if lang == language}
        if language:
            selector = f"ba[language={language}]"
            if len(same_lang_kinds) > 1:
                selector += ("[format_note*=descriptive]" if kind == "descriptive"
                             else "[format_note!*=descriptive]")
        else:
            selector = "ba"
        best = max(items, key=lambda f: (("drc" not in f["format_id"].lower()), f["abr"] or f["tbr"] or 0))
        codecs = sorted({_codec_name(f["acodec"]) for f in items})
        key = f"{language or 'default'}|{kind}"
        tracks.append(AudioTrack(key, language, kind, selector, _clean_note(best["format_note"]),
                                 float(best["abr"] or best["tbr"] or 0), tuple(codecs)))
    order = {"original": 0, "default": 1, "dubbed": 2, "dubbed-auto": 3, "descriptive": 4}
    return sorted(tracks, key=lambda t: (order.get(t.kind, 5), t.name))


def _codec_name(codec: str) -> str:
    codec = codec.lower()
    for prefix, name in (("mp4a", "AAC"), ("opus", "Opus"), ("vorbis", "Vorbis"), ("ec-3", "E-AC-3"),
                         ("ac-3", "AC-3"), ("mp3", "MP3"), ("flac", "FLAC"), ("avc", "H.264"),
                         ("vp09", "VP9"), ("vp9", "VP9"), ("av01", "AV1"), ("hev", "H.265"),
                         ("hvc", "H.265")):
        if codec.startswith(prefix):
            return name
    return codec.split(".")[0].upper()


def _subtitles(raw: dict) -> list[Subtitle]:
    result: list[Subtitle] = []
    manual_langs = set()
    for code, options in (raw.get("subtitles") or {}).items():
        if code == "live_chat" or not options or not is_valid_code(str(code)):
            continue
        name = next((str(o.get("name")) for o in options if isinstance(o, dict) and o.get("name")), "")
        result.append(Subtitle(str(code), "manual", name))
        manual_langs.add(str(code))
    for code, options in (raw.get("automatic_captions") or {}).items():
        code = str(code)
        if not options or not is_valid_code(code):
            continue
        name = next((str(o.get("name")) for o in options if isinstance(o, dict) and o.get("name")), "")
        kind, source = "", ""
        for option in options:
            if not isinstance(option, dict):
                continue
            query = parse_qs(urlparse(str(option.get("url") or "")).query)
            if "tlang" in query:
                kind, source = "translated", (query.get("lang") or [""])[0]
                break
            if (query.get("kind") or [""])[0] == "asr":
                kind = "auto"
        if not kind:
            if code in manual_langs:
                # Csak a kézi felirat HLS-tükre: nem önálló választható elem.
                continue
            kind = "auto"
        result.append(Subtitle(code, kind, name, source))
    return result


def sort_subtitles(subs: list[Subtitle], preferred: list[str]) -> list[Subtitle]:
    kind_order = {"manual": 0, "auto": 1, "translated": 2}
    return sorted(subs, key=lambda s: (
        not matches_preference(s.language, preferred),
        next((i for i, p in enumerate(preferred) if base_code(p) == base_code(s.language)), 99),
        kind_order.get(s.kind, 3), s.label))


@dataclass(frozen=True)
class PlaylistEntry:
    index: int
    video_id: str
    url: str
    title: str
    duration: float | None
    uploader: str = ""
    available: bool = True


@dataclass
class PlaylistInfo:
    url: str
    title: str
    uploader: str
    entries: list[PlaylistEntry]

    @classmethod
    def from_json(cls, raw: dict, url: str) -> "PlaylistInfo":
        entries = []
        for i, e in enumerate(raw.get("entries") or [], start=1):
            if not isinstance(e, dict):
                continue
            link = str(e.get("url") or e.get("webpage_url") or "")
            vid = str(e.get("id") or "")
            if not link.startswith("http") and vid and str(e.get("ie_key") or "").lower().startswith("youtube"):
                link = f"https://www.youtube.com/watch?v={vid}"
            title = str(e.get("title") or vid or f"{i}. elem")
            unavailable = (title in ("[Private video]", "[Deleted video]", "[Unavailable video]")
                           or e.get("availability") in ("private", "needs_auth", "subscriber_only"))
            try:
                link = validate_url(link)
            except ValueError:
                unavailable, link = True, ""
            entries.append(PlaylistEntry(int(e.get("playlist_index") or i), vid, link,
                                         title, _num(e.get("duration")),
                                         str(e.get("uploader") or e.get("channel") or ""),
                                         not unavailable))
        return cls(url, str(raw.get("title") or "Lejátszási lista"),
                   str(raw.get("uploader") or raw.get("channel") or ""), entries)


# --------------------------------------------------------------------------- #
# Letöltési beállítások
# --------------------------------------------------------------------------- #

@dataclass
class DownloadOptions:
    url: str
    dest: str
    mode: str = "video"                  # video | audio | subtitles
    container: str = "mp4"
    quality: str = "best"                # best | magasság pl. "1080"
    video_codec: str = "auto"
    audio_format: str = "mp3"
    audio_quality: str = "best"
    audio_selectors: list[str] = field(default_factory=list)
    audio_languages: list[str] = field(default_factory=list)
    preferred_audio_lang: str = ""
    subtitles: list[Subtitle] = field(default_factory=list)
    sub_langs: list[str] = field(default_factory=list)   # lejátszási listához: általános nyelvi preferencia
    subtitle_format: str = "srt"
    embed_subtitles: bool = False
    embed_metadata: bool = True
    embed_thumbnail: bool = True
    embed_chapters: bool = True
    start: float | None = None
    end: float | None = None
    accurate_cut: bool = False
    cut_method: str = "sections"         # sections | full
    filename_prefix: str = ""
    title: str = ""
    duration: float | None = None
    rate_limit: str = ""
    cookies_browser: str = ""

    @property
    def is_clip(self) -> bool:
        return self.start is not None or self.end is not None

    @property
    def wants_subtitles(self) -> bool:
        return bool(self.subtitles or self.sub_langs)

    @property
    def effective_container(self) -> str:
        if self.mode == "video" and len(self.audio_selectors) > 1:
            return "mkv"
        return self.container

    def validate(self, create_dest: bool = True) -> None:
        validate_url(self.url)
        if self.mode not in {"video", "audio", "subtitles"}:
            raise ValueError("Ismeretlen letöltési mód.")
        if self.container not in {"mp4", "mkv", "webm"}:
            raise ValueError("Nem támogatott videóformátum.")
        if self.video_codec not in {"auto", "h264", "vp9", "av1"}:
            raise ValueError("Nem támogatott videókodek.")
        if self.audio_format not in {"mp3", "m4a", "aac", "opus", "flac", "wav", "original"}:
            raise ValueError("Nem támogatott hangformátum.")
        if self.audio_quality not in {"best", "320", "256", "192", "128"}:
            raise ValueError("Nem támogatott hangminőség.")
        if self.subtitle_format not in {"srt", "vtt"}:
            raise ValueError("Nem támogatott feliratformátum.")
        if self.quality != "best" and not (self.quality.isdigit() and 100 <= int(self.quality) <= 8640):
            raise ValueError("Érvénytelen videóminőség.")
        if self.cut_method not in {"sections", "full"}:
            raise ValueError("Ismeretlen vágási módszer.")
        if self.start is not None and self.start < 0:
            raise ValueError("A kezdőpont nem lehet negatív.")
        if self.end is not None and self.end <= 0:
            raise ValueError("A végpontnak nullánál nagyobbnak kell lennie.")
        if self.start is not None and self.end is not None and self.end - self.start < 0.5:
            raise ValueError("A végpont legalább fél másodperccel legyen a kezdőpont után.")
        if self.duration and self.start is not None and self.start >= self.duration:
            raise ValueError("A kezdőpont a videó hosszán túl van.")
        if self.mode == "subtitles" and not self.wants_subtitles:
            raise ValueError("Csak felirat letöltéséhez jelölj ki legalább egy feliratot.")
        if len(self.audio_selectors) != len(self.audio_languages):
            raise ValueError("Belső hiba: a hangsávlista nem egyezik.")
        for selector in self.audio_selectors:
            if not re.fullmatch(r"ba(\[[a-z_]+(?:[!*^$~]?=|!\*=)[A-Za-z0-9_.-]+\])*", selector):
                raise ValueError("Érvénytelen hangsáv-azonosító.")
        for lang in [s.language for s in self.subtitles] + self.sub_langs + (
                [self.preferred_audio_lang] if self.preferred_audio_lang else []):
            if not is_valid_code(lang):
                raise ValueError("Érvénytelen nyelvkód.")
        if self.rate_limit and not re.fullmatch(r"\d+(\.\d+)?[KMG]?", self.rate_limit, re.I):
            raise ValueError("Érvénytelen sebességkorlát (példa: 5M vagy 800K).")
        if self.cookies_browser and not re.fullmatch(r"[a-z]{3,12}", self.cookies_browser):
            raise ValueError("Érvénytelen böngészőnév.")
        dest = Path(self.dest)
        if not str(self.dest).strip():
            raise ValueError("Adj meg mentési mappát.")
        if create_dest:
            try:
                dest.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise ValueError(f"A mentési mappa nem hozható létre: {exc}") from exc

    def with_changes(self, **kwargs) -> "DownloadOptions":
        return replace(self, **kwargs)


# --------------------------------------------------------------------------- #
# Argumentumok
# --------------------------------------------------------------------------- #

PROGRESS_TEMPLATE = ("download:__YTS_P__%(progress.status)s|%(progress.downloaded_bytes)s|"
                     "%(progress.total_bytes)s|%(progress.total_bytes_estimate)s|"
                     "%(progress.speed)s|%(progress.eta)s|%(info.format_id)s")
PP_TEMPLATE = "postprocess:__YTS_PP__%(progress.postprocessor)s|%(progress.status)s"
REQ_TEMPLATE = ("before_dl:__YTS_REQ__%(requested_formats.:.format_id)j|"
                "%(requested_formats.:.filesize)j|%(requested_formats.:.filesize_approx)j|"
                "%(filesize,filesize_approx)j")
OUT_TEMPLATE = "after_move:__YTS_OUT__%(filepath)s"


@dataclass
class Tools:
    ffmpeg_dir: Path | None = None
    deno: Path | None = None
    cache_dir: Path | None = None


def base_args(tools: Tools | None = None, cookies_browser: str = "", rate_limit: str = "") -> list[str]:
    tools = tools or Tools()
    args = ["--ignore-config", "--encoding", "utf-8", "--newline", "--no-mtime",
            "--windows-filenames", "--trim-filenames", "180", "--retries", "5",
            "--fragment-retries", "10", "--socket-timeout", "30"]
    if tools.ffmpeg_dir:
        args += ["--ffmpeg-location", str(tools.ffmpeg_dir)]
    if tools.deno:
        args += ["--js-runtimes", f"deno:{tools.deno}"]
    if tools.cache_dir:
        args += ["--cache-dir", str(tools.cache_dir)]
    if cookies_browser:
        args += ["--cookies-from-browser", cookies_browser]
    if rate_limit:
        args += ["--limit-rate", rate_limit]
    return args


def metadata_args(url: str, tools: Tools | None = None, *, allow_playlist: bool = True,
                  cookies_browser: str = "") -> list[str]:
    url = validate_url(url)
    args = base_args(tools, cookies_browser) + ["--dump-single-json", "--skip-download"]
    has_video, has_list = youtube_playlist_context(url)
    if allow_playlist and not (has_video and has_list):
        args += ["--flat-playlist", "--yes-playlist"]
    else:
        args.append("--no-playlist")
    return args + ["--", url]


def _clip_suffix(opts: DownloadOptions) -> str:
    if not opts.is_clip:
        return ""
    def stamp(value: float) -> str:
        return fmt_time(value).replace(".", ",").replace(":", ".")
    start = stamp(opts.start or 0)
    end = stamp(opts.end) if opts.end is not None else "vége"
    return f" ({start}–{end})"


def output_template(opts: DownloadOptions, per_language: bool = False) -> str:
    prefix = _template_literal(opts.filename_prefix)
    name = f"{prefix}%(title).120B [%(id)s]{_template_literal(_clip_suffix(opts))}"
    if per_language:
        name += ".%(language|hang)s"
    return name + ".%(ext)s"


def section_arg(opts: DownloadOptions) -> str:
    start = fmt_time(opts.start or 0, millis=True)
    end = fmt_time(opts.end, millis=True) if opts.end is not None else "inf"
    return f"*{start}-{end}"


def _height(opts: DownloadOptions) -> str:
    return f"[height<={int(opts.quality)}]" if opts.quality != "best" else ""


WEBM_VIDEO = "[vcodec~='^(vp0?9|vp8|av01)']"
WEBM_AUDIO = "[acodec~='^(opus|vorbis)']"


def video_format_selector(opts: DownloadOptions) -> str:
    h = _height(opts)
    webm = opts.effective_container == "webm"
    vf, af = (WEBM_VIDEO, WEBM_AUDIO) if webm else ("", "")
    if opts.audio_selectors:
        strict = "+".join(sel + af for sel in opts.audio_selectors)
        loose = "+".join(opts.audio_selectors)
        options = [f"bv{vf}{h}+{strict}", f"bv{h}+{loose}", f"bv+{loose}"]
    else:
        options = []
        if opts.preferred_audio_lang:
            options.append(f"bv{vf}{h}+ba{af}[language^={opts.preferred_audio_lang}]")
        options += [f"bv*{vf}{h}+ba{af}", f"bv*{h}+ba", f"b{h}", "bv*+ba", "b"]
    return "/".join(dict.fromkeys(options))


def video_sort(opts: DownloadOptions) -> list[str]:
    codec = opts.video_codec
    if codec == "h264":
        return ["-S", "lang,vcodec:h264,res,fps,acodec:aac"]
    if codec == "vp9":
        return ["-S", "lang,vcodec:vp9,res,fps"]
    if codec == "av1":
        return ["-S", "lang,vcodec:av01,res,fps"]
    if opts.effective_container == "mp4":
        # Azonos felbontásnál a legszélesebb körben lejátszható kodeket részesíti előnyben.
        return ["-S", "lang,res,fps,hdr:12,vcodec:h264,acodec:aac"]
    return []


def audio_format_selector(opts: DownloadOptions) -> str:
    if opts.audio_selectors:
        return ",".join(f"{sel}/{sel.replace('ba', 'b', 1)}" for sel in opts.audio_selectors)
    options = []
    if opts.preferred_audio_lang:
        options.append(f"ba[language^={opts.preferred_audio_lang}]")
    return "/".join(options + ["ba", "b"])


def audio_sort(opts: DownloadOptions) -> list[str]:
    if opts.audio_format in ("m4a", "aac"):
        return ["-S", "lang,acodec:aac"]
    if opts.audio_format == "opus":
        return ["-S", "lang,acodec:opus"]
    return []


def media_args(opts: DownloadOptions, workdir: Path, tools: Tools | None = None) -> list[str]:
    """A fő (videó vagy hang) letöltés argumentumai az ideiglenes munkamappába."""
    opts.validate(create_dest=False)
    if opts.mode == "subtitles":
        raise ValueError("Csak felirat módban nincs médialetöltés.")
    per_language = opts.mode == "audio" and len(opts.audio_selectors) > 1
    args = base_args(tools, opts.cookies_browser, opts.rate_limit) + [
        "--no-playlist", "--no-quiet", "--progress", "--progress-delta", "0.5",
        "--progress-template", PROGRESS_TEMPLATE, "--progress-template", PP_TEMPLATE,
        "--print", REQ_TEMPLATE, "--print", OUT_TEMPLATE,
        "-P", str(workdir), "-o", output_template(opts, per_language),
        "--no-write-subs", "--no-write-auto-subs",
    ]
    if opts.is_clip and opts.cut_method == "sections":
        args += ["--download-sections", section_arg(opts)]
        if opts.accurate_cut:
            args.append("--force-keyframes-at-cuts")
    if opts.embed_metadata:
        args.append("--embed-metadata")
    if not opts.embed_chapters or opts.is_clip:
        args.append("--no-embed-chapters")
    elif opts.embed_chapters and not opts.embed_metadata:
        args.append("--embed-chapters")
    if opts.mode == "audio":
        args += ["-f", audio_format_selector(opts)] + audio_sort(opts) + ["--extract-audio"]
        if opts.audio_format != "original":
            args += ["--audio-format", opts.audio_format]
        if opts.audio_format in ("mp3", "m4a", "aac", "opus"):
            args += ["--audio-quality", "0" if opts.audio_quality == "best" else f"{opts.audio_quality}K"]
        if opts.embed_thumbnail and opts.audio_format not in ("wav",):
            args += ["--embed-thumbnail", "--convert-thumbnails", "jpg"]
    else:
        container = opts.effective_container
        args += ["-f", video_format_selector(opts)] + video_sort(opts)
        if container == "webm":
            args += ["--merge-output-format", "webm/mkv", "--remux-video", "webm>webm/mkv"]
        else:
            args += ["--merge-output-format", container, "--remux-video", container]
        if len(opts.audio_selectors) > 1:
            args.append("--audio-multistreams")
        if opts.embed_thumbnail and container in ("mp4", "mkv"):
            args += ["--embed-thumbnail", "--convert-thumbnails", "jpg"]
    return args + ["--", validate_url(opts.url)]


def subtitle_args(opts: DownloadOptions, workdir: Path, tools: Tools | None = None, *,
                  langs: list[str], manual: bool, auto: bool, suffix: str = "") -> list[str]:
    """Feliratletöltés videó nélkül; a nyelvkódok a yt-dlp JSON-jából származnak."""
    opts.validate(create_dest=False)
    if not langs:
        raise ValueError("Nincs kijelölt felirat.")
    for lang in langs:
        if not is_valid_code(lang):
            raise ValueError("A felirat nyelvkódja nem támogatott.")
    name = output_template(opts).rsplit(".%(ext)s", 1)[0]
    if suffix:
        name += "." + suffix
    args = base_args(tools, opts.cookies_browser) + [
        "--no-playlist", "--skip-download", "--no-quiet", "-P", str(workdir),
        "-o", f"subtitle:{name}.%(ext)s", "-o", output_template(opts),
        "--sub-langs", ",".join(dict.fromkeys(re.escape(l) for l in langs)),
    ]
    args.append("--write-subs" if manual else "--no-write-subs")
    args.append("--write-auto-subs" if auto else "--no-write-auto-subs")
    if opts.subtitle_format == "srt":
        args += ["--sub-format", "srt/vtt/best", "--convert-subs", "srt"]
    else:
        args += ["--sub-format", "vtt/srt/best", "--convert-subs", "vtt"]
    return args + ["--", validate_url(opts.url)]


def subtitle_plan(opts: DownloadOptions) -> list[dict]:
    """A feliratletöltések csoportosítása yt-dlp-hívásokra.

    A yt-dlp azonos nyelvkódnál a kézi feliratot választja. Ha a felhasználó
    olyan automatikus feliratot kér, amelynek nyelvén kézi felirat is van, azt
    külön hívás tölti le ``.auto`` utótaggal, hogy a fájlnevek ne ütközzenek.
    """
    if opts.sub_langs:
        return [{"langs": list(opts.sub_langs), "manual": True, "auto": True, "suffix": ""}]
    manual = [s.language for s in opts.subtitles if s.group == "manual"]
    auto = [s.language for s in opts.subtitles if s.group == "auto"]
    plan = []
    clean_auto = [l for l in auto if l not in manual]
    conflict_auto = [l for l in auto if l in manual]
    if manual or clean_auto:
        plan.append({"langs": manual + clean_auto, "manual": bool(manual), "auto": bool(clean_auto),
                     "suffix": ""})
    if conflict_auto:
        plan.append({"langs": conflict_auto, "manual": False, "auto": True, "suffix": "auto"})
    return plan


# --------------------------------------------------------------------------- #
# Méretbecslés
# --------------------------------------------------------------------------- #

def _size_of(f: dict, duration: float | None) -> float | None:
    if f.get("filesize"):
        return f["filesize"]
    rate = f.get("tbr") or f.get("abr")
    if rate and duration:
        return rate * 1000 / 8 * duration
    return None


def _codec_rank(vcodec: str, preference: str, container: str) -> int:
    vcodec = vcodec.lower()
    family = ("h264" if vcodec.startswith("avc") else "av1" if vcodec.startswith("av01")
              else "vp9" if vcodec.startswith(("vp9", "vp09")) else "other")
    if preference == "auto":
        preference = "h264" if container == "mp4" else ""
    order = {"av1": 3, "vp9": 2, "h264": 1, "other": 0}
    if preference and family == preference:
        return 10
    return order[family]


def estimate_size(info: VideoInfo, opts: DownloadOptions) -> float | None:
    """Hozzávetőleges kimeneti méret bájtban (a yt-dlp választását közelíti)."""
    duration = info.duration
    if not info.formats or not duration:
        return None
    span = duration
    if opts.is_clip:
        span = max(0.0, (opts.end if opts.end is not None else duration) - (opts.start or 0))
    fraction = span / duration if duration else 1

    def best_audio(selector: str | None) -> dict | None:
        candidates = [f for f in info.formats if f["vcodec"] == "none" and f["acodec"] not in ("none", "unknown")]
        if selector:
            lang = re.search(r"\[language=([^\]]+)\]", selector)
            if lang:
                candidates = [f for f in candidates if f["language"] == lang.group(1)]
        elif any(f["language_preference"] and f["language_preference"] >= 10 for f in candidates):
            candidates = [f for f in candidates if (f["language_preference"] or 0) >= 10]
        candidates = [f for f in candidates if "drc" not in f["format_id"].lower()] or candidates
        if opts.mode == "video" and opts.effective_container == "mp4":
            candidates = [f for f in candidates if f["acodec"].startswith("mp4a")] or candidates
        if opts.mode == "video" and opts.effective_container == "webm":
            candidates = [f for f in candidates if f["acodec"].startswith(("opus", "vorbis"))] or candidates
        return max(candidates, key=lambda f: (f["abr"] or f["tbr"] or 0), default=None)

    total = 0.0
    if opts.mode == "subtitles":
        return None
    selectors = opts.audio_selectors or [None]
    if opts.mode == "audio":
        for sel in selectors:
            audio = best_audio(sel)
            if opts.audio_format == "wav":
                total += 1411 * 1000 / 8 * span
            elif opts.audio_format == "flac":
                total += 800 * 1000 / 8 * span
            elif opts.audio_format == "original" or (opts.audio_format in ("m4a", "aac") and audio
                                                     and audio["acodec"].startswith("mp4a")):
                total += (_size_of(audio, duration) or 0) * fraction if audio else 0
            else:
                kbps = 245 if opts.audio_quality == "best" else int(opts.audio_quality)
                if opts.audio_format == "opus" and opts.audio_quality == "best":
                    kbps = 160
                total += kbps * 1000 / 8 * span
        return total or None
    cap = int(opts.quality) if opts.quality != "best" else 100000
    videos = [f for f in info.formats if f["vcodec"] not in ("none", "unknown") and f["height"]]
    if opts.effective_container == "webm":
        videos = [f for f in videos if f["vcodec"].lower().startswith(("vp9", "vp09", "vp8", "av01"))] or videos
    if opts.video_codec == "h264":
        videos = [f for f in videos if f["vcodec"].lower().startswith("avc")] or videos
    allowed = [f for f in videos if f["height"] <= cap] or videos
    if not allowed:
        return None
    video = max(allowed, key=lambda f: (f["height"], f["fps"] or 0,
                                        _codec_rank(f["vcodec"], opts.video_codec, opts.effective_container),
                                        f["tbr"] or 0))
    total += (_size_of(video, duration) or 0)
    if video["acodec"] in ("none",):
        for sel in selectors:
            audio = best_audio(sel)
            if audio:
                total += _size_of(audio, duration) or 0
    return total * fraction if total else None
