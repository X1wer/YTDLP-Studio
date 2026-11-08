"""Főablak: link → elemzés → beállítások → (vágás) → letöltés → kész fájl."""
from __future__ import annotations

import ipaddress
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QByteArray, QObject, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QKeySequence, QPixmap, QShortcut
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (QApplication, QFileDialog, QGridLayout, QHBoxLayout, QLineEdit,
                               QMainWindow, QMessageBox, QScrollArea, QSizePolicy, QSplitter,
                               QStackedWidget, QVBoxLayout, QWidget, QCheckBox, QFrame)

from . import icons, theme
from .dialogs import DetailsDialog, LogWindow, SettingsDialog, ToolsDialog, open_path
from .logbus import log
from .queue import DownloadManager, Job, QueuePanel
from .widgets import (Banner, Card, CheckList, ChoiceBox, Collapsible, IconLabel, RangeSlider,
                      SegmentedControl, Spinner, ThumbnailView, TimeEdit, ToggleSwitch, button, label,
                      set_icon)
from .. import APP_NAME, __version__
from .. import engine
from ..core import (AUDIO_KIND_LABELS, SUB_KIND_LABELS, DownloadOptions, PlaylistInfo, VideoInfo,
                    estimate_size, fmt_duration, fmt_size, fmt_time, normalize_url, safe_component,
                    sort_subtitles, validate_url)
from ..errors import FriendlyError, explain
from ..langs import base_code, language_name, matches_preference
from ..settings import Settings, app_dir

VIDEO_FORMAT_HINTS = {
    "mp4": "MP4 – a legszélesebb körben lejátszható (tévé, telefon, Windows).",
    "mkv": "MKV – több hangsáv és felirat egy fájlban, az eredeti minőség megőrzésével.",
    "webm": "WebM – nyílt formátum (VP9/AV1 videó, Opus hang).",
}
AUDIO_FORMAT_HINTS = {
    "mp3": "MP3 – bármilyen eszközön lejátszható.",
    "m4a": "M4A (AAC) – jó minőség, Apple-eszközökön is; gyakran átkódolás nélkül.",
    "aac": "AAC – nyers AAC hangfájl.",
    "opus": "Opus – kis méret, kiváló minőség; gyakran átkódolás nélkül.",
    "flac": "FLAC – veszteségmentes tárolás (nagy fájl; a forrásnál jobb nem lesz).",
    "wav": "WAV – tömörítetlen, nagyon nagy fájl.",
    "original": "Eredeti – a legjobb hangsáv újrakódolás nélkül (általában Opus vagy AAC).",
}
CODEC_CHOICES = [("auto", "Automatikus (ajánlott)"), ("h264", "H.264 – legjobb kompatibilitás, max. 1080p"),
                 ("vp9", "VP9"), ("av1", "AV1 – kisebb fájl, újabb eszközökhöz")]
AUDIO_QUALITY = [("best", "Legjobb (változó bitráta)"), ("320", "320 kb/s"), ("256", "256 kb/s"),
                 ("192", "192 kb/s"), ("128", "128 kb/s")]


def resource(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", app_dir()))
    return base / "assets" / name


class _Bridge(QObject):
    analysisDone = Signal(int, object)
    analysisFailed = Signal(int, object)


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.manager = DownloadManager(settings.max_parallel, self)
        self.manager.jobFinished.connect(self._job_finished)
        self.info: VideoInfo | None = None
        self.playlist: PlaylistInfo | None = None
        self.player = None
        self.log_window: LogWindow | None = None
        self._token = 0
        self._cancel: threading.Event | None = None
        self._bridge = _Bridge()
        self._bridge.analysisDone.connect(self._analysis_done)
        self._bridge.analysisFailed.connect(self._analysis_failed)
        self._net = QNetworkAccessManager(self)
        self._thumb_reply: QNetworkReply | None = None
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setAcceptDrops(True)
        self.setMinimumSize(1000, 660)
        self._build()
        self._restore_geometry()
        theme.manager.changed.connect(self._theme_changed)
        self._theme_changed()

    # ------------------------------------------------------------------ #
    # Felépítés
    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 14, 20, 18)
        outer.setSpacing(12)
        outer.addLayout(self._build_header())
        outer.addWidget(self._build_url_card())
        self.banner = Banner()
        outer.addWidget(self.banner)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        left = QWidget()
        left.setObjectName("transparent")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_empty_state())
        self.scroll = QScrollArea()
        self.scroll.setObjectName("workspaceScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        workspace = QWidget()
        workspace.setObjectName("workspace")
        self.work = QVBoxLayout(workspace)
        self.work.setContentsMargins(0, 0, 6, 0)
        self.work.setSpacing(12)
        self.work.addWidget(self._build_video_card())
        self.work.addWidget(self._build_playlist_card())
        self.work.addWidget(self._build_options_card())
        self.work.addWidget(self._build_tracks_row())
        self.work.addWidget(self._build_playlist_lang_card())
        self.work.addWidget(self._build_trim_card())
        self.work.addStretch(1)
        self.scroll.setWidget(workspace)
        self.stack.addWidget(self.scroll)
        left_layout.addWidget(self.stack, 1)
        left_layout.addWidget(self._build_action_bar())
        self.splitter.addWidget(left)
        self.queue = QueuePanel(self.manager)
        self.queue.setMinimumWidth(320)
        self.queue.actionRequested.connect(self._job_action)
        self.splitter.addWidget(self.queue)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([820, 400])
        outer.addWidget(self.splitter, 1)
        self._show_page("empty")

        QShortcut(QKeySequence("Ctrl+L"), self, activated=lambda: (self.url_edit.setFocus(), self.url_edit.selectAll()))
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=lambda: self._download(True))
        QShortcut(QKeySequence("F5"), self, activated=self._analyze)

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        logo = label()
        logo.setPixmap(app_icon().pixmap(QSize(30, 30)))
        row.addWidget(logo)
        title = label(APP_NAME, "appTitle")
        row.addWidget(title)
        version = label(f"v{__version__}", "chip")
        row.addWidget(version)
        row.addStretch(1)
        self.theme_button = button("", "ghost", "auto-theme", "muted", "Téma váltása")
        self.theme_button.setFixedSize(36, 34)
        self.theme_button.clicked.connect(self._cycle_theme)
        log_button = button("Napló", "ghost", "log", "muted", "Részletes technikai napló")
        log_button.clicked.connect(self._show_log)
        tools_button = button("Eszközök és frissítés", "ghost", "update", "muted",
                              "Összetevők verziói, yt-dlp frissítése")
        tools_button.clicked.connect(self._show_tools)
        settings_button = button("Beállítások", "ghost", "settings", "muted")
        settings_button.clicked.connect(self._show_settings)
        for b in (self.theme_button, log_button, tools_button, settings_button):
            row.addWidget(b)
        return row

    def _build_url_card(self) -> Card:
        card = Card(margins=14)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.url_edit = QLineEdit()
        self.url_edit.setProperty("size", "large")
        self.url_edit.setPlaceholderText("Illeszd be a videó vagy lejátszási lista linkjét (YouTube és sok más oldal)…")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.addAction(icons.icon("link", theme.c("faint")), QLineEdit.ActionPosition.LeadingPosition)
        self._url_icon_action = self.url_edit.actions()[-1]
        self.url_edit.returnPressed.connect(self._analyze)
        row.addWidget(self.url_edit, 1)
        self.paste_button = button("Beillesztés", None, "paste", "text", "Link beillesztése a vágólapról")
        self.paste_button.clicked.connect(self._paste)
        row.addWidget(self.paste_button)
        self.analyze_button = button("Elemzés", "primary", "search", large=True)
        self.analyze_button.setMinimumWidth(120)
        self.analyze_button.clicked.connect(self._analyze_or_cancel)
        row.addWidget(self.analyze_button)
        card.body.addLayout(row)
        status = QHBoxLayout()
        status.setSpacing(8)
        self.spinner = Spinner(16)
        self.spinner.hide()
        self.status_icon = IconLabel("check-circle", "success", 16)
        self.status_icon.hide()
        self.status_label = label("Másold be egy videó linkjét, majd kattints az Elemzés gombra (vagy nyomj Entert).", "caption")
        status.addWidget(self.spinner)
        status.addWidget(self.status_icon)
        status.addWidget(self.status_label, 1)
        self.load_list_button = button("A teljes lejátszási lista betöltése", "link")
        self.load_list_button.hide()
        self.load_list_button.clicked.connect(self._load_full_playlist)
        status.addWidget(self.load_list_button)
        card.body.addLayout(status)
        return card

    def _build_empty_state(self) -> QWidget:
        page = QWidget()
        page.setObjectName("transparent")
        layout = QVBoxLayout(page)
        layout.addStretch(2)
        card = Card(margins=32)
        card.setMaximumWidth(640)
        icon = label()
        icon.setPixmap(app_icon().pixmap(QSize(64, 64)))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card.body.addWidget(icon)
        title = label("Videó, zene vagy felirat letöltése néhány kattintással", "emptyTitle", wrap=True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card.body.addWidget(title)
        steps = [("1", "Illeszd be a linket", "YouTube-videó, lejátszási lista vagy más támogatott oldal."),
                 ("2", "Válaszd ki, mit kérsz", "Videó vagy csak hang, minőség, hangsávok és feliratok."),
                 ("3", "Töltsd le", "Azonnal vagy a letöltési sorba téve – akár csak egy részletet.")]
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        for i, (num, head, text) in enumerate(steps):
            badge = label(num, "step")
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(badge, i, 0, Qt.AlignmentFlag.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(label(head, "h2"))
            col.addWidget(label(text, "muted", wrap=True))
            grid.addLayout(col, i, 1)
        grid.setColumnStretch(1, 1)
        card.body.addSpacing(8)
        card.body.addLayout(grid)
        note = label("Tipp: a linket az ablakra húzva is beillesztheted. Csak olyan tartalmat tölts le, "
                     "amelyhez jogod van.", "faint", wrap=True)
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card.body.addSpacing(6)
        card.body.addWidget(note)
        wrap = QHBoxLayout()
        wrap.addStretch(1)
        wrap.addWidget(card, 3)
        wrap.addStretch(1)
        layout.addLayout(wrap)
        layout.addStretch(3)
        return page

    def _build_video_card(self) -> Card:
        card = Card(margins=16)
        self.video_card = card
        row = QHBoxLayout()
        row.setSpacing(18)
        self.media_stack = QStackedWidget()
        self.media_stack.setFixedWidth(400)
        self.thumb = ThumbnailView()
        self.thumb.clicked.connect(self._start_preview)
        self.media_stack.addWidget(self.thumb)
        row.addWidget(self.media_stack, 0, Qt.AlignmentFlag.AlignTop)
        info = QVBoxLayout()
        info.setSpacing(6)
        self.title_label = label("", "h1", wrap=True, selectable=True)
        info.addWidget(self.title_label)
        self.meta_label = label("", "muted", wrap=True)
        info.addWidget(self.meta_label)
        self.chips = QHBoxLayout()
        self.chips.setSpacing(6)
        info.addLayout(self.chips)
        self.notice = label("", "warnText", wrap=True)
        self.notice.hide()
        info.addWidget(self.notice)
        info.addStretch(1)
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.preview_button = button("Előnézet", None, "play", "accent", "A videó lejátszása az alkalmazásban")
        self.preview_button.clicked.connect(self._start_preview)
        self.browser_button = button("Megnyitás böngészőben", "ghost", "external", "muted")
        self.browser_button.clicked.connect(self._open_in_browser)
        buttons.addWidget(self.preview_button)
        buttons.addWidget(self.browser_button)
        buttons.addStretch(1)
        info.addLayout(buttons)
        row.addLayout(info, 1)
        card.body.addLayout(row)
        return card

    def _build_playlist_card(self) -> Card:
        card = Card("Lejátszási lista", "list")
        self.playlist_card = card
        self.pl_title = label("", "h1", wrap=True)
        self.pl_meta = label("", "muted")
        card.body.addWidget(self.pl_title)
        card.body.addWidget(self.pl_meta)
        self.pl_list = CheckList(placeholder="Keresés a videók között…", empty_text="A lista üres.")
        self.pl_list.setMinimumHeight(320)
        all_button = button("Mind", "ghost", tooltip="Az összes látható videó kijelölése")
        all_button.clicked.connect(self.pl_list.select_visible)
        self.pl_list.footer.insertWidget(2, all_button)
        self.pl_list.selectionChanged.connect(self._update_summary)
        card.body.addWidget(self.pl_list, 1)
        opts = QHBoxLayout()
        self.pl_subfolder = QCheckBox("Mentés a lista nevével ellátott almappába")
        self.pl_subfolder.setChecked(True)
        self.pl_numbering = QCheckBox("Sorszám a fájlnév elejére")
        self.pl_numbering.setChecked(True)
        opts.addWidget(self.pl_subfolder)
        opts.addWidget(self.pl_numbering)
        opts.addStretch(1)
        card.body.addLayout(opts)
        return card

    def _build_options_card(self) -> Card:
        card = Card("Mit szeretnél letölteni?", "download")
        self.mode = SegmentedControl([("video", "Videó"), ("audio", "Csak hang"), ("subtitles", "Csak felirat")],
                                     large=True, icons_map={"video": "video", "audio": "audio", "subtitles": "subtitles"})
        self.mode.changed.connect(self._mode_changed)
        card.body.addWidget(self.mode)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.setColumnMinimumWidth(0, 90)
        # videó
        self.video_widgets = []
        self.container = SegmentedControl([("mp4", "MP4"), ("mkv", "MKV"), ("webm", "WebM")])
        self.container.changed.connect(self._options_changed)
        self.container_hint = label("", "caption", wrap=True)
        self.quality = ChoiceBox([("best", "Legjobb elérhető")])
        self.quality.setMinimumWidth(260)
        self.quality.currentIndexChanged.connect(self._options_changed)
        l1, l2 = label("Formátum", "muted"), label("Minőség", "muted")
        grid.addWidget(l1, 0, 0)
        grid.addWidget(self.container, 0, 1, Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(self.container_hint, 1, 1)
        grid.addWidget(l2, 2, 0)
        grid.addWidget(self.quality, 2, 1, Qt.AlignmentFlag.AlignLeft)
        self.video_widgets = [l1, l2, self.container, self.container_hint, self.quality]
        # hang
        self.audio_format = SegmentedControl([("mp3", "MP3"), ("m4a", "M4A"), ("aac", "AAC"), ("opus", "Opus"),
                                              ("flac", "FLAC"), ("wav", "WAV"), ("original", "Eredeti")])
        self.audio_format.changed.connect(self._options_changed)
        self.audio_hint = label("", "caption", wrap=True)
        self.audio_quality = ChoiceBox(AUDIO_QUALITY)
        self.audio_quality.currentIndexChanged.connect(self._options_changed)
        a1, self.audio_quality_label = label("Formátum", "muted"), label("Minőség", "muted")
        grid.addWidget(a1, 3, 0)
        grid.addWidget(self.audio_format, 3, 1, Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(self.audio_hint, 4, 1)
        grid.addWidget(self.audio_quality_label, 5, 0)
        grid.addWidget(self.audio_quality, 5, 1, Qt.AlignmentFlag.AlignLeft)
        self.audio_widgets = [a1, self.audio_format, self.audio_hint, self.audio_quality_label, self.audio_quality]
        # felirat mód
        self.subs_mode_hint = label("Csak a lenti „Feliratok” listában kijelölt feliratok töltődnek le, "
                                    "videó nélkül.", "caption", wrap=True)
        grid.addWidget(self.subs_mode_hint, 6, 0, 1, 2)
        grid.setColumnStretch(1, 1)
        card.body.addLayout(grid)
        # haladó
        self.advanced = Collapsible("További beállítások")
        adv = QGridLayout()
        adv.setHorizontalSpacing(14)
        adv.setVerticalSpacing(8)
        self.codec_label = label("Videókodek", "muted")
        self.codec = ChoiceBox(CODEC_CHOICES)
        self.codec.currentIndexChanged.connect(self._options_changed)
        adv.addWidget(self.codec_label, 0, 0)
        adv.addWidget(self.codec, 0, 1, Qt.AlignmentFlag.AlignLeft)
        self.embed_metadata = QCheckBox("Metaadatok beágyazása (cím, előadó, dátum, hangsávnyelvek)")
        self.embed_thumbnail = QCheckBox("Borítókép beágyazása")
        self.embed_chapters = QCheckBox("Fejezetjelölők beágyazása")
        adv.addWidget(self.embed_metadata, 1, 0, 1, 2)
        adv.addWidget(self.embed_thumbnail, 2, 0, 1, 2)
        adv.addWidget(self.embed_chapters, 3, 0, 1, 2)
        adv.setColumnStretch(1, 1)
        self.advanced.body.addLayout(adv)
        card.body.addWidget(self.advanced)
        s = self.settings
        self.mode.set_value(s.mode)
        self.container.set_value(s.container)
        self.audio_format.set_value(s.audio_format)
        self.audio_quality.set_value(s.audio_quality)
        self.codec.set_value(s.video_codec)
        self.embed_metadata.setChecked(s.embed_metadata)
        self.embed_thumbnail.setChecked(s.embed_thumbnail)
        self.embed_chapters.setChecked(s.embed_chapters)
        return card

    def _build_tracks_row(self) -> QWidget:
        row_widget = QWidget()
        row_widget.setObjectName("transparent")
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        self.tracks_row = row_widget
        self.audio_card = Card("Hangsávok", "audio")
        self.audio_count = label("", "accentChip")
        self.audio_card.header_right.addWidget(self.audio_count)
        self.audio_list = CheckList(placeholder="Nyelv keresése…",
                                    kinds=[("original", "Eredeti"), ("dubbed", "Szinkron"),
                                           ("dubbed-auto", "AI-szinkron"), ("descriptive", "Narrált")])
        self.audio_list.selectionChanged.connect(self._options_changed)
        self.audio_card.body.addWidget(self.audio_list, 1)
        self.audio_single = label("", "muted", wrap=True)
        self.audio_single.hide()
        self.audio_card.body.addWidget(self.audio_single)
        self.audio_note = label("", "caption", wrap=True)
        self.audio_card.body.addWidget(self.audio_note)
        self.audio_card.setFixedHeight(380)
        row.addWidget(self.audio_card, 1)
        self.subs_card = Card("Feliratok", "subtitles")
        self.subs_count = label("", "accentChip")
        self.subs_card.header_right.addWidget(self.subs_count)
        self.sub_list = CheckList(placeholder="Nyelv keresése…",
                                  kinds=[("manual", "Eredeti"), ("auto", "Automatikus"), ("translated", "Fordítás")])
        self.sub_list.selectionChanged.connect(self._options_changed)
        star = button("★ Preferált", "ghost", tooltip="A beállításokban megadott preferált nyelvek kijelölése "
                                                      "(eredeti felirat, ha van, különben automatikus)")
        star.clicked.connect(self._select_preferred_subs)
        self.sub_list.footer.insertWidget(2, star)
        self.subs_card.body.addWidget(self.sub_list, 1)
        self.subs_none = label("Ehhez a videóhoz nem érhető el felirat.", "muted", wrap=True)
        self.subs_none.hide()
        self.subs_card.body.addWidget(self.subs_none)
        self.sub_options = QWidget()
        self.sub_options.setObjectName("transparent")
        sub_opts = QHBoxLayout(self.sub_options)
        sub_opts.setContentsMargins(0, 0, 0, 0)
        sub_opts.setSpacing(8)
        sub_opts.addWidget(label("Formátum", "muted"))
        self.sub_format = SegmentedControl([("srt", "SRT"), ("vtt", "VTT")])
        self.sub_format.set_value(self.settings.subtitle_format)
        sub_opts.addWidget(self.sub_format)
        self.embed_subs = QCheckBox("Beágyazás a videóba")
        self.embed_subs.setChecked(self.settings.embed_subtitles)
        self.embed_subs.setToolTip("A kijelölt feliratok a videófájlba kerülnek (nyelvi címkével). "
                                   "Ha ez nem sikerül, külön fájlként maradnak meg.")
        sub_opts.addWidget(self.embed_subs)
        sub_opts.addStretch(1)
        self.subs_card.body.addWidget(self.sub_options)
        self.subs_card.setFixedHeight(380)
        row.addWidget(self.subs_card, 1)
        return row_widget

    def _build_playlist_lang_card(self) -> Card:
        card = Card("Nyelvek a lista videóihoz", "subtitles")
        self.pl_lang_card = card
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        self.pl_subs = QCheckBox("Feliratok letöltése, ha elérhetők")
        self.pl_sub_langs = QLineEdit(", ".join(self.settings.preferred_sub_langs))
        self.pl_sub_langs.setPlaceholderText("pl. hu, en")
        self.pl_sub_langs.setMaximumWidth(220)
        grid.addWidget(self.pl_subs, 0, 0)
        grid.addWidget(label("Nyelvek:", "muted"), 0, 1)
        grid.addWidget(self.pl_sub_langs, 0, 2, Qt.AlignmentFlag.AlignLeft)
        from .dialogs import LANG_CHOICES
        self.pl_audio_lang = ChoiceBox(LANG_CHOICES)
        self.pl_audio_lang.set_value(self.settings.preferred_audio_lang)
        grid.addWidget(label("Hangsáv:", "muted"), 1, 0)
        grid.addWidget(self.pl_audio_lang, 1, 1, 1, 2, Qt.AlignmentFlag.AlignLeft)
        grid.setColumnStretch(3, 1)
        card.body.addLayout(grid)
        card.body.addWidget(label("A videónként eltérő hangsávok és feliratok közül a megadott nyelveket "
                                  "választja; ha egy videónál nincs ilyen, az alapértelmezettet tölti le.",
                                  "caption", wrap=True))
        return card

    def _build_trim_card(self) -> Card:
        card = Card("Időbeli vágás", "scissors")
        self.trim_card = card
        self.trim_switch = ToggleSwitch("Csak egy részlet letöltése")
        self.trim_switch.toggled.connect(self._trim_toggled)
        card.header_right.addWidget(self.trim_switch)
        self.trim_off_label = label("A teljes videó letöltődik. Kapcsold be, ha csak egy szakaszra van szükséged.",
                                    "caption", wrap=True)
        card.body.addWidget(self.trim_off_label)
        self.trim_body = QWidget()
        self.trim_body.setObjectName("transparent")
        body = QVBoxLayout(self.trim_body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        self.range = RangeSlider()
        self.range.rangeChanged.connect(self._range_moved)
        body.addWidget(self.range)
        times = QHBoxLayout()
        times.setSpacing(8)
        self.start_edit = TimeEdit("00:00:00")
        self.end_edit = TimeEdit("vége")
        self.start_edit.timeChanged.connect(self._time_edited)
        self.end_edit.timeChanged.connect(self._time_edited)
        times.addWidget(label("Kezdés", "muted"))
        times.addWidget(self.start_edit)
        times.addSpacing(8)
        times.addWidget(label("Vége", "muted"))
        times.addWidget(self.end_edit)
        times.addSpacing(8)
        self.clip_length = label("", "accentChip")
        times.addWidget(self.clip_length)
        times.addStretch(1)
        self.chapter_box = ChoiceBox([("", "Fejezet kiválasztása…")])
        self.chapter_box.setMaximumWidth(280)
        self.chapter_box.currentIndexChanged.connect(self._chapter_selected)
        times.addWidget(self.chapter_box)
        body.addLayout(times)
        method = QHBoxLayout()
        method.setSpacing(8)
        self.accurate = QCheckBox("Pontos vágás (lassabb, a vágott részt újrakódolja)")
        self.accurate.setChecked(self.settings.accurate_cut)
        self.accurate.toggled.connect(self._options_changed)
        method.addWidget(self.accurate)
        method.addStretch(1)
        self.cut_method = ChoiceBox([("sections", "Csak a szakasz letöltése (gyors)"),
                                     ("full", "Teljes letöltés, utána vágás (megbízható)")])
        self.cut_method.set_value(self.settings.cut_method)
        self.cut_method.setToolTip("Ha a gyors mód egy oldalon nem működik, a teljes videó letöltése után "
                                   "a program helyben vágja ki a részletet.")
        self.cut_method.currentIndexChanged.connect(self._options_changed)
        method.addWidget(self.cut_method)
        body.addLayout(method)
        self.trim_hint = label("", "caption", wrap=True)
        body.addWidget(self.trim_hint)
        card.body.addWidget(self.trim_body)
        self.trim_body.hide()
        return card

    def _build_action_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("actionBar")
        self.action_bar = bar
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(10)
        row.addWidget(IconLabel("folder", "muted", 18))
        col = QVBoxLayout()
        col.setSpacing(0)
        self.dest_label = label("", None)
        self.dest_label.setMinimumWidth(120)
        self.dest_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.summary_label = label("", "caption")
        self.summary_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        col.addWidget(self.dest_label)
        col.addWidget(self.summary_label)
        row.addLayout(col, 1)
        change = button("Módosítás", "ghost", tooltip="Mentési mappa kiválasztása")
        change.clicked.connect(self._choose_dest)
        row.addWidget(change)
        self.queue_button = button("Hozzáadás a sorhoz", None, "queue", "text",
                                   "A sor végére kerül, és sorra kerülve automatikusan indul")
        self.queue_button.clicked.connect(lambda: self._download(False))
        self.download_button = button("Letöltés most", "primary", "download",
                                      tooltip="Azonnal elindul, a sorban várakozókat megelőzve (Ctrl+Enter)",
                                      large=True)
        self.download_button.clicked.connect(lambda: self._download(True))
        row.addWidget(self.queue_button)
        row.addWidget(self.download_button)
        self._update_dest_label()
        return bar

    # ------------------------------------------------------------------ #
    # Oldalváltás, téma
    # ------------------------------------------------------------------ #
    def _show_page(self, page: str) -> None:
        single = page == "video"
        playlist = page == "playlist"
        self.stack.setCurrentIndex(0 if page == "empty" else 1)
        self.action_bar.setVisible(page != "empty")
        self.video_card.setVisible(single)
        self.playlist_card.setVisible(playlist)
        self.tracks_row.setVisible(single)
        self.pl_lang_card.setVisible(playlist)
        self.trim_card.setVisible(single)
        self._mode_changed(self.mode.value())

    def _theme_changed(self) -> None:
        self._url_icon_action.setIcon(icons.icon("link", theme.c("faint")))
        name = {"system": "auto-theme", "light": "sun", "dark": "moon"}[theme.manager.mode]
        set_icon(self.theme_button, name, "muted")
        self.theme_button.setToolTip({"system": "Téma: rendszer szerint", "light": "Téma: világos",
                                      "dark": "Téma: sötét"}[theme.manager.mode] + " (kattints a váltáshoz)")
        theme.set_dark_title_bar(self, theme.manager.dark)

    def _cycle_theme(self) -> None:
        order = ["system", "light", "dark"]
        mode = order[(order.index(theme.manager.mode) + 1) % 3]
        self.settings.theme = mode
        self.settings.save()
        theme.manager.apply(mode)

    # ------------------------------------------------------------------ #
    # Elemzés
    # ------------------------------------------------------------------ #
    def _paste(self) -> None:
        text = QGuiApplication.clipboard().text()
        url = normalize_url(text)
        if not url:
            self._set_status("error", "A vágólap üres, vagy nem tartalmaz linket.")
            return
        self.url_edit.setText(url)
        if self.settings.auto_analyze_paste:
            self._analyze()

    def _analyze_or_cancel(self) -> None:
        if self._cancel is not None:
            self._cancel.set()
            self._cancel = None
            self._token += 1
            self._busy(False)
            self._set_status("info", "Az elemzés megszakítva.")
            return
        self._analyze()

    def _analyze(self, url: str | None = None, allow_playlist: bool = True) -> None:
        raw = url or normalize_url(self.url_edit.text())
        if raw != self.url_edit.text():
            self.url_edit.setText(raw)
        try:
            url = validate_url(raw)
        except ValueError as exc:
            self._set_status("error", str(exc))
            self.url_edit.setFocus()
            return
        if self._cancel is not None:
            self._cancel.set()
        self.banner.hide()
        self._token += 1
        token = self._token
        cancel = threading.Event()
        self._cancel = cancel
        self._busy(True)
        self._set_status("busy", "Videó adatainak lekérése… (néhány másodperc)")
        cookies = self.settings.cookies_browser
        log(f"Elemzés indítása: {url}")

        def work():
            try:
                result = engine.analyze(url, cancel=cancel, allow_playlist=allow_playlist,
                                        cookies_browser=cookies, on_log=log)
                self._bridge.analysisDone.emit(token, (url, result))
            except engine.Cancelled:
                pass
            except engine.OperationError as exc:
                self._bridge.analysisFailed.emit(token, (url, exc.friendly, exc.details))
            except Exception as exc:  # noqa: BLE001
                self._bridge.analysisFailed.emit(token, (url, explain(str(exc)), repr(exc)))

        threading.Thread(target=work, name="analyze", daemon=True).start()

    def _busy(self, busy: bool) -> None:
        self.analyze_button.setText("Mégse" if busy else "Elemzés")
        set_icon(self.analyze_button, "close" if busy else "search", "accent_text")
        if not busy:
            self._cancel = None

    def _set_status(self, kind: str, text: str) -> None:
        self.status_label.setText(text)
        if kind == "busy":
            self.spinner.start()
            self.status_icon.hide()
        else:
            self.spinner.stop()
            spec = {"ok": ("check-circle", "success"), "error": ("error", "danger"),
                    "info": ("info", "muted")}.get(kind)
            if spec:
                self.status_icon.set_spec(*spec)
                self.status_icon.show()
            else:
                self.status_icon.hide()

    def _analysis_done(self, token: int, payload) -> None:
        if token != self._token:
            return
        self._busy(False)
        url, result = payload
        if isinstance(result, PlaylistInfo):
            self._show_playlist(result)
        else:
            self._show_video(result)

    def _analysis_failed(self, token: int, payload) -> None:
        if token != self._token:
            return
        self._busy(False)
        url, friendly, details = payload
        self._set_status("error", "Az elemzés nem sikerült.")
        actions = [("Újrapróbálás", lambda: self._analyze(url))]
        if details:
            actions.append(("Részletek", lambda: DetailsDialog(friendly.title, friendly.message, details,
                                                                  parent=self).exec()))
        if friendly.kind == "rate_limit":
            # A sorban várakozó letöltések se terheljék tovább a szolgáltatót.
            self.manager.start_cooldown()
            actions.append(("Böngészősütik…", self._show_settings))
        elif "frissítsd" in friendly.message:
            actions.append(("yt-dlp frissítése", self._show_tools))
        self.banner.show_message("warning" if friendly.kind == "rate_limit" else "error",
                                 friendly.title, friendly.message, actions)

    def _load_full_playlist(self) -> None:
        if self.info is None:
            return
        # A videó+lista linknél a teljes lista a "list" paraméterből tölthető be.
        from urllib.parse import parse_qs
        list_id = parse_qs(urlparse(self.info.url).query).get("list", [""])[0]
        if list_id and all(ch.isalnum() or ch in "-_" for ch in list_id):
            url = f"https://www.youtube.com/playlist?list={list_id}"
            self.url_edit.setText(url)
            self._analyze(url)

    # ------------------------------------------------------------------ #
    # Egyetlen videó
    # ------------------------------------------------------------------ #
    def _show_video(self, info: VideoInfo) -> None:
        self.info, self.playlist = info, None
        self._stop_preview()
        self.title_label.setText(info.title)
        meta = [m for m in (info.uploader, fmt_duration(info.duration) if info.duration else "",
                            _date(info.upload_date), _views(info.view_count),
                            info.extractor if not info.is_youtube else "") if m]
        self.meta_label.setText("  ·  ".join(meta))
        while self.chips.count():
            item = self.chips.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        chips = []
        if info.heights:
            chips.append(info.quality_label(info.heights[0]))
        if info.multi_language_audio:
            chips.append(f"{len(info.audio_tracks)} hangsáv")
        if info.subtitles:
            chips.append(f"{len(info.subtitles)} felirat")
        if info.chapters:
            chips.append(f"{len(info.chapters)} fejezet")
        for text in chips:
            self.chips.addWidget(label(text, "chip"))
        self.chips.addStretch(1)
        notices = []
        if info.is_live:
            notices.append("Élő közvetítés vagy közelgő premier: a letöltés a közvetítés végéig tarthat, vágás nem lehetséges.")
        self.notice.setText("\n".join(notices))
        self.notice.setVisible(bool(notices))
        self.thumb.badge = fmt_duration(info.duration) if info.duration else ""
        self.thumb.set_pixmap(None)
        self.thumb.placeholder = "Nincs előnézeti kép"
        playable = bool(info.preview_url) and _multimedia_available()
        self.thumb.set_playable(playable)
        self.preview_button.setVisible(playable)
        self._load_thumbnail(info.thumbnail)
        # minőség
        items = []
        best = info.quality_label(info.heights[0]) if info.heights else ""
        items.append(("best", f"Legjobb elérhető – {best}" if best else "Legjobb elérhető"))
        for h in info.heights:
            items.append((str(h), info.quality_label(h)))
        self.quality.set_items(items, keep=False)
        if self.settings.quality != "best":
            wanted = int(self.settings.quality)
            fitting = [h for h in info.heights if h <= wanted]
            if fitting:
                self.quality.set_value(str(fitting[0]))
        has_webm = any(f["vcodec"].lower().startswith(("vp9", "vp09", "av01", "vp8")) for f in info.formats)
        self.container.set_option_enabled("webm", has_webm or not info.formats,
                                          "" if has_webm else "Ennél a videónál nincs WebM-kompatibilis (VP9/AV1) videósáv.")
        if not has_webm and self.container.value() == "webm":
            self.container.set_value("mp4")
        # hangsávok
        preferred_audio = self.settings.preferred_audio_lang
        audio_items = []
        for t in info.audio_tracks:
            detail = AUDIO_KIND_LABELS.get(t.kind, "")
            if t.kind == "default":
                detail = "alapértelmezett hangsáv"
            if t.detail:
                detail += " · " + t.detail
            audio_items.append({"key": t.key, "text": t.name, "detail": detail, "kind": t.kind,
                                "star": bool(preferred_audio and t.language and base_code(t.language) == base_code(preferred_audio)),
                                "search": t.language + " " + (t.note or "")})
        self.audio_list.set_items(audio_items)
        multi = len(info.audio_tracks) > 1
        self.audio_list.setVisible(multi)
        self.audio_single.setText(
            "Ennek a videónak egy hangsávja van, ez kerül a letöltésbe." if info.audio_tracks
            else "A forrás nem ad külön hangsáv-információt; az alapértelmezett hang töltődik le.")
        self.audio_single.setVisible(not multi)
        self.audio_count.setText(f"{len(info.audio_tracks)}" if multi else "")
        self.audio_count.setVisible(multi)
        # feliratok
        subs = sort_subtitles(info.subtitles, self.settings.preferred_sub_langs)
        sub_items = []
        for s in subs:
            lang = s.language[:-5] if s.language.endswith("-orig") else s.language
            detail = SUB_KIND_LABELS.get(s.kind, s.kind)
            if s.kind == "auto" and s.language.endswith("-orig"):
                detail += " – eredeti beszéd"
            if s.kind == "translated" and s.source:
                detail += f" ({language_name(s.source).lower()} nyelvből)"
            detail += f" · {s.language}"
            sub_items.append({"key": s.key, "text": language_name(lang, s.name or s.language), "detail": detail,
                              "kind": s.kind, "star": matches_preference(lang, self.settings.preferred_sub_langs),
                              "search": f"{s.language} {s.name}"})
        self.sub_list.set_items(sub_items)
        self.sub_list.setVisible(bool(subs))
        self.subs_none.setVisible(not subs)
        self.sub_options.setVisible(bool(subs))
        self.subs_count.setText(str(len(subs)) if subs else "")
        self.subs_count.setVisible(bool(subs))
        tall = multi or bool(subs)
        for card in (self.audio_card, self.subs_card):
            if tall:
                card.setFixedHeight(380)
            else:
                card.setMinimumHeight(0)
                card.setMaximumHeight(16777215)
        self.mode.set_option_enabled("subtitles", bool(subs), "" if subs else "Ehhez a videóhoz nincs felirat.")
        if not subs and self.mode.value() == "subtitles":
            self.mode.set_value("video")
        # vágás
        can_trim = bool(info.duration) and not info.is_live
        self.trim_switch.setChecked(False)
        self.trim_switch.setEnabled(can_trim)
        self.trim_off_label.setText("A teljes videó letöltődik. Kapcsold be, ha csak egy szakaszra van szükséged."
                                    if can_trim else "Ennél a tartalomnál a vágás nem érhető el (ismeretlen hossz vagy élő adás).")
        self.range.set_duration(info.duration or 0, [c.start for c in info.chapters])
        self.start_edit.set_value(0)
        self.end_edit.set_value(info.duration)
        self.chapter_box.set_items([("", "Fejezet kiválasztása…")] + [
            (str(i), f"{fmt_time(c.start)}  {c.title}") for i, c in enumerate(info.chapters)], keep=False)
        self.chapter_box.setVisible(bool(info.chapters))
        self.load_list_button.setVisible(info.playlist_hint)
        self._set_status("ok", f"Elemzés kész: {info.title}")
        self._show_page("video")
        self.scroll.verticalScrollBar().setValue(0)
        self._options_changed()

    def _show_playlist(self, playlist: PlaylistInfo) -> None:
        self.playlist, self.info = playlist, None
        self._stop_preview()
        available = [e for e in playlist.entries if e.available]
        missing = len(playlist.entries) - len(available)
        self.pl_title.setText(playlist.title)
        meta = [playlist.uploader, f"{len(playlist.entries)} videó"]
        total = sum(e.duration or 0 for e in available)
        if total:
            meta.append("összesen " + fmt_duration(total))
        if missing:
            meta.append(f"{missing} nem elérhető (privát/törölt)")
        self.pl_meta.setText("  ·  ".join(m for m in meta if m))
        items = []
        for e in available:
            detail = " · ".join(x for x in (e.uploader, fmt_duration(e.duration) if e.duration else "") if x)
            items.append({"key": str(e.index) + "|" + e.url, "text": f"{e.index}. {e.title}",
                          "detail": detail or e.url, "search": e.video_id})
        self.pl_list.set_items(items)
        self.pl_list.select_visible()
        self.pl_subs.setChecked(False)
        self.mode.set_option_enabled("subtitles", True, "")
        self.quality.set_items([("best", "Legjobb elérhető")] + [
            (str(h), f"Legfeljebb {h}p") for h in (2160, 1440, 1080, 720, 480, 360)], keep=False)
        if self.settings.quality != "best":
            self.quality.set_value(self.settings.quality)
        self.container.set_option_enabled("webm", True)
        self.load_list_button.hide()
        self._set_status("ok", f"Lejátszási lista: {len(available)} letölthető videó")
        self._show_page("playlist")
        self.scroll.verticalScrollBar().setValue(0)
        self._options_changed()

    # ------------------------------------------------------------------ #
    # Beállítások változása, összegzés
    # ------------------------------------------------------------------ #
    def _mode_changed(self, mode: str) -> None:
        video, audio, subs = mode == "video", mode == "audio", mode == "subtitles"
        for w in self.video_widgets:
            w.setVisible(video)
        for w in self.audio_widgets:
            w.setVisible(audio)
        self.subs_mode_hint.setVisible(subs and self.playlist is None)
        self.advanced.setVisible(not subs)
        self.codec_label.setVisible(video)
        self.codec.setVisible(video)
        self.embed_chapters.setVisible(video)
        if self.info is not None:
            self.audio_card.setVisible(not subs)
        self.embed_subs.setVisible(video)
        self.trim_card.setVisible(self.info is not None and not subs)
        if self.playlist is not None and subs:
            self.pl_subs.setChecked(True)
        self._options_changed()

    def _options_changed(self, *_):
        mode = self.mode.value()
        selected_audio = len(self.audio_list.checked_keys()) if self.info else 0
        multi_audio = mode == "video" and selected_audio > 1
        for value in ("mp4", "webm"):
            enabled = not multi_audio
            if value == "webm" and self.info is not None and self.info.formats:
                enabled = enabled and any(f["vcodec"].lower().startswith(("vp9", "vp09", "av01", "vp8"))
                                          for f in self.info.formats)
            self.container.set_option_enabled(value, enabled,
                                              "Több hangsáv egy fájlban csak MKV-ban lehetséges." if multi_audio else "")
        if multi_audio and self.container.value() != "mkv":
            self.container.set_value("mkv")
        hint = VIDEO_FORMAT_HINTS.get(self.container.value(), "")
        if multi_audio:
            hint = "Több kijelölt hangsáv → MKV formátum (minden sáv nyelvi címkével kerül a fájlba)."
        self.container_hint.setText(hint)
        fmt = self.audio_format.value()
        self.audio_hint.setText(AUDIO_FORMAT_HINTS.get(fmt, ""))
        lossy = fmt in ("mp3", "m4a", "aac", "opus")
        self.audio_quality.setVisible(mode == "audio" and lossy)
        self.audio_quality_label.setVisible(mode == "audio" and lossy)
        self.embed_thumbnail.setEnabled(not (mode == "audio" and fmt == "wav") and
                                        not (mode == "video" and self.container.value() == "webm"))
        if self.info is not None:
            if mode == "audio" and selected_audio > 1:
                self.audio_note.setText("A kijelölt hangsávok külön fájlokba kerülnek.")
            elif mode == "video" and not selected_audio:
                self.audio_note.setText("Nincs kijelölés: az eredeti (alapértelmezett) hangsáv kerül a videóba.")
            elif mode == "audio" and not selected_audio:
                self.audio_note.setText("Nincs kijelölés: az eredeti (alapértelmezett) hangsáv töltődik le.")
            else:
                self.audio_note.setText("")
            self.audio_note.setVisible(bool(self.audio_note.text()) and len(self.info.audio_tracks) > 1)
            self.embed_subs.setEnabled(bool(self.sub_list.checked_keys()))
        self._update_trim_hint()
        self._update_summary()

    def _update_summary(self) -> None:
        self._update_dest_label()
        text = ""
        if self.info is not None:
            try:
                opts = self._single_options(validate=False)
                size = estimate_size(self.info, opts)
                parts = []
                if opts.mode == "subtitles":
                    parts.append(f"{len(opts.subtitles)} felirat")
                else:
                    parts.append(f"Becsült méret: ~{fmt_size(size)}" if size else "Méret: ismeretlen")
                    if opts.subtitles:
                        parts.append(f"+ {len(opts.subtitles)} felirat")
                if opts.is_clip:
                    span = (opts.end if opts.end is not None else self.info.duration or 0) - (opts.start or 0)
                    parts.append(f"részlet: {fmt_duration(span)}")
                text = "  ·  ".join(parts)
            except ValueError as exc:
                text = str(exc)
            self.download_button.setText("Letöltés most")
            self.queue_button.setText("Hozzáadás a sorhoz")
            self.download_button.setEnabled(True)
        elif self.playlist is not None:
            count = len(self.pl_list.checked_keys())
            total = sum(self._entry(k).duration or 0 for k in self.pl_list.checked_keys() if self._entry(k))
            text = f"{count} videó kijelölve" + (f" · összesen {fmt_duration(total)}" if total else "")
            self.download_button.setText(f"{count} videó letöltése" if count else "Letöltés most")
            self.queue_button.setText("Hozzáadás a sorhoz")
            self.download_button.setEnabled(count > 0)
            self.queue_button.setEnabled(count > 0)
        self.summary_label.setText(text)

    def _update_dest_label(self) -> None:
        path = self.settings.destination
        fm = self.dest_label.fontMetrics()
        width = max(120, self.dest_label.width() or 300)
        self.dest_label.setText(fm.elidedText(path, Qt.TextElideMode.ElideMiddle, width))
        self.dest_label.setToolTip(path)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        QTimer.singleShot(0, self._update_dest_label)

    def _choose_dest(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Mentési mappa kiválasztása", self.settings.destination)
        if folder:
            self.settings.destination = folder
            self.settings.save()
            self._update_dest_label()

    def _select_preferred_subs(self) -> None:
        if self.info is None:
            return
        keys = []
        for pref in self.settings.preferred_sub_langs:
            candidates = [s for s in self.info.subtitles if base_code(s.language) == base_code(pref)
                          and not s.language.endswith("-orig")]
            order = {"manual": 0, "auto": 1, "translated": 2}
            candidates.sort(key=lambda s: (order.get(s.kind, 3), len(s.language)))
            if candidates:
                keys.append(candidates[0].key)
        if keys:
            self.sub_list.set_checked(keys)
        else:
            self._set_status("info", "A preferált nyelveken nincs felirat. A nyelveket a Beállításokban adhatod meg.")

    # ------------------------------------------------------------------ #
    # Vágás
    # ------------------------------------------------------------------ #
    def _trim_toggled(self, on: bool) -> None:
        self.trim_body.setVisible(on)
        self.trim_off_label.setVisible(not on)
        self._options_changed()

    def _range_moved(self, start: float, end: float) -> None:
        self.start_edit.set_value(start)
        self.end_edit.set_value(end)
        if self.player is not None:
            self.player.seek(start if self.range._drag == "start" else end)
        self._options_changed()

    def _time_edited(self, _value) -> None:
        if self.info is None or not self.info.duration:
            return
        start = self.start_edit.value() or 0.0
        end = self.end_edit.value()
        end = self.info.duration if end is None else min(end, self.info.duration)
        if end - start < 0.5:
            self.trim_hint.setText("A végpontnak legalább fél másodperccel a kezdőpont után kell lennie.")
            return
        self.range.set_range(start, end)
        self.start_edit.set_value(start)
        self.end_edit.set_value(end)
        self._options_changed()

    def _chapter_selected(self, _index: int) -> None:
        value = self.chapter_box.value()
        if not value or self.info is None:
            return
        chapter = self.info.chapters[int(value)]
        self.trim_switch.setChecked(True)
        self.range.set_range(chapter.start, chapter.end)
        self.start_edit.set_value(chapter.start)
        self.end_edit.set_value(chapter.end)
        self._options_changed()

    def _clip_bounds(self) -> tuple[float | None, float | None]:
        if self.info is None or not self.trim_switch.isChecked() or not self.info.duration:
            return None, None
        start = self.start_edit.value() or 0.0
        end = self.end_edit.value()
        start_v = start if start > 0.05 else None
        end_v = end if end is not None and end < self.info.duration - 0.05 else None
        return start_v, end_v

    def _update_trim_hint(self) -> None:
        if self.info is None or not self.trim_switch.isChecked():
            return
        start, end = self._clip_bounds()
        span = (end if end is not None else self.info.duration) - (start or 0)
        self.clip_length.setText("Hossz: " + fmt_duration(span))
        if start is None and end is None:
            self.trim_hint.setText("A kijelölés a teljes videót lefedi – húzd a végpontokat, vagy írd be az időket.")
        elif self.cut_method.value() == "full":
            self.trim_hint.setText("A teljes videó letöltődik, majd a program helyben vágja ki a részletet. "
                                   "Lassabb, de minden oldalon működik.")
        elif self.accurate.isChecked():
            self.trim_hint.setText("Csak a kijelölt szakasz töltődik le; a pontos vágás miatt a részletet "
                                   "újrakódolja (hosszabb ideig tart, a minőség minimálisan változhat).")
        else:
            self.trim_hint.setText("Csak a kijelölt szakasz töltődik le, újrakódolás nélkül. A kép a legközelebbi "
                                   "kulcskockánál kezdődhet (néhány tized másodperc eltérés); a feliratokat a "
                                   "program ehhez igazítja.")

    # ------------------------------------------------------------------ #
    # Előnézet
    # ------------------------------------------------------------------ #
    def _start_preview(self) -> None:
        if self.info is None or not self.info.preview_url:
            return
        if self.player is None:
            try:
                from .player import PreviewPlayer
            except Exception as exc:  # noqa: BLE001 - a lejátszó opcionális
                log(f"Az előnézet nem elérhető: {exc}")
                self._open_in_browser()
                return
            self.player = PreviewPlayer()
            self.player.markIn.connect(self._mark_in)
            self.player.markOut.connect(self._mark_out)
            self.player.closed.connect(self._stop_preview)
            self.player.failed.connect(self._preview_failed)
            self.player.positionChanged.connect(self.range.set_position)
            self.media_stack.addWidget(self.player)
        self.media_stack.setFixedHeight(self.media_stack.width() * 9 // 16 + 92)
        self.media_stack.setCurrentWidget(self.player)
        start = self._clip_bounds()[0] or 0.0
        self.player.load(self.info.preview_url, start)
        log("Előnézet indítása (alacsony felbontású változat).")

    def _stop_preview(self) -> None:
        if self.player is not None:
            self.player.player.stop()
        self.media_stack.setCurrentWidget(self.thumb)
        self.media_stack.setFixedHeight(self.media_stack.width() * 9 // 16)
        self.range.set_position(None)

    def _preview_failed(self, message: str) -> None:
        log("Előnézeti hiba: " + message)
        self._stop_preview()
        self.banner.show_message("warning", "Az előnézet nem játszható le",
                                 "A videó a böngészőben megtekinthető; a letöltést ez nem befolyásolja.",
                                 [("Megnyitás böngészőben", self._open_in_browser)])

    def _mark_in(self, seconds: float) -> None:
        self.trim_switch.setChecked(True)
        end = self.end_edit.value() or (self.info.duration if self.info else seconds + 1)
        if end - seconds < 0.5:
            end = self.info.duration if self.info else seconds + 1
        self.range.set_range(seconds, end)
        self.start_edit.set_value(seconds)
        self.end_edit.set_value(end)
        self._options_changed()

    def _mark_out(self, seconds: float) -> None:
        self.trim_switch.setChecked(True)
        start = self.start_edit.value() or 0.0
        if seconds - start < 0.5:
            start = 0.0
        self.range.set_range(start, seconds)
        self.start_edit.set_value(start)
        self.end_edit.set_value(seconds)
        self._options_changed()

    def _open_in_browser(self) -> None:
        url = (self.info.webpage_url or self.info.url) if self.info else self.url_edit.text()
        try:
            url = validate_url(url)
        except ValueError:
            return
        start = self._clip_bounds()[0]
        if start and self.info and self.info.is_youtube:
            url += ("&" if "?" in url else "?") + f"t={int(start)}s"
        webbrowser.open(url)

    def _load_thumbnail(self, url: str, retry: bool = True) -> None:
        if self._thumb_reply is not None:
            self._thumb_reply.abort()
            self._thumb_reply = None
        if not url or not _safe_image_url(url):
            return
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, f"YTDLPStudio/{__version__}")
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        request.setTransferTimeout(15000)
        reply = self._net.get(request)
        self._thumb_reply = reply
        info = self.info

        def finished():
            if self._thumb_reply is reply:
                self._thumb_reply = None
            data = reply.read(8_000_000) if reply.error() == QNetworkReply.NetworkError.NoError else b""
            reply.deleteLater()
            if self.info is not info:
                return
            pixmap = QPixmap()
            if data and pixmap.loadFromData(QByteArray(data)):
                self.thumb.set_pixmap(pixmap)
            elif retry and "vi_webp" in url:
                self._load_thumbnail(url.replace("/vi_webp/", "/vi/").replace(".webp", ".jpg"), False)

        reply.finished.connect(finished)

    # ------------------------------------------------------------------ #
    # Letöltés
    # ------------------------------------------------------------------ #
    def _single_options(self, validate: bool = True) -> DownloadOptions:
        info = self.info
        assert info is not None
        mode = self.mode.value()
        tracks = {t.key: t for t in info.audio_tracks}
        selected = [tracks[k] for k in self.audio_list.checked_keys() if k in tracks] if mode != "subtitles" else []
        if len(info.audio_tracks) <= 1:
            selected = []
        subs_by_key = {s.key: s for s in info.subtitles}
        subs = [subs_by_key[k] for k in self.sub_list.checked_keys() if k in subs_by_key]
        start, end = self._clip_bounds()
        s = self.settings
        opts = DownloadOptions(
            url=info.webpage_url if info.webpage_url.startswith("http") else info.url,
            dest=s.destination, mode=mode, container=self.container.value() or "mp4",
            quality=self.quality.value() or "best", video_codec=self.codec.value() or "auto",
            audio_format=self.audio_format.value() or "mp3", audio_quality=self.audio_quality.value() or "best",
            audio_selectors=[t.selector for t in selected], audio_languages=[t.language for t in selected],
            subtitles=subs, subtitle_format=self.sub_format.value() or "srt",
            embed_subtitles=self.embed_subs.isChecked() and mode == "video",
            embed_metadata=self.embed_metadata.isChecked(), embed_thumbnail=self.embed_thumbnail.isChecked()
            and self.embed_thumbnail.isEnabled(), embed_chapters=self.embed_chapters.isChecked(),
            start=start, end=end, accurate_cut=self.accurate.isChecked(),
            cut_method=self.cut_method.value() or "sections", title=info.title, duration=info.duration,
            rate_limit=s.rate_limit, cookies_browser=s.cookies_browser,
            info_json=engine.reusable_info_json(info))
        if validate:
            opts.validate()
        return opts

    def _entry(self, key: str):
        if self.playlist is None:
            return None
        index, _, url = key.partition("|")
        return next((e for e in self.playlist.entries if str(e.index) == index and e.url == url), None)

    def _playlist_options(self) -> list[tuple[DownloadOptions, str]]:
        assert self.playlist is not None
        import re
        s = self.settings
        langs = [p.strip() for p in re.split(r"[,; ]+", self.pl_sub_langs.text()) if p.strip()]
        want_subs = self.pl_subs.isChecked() or self.mode.value() == "subtitles"
        if want_subs and not langs:
            raise ValueError("Add meg a letöltendő feliratok nyelvét (pl. hu, en).")
        dest = Path(s.destination)
        if self.pl_subfolder.isChecked():
            dest = dest / safe_component(self.playlist.title)
        width = max(2, len(str(len(self.playlist.entries))))
        result = []
        for key in self.pl_list.checked_keys():
            entry = self._entry(key)
            if entry is None:
                continue
            opts = DownloadOptions(
                url=entry.url, dest=str(dest), mode=self.mode.value(), container=self.container.value() or "mp4",
                quality=self.quality.value() or "best", video_codec=self.codec.value() or "auto",
                audio_format=self.audio_format.value() or "mp3", audio_quality=self.audio_quality.value() or "best",
                preferred_audio_lang=self.pl_audio_lang.value(), sub_langs=langs if want_subs else [],
                subtitle_format=self.sub_format.value() or "srt",
                embed_metadata=self.embed_metadata.isChecked(), embed_thumbnail=self.embed_thumbnail.isChecked(),
                embed_chapters=self.embed_chapters.isChecked(),
                filename_prefix=f"{entry.index:0{width}d} - " if self.pl_numbering.isChecked() else "",
                title=entry.title, duration=entry.duration, rate_limit=s.rate_limit,
                cookies_browser=s.cookies_browser, polite=True)
            opts.validate()
            result.append((opts, entry.title))
        return result

    def _download(self, now: bool) -> None:
        if self.stack.currentIndex() == 0:
            return
        try:
            if self.info is not None:
                opts = self._single_options()
                self.manager.add(opts, self.info.title, immediate=now)
                self._remember(opts)
                where = "elindult" if now else "a sorba került"
                self._set_status("ok", f"A letöltés {where}: {self.info.title}")
            elif self.playlist is not None:
                jobs = self._playlist_options()
                if not jobs:
                    raise ValueError("Jelölj ki legalább egy videót a listából.")
                if now and self.manager.paused:
                    self.queue.pause.setChecked(False)
                for opts, title in jobs:
                    self.manager.add(opts, title)
                self._remember(jobs[0][0])
                self._set_status("ok", f"{len(jobs)} videó a letöltési sorba került.")
        except ValueError as exc:
            self.banner.show_message("warning", "Ellenőrizd a beállításokat", str(exc))
            return
        self.banner.hide()

    def _remember(self, opts: DownloadOptions) -> None:
        s = self.settings
        s.mode = opts.mode
        if not (opts.mode == "video" and len(opts.audio_selectors) > 1):
            s.container = opts.container
        s.quality = opts.quality
        s.video_codec = opts.video_codec
        s.audio_format = opts.audio_format
        s.audio_quality = opts.audio_quality
        s.subtitle_format = opts.subtitle_format
        s.embed_subtitles = self.embed_subs.isChecked()
        s.embed_metadata = opts.embed_metadata
        s.embed_thumbnail = self.embed_thumbnail.isChecked()
        s.embed_chapters = opts.embed_chapters
        s.accurate_cut = self.accurate.isChecked()
        s.cut_method = self.cut_method.value() or "sections"
        if s.remember_languages:
            langs = []
            for sub in opts.subtitles:
                code = base_code(sub.language)
                if code not in langs:
                    langs.append(code)
            if langs:
                s.preferred_sub_langs = (langs + [l for l in s.preferred_sub_langs if l not in langs])[:6]
            if len(opts.audio_languages) == 1 and opts.audio_languages[0]:
                s.preferred_audio_lang = base_code(opts.audio_languages[0])
        s.save()

    def _job_finished(self, job: Job) -> None:
        if job.status == "done":
            QApplication.alert(self)
            if self.settings.open_folder_when_done and job.files:
                self._reveal(job.files[0])

    def _job_action(self, action: str, job: Job) -> None:
        if action == "cancel":
            self.manager.cancel(job)
        elif action == "retry":
            self.manager.retry(job)
        elif action == "remove":
            if job.status == "running" and QMessageBox.question(
                    self, "Letöltés", "Megszakítod a folyamatban lévő letöltést?") != QMessageBox.StandardButton.Yes:
                return
            self.manager.remove(job)
        elif action == "open":
            target = next((f for f in job.files if f.exists()), None)
            if target:
                open_path(target)
            else:
                QMessageBox.information(self, "Megnyitás", "A fájl már nem található (áthelyezték vagy törölték).")
        elif action == "folder":
            target = next((f for f in job.files if f.exists()), None)
            if target:
                self._reveal(target)
            else:
                folder = Path(job.options.dest)
                if folder.is_dir():
                    open_path(folder)
        elif action == "details":
            friendly = job.error or FriendlyError("Figyelmeztetések", "")
            DetailsDialog(friendly.title, friendly.message, job.details, job.warnings, self,
                          retry=(lambda: self.manager.retry(job)) if job.status == "error" else None).exec()
        elif action == "copy":
            QGuiApplication.clipboard().setText(job.options.url)
        elif action == "browser":
            webbrowser.open(validate_url(job.options.url))

    @staticmethod
    def _reveal(path: Path) -> None:
        if sys.platform == "win32" and path.exists():
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            open_path(path.parent)

    # ------------------------------------------------------------------ #
    # Párbeszédablakok, ablakkezelés
    # ------------------------------------------------------------------ #
    def _show_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            theme.manager.apply(self.settings.theme)
            self.manager.max_parallel = self.settings.max_parallel
            self.manager.schedule()
            self.pl_sub_langs.setText(", ".join(self.settings.preferred_sub_langs))
            self.pl_audio_lang.set_value(self.settings.preferred_audio_lang)
            self._update_summary()

    def _show_tools(self) -> None:
        ToolsDialog(self.settings, self._can_update, self).exec()

    def _can_update(self) -> bool:
        return not self.manager.running() and self._cancel is None

    def _show_log(self) -> None:
        if self.log_window is None:
            self.log_window = LogWindow(self)
        self.log_window.show()
        self.log_window.raise_()
        self.log_window.activateWindow()

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        data = event.mimeData()
        text = data.urls()[0].toString() if data.hasUrls() else data.text()
        url = normalize_url(text)
        if url:
            self.url_edit.setText(url)
            self._analyze()

    def _restore_geometry(self) -> None:
        geometry = self.settings.window_geometry
        if geometry:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geometry.encode()))
            except Exception:  # noqa: BLE001
                pass
        else:
            self.resize(1320, 880)
        if self.settings.splitter_state:
            self.splitter.restoreState(QByteArray.fromBase64(self.settings.splitter_state.encode()))

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.manager.running():
            answer = QMessageBox.question(self, "Kilépés", "Letöltés van folyamatban. Megszakítod és kilépsz?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        if self._cancel is not None:
            self._cancel.set()
        if self.player is not None:
            self.player.player.stop()
        self.settings.window_geometry = bytes(self.saveGeometry().toBase64()).decode()
        self.settings.splitter_state = bytes(self.splitter.saveState().toBase64()).decode()
        self.settings.save()
        self.manager.shutdown()
        event.accept()


def _date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y%m%d").strftime("%Y. %m. %d.")
    except (ValueError, TypeError):
        return ""


def _views(count: int | None) -> str:
    if not count:
        return ""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f} M megtekintés".replace(".", ",")
    if count >= 1000:
        return f"{count / 1000:.0f} E megtekintés"
    return f"{count} megtekintés"


def _safe_image_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname
    if host == "localhost" or host.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(host)
        return address.is_global
    except ValueError:
        return True


_MM: bool | None = None


def _multimedia_available() -> bool:
    global _MM
    if _MM is None:
        try:
            from PySide6 import QtMultimedia, QtMultimediaWidgets  # noqa: F401
            _MM = True
        except Exception:  # noqa: BLE001
            _MM = False
    return _MM


_ICON = None


def app_icon():
    global _ICON
    if _ICON is None:
        from PySide6.QtGui import QIcon
        icon = QIcon()
        for name in ("icon.ico", "icon.png"):
            path = resource(name)
            if path.exists():
                icon = QIcon(str(path))
                break
        _ICON = icon
    return _ICON
