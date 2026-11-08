"""Forrásból indítás és PyInstaller-belépési pont."""
from pathlib import Path
import sys

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ytstudio.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
