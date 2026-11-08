"""Letöltési sor: feladatok, párhuzamos végrehajtás és a sor megjelenítése."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import itertools
import threading
import time
import uuid

from PySide6.QtCore import (QAbstractListModel, QEvent, QModelIndex, QObject, QPoint, QRect, QRectF,
                            QSize, Qt, Signal)
from PySide6.QtGui import QAction, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QListView, QMenu, QStyle,
                               QStyledItemDelegate, QToolTip, QVBoxLayout, QWidget)

from . import icons, theme
from .logbus import log
from .widgets import Card, button, label
from ..core import DownloadOptions, fmt_duration, fmt_size
from ..engine import Cancelled, DownloadResult, DownloadTask, OperationError, Progress, cleanup_workdir
from ..errors import FriendlyError, explain

STATUS_TEXT = {"queued": "Várakozik", "running": "Folyamatban", "done": "Kész",
               "error": "Sikertelen", "cancelled": "Megszakítva", "paused": "Szüneteltetve"}


@dataclass
class Job:
    id: int
    options: DownloadOptions
    title: str
    key: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    status: str = "queued"
    progress: Progress = field(default_factory=Progress)
    files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: FriendlyError | None = None
    details: str = ""
    immediate: bool = False
    started: float = 0.0
    finished: float = 0.0
    task: DownloadTask | None = None

    @property
    def summary(self) -> str:
        o = self.options
        if o.mode == "audio":
            text = {"original": "Eredeti hang"}.get(o.audio_format, o.audio_format.upper())
        elif o.mode == "subtitles":
            text = "Felirat (" + o.subtitle_format.upper() + ")"
        else:
            text = o.effective_container.upper()
            text += " · " + ("legjobb minőség" if o.quality == "best" else f"max. {o.quality}p")
        if o.is_clip:
            text += " · részlet"
        return text

    def status_line(self) -> str:
        p = self.progress
        if self.status == "queued":
            return "Várakozik · " + self.summary
        if self.status == "running":
            parts = [p.text or "Folyamatban…"]
            if p.percent is not None and p.stage == "downloading":
                parts.append(f"{p.percent:.0f}%")
            if p.speed:
                parts.append(fmt_size(p.speed) + "/s")
            if p.eta and p.stage == "downloading":
                parts.append(fmt_duration(p.eta) + " van hátra")
            return " · ".join(parts)
        if self.status == "done":
            size = sum(f.stat().st_size for f in self.files if f.exists())
            text = "Kész · " + (fmt_size(size) if size else self.summary)
            if self.warnings:
                text += " · figyelmeztetés"
            return text
        if self.status == "error":
            return "Sikertelen: " + (self.error.title if self.error else "ismeretlen hiba")
        if self.status == "cancelled":
            return "Megszakítva"
        return STATUS_TEXT.get(self.status, self.status)


class DownloadManager(QObject):
    """A sor végrehajtása háttérszálakon; a felület csak jelzéseket kap."""

    jobAdded = Signal(object)
    jobChanged = Signal(object)
    jobRemoved = Signal(object)
    jobFinished = Signal(object)
    _progress = Signal(object, object)
    _finished = Signal(object, str, object)

    def __init__(self, max_parallel: int = 1, parent=None):
        super().__init__(parent)
        self.jobs: list[Job] = []
        self.max_parallel = max_parallel
        self.paused = False
        self._ids = itertools.count(1)
        self._progress.connect(self._on_progress)
        self._finished.connect(self._on_finished)

    # -- lekérdezés -------------------------------------------------------- #
    def running(self) -> list[Job]:
        return [j for j in self.jobs if j.status == "running"]

    def busy(self) -> bool:
        return any(j.status in ("running", "queued") for j in self.jobs) and bool(self.running())

    def counts(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for j in self.jobs:
            result[j.status] = result.get(j.status, 0) + 1
        return result

    # -- műveletek ----------------------------------------------------------- #
    def add(self, options: DownloadOptions, title: str, immediate: bool = False) -> Job:
        job = Job(next(self._ids), options, title or options.url, immediate=immediate)
        if immediate:
            position = len(self.running())
            self.jobs.insert(position, job)
        else:
            self.jobs.append(job)
        self.jobAdded.emit(job)
        log(f"Sorba állítva: {job.title} ({job.summary})")
        self.schedule()
        return job

    def schedule(self) -> None:
        for job in list(self.jobs):
            if job.status != "queued":
                continue
            if job.immediate or (not self.paused and len(self.running()) < self.max_parallel):
                self._start(job)

    def _start(self, job: Job) -> None:
        job.status = "running"
        job.started = time.time()
        job.error, job.details, job.warnings, job.files = None, "", [], []
        job.progress = Progress(stage="starting", text="Indítás…")
        task = DownloadTask(job.options, job.key,
                            on_progress=lambda p, j=job: self._progress.emit(j, p),
                            on_log=log)
        job.task = task
        self.jobChanged.emit(job)

        def work():
            try:
                result = task.run()
                self._finished.emit(job, "done", result)
            except Cancelled:
                self._finished.emit(job, "cancelled", None)
            except OperationError as exc:
                self._finished.emit(job, "error", exc)
            except Exception as exc:  # noqa: BLE001 - minden hiba a felületen jelenjen meg
                self._finished.emit(job, "error", OperationError(explain(str(exc)), repr(exc)))

        threading.Thread(target=work, name=f"job-{job.id}", daemon=True).start()

    def _on_progress(self, job: Job, progress: Progress) -> None:
        if job.status == "running":
            job.progress = progress
            self.jobChanged.emit(job)

    def _on_finished(self, job: Job, status: str, payload) -> None:
        job.task = None
        job.finished = time.time()
        job.immediate = False
        if status == "done":
            result: DownloadResult = payload
            job.files = result.files
            job.warnings = result.warnings
            job.status = "done"
            job.progress = Progress(stage="done", text="Kész", percent=100)
            log(f"Kész: {job.title} → {result.main_file}")
        elif status == "cancelled":
            job.status = "cancelled"
            log(f"Megszakítva: {job.title}")
        else:
            error: OperationError = payload
            job.status = "error"
            job.error = error.friendly
            job.details = error.details or str(error)
            log(f"HIBA ({job.title}): {error.friendly.title} – {error.friendly.message}")
            if error.details:
                log(error.details)
        if job not in self.jobs:
            self._cleanup_later(job)
        self.jobChanged.emit(job)
        self.jobFinished.emit(job)
        self.schedule()

    def cancel(self, job: Job) -> None:
        if job.status == "running" and job.task is not None:
            job.progress = Progress(stage="finishing", text="Megszakítás…")
            self.jobChanged.emit(job)
            job.task.cancel()
        elif job.status == "queued":
            job.status = "cancelled"
            self.jobChanged.emit(job)

    def retry(self, job: Job) -> None:
        if job.status in ("error", "cancelled"):
            job.status = "queued"
            job.immediate = True
            job.progress = Progress()
            self.jobChanged.emit(job)
            self.schedule()

    def remove(self, job: Job) -> None:
        if job.status == "running":
            self.cancel(job)
        if job in self.jobs:
            self.jobs.remove(job)
            self.jobRemoved.emit(job)
        if job.status != "running":
            self._cleanup_later(job)

    @staticmethod
    def _cleanup_later(job: Job) -> None:
        threading.Thread(target=cleanup_workdir, args=(Path(job.options.dest), job.key),
                         name=f"cleanup-{job.id}", daemon=True).start()

    def clear_finished(self) -> None:
        for job in [j for j in self.jobs if j.status in ("done", "cancelled", "error")]:
            self.remove(job)

    def retry_failed(self) -> None:
        for job in [j for j in self.jobs if j.status in ("error", "cancelled")]:
            job.status = "queued"
            job.progress = Progress()
            self.jobChanged.emit(job)
        self.schedule()

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        if not paused:
            self.schedule()

    def shutdown(self) -> None:
        """Kilépéskor: futó feladatok leállítása, ideiglenes fájlok törlése."""
        for job in self.jobs:
            if job.status == "running" and job.task is not None:
                job.task.cancel()
        deadline = time.time() + 8
        while any(j.task is not None for j in self.jobs) and time.time() < deadline:
            time.sleep(0.1)
        for job in self.jobs:
            if job.status != "done":
                cleanup_workdir(Path(job.options.dest), job.key)


class JobModel(QAbstractListModel):
    def __init__(self, manager: DownloadManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        manager.jobAdded.connect(self._reset)
        manager.jobRemoved.connect(self._reset)
        manager.jobChanged.connect(self._changed)

    def _reset(self, *_):
        self.beginResetModel()
        self.endResetModel()

    def _changed(self, job: Job) -> None:
        if job in self.manager.jobs:
            row = self.manager.jobs.index(job)
            index = self.index(row)
            self.dataChanged.emit(index, index)

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.manager.jobs)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.manager.jobs):
            return None
        job = self.manager.jobs[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return job
        if role == Qt.ItemDataRole.DisplayRole:
            return job.title
        return None


ACTIONS = {
    "queued": [("remove", "close", "Eltávolítás a sorból")],
    "running": [("cancel", "stop", "Megszakítás")],
    "done": [("folder", "folder-open", "Mappa megnyitása"), ("open", "play", "Megnyitás")],
    "error": [("remove", "close", "Eltávolítás"), ("details", "info", "Hiba részletei"),
              ("retry", "retry", "Újrapróbálás")],
    "cancelled": [("remove", "close", "Eltávolítás"), ("retry", "retry", "Újrapróbálás")],
}

MODE_ICONS = {"video": "video", "audio": "audio", "subtitles": "subtitles"}


class JobDelegate(QStyledItemDelegate):
    actionTriggered = Signal(str, object)
    HEIGHT = 86

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover_action: tuple[int, str] | None = None

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), self.HEIGHT)

    def _buttons(self, rect: QRect, job: Job) -> list[tuple[str, str, str, QRect]]:
        result = []
        x = rect.right() - 12
        for action, icon_name, tip in reversed(ACTIONS.get(job.status, [])):
            r = QRect(x - 30, rect.top() + 12, 30, 30)
            result.append((action, icon_name, tip, r))
            x -= 34
        return list(reversed(result))

    def paint(self, painter: QPainter, option, index) -> None:
        job: Job = index.data(Qt.ItemDataRole.UserRole)
        if job is None:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(2, 4, -2, -4)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.setPen(QPen(theme.qc("accent" if selected else "border"), 1))
        painter.setBrush(theme.qc("hover" if hovered and not selected else "surface"))
        painter.drawRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        # ikon
        icon_rect = QRectF(rect.left() + 12, rect.top() + 12, 36, 36)
        role, bg = {"done": ("success", "success_soft"), "error": ("danger", "danger_soft"),
                    "cancelled": ("muted", "surface2")}.get(job.status, ("accent", "accent_soft"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme.qc(bg))
        painter.drawRoundedRect(icon_rect, 9, 9)
        name = {"done": "check", "error": "alert"}.get(job.status, MODE_ICONS.get(job.options.mode, "video"))
        painter.drawPixmap(int(icon_rect.left() + 8), int(icon_rect.top() + 8), icons.pixmap(name, theme.c(role), 20))
        buttons = self._buttons(rect, job)
        text_left = int(icon_rect.right()) + 12
        text_right = (buttons[0][3].left() - 8) if buttons else rect.right() - 12
        # cím
        font = QFont(option.font)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(theme.qc("text"))
        fm = QFontMetrics(font)
        title_rect = QRect(text_left, rect.top() + 10, text_right - text_left, fm.height() + 2)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         fm.elidedText(job.title, Qt.TextElideMode.ElideRight, title_rect.width()))
        # állapotsor
        small = QFont(option.font)
        small.setPointSizeF(max(7.5, option.font.pointSizeF() - 1))
        painter.setFont(small)
        sfm = QFontMetrics(small)
        status_role = {"error": "danger", "done": "success"}.get(job.status, "muted")
        if job.status == "done" and job.warnings:
            status_role = "warning"
        painter.setPen(theme.qc(status_role))
        status_rect = QRect(text_left, title_rect.bottom() + 3, text_right - text_left, sfm.height() + 2)
        painter.drawText(status_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         sfm.elidedText(job.status_line(), Qt.TextElideMode.ElideRight, status_rect.width()))
        # haladásjelző
        if job.status in ("running", "queued"):
            bar = QRectF(text_left, rect.bottom() - 16, rect.right() - 12 - text_left, 5)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.qc("track"))
            painter.drawRoundedRect(bar, 2.5, 2.5)
            p = job.progress
            if job.status == "running":
                painter.setBrush(theme.qc("accent"))
                if p.percent is not None and p.stage == "downloading":
                    width = bar.width() * max(0.0, min(100.0, p.percent)) / 100
                    painter.drawRoundedRect(QRectF(bar.left(), bar.top(), width, bar.height()), 2.5, 2.5)
                else:
                    # határozatlan: mozgó szakasz
                    phase = (time.monotonic() * 0.6) % 1.0
                    seg = bar.width() * 0.25
                    left = bar.left() + (bar.width() + seg) * phase - seg
                    clip = QRectF(max(bar.left(), left), bar.top(),
                                  min(bar.right(), left + seg) - max(bar.left(), left), bar.height())
                    if clip.width() > 0:
                        painter.drawRoundedRect(clip, 2.5, 2.5)
        # gombok
        for action, icon_name, _tip, r in buttons:
            hot = self._hover_action == (index.row(), action)
            if hot:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(theme.qc("border"))
                painter.drawRoundedRect(QRectF(r), 7, 7)
            color = theme.c("danger") if action == "cancel" else theme.c("accent") if action in ("open", "retry") else theme.c("muted")
            painter.drawPixmap(r.left() + 6, r.top() + 6, icons.pixmap(icon_name, color, 18))
        painter.restore()

    def _hit(self, option, index, pos: QPoint) -> str | None:
        job: Job = index.data(Qt.ItemDataRole.UserRole)
        if job is None:
            return None
        rect = option.rect.adjusted(2, 4, -2, -4)
        for action, _icon, _tip, r in self._buttons(rect, job):
            if r.contains(pos):
                return action
        return None

    def editorEvent(self, event, model, option, index) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.MouseMove:
            action = self._hit(option, index, event.position().toPoint())
            key = (index.row(), action) if action else None
            if key != self._hover_action:
                self._hover_action = key
                if self.parent():
                    self.parent().viewport().update()
            return False
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            action = self._hit(option, index, event.position().toPoint())
            if action:
                self.actionTriggered.emit(action, index.data(Qt.ItemDataRole.UserRole))
                return True
        if event.type() == QEvent.Type.MouseButtonDblClick:
            job = index.data(Qt.ItemDataRole.UserRole)
            if job is not None and job.status == "done":
                self.actionTriggered.emit("open", job)
                return True
        return False

    def helpEvent(self, event, view, option, index) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.ToolTip:
            job: Job = index.data(Qt.ItemDataRole.UserRole)
            rect = option.rect.adjusted(2, 4, -2, -4)
            for _action, _icon, tip, r in self._buttons(rect, job):
                if r.contains(event.pos()):
                    QToolTip.showText(event.globalPos(), tip, view)
                    return True
            text = f"{job.title}\n{job.status_line()}"
            if job.error:
                text += f"\n\n{job.error.message}"
            for warning in job.warnings:
                text += f"\n⚠ {warning}"
            QToolTip.showText(event.globalPos(), text, view)
            return True
        return super().helpEvent(event, view, option, index)


class QueuePanel(Card):
    """A jobb oldali „Letöltések” panel."""

    actionRequested = Signal(str, object)

    def __init__(self, manager: DownloadManager, parent=None):
        super().__init__("Letöltések", "download", parent, margins=14)
        self.manager = manager
        self.summary = label("", "caption")
        self.header_right.addWidget(self.summary)
        self.pause = button("", "ghost", "pause", "muted", "A sor szüneteltetése (a futó letöltés folytatódik)")
        self.pause.setCheckable(True)
        self.pause.setFixedSize(32, 32)
        self.pause.toggled.connect(self._toggle_pause)
        self.header_right.addWidget(self.pause)
        self.model = JobModel(manager, self)
        self.view = QListView()
        self.view.setObjectName("queueList")
        self.view.setModel(self.model)
        self.delegate = JobDelegate(self.view)
        self.view.setItemDelegate(self.delegate)
        self.view.setMouseTracking(True)
        self.view.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._menu)
        self.delegate.actionTriggered.connect(self.actionRequested)
        self.body.addWidget(self.view, 1)
        self.empty = QWidget()
        self.empty.setObjectName("transparent")
        empty_layout = QVBoxLayout(self.empty)
        empty_layout.addStretch(1)
        title = label("Még nincs letöltés", "h2")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = label("Elemezz egy videót, majd válaszd a „Letöltés most” vagy a „Hozzáadás a sorhoz” "
                     "gombot. A letöltések itt jelennek meg.", "muted", wrap=True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(title)
        empty_layout.addWidget(hint)
        empty_layout.addStretch(2)
        self.body.addWidget(self.empty, 1)
        footer = QHBoxLayout()
        footer.setSpacing(6)
        self.clear_button = button("Befejezettek törlése", "ghost", "trash", "muted")
        self.clear_button.clicked.connect(manager.clear_finished)
        self.retry_button = button("Sikertelenek újra", "ghost", "retry", "muted")
        self.retry_button.clicked.connect(manager.retry_failed)
        footer.addWidget(self.clear_button)
        footer.addWidget(self.retry_button)
        footer.addStretch(1)
        self.body.addLayout(footer)
        for sig in (manager.jobAdded, manager.jobRemoved, manager.jobChanged):
            sig.connect(self._update)
        theme.manager.changed.connect(self.view.viewport().update)
        from PySide6.QtCore import QTimer
        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)
        self._anim.start(60)
        self._update()

    def _tick(self) -> None:
        if any(j.status == "running" and (j.progress.percent is None or j.progress.stage != "downloading")
               for j in self.manager.jobs):
            self.view.viewport().update()

    def _toggle_pause(self, paused: bool) -> None:
        self.manager.set_paused(paused)
        from .widgets import set_icon
        set_icon(self.pause, "play" if paused else "pause", "accent" if paused else "muted")
        self.pause.setToolTip("A sor folytatása" if paused else "A sor szüneteltetése (a futó letöltés folytatódik)")
        self._update()

    def _update(self, *_):
        counts = self.manager.counts()
        has = bool(self.manager.jobs)
        self.view.setVisible(has)
        self.empty.setVisible(not has)
        parts = []
        if counts.get("running"):
            parts.append(f"{counts['running']} fut")
        if counts.get("queued"):
            parts.append(f"{counts['queued']} vár")
        if counts.get("done"):
            parts.append(f"{counts['done']} kész")
        if counts.get("error"):
            parts.append(f"{counts['error']} hibás")
        if self.manager.paused:
            parts.append("szünetel")
        self.summary.setText(" · ".join(parts))
        self.clear_button.setEnabled(any(counts.get(s) for s in ("done", "error", "cancelled")))
        self.retry_button.setEnabled(any(counts.get(s) for s in ("error", "cancelled")))

    def _menu(self, pos: QPoint) -> None:
        index = self.view.indexAt(pos)
        if not index.isValid():
            return
        job: Job = index.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        entries = [
            ("open", "Megnyitás", job.status == "done"),
            ("folder", "Mappa megnyitása", True),
            (None, None, None),
            ("cancel", "Megszakítás", job.status in ("running", "queued")),
            ("retry", "Újrapróbálás", job.status in ("error", "cancelled")),
            ("details", "Részletek…", job.status == "error" or bool(job.warnings)),
            (None, None, None),
            ("copy", "Link másolása", True),
            ("browser", "Megnyitás böngészőben", True),
            ("remove", "Eltávolítás a listából", True),
        ]
        for action, text, enabled in entries:
            if action is None:
                menu.addSeparator()
                continue
            item = QAction(text, menu)
            item.setEnabled(bool(enabled))
            item.triggered.connect(lambda _=False, a=action: self.actionRequested.emit(a, job))
            menu.addAction(item)
        menu.exec(self.view.viewport().mapToGlobal(pos))
