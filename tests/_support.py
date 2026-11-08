"""Közös tesztsegédlet: forrásútvonal, mintafájlok, elkülönített adatmappa."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

# A tesztek ne írjanak a valódi data/ mappába.
_DATA = tempfile.mkdtemp(prefix="ytstudio-test-data-")
os.environ.setdefault("YTDLPSTUDIO_DATA_DIR", _DATA)


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def bin_tool(name: str) -> Path | None:
    path = ROOT / "bin" / (name + ".exe")
    return path if path.is_file() else None
