"""Központi technikai napló: a felület Napló ablakába és a data/logs mappába ír."""
from __future__ import annotations

from datetime import datetime
import threading

from PySide6.QtCore import QObject, Signal

from ..settings import data_dir

MAX_BYTES = 2_000_000


class LogBus(QObject):
    message = Signal(str)

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self.lines: list[str] = []
        self.path = None
        try:
            folder = data_dir() / "logs"
            folder.mkdir(parents=True, exist_ok=True)
            self.path = folder / "ytdlp-studio.log"
        except OSError:
            self.path = None

    def log(self, text: str) -> None:
        if not text:
            return
        stamp = datetime.now().strftime("%H:%M:%S")
        lines = [f"[{stamp}] {line}" for line in str(text).splitlines() if line.strip()]
        if not lines:
            return
        with self._lock:
            self.lines.extend(lines)
            if len(self.lines) > 6000:
                del self.lines[:1000]
            self._write(lines)
        for line in lines:
            self.message.emit(line)

    def _write(self, lines: list[str]) -> None:
        if self.path is None:
            return
        try:
            if self.path.exists() and self.path.stat().st_size > MAX_BYTES:
                old = self.path.with_suffix(".1.log")
                old.unlink(missing_ok=True)
                self.path.replace(old)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")
        except OSError:
            pass


bus = LogBus()


def log(text: str) -> None:
    bus.log(text)
