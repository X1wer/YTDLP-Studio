"""Small, native Tk controls for reliable dropdown and checkbox selection.

No ttk Combobox popdown is used: packaged Tk builds on some Windows machines
can silently fail to display it. A real Tk Menu is also keyboard accessible.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Sequence


class ChoiceMenu(ttk.Menubutton):
    """A single-choice dropdown backed by tk.Menu rather than ttk.Combobox."""

    def __init__(self, master, variable: tk.StringVar, choices: Sequence[str], **kw):
        super().__init__(master, textvariable=variable, direction="below", style="Choice.TMenubutton", **kw)
        self.variable = variable
        self.menu = tk.Menu(self, tearoff=False)
        self.configure(menu=self.menu)
        self.set_choices(choices)
        self.bind("<space>", self._post_menu)
        self.bind("<Return>", self._post_menu)
        self.bind("<Down>", self._post_menu)

    def set_choices(self, choices: Sequence[str]) -> None:
        self.choices = list(choices)
        self.menu.delete(0, "end")
        for choice in self.choices:
            self.menu.add_radiobutton(label=choice, value=choice,
                                      variable=self.variable, indicatoron=True)
        # The persisted preference can be temporarily absent from a particular
        # video's formats. Keep the user's preference; yt-dlp uses it as a cap.
        if not self.variable.get() and self.choices:
            self.variable.set(self.choices[0])

    def _post_menu(self, _event):
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        self.menu.post(x, y)
        return "break"

    def set_palette(self, colors: dict[str, str]) -> None:
        self.menu.configure(bg=colors["panel"], fg=colors["fg"],
                            activebackground=colors["active"],
                            activeforeground=colors["fg"], selectcolor=colors["accent"])


class CheckList(ttk.Frame):
    """Scrollable, searchable group of *real* checkbox widgets.

    Filtering never changes the checked state of hidden items. Original list
    indices are preserved for mapping back to yt-dlp format IDs and subtitles.
    """

    def __init__(self, master, colors: dict[str, str], *, height: int = 210):
        super().__init__(master, style="Panel.TFrame")
        self.colors = colors
        self.labels: list[str] = []
        self.checked: list[tk.BooleanVar] = []
        self.checkbuttons: list[tk.Checkbutton] = []
        self._visible: list[int] = []
        self.filter = tk.StringVar()
        self.count = tk.StringVar(value="Nincs elérhető elem")

        top = ttk.Frame(self, style="Panel.TFrame")
        top.pack(fill="x", pady=(2, 5))
        ttk.Label(top, text="Szűrés:", style="Muted.TLabel").pack(side="left", padx=(0, 4))
        self.search = ttk.Entry(top, textvariable=self.filter, width=14)
        self.search.pack(side="left", fill="x", expand=True)
        self.filter.trace_add("write", lambda *_: self._apply_filter())

        body = ttk.Frame(self, style="Panel.TFrame")
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, height=height, background=colors["field"],
                                highlightthickness=0, borderwidth=0)
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas, style="Choices.TFrame")
        self.canvas_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._resize_scroll)
        self.canvas.bind("<Configure>", self._resize_width)

        footer = ttk.Frame(self, style="Panel.TFrame")
        footer.pack(fill="x", pady=(5, 0))
        ttk.Label(footer, textvariable=self.count, style="Muted.TLabel").pack(side="left", expand=True, anchor="w")
        ttk.Button(footer, text="Mind", command=self.select_visible).pack(side="right", padx=(3, 0))
        ttk.Button(footer, text="Törlés", command=self.clear_selection).pack(side="right")

    def _resize_scroll(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_width(self, event):
        self.canvas.itemconfigure(self.canvas_window, width=event.width)
        for item in self.checkbuttons:
            item.configure(wraplength=max(100, event.width - 44))

    def set_items(self, labels: Sequence[str]) -> None:
        for item in self.checkbuttons:
            item.destroy()
        self.labels = list(labels)
        self.checked = []
        self.checkbuttons = []
        for label in self.labels:
            var = tk.BooleanVar(value=False)
            self.checked.append(var)
            check = tk.Checkbutton(
                self.inner, text=label, variable=var, command=self._update_count,
                bg=self.colors["field"], fg=self.colors["fg"],
                activebackground=self.colors["field"],
                activeforeground=self.colors["fg"],
                selectcolor=self.colors["field"],
                anchor="w", justify="left", relief="flat", bd=0,
                highlightthickness=0, padx=5, pady=3,
                wraplength=max(100, self.canvas.winfo_width() - 44),
                font=("Segoe UI", 9),
            )
            self.checkbuttons.append(check)
        self._apply_filter()
        self.canvas.yview_moveto(0)

    def _apply_filter(self) -> None:
        if not hasattr(self, "inner"):
            return
        needle = self.filter.get().strip().casefold()
        self._visible = []
        for index, (label, checkbox) in enumerate(zip(self.labels, self.checkbuttons)):
            checkbox.pack_forget()
            if needle in label.casefold():
                checkbox.pack(fill="x", anchor="w")
                self._visible.append(index)
        self.canvas.yview_moveto(0)
        self.after_idle(self._resize_scroll)
        self._update_count()

    def _update_count(self):
        selected = len(self.selected_indices())
        self.count.set(f"Kijelölve: {selected} / {len(self.labels)}  •  látható: {len(self._visible)}")

    def selected_indices(self) -> list[int]:
        return [i for i, state in enumerate(self.checked) if state.get()]

    def select_visible(self):
        for index in self._visible:
            self.checked[index].set(True)
        self._update_count()

    def clear_selection(self):
        for var in self.checked:
            var.set(False)
        self._update_count()

    def owns(self, widget) -> bool:
        while widget is not None:
            if widget is self:
                return True
            widget = getattr(widget, "master", None)
        return False

    def scroll(self, delta: int) -> None:
        self.canvas.yview_scroll(delta, "units")
