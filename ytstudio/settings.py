"""Portable user preferences and tool discovery."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import os
import shutil
import sys


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    destination: str = str(Path.home() / "Downloads")
    quality: str = "Legjobb"
    container: str = "mp4"
    audio_format: str = "mp3"
    theme: str = "dark"
    subtitles_format: str = "srt"

    @classmethod
    def load(cls) -> "Settings":
        f = app_dir() / "settings.json"
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            return cls(**{key: data[key] for key in cls.__dataclass_fields__ if key in data})
        except (ValueError, OSError, TypeError):
            return cls()

    def save(self) -> None:
        out = app_dir() / "settings.json"
        tmp = out.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, out)
        except OSError:
            # USB locations may be read-only. App remains usable this session.
            pass


def find_exe(name: str) -> Path | None:
    binary = name + (".exe" if os.name == "nt" else "")
    for candidate in (app_dir() / "bin" / binary, app_dir() / binary):
        if candidate.is_file():
            return candidate
    found = shutil.which(name) or shutil.which(binary)
    return Path(found) if found else None


def ffmpeg_location() -> Path | None:
    ffmpeg = find_exe("ffmpeg")
    return ffmpeg.parent if ffmpeg else None


def command_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = str(app_dir() / "bin") + os.pathsep + env.get("PATH", "")
    return env
