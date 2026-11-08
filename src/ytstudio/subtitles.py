"""SRT és WebVTT feliratok vágása és időeltolása a letöltött szakaszhoz."""
from __future__ import annotations

from pathlib import Path
import re

_STAMP = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{1,3})")
_TIMELINE = re.compile(
    r"(?P<first>(?:\d+:)?\d{1,2}:\d{2}[,.]\d{1,3})\s*-->\s*"
    r"(?P<last>(?:\d+:)?\d{1,2}:\d{2}[,.]\d{1,3})(?P<flags>.*)")
_INLINE_STAMP = re.compile(r"<(\d+:\d{2}:\d{2}\.\d{3})>")


def stamp_to_ms(value: str) -> int:
    found = _STAMP.fullmatch(value.strip())
    if not found:
        raise ValueError(f"Ismeretlen feliratidő: {value}")
    hours, mins, secs, millis = found.groups()
    millis = (millis + "00")[:3]
    return (int(hours or 0) * 3600 + int(mins) * 60 + int(secs)) * 1000 + int(millis)


def ms_to_stamp(ms: int, vtt: bool) -> str:
    ms = max(0, int(ms))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02}{'.' if vtt else ','}{milli:03}"


def trim_subtitle_text(content: str, start: float = 0.0, end: float | None = None,
                       vtt: bool = False, offset: float = 0.0) -> str:
    """A [start, end] szakaszba eső feliratokat tartja meg, és az időket átírja.

    Az új idő ``t - start + offset``. Az ``offset`` azt kompenzálja, ha a
    gyors (kulcskocka-alapú) vágás miatt a videó a kért kezdőpont előtt
    kezdődik, így a hang a fájlban később indul. A többsoros feliratszöveg és
    a VTT-fejléc (STYLE/REGION blokkok) megmarad.
    """
    content = content.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n[ \t]*\n", content.strip())
    start_ms = int(round(start * 1000))
    end_ms = int(round(end * 1000)) if end is not None else None
    shift = int(round(offset * 1000)) - start_ms
    output: list[str] = []
    count = 0
    header_done = False
    for block in blocks:
        lines = block.split("\n")
        timeline_idx = next((i for i, line in enumerate(lines) if _TIMELINE.fullmatch(line.strip())), None)
        if timeline_idx is None:
            if vtt and not header_done:
                first = lines[0].strip()
                if first.startswith("WEBVTT"):
                    output.append(block)
                    header_done = True
                elif first.startswith(("STYLE", "REGION", "NOTE")):
                    output.append(block)
            continue
        if vtt and not header_done:
            output.insert(0, "WEBVTT")
            header_done = True
        match = _TIMELINE.fullmatch(lines[timeline_idx].strip())
        assert match is not None
        first, last = stamp_to_ms(match["first"]), stamp_to_ms(match["last"])
        clip_start = max(first, start_ms)
        clip_end = min(last, end_ms) if end_ms is not None else last
        if clip_end <= clip_start:
            continue
        count += 1
        stamp_line = (f"{ms_to_stamp(clip_start + shift, vtt)} --> "
                      f"{ms_to_stamp(clip_end + shift, vtt)}{match['flags'] if vtt else ''}")
        body = lines[timeline_idx + 1:]
        if vtt:
            body = [_INLINE_STAMP.sub(lambda m: "<" + ms_to_stamp(stamp_to_ms(m.group(1)) + shift, True) + ">", line)
                    for line in body]
            output.append("\n".join(lines[:timeline_idx] + [stamp_line] + body))
        else:
            output.append("\n".join([str(count), stamp_line] + body))
    if vtt and not header_done:
        output.insert(0, "WEBVTT")
    if not count:
        return "WEBVTT\n" if vtt else ""
    return "\n\n".join(output) + "\n"


def trim_file(path: Path, start: float, end: float | None, offset: float = 0.0) -> int:
    """Atomikusan átírja a feliratfájlt; visszaadja a megmaradt feliratok számát."""
    suffix = path.suffix.lower()
    if suffix not in {".srt", ".vtt"}:
        raise ValueError("Csak SRT és WebVTT fájlok időzítése igazítható.")
    # Bájtként olvas, hogy a hibás CR-CR-LF sorvégek se okozzanak üres sorokat.
    text = path.read_bytes().decode("utf-8-sig", errors="replace").replace("\r\r\n", "\n")
    trimmed = trim_subtitle_text(text, start, end, suffix == ".vtt", offset)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(trimmed, encoding="utf-8")
    tmp.replace(path)
    return len(_TIMELINE.findall(trimmed))
