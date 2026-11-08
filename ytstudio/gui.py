"""Hungarian-language Tk/ttk UI. All lengthy operations run off the UI thread."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import unicodedata
import webbrowser
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import os
import re
import subprocess
import sys
import threading
import tkinter as tk

from . import __version__
from .core import DownloadOptions, VideoInfo, fmt_time, parse_time
from .engine import Cancelled, Engine, Job
from .settings import Settings, app_dir, find_exe
from .updater import Release, fetch_latest, install_release

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

COLORS = {
    "dark": {"bg": "#111827", "panel": "#1f2937", "field": "#273449",
             "fg": "#f3f4f6", "muted": "#b7c2d1", "accent": "#38bdf8",
             "active": "#075985", "border": "#39465a"},
    "light": {"bg": "#eef2f6", "panel": "#ffffff", "field": "#f8fafc",
              "fg": "#162331", "muted": "#4b6073", "accent": "#0369a1",
              "active": "#bae6fd", "border": "#cbd5e1"},
}


def _fold(text: str) -> str:
    """Accent-insensitive filtering for Hungarian and international names."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(c))


class CheckableList(ttk.Frame):
    """Scrollable native checkboxes with independent multi-selection and search.

    Selection is keyed by track ID / (language, subtitle kind), not by the
    currently visible row number; filtering cannot silently change the choice.
    """

    def __init__(self, master, *, colors: dict[str, str], hint: str = ""):
        super().__init__(master, style="Panel.TFrame")
        self.colors = colors
        self.items: list[tuple[str, str]] = []
        self.vars: dict[str, tk.BooleanVar] = {}
        self.search = tk.StringVar()
        self.search.trace_add("write", self._search_changed)
        top = ttk.Frame(self, style="Panel.TFrame")
        top.pack(fill="x", pady=(0, 4))
        ttk.Label(top, text="Szűrés:", style="Muted.TLabel").pack(side="left", padx=(0, 4))
        ttk.Entry(top, textvariable=self.search, width=12).pack(side="left", fill="x", expand=True)
        row = ttk.Frame(self, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Button(row, text="Láthatók mind", command=self.select_visible).pack(side="left")
        ttk.Button(row, text="Kijelölés törlése", command=self.clear_selection).pack(side="left", padx=4)
        self.counter = tk.StringVar(value="0 kijelölve")
        ttk.Label(self, textvariable=self.counter, style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
        viewport = ttk.Frame(self, style="Panel.TFrame")
        viewport.pack(fill="both", expand=True, pady=(4, 0))
        self.canvas = tk.Canvas(viewport, background=colors["field"], borderwidth=0,
                                highlightthickness=0, width=120, height=132)
        self.scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=colors["field"])
        self._window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._resize_inner)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.inner.bind("<MouseWheel>", self._on_wheel)
        self.hint = hint
        self._render()

    def _resize_inner(self, event):
        self.canvas.itemconfigure(self._window_id, width=event.width)
        # Preserve complete labels even in the narrower two-column layout.
        for widget in self.inner.winfo_children():
            if isinstance(widget, tk.Checkbutton):
                widget.configure(wraplength=max(120, event.width - 36))

    def _on_wheel(self, event):
        if event.delta:
            units = max(1, round(abs(event.delta) / 120))
            self.canvas.yview_scroll(-units if event.delta > 0 else units, "units")
        return "break"

    def contains(self, widget):
        while widget is not None:
            if widget is self:
                return True
            widget = widget.master
        return False

    def set_items(self, items: list[tuple[str, str]]):
        # Stable unique keys; a new video's selections must start clear.
        if len(items) != len({key for key, _label in items}):
            raise ValueError("Duplicate checkbox keys")
        self.items = list(items)
        self.vars = {key: tk.BooleanVar(value=False) for key, _ in items}
        self.search.set("")
        self._render()

    def _filtered_items(self):
        query = _fold(self.search.get().strip())
        return [(key, label) for key, label in self.items if not query or query in _fold(label)]

    def _search_changed(self, *_):
        self._render()

    def _render(self):
        for widget in self.inner.winfo_children():
            widget.destroy()
        visible = self._filtered_items()
        if not visible:
            text = "Nincs találat." if self.items else (self.hint or "Nincs elérhető elem.")
            tk.Label(self.inner, text=text, bg=self.colors["field"], fg=self.colors["muted"],
                     font=("Segoe UI", 9), anchor="w", justify="left",
                     wraplength=230).pack(fill="x", padx=7, pady=7)
        for key, label in visible:
            # Native checkbox. Each click changes exactly one persistent ID.
            widget = tk.Checkbutton(self.inner, text=label, variable=self.vars[key],
                                    bg=self.colors["field"], fg=self.colors["fg"],
                                    activebackground=self.colors["field"],
                                    activeforeground=self.colors["fg"],
                                    selectcolor=self.colors["panel"],
                                    font=("Segoe UI", 9), anchor="w", justify="left",
                                    borderwidth=0, highlightthickness=0,
                                    wraplength=max(120, self.canvas.winfo_width() - 36),
                                    command=self._update_counter)
            widget.pack(fill="x", padx=5, pady=1)
            widget.bind("<MouseWheel>", self._on_wheel)
        self.canvas.yview_moveto(0)
        self._update_counter()

    def _update_counter(self):
        self.counter.set(f"{sum(var.get() for var in self.vars.values())} / {len(self.items)} kijelölve")

    def select_visible(self):
        for key, _ in self._filtered_items():
            self.vars[key].set(True)
        self._update_counter()

    def clear_selection(self):
        for var in self.vars.values():
            var.set(False)
        self._update_counter()

    def selected_keys(self) -> list[str]:
        return [key for key, _ in self.items if self.vars[key].get()]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.settings = Settings.load()
        self.engine = Engine()
        self.ui_events: Queue[tuple] = Queue()
        self.jobs: list[Job] = []
        self.pending: list[Job] = []
        self.jobs_lock = threading.Lock()
        self.worker_running = False
        self.active_job: Job | None = None
        self.info: VideoInfo | None = None
        self.latest_release: Release | None = None
        self._thumb_ref = None
        self._thumb_pil = None
        self._preview_refresh_after = None
        self._busy_analysis = False
        self._updating = False
        self.title(f"YTDLP Studio {__version__} — portable videóletöltő")
        self.geometry("1200x900")
        self.minsize(980, 740)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._make_variables()
        self._style()
        self._build()
        self.after(130, self._consume_events)
        self.after(250, self._check_dependencies)

    def _make_variables(self):
        s = self.settings
        self.url = tk.StringVar()
        self.destination = tk.StringVar(value=s.destination)
        self.mode = tk.StringVar(value="Videó")
        self.quality = tk.StringVar(value=s.quality)
        self.container = tk.StringVar(value=s.container)
        self.audio_format = tk.StringVar(value=s.audio_format)
        self.subtitle_format = tk.StringVar(value=s.subtitles_format)
        self.embed = tk.BooleanVar(value=False)
        self.playlist = tk.BooleanVar(value=False)
        self.accurate = tk.BooleanVar(value=False)
        self.clip_start = tk.StringVar()
        self.clip_end = tk.StringVar()
        self.status = tk.StringVar(value="Készen áll.")
        self.progress = tk.DoubleVar(value=0)
        self.theme = tk.StringVar(value=s.theme)
        self.video_title = tk.StringVar(value="Még nincs elemzett videó")
        self.video_summary = tk.StringVar(value="Illessz be egy linket, majd kattints az Elemzés gombra.")

    def _style(self):
        c = COLORS.get(self.theme.get(), COLORS["dark"])
        self.configure(bg=c["bg"])
        style = ttk.Style(self)
        style.theme_use("clam")
        for name, kwargs in {
            "TFrame": {"background": c["bg"]},
            "Panel.TFrame": {"background": c["panel"]},
            "TLabel": {"background": c["bg"], "foreground": c["fg"], "font": ("Segoe UI", 10)},
            "Panel.TLabel": {"background": c["panel"], "foreground": c["fg"], "font": ("Segoe UI", 10)},
            "Muted.TLabel": {"background": c["panel"], "foreground": c["muted"], "font": ("Segoe UI", 9)},
            "Title.TLabel": {"background": c["bg"], "foreground": c["fg"], "font": ("Segoe UI", 19, "bold")},
            "Video.TLabel": {"background": c["panel"], "foreground": c["fg"], "font": ("Segoe UI", 12, "bold")},
            "TLabelframe": {"background": c["panel"], "foreground": c["fg"], "bordercolor": c["border"]},
            "TLabelframe.Label": {"background": c["panel"], "foreground": c["fg"], "font": ("Segoe UI", 10, "bold")},
            "TButton": {"font": ("Segoe UI", 10), "padding": (10, 6)},
            "Accent.TButton": {"font": ("Segoe UI", 10, "bold"), "padding": (10, 7),
                               "background": c["accent"], "foreground": c["bg"]},
            "TEntry": {"fieldbackground": c["field"], "foreground": c["fg"], "insertcolor": c["fg"], "padding": 6},
            "TMenubutton": {"background": c["field"], "foreground": c["fg"], "padding": (8, 6), "relief": "raised"},
            "TCheckbutton": {"background": c["panel"], "foreground": c["fg"], "font": ("Segoe UI", 9)},
            "Horizontal.TProgressbar": {"background": c["accent"], "troughcolor": c["field"]},
            "Treeview": {"background": c["field"], "fieldbackground": c["field"], "foreground": c["fg"],
                         "rowheight": 24, "font": ("Segoe UI", 9)},
            "Treeview.Heading": {"background": c["panel"], "foreground": c["fg"], "font": ("Segoe UI", 9, "bold")},
        }.items():
            style.configure(name, **kwargs)
        style.map("Accent.TButton", background=[("active", c["active"])])
        style.map("TMenubutton", background=[("active", c["active"])], foreground=[("disabled", c["muted"])])
        style.map("Treeview", background=[("selected", c["active"])], foreground=[("selected", c["fg"])])
        self.option_add("*Menu.font", "{Segoe UI} 10")
        self._colors = c

    def _panel(self, parent, title=None):
        if title:
            return ttk.LabelFrame(parent, text=title, padding=10)
        return ttk.Frame(parent, style="Panel.TFrame", padding=10)

    def _build(self):
        # Scrolling keeps every control reachable on 768p laptops.
        base = ttk.Frame(self)
        base.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(base, bg=self._colors["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(base, orient="vertical", command=self.canvas.yview)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.outer = ttk.Frame(self.canvas, padding=16)
        canvas_item = self.canvas.create_window((0, 0), window=self.outer, anchor="nw")
        self.outer.bind("<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(canvas_item, width=event.width))
        self.bind_all("<MouseWheel>", self._mousewheel)
        head = ttk.Frame(self.outer)
        head.pack(fill="x", pady=(0, 10))
        ttk.Label(head, text="YTDLP Studio", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text=f"v{__version__}  •  Windows portable", foreground=self._colors["muted"]).pack(side="left", padx=13)
        ttk.Button(head, text="Eszközök / Frissítés", command=self._update_dialog).pack(side="right", padx=4)
        ttk.Button(head, text="Téma váltása", command=self._toggle_theme).pack(side="right", padx=4)

        url_panel = self._panel(self.outer)
        url_panel.pack(fill="x", pady=(0, 8))
        ttk.Label(url_panel, text="Videó vagy lejátszási lista URL", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        entry = ttk.Entry(url_panel, textvariable=self.url)
        entry.grid(row=1, column=0, sticky="ew", padx=(0, 7), pady=4)
        entry.bind("<Return>", lambda _: self._analyze())
        ttk.Button(url_panel, text="Beillesztés", command=self._paste).grid(row=1, column=1, padx=3)
        self.analyze_button = ttk.Button(url_panel, text="Elemzés", command=self._analyze, style="Accent.TButton")
        self.analyze_button.grid(row=1, column=2, padx=3)
        url_panel.columnconfigure(0, weight=1)

        details = self._panel(self.outer)
        details.pack(fill="x", pady=(0, 8))
        ttk.Label(details, textvariable=self.video_title, style="Video.TLabel", wraplength=900).pack(anchor="w")
        ttk.Label(details, textvariable=self.video_summary, style="Muted.TLabel", wraplength=900).pack(anchor="w", pady=(3, 0))

        workspace = ttk.Frame(self.outer)
        workspace.pack(fill="both", expand=True)
        workspace.columnconfigure(0, weight=1, uniform="workspace")
        workspace.columnconfigure(1, weight=1, uniform="workspace")
        workspace.rowconfigure(0, weight=1)
        left = ttk.Frame(workspace)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        right = ttk.Frame(workspace)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        opts = self._panel(left, "Formátum és minőség")
        opts.pack(fill="x", pady=(0, 8))
        self.mode_cb = self._form_row(opts, 0, "Letöltés típusa", self.mode, ["Videó", "Csak hang", "Csak felirat"])
        self.quality_cb = self._form_row(opts, 1, "Videóminőség", self.quality, ["Legjobb", "2160p", "1440p", "1080p", "720p", "480p", "360p"])
        self.container_cb = self._form_row(opts, 2, "Videóformátum", self.container, ["mp4", "mkv", "webm"])
        self.audio_format_cb = self._form_row(opts, 3, "Hangformátum", self.audio_format, ["mp3", "m4a", "aac", "opus", "flac", "wav"])
        self.subtitle_format_cb = self._form_row(opts, 4, "Feliratformátum", self.subtitle_format, ["srt", "vtt"])
        ttk.Checkbutton(opts, text="Feliratok beágyazása (MP4/MKV)", variable=self.embed).grid(row=5, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Checkbutton(opts, text="Teljes lejátszási lista letöltése", variable=self.playlist).grid(row=6, column=0, columnspan=2, sticky="w", pady=4)
        opts.columnconfigure(1, weight=1)

        clip = self._panel(left, "Időbeli vágás (opcionális)")
        clip.pack(fill="x", pady=(0, 8))
        ttk.Label(clip, text="Kezdőpont", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(clip, text="Végpont", style="Panel.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Entry(clip, textvariable=self.clip_start, width=16).grid(row=1, column=0, sticky="ew", padx=(0, 5), pady=4)
        ttk.Entry(clip, textvariable=self.clip_end, width=16).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Checkbutton(clip, text="Pontos vágás (lassabb, újrakódolhat)", variable=self.accurate).grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Label(clip, text="Példa: 00:15:30 – 01:42:00", style="Muted.TLabel").grid(row=3, column=0, columnspan=2, sticky="w", pady=(3, 0))
        clip.columnconfigure(0, weight=1)
        clip.columnconfigure(1, weight=1)

        # Audio and subtitles share the same horizontal space previously used
        # by a single list. The freed vertical space becomes the large preview.
        track_row = ttk.Frame(right, style="Panel.TFrame", height=250)
        track_row.pack(fill="x", pady=(0, 8))
        track_row.pack_propagate(False)
        track_row.columnconfigure(0, weight=1, uniform="tracks")
        track_row.columnconfigure(1, weight=1, uniform="tracks")
        track_row.rowconfigure(0, weight=1)

        audio_box = self._panel(track_row, "Hangsávok")
        audio_box.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self.audio_list = CheckableList(audio_box, colors=self._colors,
                                        hint="Nincs külön választható hangsáv.\nAlapértelmezett hang használata.")
        self.audio_list.pack(fill="both", expand=True)
        sub_box = self._panel(track_row, "Feliratok")
        sub_box.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        self.sub_list = CheckableList(sub_box, colors=self._colors, hint="Nincs felirat az elemzett videóhoz.")
        self.sub_list.pack(fill="both", expand=True)

        preview = self._panel(right, "Videó előnézete — borítókép")
        preview.pack(fill="both", expand=True)
        self.preview_area = ttk.Frame(preview, style="Panel.TFrame", height=175)
        self.preview_area.pack(fill="both", expand=True)
        self.preview_area.pack_propagate(False)
        self.thumbnail = ttk.Label(self.preview_area, text="▶\nElemzés után itt jelenik meg\na videó nagy előnézeti képe.",
                                   style="Video.TLabel", anchor="center", justify="center")
        self.thumbnail.pack(fill="both", expand=True)
        self.preview_area.bind("<Configure>", self._preview_resize)
        self.open_video = ttk.Button(preview, text="Videó megnyitása böngészőben",
                                     command=self._open_video, state="disabled")
        self.open_video.pack(anchor="e", pady=(7, 0))

        output = self._panel(self.outer)
        output.pack(fill="x", pady=(8, 8))
        ttk.Label(output, text="Mentési mappa:", style="Panel.TLabel").pack(side="left", padx=(0, 8))
        ttk.Entry(output, textvariable=self.destination).pack(side="left", fill="x", expand=True)
        ttk.Button(output, text="Tallózás", command=self._choose_dest).pack(side="left", padx=5)
        ttk.Button(output, text="Mappa megnyitása", command=self._open_dest).pack(side="left")

        tasks = self._panel(self.outer, "Letöltési sor")
        tasks.pack(fill="both", expand=True)
        bar = ttk.Frame(tasks, style="Panel.TFrame")
        bar.pack(fill="x")
        ttk.Button(bar, text="Hozzáadás a sorhoz", command=self._enqueue, style="Accent.TButton").pack(side="left", padx=(0, 6))
        ttk.Button(bar, text="Kijelölt várakozó törlése", command=self._remove_job).pack(side="left", padx=4)
        ttk.Button(bar, text="Aktuális megszakítása", command=self._cancel).pack(side="right")
        self.tree = ttk.Treeview(tasks, columns=("num", "title", "state"), show="headings", height=4)
        self.tree.heading("num", text="#")
        self.tree.heading("title", text="Videó")
        self.tree.heading("state", text="Állapot")
        self.tree.column("num", width=40, anchor="center", stretch=False)
        self.tree.column("state", width=140, anchor="w", stretch=False)
        self.tree.column("title", stretch=True)
        self.tree.pack(fill="both", expand=True, pady=7)
        ttk.Progressbar(tasks, variable=self.progress, maximum=100).pack(fill="x")
        ttk.Label(tasks, textvariable=self.status, style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
        logbox = self._panel(self.outer, "Részletes napló")
        logbox.pack(fill="both", expand=True, pady=(8, 0))
        self.log = tk.Text(logbox, height=5, bg=self._colors["field"], fg=self._colors["fg"],
                           selectbackground=self._colors["active"], relief="flat", wrap="word",
                           font=("Consolas", 9), state="disabled")
        self.log.pack(fill="both", expand=True)
        self._log("Az alkalmazás készen áll. Tölts le csak olyan tartalmat, amelyhez jogod van.")

    def _mousewheel(self, event):
        widget = self.winfo_containing(event.x_root, event.y_root)
        # Local wheel scrolling must not also scroll the whole window.
        if (widget is None or isinstance(widget, (tk.Text, ttk.Treeview))
                or self.audio_list.contains(widget) or self.sub_list.contains(widget)):
            return
        if event.delta:
            self.canvas.yview_scroll(-int(event.delta / 120), "units")

    def _form_row(self, parent, row, label, variable, choices):
        ttk.Label(parent, text=label + ":", style="Panel.TLabel").grid(
            row=row, column=0, sticky="w", pady=3, padx=(0, 7))
        # Native menus work reliably on Windows even when ttk.Combobox popup
        # fails to display with the Clam theme / high-DPI configurations.
        choices = list(choices)
        current = variable.get() if variable.get() in choices else choices[0]
        widget = ttk.OptionMenu(parent, variable, current, *choices)
        widget.grid(row=row, column=1, sticky="ew", pady=3)
        return widget

    def _preview_resize(self, _event=None):
        if self._preview_refresh_after is not None:
            self.after_cancel(self._preview_refresh_after)
        self._preview_refresh_after = self.after(80, self._render_preview)

    def _render_preview(self):
        self._preview_refresh_after = None
        if self._thumb_pil is None or ImageTk is None:
            return
        width = max(1, self.preview_area.winfo_width() - 10)
        height = max(1, self.preview_area.winfo_height() - 10)
        if width < 30 or height < 30:
            return
        picture = self._thumb_pil.copy()
        picture.thumbnail((width, height), Image.Resampling.LANCZOS)
        self._thumb_ref = ImageTk.PhotoImage(picture)
        self.thumbnail.configure(image=self._thumb_ref, text="")

    def _open_video(self):
        if self.info is not None:
            from .core import validate_url
            try:
                webbrowser.open(validate_url(self.info.url))
            except Exception as exc:
                messagebox.showerror("Hiba", str(exc))

    def _log(self, msg: str):
        if not msg:
            return
        self.log.configure(state="normal")
        self.log.insert("end", msg[:2000] + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 900:
            self.log.delete("1.0", "200.0")
        self.log.see("end")
        self.log.configure(state="disabled")
        progress = re.search(r"\[download\]\s+([\d.]+)%", msg)
        if progress:
            self.progress.set(min(float(progress.group(1)), 100))
            self.status.set("Letöltés: " + msg.strip()[-105:])

    def _event(self, *args):
        self.ui_events.put(args)

    def _consume_events(self):
        try:
            while True:
                event = self.ui_events.get_nowait()
                kind, *args = event
                if kind == "info":
                    self._metadata_ready(args[0])
                elif kind == "thumb":
                    # Ignore thumbnails arriving after a newer URL was analyzed.
                    if self.info is not None and self.info.url == args[0]:
                        self._display_thumbnail(args[1])
                elif kind == "analysis-error":
                    messagebox.showerror("Elemzési hiba", str(args[0]))
                    self._log("HIBA: " + str(args[0]))
                elif kind == "analysis-done":
                    self._busy_analysis = False
                    self.analyze_button.configure(state="normal")
                elif kind == "log":
                    self._log(args[0])
                elif kind == "job-status":
                    job, status = args
                    job.status = status
                    if self.tree.exists(str(job.id)):
                        self.tree.set(str(job.id), "state", status)
                    self.status.set(f"{job.info_title}: {status}")
                    if status == "Letöltés...":
                        self.progress.set(0)
                elif kind == "update-info":
                    self.latest_release = args[0]
                    self._log(f"GitHub: legutóbbi stabil kiadás {args[0].tag} ({args[0].date}).")
                    if self._local_version() == args[0].tag:
                        messagebox.showinfo("yt-dlp frissítés", f"Már a legutóbbi stabil verzió van telepítve: {args[0].tag}")
                    elif messagebox.askyesno("yt-dlp frissítés", f"Hivatalos stabil kiadás: {args[0].tag}\nDátum: {args[0].date}\n\nTelepíted most?"):
                        self._install_update(args[0])
                elif kind == "update-complete":
                    self._updating = False
                    messagebox.showinfo("yt-dlp frissítés", args[0])
                elif kind == "update-error":
                    self._updating = False
                    self._log("HIBA: " + str(args[0]))
                    messagebox.showerror("Frissítési hiba", str(args[0]))
        except Empty:
            pass
        self.after(130, self._consume_events)

    def _check_dependencies(self):
        status = self.engine.tool_status()
        missing = [k for k in ("yt-dlp", "ffmpeg", "ffprobe", "deno") if status[k] == "HIÁNYZIK"]
        if missing:
            self._log("Hiányzó összetevők: " + ", ".join(missing) + ". A forráscsomag NEM tartalmaz letöltött Windows-binárisokat; a Windows buildfolyamat csomagolja őket.")
        else:
            self._log("Eszközök megtalálva: " + ", ".join(status))

    def _analyze(self):
        if self._busy_analysis or self.worker_running or self._updating:
            messagebox.showwarning("Folyamatban", "Elemzés nem indítható egy másik aktív művelet közben.")
            return
        url = self.url.get().strip()
        self._busy_analysis = True
        self.analyze_button.configure(state="disabled")
        self.status.set("Videó adatainak lekérése...")
        self._log("Elemzés indítása: " + url)
        def work():
            try:
                from .core import validate_url
                data = self.engine.analyze(validate_url(url))
                if data.get("_type") in {"playlist", "multi_video"}:
                    self._event("analysis-error", "Ez egy lejátszási lista. Kapcsold be a lista letöltését; a formátumok és hangsávok videónként eltérhetnek.")
                else:
                    info = VideoInfo.from_json(data, url)
                    self._event("info", info)
                    if info.thumbnail:
                        self._fetch_thumb(info.thumbnail, info.url)
            except Exception as exc:
                self._event("analysis-error", str(exc))
            finally:
                self._event("analysis-done")
        threading.Thread(target=work, daemon=True).start()

    def _fetch_thumb(self, url: str, video_url: str):
        if Image is None or ImageTk is None:
            return
        parsed = urlparse(url)
        # Only YouTube's own image CDN, never arbitrary private-network URLs.
        if parsed.scheme != "https" or not (parsed.hostname == "ytimg.com" or (parsed.hostname or "").endswith(".ytimg.com")):
            return
        try:
            req = Request(url, headers={"User-Agent": "YTDLPStudio/0.1"})
            with urlopen(req, timeout=8) as response:
                data = response.read(2_500_001)
            if len(data) > 2_500_000:
                return
            with Image.open(BytesIO(data)) as im:
                image = im.convert("RGB")
                image.thumbnail((720, 480))
                # Tk PhotoImage creation must occur on main thread.
                copy = image.copy()
            self._event("thumb", video_url, copy)
        except Exception:
            return

    def _display_thumbnail(self, image):
        if ImageTk is None:
            return
        self._thumb_pil = image
        self._render_preview()

    def _metadata_ready(self, info: VideoInfo):
        self.info = info
        self._thumb_ref = None
        self._thumb_pil = None
        self.thumbnail.configure(image="", text="▶\nNincs elérhető előnézeti kép")
        self.open_video.configure(state="normal")
        self.video_title.set(info.title)
        duration = fmt_time(info.duration) if info.duration else "Ismeretlen hossz"
        self.video_summary.set(f"{info.uploader}   •   {duration}   •   {len(info.audio_tracks)} hangsáv   •   {len(info.subtitles)} feliratnyelv/típus")
        self.audio_list.set_items([(track.format_id, track.label) for track in info.audio_tracks])
        self.sub_list.set_items([(f"{sub.kind}:{sub.language}", sub.label) for sub in info.subtitles])
        if info.resolutions:
            values = ["Legjobb"] + [f"{h}p" for h in info.resolutions]
            self.quality_cb.set_menu(self.quality.get() if self.quality.get() in values else "Legjobb", *values)
        self._log(f"Elemzés kész: {info.title}")
        self.status.set("Elemzés kész. Válassz formátumot, hangsávot és feliratot.")

    def _make_opts(self) -> DownloadOptions:
        from .core import validate_url
        url = validate_url(self.url.get())
        same_video = self.info is not None and self.info.url == url
        audios = self.audio_list.selected_keys() if same_video else []
        selected_subs = set(self.sub_list.selected_keys()) if same_video else set()
        subtitles = ([sub for sub in self.info.subtitles if f"{sub.kind}:{sub.language}" in selected_subs]
                     if same_video else [])
        mode = {"Videó": "video", "Csak hang": "audio", "Csak felirat": "subtitles"}[self.mode.get()]
        opts = DownloadOptions(url=url, dest=self.destination.get(), mode=mode,
                               quality=self.quality.get(), container=self.container.get(),
                               audio_format=self.audio_format.get(), audio_track_ids=audios,
                               subtitles=subtitles, subtitle_format=self.subtitle_format.get(),
                               embed_subtitles=self.embed.get(),
                               start=parse_time(self.clip_start.get()),
                               end=parse_time(self.clip_end.get()),
                               accurate_cut=self.accurate.get(), playlist=self.playlist.get())
        if opts.playlist and (audios or subtitles):
            raise ValueError("Lejátszási listánál a konkrét videó hangsávjai/feliratai nem általánosíthatók. Kapcsold ki a lista opciót, vagy töröld a kijelöléseket.")
        opts.validate()
        return opts

    def _enqueue(self):
        if self._updating:
            messagebox.showwarning("Frissítés", "Várj, amíg a yt-dlp frissítése befejeződik.")
            return
        try:
            opts = self._make_opts()
        except Exception as exc:
            messagebox.showerror("Hibás beállítás", str(exc))
            return
        self.settings.destination = opts.dest
        self.settings.quality = opts.quality
        self.settings.container = opts.container
        self.settings.audio_format = opts.audio_format
        self.settings.subtitles_format = opts.subtitle_format
        self.settings.save()
        job = Job(len(self.jobs) + 1, self.info.title if self.info and self.info.url == opts.url else opts.url, opts)
        self.jobs.append(job)
        self.tree.insert("", "end", iid=str(job.id), values=(job.id, job.info_title[:115], job.status))
        with self.jobs_lock:
            self.pending.append(job)
            if not self.worker_running:
                self.worker_running = True
                threading.Thread(target=self._run_jobs, daemon=True).start()
        self._log(f"Sorba állítva: {job.info_title}")

    def _run_jobs(self):
        while True:
            with self.jobs_lock:
                if not self.pending:
                    self.active_job = None
                    self.worker_running = False
                    break
                job = self.pending.pop(0)
                self.active_job = job
            self.engine.reset()
            self._event("job-status", job, "Letöltés...")
            try:
                result = self.engine.download(job.options, lambda line: self._event("log", line))
                job.output = result
                self._event("job-status", job, "Kész")
                self._event("log", "Sikeres: " + result)
            except Cancelled:
                self._event("job-status", job, "Megszakítva")
                self._event("log", "A művelet megszakítva.")
            except Exception as exc:
                self._event("job-status", job, "Hiba")
                self._event("log", f"HIBA ({job.info_title}): {exc}")

    def _remove_job(self):
        rows = self.tree.selection()
        with self.jobs_lock:
            removable = [j for j in self.pending if str(j.id) in rows]
            for job in removable:
                self.pending.remove(job)
                job.status = "Törölve"
                self.tree.set(str(job.id), "state", "Törölve")

    def _cancel(self):
        if self.active_job:
            self.engine.stop()
            self._log("Megszakítás kérése...")

    def _choose_dest(self):
        directory = filedialog.askdirectory(initialdir=self.destination.get())
        if directory:
            self.destination.set(directory)

    def _open_dest(self):
        p = Path(self.destination.get())
        p.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(str(p))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as exc:
            messagebox.showerror("Nem nyitható meg", str(exc))

    def _paste(self):
        try:
            self.url.set(self.clipboard_get().strip())
        except tk.TclError:
            pass

    def _toggle_theme(self):
        self.settings.theme = "light" if self.theme.get() == "dark" else "dark"
        self.settings.save()
        messagebox.showinfo("Téma", "A téma az alkalmazás újraindításakor változik meg.")

    def _local_version(self) -> str:
        path = find_exe("yt-dlp")
        if not path:
            return "nincs telepítve"
        try:
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            result = subprocess.run([str(path), "--version"], stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True, timeout=7,
                                    creationflags=flags)
            return result.stdout.strip() if result.returncode == 0 else "ismeretlen"
        except (OSError, subprocess.TimeoutExpired):
            return "ismeretlen"

    def _update_dialog(self):
        status = self.engine.tool_status()
        text = "\n".join(f"{k}: {v}" for k, v in status.items())
        text += "\nTelepített yt-dlp-verzió: " + self._local_version()
        if self.worker_running or self._busy_analysis:
            messagebox.showwarning("Frissítések", "Frissítés csak a letöltések/elemzés befejezése után lehetséges.")
            return
        if messagebox.askyesno("Eszközök és frissítés", text + "\n\nLekérdezzem a legutóbbi stabil yt-dlp GitHub-kiadást?"):
            self._log("yt-dlp frissítés ellenőrzése...")
            def check():
                try:
                    self._event("update-info", fetch_latest())
                except Exception as exc:
                    self._event("update-error", exc)
            threading.Thread(target=check, daemon=True).start()

    def _install_update(self, release: Release):
        if self.worker_running or self._busy_analysis:
            messagebox.showwarning("Frissítés", "A letöltések befejezéséig nem frissíthető a yt-dlp.")
            return
        self._updating = True
        from .settings import app_dir
        target = app_dir() / "bin" / "yt-dlp.exe"
        def work():
            try:
                install_release(release, target, lambda msg: self._event("log", msg))
                self._event("update-complete", f"yt-dlp frissítve: {release.tag}\nHely: {target}")
            except Exception as exc:
                self._event("update-error", exc)
        threading.Thread(target=work, daemon=True).start()

    def _close(self):
        if self.worker_running:
            if not messagebox.askyesno("Kilépés", "Letöltés folyamatban. Megszakítod és kilépsz?"):
                return
            self.engine.stop()
        self.settings.save()
        self.destroy()
