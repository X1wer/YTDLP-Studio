"""Trim SRT and WebVTT captions to an extracted video segment."""
from __future__ import annotations

from pathlib import Path
import re

_STAMP = re.compile(r"(?:(\d+):)?(\d{2}):(\d{2})[,.](\d{3})")
_TIMELINE = re.compile(r"(?P<first>(?:\d+:)?\d{2}:\d{2}[,.]\d{3})\s*-->\s*(?P<last>(?:\d+:)?\d{2}:\d{2}[,.]\d{3})(?P<flags>.*)")


def stamp_to_ms(value: str) -> int:
    found = _STAMP.fullmatch(value.strip())
    if not found:
        raise ValueError(f"Ismeretlen feliratidő: {value}")
    hours, mins, secs, millis = found.groups()
    return ((int(hours or 0) * 3600 + int(mins) * 60 + int(secs)) * 1000 + int(millis))


def ms_to_stamp(ms: int, vtt: bool) -> str:
    ms = max(0, ms)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02}{'.' if vtt else ','}{milli:03}"


def trim_subtitle_text(content: str, start: float = 0.0,
                       end: float | None = None, vtt: bool = False) -> str:
    """Clip cues and rebase to t=0, preserving multiline cue text.

    Accepts normal SRT/VTT files with blank-line-delimited cues. Complex VTT
    constructs (STYLE/REGION) are not modified.
    """
    content = content.lstrip("\ufeff").replace("\r\n", "\n")
    blocks = re.split(r"\n\s*\n", content.strip())
    start_ms = int(start * 1000)
    end_ms = int(end * 1000) if end is not None else None
    output: list[str] = []
    count = 0
    if vtt:
        output.append("WEBVTT")
    for block in blocks:
        lines = block.split("\n")
        timeline_idx = next((i for i, line in enumerate(lines) if _TIMELINE.fullmatch(line.strip())), None)
        if timeline_idx is None:
            # VTT header is kept, but styles can reference offsets outside the
            # clip and should be handled separately if advanced VTT features used.
            continue
        line = lines[timeline_idx].strip()
        match = _TIMELINE.fullmatch(line)
        assert match is not None
        first, last = stamp_to_ms(match["first"]), stamp_to_ms(match["last"])
        clip_start = max(first, start_ms)
        clip_end = min(last, end_ms) if end_ms is not None else last
        if clip_end <= clip_start:
            continue
        count += 1
        stamp_line = (f"{ms_to_stamp(clip_start - start_ms, vtt)} --> "
                      f"{ms_to_stamp(clip_end - start_ms, vtt)}{match['flags']}")
        if vtt:
            # Keep cue identifiers if provided (not numeric SRT counters).
            prefix = lines[:timeline_idx]
            output.append("\n".join(prefix + [stamp_line] + lines[timeline_idx + 1:]))
        else:
            output.append("\n".join([str(count), stamp_line] + lines[timeline_idx + 1:]))
    if not output:
        return "WEBVTT\n" if vtt else ""
    return "\n\n".join(output) + "\n"


def trim_file(path: Path, start: float, end: float | None) -> None:
    if path.suffix.lower() not in {".srt", ".vtt"}:
        raise ValueError("Csak SRT és WebVTT fájlok időzítése igazítható.")
    text = path.read_text(encoding="utf-8-sig")
    trimmed = trim_subtitle_text(text, start, end, path.suffix.lower() == ".vtt")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(trimmed, encoding="utf-8")
    tmp.replace(path)
