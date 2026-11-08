"""Portable mappák, eszközkeresés és felhasználói beállítások.

Minden adat az alkalmazás saját mappájában marad (``data/``), így a program
USB-meghajtóról is használható, és nem ír a rendszerleíró adatbázisba.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
import json
import os
import shutil
import sys
import tempfile

MODES = ("video", "audio", "subtitles")
CONTAINERS = ("mp4", "mkv", "webm")
VIDEO_CODECS = ("auto", "h264", "vp9", "av1")
AUDIO_FORMATS = ("mp3", "m4a", "aac", "opus", "flac", "wav", "original")
AUDIO_QUALITIES = ("best", "320", "256", "192", "128")
SUBTITLE_FORMATS = ("srt", "vtt")
THEMES = ("system", "light", "dark")
CUT_METHODS = ("sections", "full")
COOKIE_BROWSERS = ("", "firefox", "chrome", "edge", "brave", "opera", "vivaldi", "chromium")
YTDLP_CHANNELS = ("stable", "nightly")


def app_dir() -> Path:
    """A portable csomag gyökere (EXE mellett) vagy forrásból a projekt gyökere."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def bin_dir() -> Path:
    return app_dir() / "bin"


def _writable(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".write-test-", delete=True):
            pass
        return True
    except OSError:
        return False


_DATA_DIR: Path | None = None


def data_dir() -> Path:
    """Beállítások, napló és gyorsítótár helye.

    Elsődlegesen ``<alkalmazás>/data``. Ha az alkalmazás írásvédett helyen fut
    (pl. Program Files vagy írásvédett pendrive), a felhasználói
    ``%LOCALAPPDATA%\\YTDLPStudio`` mappa a tartalék, hogy a program működjön.
    """
    global _DATA_DIR
    if _DATA_DIR is not None:
        return _DATA_DIR
    override = os.environ.get("YTDLPSTUDIO_DATA_DIR")
    primary = Path(override) if override else app_dir() / "data"
    if _writable(primary):
        _DATA_DIR = primary
    else:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
        _DATA_DIR = Path(base) / "YTDLPStudio"
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _DATA_DIR


def find_exe(name: str) -> Path | None:
    """A csomagolt eszközt keresi; forrásból futtatva a PATH a tartalék."""
    binary = name + (".exe" if os.name == "nt" else "")
    for candidate in (bin_dir() / binary, app_dir() / binary):
        if candidate.is_file():
            return candidate
    found = shutil.which(binary) or shutil.which(name)
    return Path(found) if found else None


def ffmpeg_location() -> Path | None:
    ffmpeg = find_exe("ffmpeg")
    return ffmpeg.parent if ffmpeg else None


def command_env() -> dict[str, str]:
    """Környezet a gyerekfolyamatokhoz: a csomagolt eszközök előre kerülnek."""
    env = os.environ.copy()
    env["PATH"] = str(bin_dir()) + os.pathsep + env.get("PATH", "")
    env["DENO_DIR"] = str(data_dir() / "cache" / "deno")
    env["DENO_NO_UPDATE_CHECK"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def default_download_dir() -> str:
    downloads = Path.home() / "Downloads"
    return str(downloads if downloads.is_dir() else Path.home())


@dataclass
class Settings:
    destination: str = field(default_factory=default_download_dir)
    theme: str = "system"
    mode: str = "video"
    container: str = "mp4"
    quality: str = "best"           # "best" vagy pl. "1080"
    video_codec: str = "auto"
    audio_format: str = "mp3"
    audio_quality: str = "best"
    subtitle_format: str = "srt"
    embed_subtitles: bool = False
    embed_metadata: bool = True
    embed_thumbnail: bool = True
    embed_chapters: bool = True
    accurate_cut: bool = False
    cut_method: str = "sections"
    preferred_sub_langs: list[str] = field(default_factory=lambda: ["hu", "en"])
    preferred_audio_lang: str = ""
    remember_languages: bool = True
    max_parallel: int = 1
    rate_limit: str = ""            # pl. "5M"; üres = korlátlan
    cookies_browser: str = ""
    ytdlp_channel: str = "stable"
    auto_analyze_paste: bool = True
    open_folder_when_done: bool = False
    window_geometry: str = ""
    splitter_state: str = ""

    _ENUMS = {
        "theme": THEMES, "mode": MODES, "container": CONTAINERS, "video_codec": VIDEO_CODECS,
        "audio_format": AUDIO_FORMATS, "audio_quality": AUDIO_QUALITIES,
        "subtitle_format": SUBTITLE_FORMATS, "cut_method": CUT_METHODS,
        "cookies_browser": COOKIE_BROWSERS, "ytdlp_channel": YTDLP_CHANNELS,
    }

    @staticmethod
    def path() -> Path:
        return data_dir() / "settings.json"

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        result = cls()
        if not isinstance(data, dict):
            return result
        for f in fields(cls):
            if f.name.startswith("_") or f.name not in data:
                continue
            value = data[f.name]
            current = getattr(result, f.name)
            if isinstance(current, bool):
                if isinstance(value, bool):
                    setattr(result, f.name, value)
            elif isinstance(current, int):
                if isinstance(value, int) and not isinstance(value, bool):
                    setattr(result, f.name, value)
            elif isinstance(current, list):
                if isinstance(value, list) and all(isinstance(v, str) for v in value):
                    setattr(result, f.name, [v for v in value if v][:20])
            elif isinstance(value, str):
                allowed = cls._ENUMS.get(f.name)
                if allowed is None or value in allowed:
                    setattr(result, f.name, value)
        result.max_parallel = min(3, max(1, result.max_parallel))
        if result.quality != "best" and not result.quality.isdigit():
            result.quality = "best"
        return result

    @classmethod
    def load(cls) -> "Settings":
        try:
            return cls.from_dict(json.loads(cls.path().read_text(encoding="utf-8")))
        except FileNotFoundError:
            return cls._migrate_v01()
        except (ValueError, OSError):
            return cls()

    @classmethod
    def _migrate_v01(cls) -> "Settings":
        """A v0.1.x a beállításokat közvetlenül az EXE mellé írta."""
        old = app_dir() / "settings.json"
        try:
            data = json.loads(old.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        mapped = {"destination": data.get("destination"), "container": data.get("container"),
                  "audio_format": data.get("audio_format"),
                  "subtitle_format": data.get("subtitles_format"), "theme": data.get("theme")}
        quality = str(data.get("quality") or "")
        if quality.endswith("p") and quality[:-1].isdigit():
            mapped["quality"] = quality[:-1]
        return cls.from_dict({k: v for k, v in mapped.items() if v is not None})

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if not k.startswith("_")}

    def save(self) -> bool:
        out = self.path()
        tmp = out.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, out)
            return True
        except OSError:
            # Írásvédett hordozó: a munkamenet így is használható marad.
            return False
