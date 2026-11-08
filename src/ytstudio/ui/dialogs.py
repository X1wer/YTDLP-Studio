"""Párbeszédablakok: beállítások, eszközök és frissítés, napló, hibarészletek."""
from __future__ import annotations

import threading
import webbrowser
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGridLayout,
                               QHBoxLayout, QLineEdit, QMessageBox, QPlainTextEdit, QSpinBox,
                               QVBoxLayout, QWidget, QCheckBox, QRadioButton, QButtonGroup)

from . import theme
from .logbus import bus, log
from .widgets import Card, ChoiceBox, Spinner, button, label, hline
from .. import APP_NAME, APP_REPO, __version__
from ..langs import NAMES, language_name
from ..settings import COOKIE_BROWSERS, Settings, bin_dir, data_dir
from .. import updater
from ..engine import tool_version


def open_path(path: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class _Dialog(QDialog):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(20, 18, 20, 16)
        self.root.setSpacing(14)

    def showEvent(self, event) -> None:  # noqa: N802
        theme.set_dark_title_bar(self, theme.manager.dark)
        super().showEvent(event)


LANG_CHOICES = [("", "Eredeti (alapértelmezett)")] + sorted(
    ((code, language_name(code)) for code in NAMES if len(code) == 2 and code != "iw"),
    key=lambda x: x[1])


class SettingsDialog(_Dialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__("Beállítások", parent)
        self.settings = settings
        self.resize(560, 0)
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        dest_row = QHBoxLayout()
        self.dest = QLineEdit(settings.destination)
        browse = button("Tallózás…")
        browse.clicked.connect(self._browse)
        dest_row.addWidget(self.dest, 1)
        dest_row.addWidget(browse)
        form.addRow("Alapértelmezett mentési mappa", dest_row)

        self.theme_box = ChoiceBox([("system", "Rendszer szerint"), ("light", "Világos"), ("dark", "Sötét")])
        self.theme_box.set_value(settings.theme)
        form.addRow("Téma", self.theme_box)

        self.subs = QLineEdit(", ".join(settings.preferred_sub_langs))
        self.subs.setPlaceholderText("pl. hu, en")
        self.subs.setToolTip("Nyelvkódok vesszővel elválasztva. Ezek a nyelvek a lista elejére kerülnek, "
                             "és lejátszási listáknál ezeket tölti le a program.")
        form.addRow("Preferált feliratnyelvek", self.subs)

        self.audio_lang = ChoiceBox(LANG_CHOICES)
        self.audio_lang.set_value(settings.preferred_audio_lang)
        self.audio_lang.setToolTip("Lejátszási listáknál ezt a hangsávot választja, ha elérhető.")
        form.addRow("Preferált hangsáv nyelve", self.audio_lang)

        self.remember = QCheckBox("Választott nyelvek megjegyzése")
        self.remember.setChecked(settings.remember_languages)
        form.addRow("", self.remember)

        self.parallel = QSpinBox()
        self.parallel.setRange(1, 3)
        self.parallel.setValue(settings.max_parallel)
        form.addRow("Egyszerre futó letöltések", self.parallel)

        self.rate = QLineEdit(settings.rate_limit)
        self.rate.setPlaceholderText("korlátlan (pl. 5M vagy 800K)")
        form.addRow("Sebességkorlát", self.rate)

        self.cookies = ChoiceBox([("", "Nem használ sütiket")] + [(b, b.capitalize()) for b in COOKIE_BROWSERS if b])
        self.cookies.set_value(settings.cookies_browser)
        self.cookies.setToolTip("Korhatáros vagy bejelentkezést igénylő videókhoz a kiválasztott böngésző "
                                "sütijeit olvassa (a program nem tárolja őket). Firefox ajánlott.")
        form.addRow("Böngészősütik", self.cookies)

        self.paste = QCheckBox("Beillesztés után automatikus elemzés")
        self.paste.setChecked(settings.auto_analyze_paste)
        self.open_done = QCheckBox("Kész letöltés után a mappa megnyitása")
        self.open_done.setChecked(settings.open_folder_when_done)
        form.addRow("", self.paste)
        form.addRow("", self.open_done)
        self.root.addLayout(form)
        note = label(f"A beállítások helye: {data_dir()}", "faint", wrap=True, selectable=True)
        self.root.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Mentés")
        buttons.button(QDialogButtonBox.StandardButton.Save).setProperty("variant", "primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Mégse")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        self.root.addWidget(buttons)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Mentési mappa", self.dest.text())
        if folder:
            self.dest.setText(folder)

    def _save(self) -> None:
        import re
        rate = self.rate.text().strip().upper()
        if rate and not re.fullmatch(r"\d+(\.\d+)?[KMG]?", rate):
            QMessageBox.warning(self, "Beállítások", "A sebességkorlát formátuma pl. 5M vagy 800K.")
            return
        langs = [p.strip() for p in re.split(r"[,; ]+", self.subs.text()) if p.strip()]
        if any(not re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})?", l) for l in langs):
            QMessageBox.warning(self, "Beállítások", "A feliratnyelvek kódjai pl.: hu, en, de.")
            return
        s = self.settings
        s.destination = self.dest.text().strip() or s.destination
        s.theme = self.theme_box.value()
        s.preferred_sub_langs = langs[:10]
        s.preferred_audio_lang = self.audio_lang.value()
        s.remember_languages = self.remember.isChecked()
        s.max_parallel = self.parallel.value()
        s.rate_limit = rate
        s.cookies_browser = self.cookies.value()
        s.auto_analyze_paste = self.paste.isChecked()
        s.open_folder_when_done = self.open_done.isChecked()
        s.save()
        self.accept()


class _Worker(QObject):
    done = Signal(str, object)


class ToolsDialog(_Dialog):
    """Összetevők verziói, yt-dlp frissítés (stable/nightly), visszaállítás."""

    def __init__(self, settings: Settings, can_update, parent=None):
        super().__init__("Eszközök és frissítés", parent)
        self.settings = settings
        self.can_update = can_update
        self.release: updater.Release | None = None
        self.resize(620, 0)
        self.worker = _Worker()
        self.worker.done.connect(self._on_done)

        versions = Card("Összetevők", "tools")
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        self.version_labels: dict[str, object] = {}
        rows = [("app", APP_NAME), ("yt-dlp", "yt-dlp"), ("ffmpeg", "FFmpeg"), ("deno", "Deno (JavaScript-futtató)")]
        for row, (key, name) in enumerate(rows):
            grid.addWidget(label(name), row, 0)
            value = label(__version__ if key == "app" else "lekérdezés…", "muted", selectable=True)
            grid.addWidget(value, row, 1)
            self.version_labels[key] = value
        grid.setColumnStretch(1, 1)
        versions.body.addLayout(grid)
        versions.body.addWidget(label(f"Programmappa: {bin_dir()}", "faint", wrap=True, selectable=True))
        self.root.addWidget(versions)

        upd = Card("yt-dlp frissítése", "update")
        upd.body.addWidget(label("A YouTube és más oldalak gyakran változnak; ha a letöltés hibát ad, "
                                 "először frissítsd a yt-dlp-t. A program csak a hivatalos GitHub-kiadást "
                                 "telepíti, SHA-256 ellenőrzés után, és megtartja az előző verziót.",
                                 "muted", wrap=True))
        channel_row = QHBoxLayout()
        channel_row.addWidget(label("Csatorna:"))
        self.stable = QRadioButton("Stabil (ajánlott)")
        self.nightly = QRadioButton("Nightly (legfrissebb javítások)")
        group = QButtonGroup(self)
        group.addButton(self.stable)
        group.addButton(self.nightly)
        (self.nightly if settings.ytdlp_channel == "nightly" else self.stable).setChecked(True)
        channel_row.addWidget(self.stable)
        channel_row.addWidget(self.nightly)
        channel_row.addStretch(1)
        upd.body.addLayout(channel_row)
        status_row = QHBoxLayout()
        self.spinner = Spinner()
        self.spinner.hide()
        self.status = label("", "muted", wrap=True)
        status_row.addWidget(self.spinner)
        status_row.addWidget(self.status, 1)
        upd.body.addLayout(status_row)
        actions = QHBoxLayout()
        self.check_button = button("Frissítés keresése", None, "search")
        self.check_button.clicked.connect(self._check)
        self.install_button = button("Telepítés", "primary", "download")
        self.install_button.clicked.connect(self._install)
        self.install_button.setEnabled(False)
        self.restore_button = button("Előző verzió visszaállítása", "ghost", "restore", "muted")
        self.restore_button.clicked.connect(self._restore)
        actions.addWidget(self.check_button)
        actions.addWidget(self.install_button)
        actions.addStretch(1)
        actions.addWidget(self.restore_button)
        upd.body.addLayout(actions)
        self.root.addWidget(upd)

        app_card = Card(f"{APP_NAME} frissítése", "info")
        if APP_REPO:
            row = QHBoxLayout()
            self.app_status = label("", "muted", wrap=True)
            check_app = button("Új verzió keresése")
            check_app.clicked.connect(self._check_app)
            row.addWidget(self.app_status, 1)
            row.addWidget(check_app)
            app_card.body.addLayout(row)
        else:
            app_card.body.addWidget(label(
                f"A program verziója ({__version__}) a yt-dlp-től függetlenül kezelt. Saját frissítéskereső "
                "a GitHub-tároló közzététele után kapcsol be.", "muted", wrap=True))
        self.root.addWidget(app_card)

        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.button(QDialogButtonBox.StandardButton.Close).setText("Bezárás")
        close.rejected.connect(self.reject)
        self.root.addWidget(close)
        self._refresh_versions()

    def _run(self, kind: str, func) -> None:
        self.spinner.start()
        for b in (self.check_button, self.install_button, self.restore_button):
            b.setEnabled(False)

        def work():
            try:
                self.worker.done.emit(kind, func())
            except Exception as exc:  # noqa: BLE001
                self.worker.done.emit("error:" + kind, exc)

        threading.Thread(target=work, daemon=True).start()

    def _refresh_versions(self) -> None:
        def collect():
            return {name: tool_version(name) for name in ("yt-dlp", "ffmpeg", "deno")}
        self._run("versions", collect)

    def _channel(self) -> str:
        return "nightly" if self.nightly.isChecked() else "stable"

    def _check(self) -> None:
        self.status.setText("Kiadás lekérdezése a GitHubról…")
        channel = self._channel()
        self._run("check", lambda: updater.fetch_latest(channel))

    def _install(self) -> None:
        if not self.release:
            return
        if not self.can_update():
            QMessageBox.information(self, "Frissítés", "A frissítés a futó letöltések és elemzések "
                                    "befejezése után lehetséges.")
            return
        release = self.release
        current = self._current
        target = bin_dir() / "yt-dlp.exe"
        self.status.setText(f"yt-dlp {release.tag} letöltése és ellenőrzése…")
        self._run("install", lambda: updater.install_release(release, target, current, log))

    def _restore(self) -> None:
        target = bin_dir() / "yt-dlp.exe"
        if not updater.backup_path(target).is_file():
            QMessageBox.information(self, "Visszaállítás", "Nincs korábbi yt-dlp-verzió elmentve.")
            return
        if not self.can_update():
            QMessageBox.information(self, "Visszaállítás", "Várd meg a futó letöltések végét.")
            return
        old = updater.backup_version(target) or "korábbi"
        if QMessageBox.question(self, "Visszaállítás", f"Visszaállítod a(z) {old} yt-dlp-verziót?") != QMessageBox.StandardButton.Yes:
            return
        self._run("restore", lambda: updater.restore_backup(target, log))

    @property
    def _current(self) -> str:
        return self.version_labels["yt-dlp"].text()

    def _check_app(self) -> None:
        self.app_status.setText("Lekérdezés…")
        self._run("app", updater.fetch_app_release)

    def _on_done(self, kind: str, payload) -> None:
        self.spinner.stop()
        self.check_button.setEnabled(True)
        target = bin_dir() / "yt-dlp.exe"
        self.restore_button.setEnabled(updater.backup_path(target).is_file())
        self.restore_button.setToolTip(f"Mentett verzió: {updater.backup_version(target) or 'ismeretlen'}")
        if kind.startswith("error:"):
            message = str(payload)
            if "urlopen" in message or "getaddrinfo" in message:
                message = "Nincs internetkapcsolat, vagy a GitHub nem érhető el."
            self.status.setText("Hiba: " + message)
            log("Frissítési hiba: " + str(payload))
            if kind == "error:install":
                QMessageBox.warning(self, "Frissítés", "A frissítés nem sikerült, a korábbi verzió maradt.\n\n" + message)
            if kind == "error:app" and APP_REPO:
                self.app_status.setText("Nem sikerült lekérdezni: " + message)
            self.install_button.setEnabled(self.release is not None)
            return
        if kind == "versions":
            for name, value in payload.items():
                self.version_labels[name].setText(value or "hiányzik")
            self.install_button.setEnabled(self.release is not None)
        elif kind == "check":
            self.release = payload
            current = self._current
            if updater.is_newer(payload.tag, current):
                self.status.setText(f"Elérhető: yt-dlp {payload.tag} ({payload.date}, {payload.channel}). "
                                    f"Telepített: {current}.")
                self.install_button.setEnabled(True)
            else:
                self.status.setText(f"A telepített yt-dlp ({current}) naprakész a(z) {payload.channel} csatornán.")
                self.install_button.setEnabled(payload.channel != self.settings.ytdlp_channel)
            self.settings.ytdlp_channel = payload.channel
            self.settings.save()
        elif kind in ("install", "restore"):
            self.status.setText(("Telepítve: " if kind == "install" else "Visszaállítva: ") + str(payload))
            self.version_labels["yt-dlp"].setText(str(payload))
            self.install_button.setEnabled(False)
        elif kind == "app" and APP_REPO:
            if payload is None:
                self.app_status.setText("Nincs beállítva frissítési forrás.")
            else:
                tag, page = payload
                if updater.is_newer(tag, __version__):
                    self.app_status.setText(f"Új verzió: {tag}. Letöltés a kiadási oldalról.")
                    webbrowser.open(page)
                else:
                    self.app_status.setText("A program naprakész.")


BROWSERS = [
    ("firefox", "Firefox", ("APPDATA", r"Mozilla\Firefox\Profiles")),
    ("chrome", "Google Chrome", ("LOCALAPPDATA", r"Google\Chrome\User Data")),
    ("edge", "Microsoft Edge", ("LOCALAPPDATA", r"Microsoft\Edge\User Data")),
    ("brave", "Brave", ("LOCALAPPDATA", r"BraveSoftware\Brave-Browser\User Data")),
    ("opera", "Opera", ("APPDATA", r"Opera Software\Opera Stable")),
    ("vivaldi", "Vivaldi", ("LOCALAPPDATA", r"Vivaldi\User Data")),
    ("chromium", "Chromium", ("LOCALAPPDATA", r"Chromium\User Data")),
]


def installed_browsers() -> set[str]:
    """A böngészőprofilok megléte alapján (rendszerleíró adatbázis nélkül)."""
    import os
    found = set()
    for key, _name, (env, sub) in BROWSERS:
        base = os.environ.get(env)
        if base and (Path(base) / sub).is_dir():
            found.add(key)
    return found


class BrowserCheckDialog(_Dialog):
    """Vezetett ellenőrzés: a robotellenőrzést/bejelentkezést a felhasználó a saját
    böngészőjében végzi el, a yt-dlp pedig annak munkamenetével próbálja újra.

    A YouTube a letöltőprogramoknak nem küld kitölthető ellenőrzést, csak elutasítja a
    kérést, ezért az ellenőrzés a programon belül nem jeleníthető meg.
    """

    INTROS = {
        "bot_check": "A YouTube robotellenőrzést kért, és ezt a kérést nem engedte át.",
        "rate_limit": "A YouTube „túl sok kérés” (429) választ adott: erről a hálózatról rövid idő alatt sok "
                      "kérés érkezett.",
        "login": "A videó megtekintéséhez bejelentkezés szükséges (pl. korhatáros tartalom).",
        "subtitles": "A YouTube nem engedte letölteni a feliratot (429 – túl sok kérés). A videó már "
                     "letöltődött; most csak a hiányzó feliratot próbálja újra a program, a videót nem "
                     "tölti le még egyszer. Bejelentkezett felhasználónak a YouTube gyakran kiadja – de nem "
                     "mindig: ha így sem sikerül, ezt a feliratot jelenleg nem adja ki, és az eredeti nyelvű "
                     "felirat a megoldás.",
    }

    def __init__(self, url: str, settings: Settings, parent=None, reason: str = "bot_check"):
        super().__init__("Ellenőrzés a böngészőben", parent)
        self.settings = settings
        self.url = url
        self.reason = reason if reason in self.INTROS else "bot_check"
        self.resize(600, 0)
        intro = label(self.INTROS[self.reason] + " A letöltőprogramok nem kapnak kitölthető ellenőrzést "
                      "(például képes feladványt), csak elutasítást, ezért ez itt, a programban nem végezhető "
                      "el. Végezd el a saját böngésződben, és a program az ott létrejött bejelentkezéssel "
                      "próbálja újra.", "muted", wrap=True)
        self.root.addWidget(intro)

        step1 = Card("1. Nyisd meg a videót a böngésződben", "external")
        step1.body.addWidget(label("Ha a YouTube vagy a Google ellenőrzést kér (például „szokatlan forgalom” "
                                   "oldal vagy képes feladvány), végezd el. Jelentkezz be a YouTube-fiókodba, "
                                   "és győződj meg róla, hogy a videó elindul.", None, wrap=True))
        open_button = button("Megnyitás a böngészőben", None, "external", "accent")
        open_button.clicked.connect(self._open)
        step1.body.addWidget(open_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.root.addWidget(step1)

        step2 = Card("2. Melyik böngészőt használtad?", "settings")
        installed = installed_browsers()
        items = [(key, name + ("" if key in installed else " (nem található)")) for key, name, _ in BROWSERS]
        self.browser_box = ChoiceBox(items)
        preferred = settings.cookies_browser or next((k for k, _, _ in BROWSERS if k in installed), "firefox")
        self.browser_box.set_value(preferred)
        self.browser_box.currentIndexChanged.connect(self._update_hint)
        step2.body.addWidget(self.browser_box, 0, Qt.AlignmentFlag.AlignLeft)
        self.hint = label("", "caption", wrap=True)
        step2.body.addWidget(self.hint)
        self.keep = QCheckBox("A további letöltésekhez is ezt a böngészőt használja")
        self.keep.setChecked(True)
        step2.body.addWidget(self.keep)
        self.root.addWidget(step2)

        self.root.addWidget(label(
            "Adatvédelem: a program a sütiket nem menti el és nem küldi tovább – a yt-dlp csak az adott "
            "lekéréshez olvassa őket közvetlenül a böngésző profiljából. Ha nagyon sok videót töltesz le "
            "bejelentkezett fiókkal, a YouTube a fiókot is korlátozhatja.", "faint", wrap=True))
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = button("Inkább várok")
        cancel.setToolTip("A program a korlátozás lejárta után magától újrapróbálja")
        cancel.clicked.connect(self.reject)
        retry = button("3. Felirat újrapróbálása" if self.reason == "subtitles" else "3. Újrapróbálás",
                       "primary", "retry")
        retry.clicked.connect(self._accept)
        row.addWidget(cancel)
        row.addWidget(retry)
        self.root.addLayout(row)
        self._update_hint()

    def browser(self) -> str:
        return self.browser_box.value()

    def _open(self) -> None:
        from ..core import validate_url
        try:
            webbrowser.open(validate_url(self.url))
        except ValueError:
            pass

    def _update_hint(self, *_):
        if self.browser() == "firefox":
            text = "Ajánlott: a Firefox sütijei akkor is olvashatók, ha a böngésző nyitva van."
        else:
            text = ("Az újrapróbálás előtt zárd be teljesen a böngészőt. Az újabb Chrome-alapú böngészők "
                    "titkosítják a sütiket, ezért előfordulhat, hogy a program nem tudja olvasni őket – "
                    "ilyenkor a Firefox a megbízható megoldás.")
        self.hint.setText(text)

    def _accept(self) -> None:
        if self.keep.isChecked():
            self.settings.cookies_browser = self.browser()
            self.settings.save()
        log(f"Ellenőrzés a böngészőben: {self.browser()} munkamenetének használata.")
        self.accept()


class LogWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Részletes napló")
        self.resize(900, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        self.text = QPlainTextEdit()
        self.text.setObjectName("log")
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(6000)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text.setPlainText("\n".join(bus.lines))
        layout.addWidget(self.text, 1)
        row = QHBoxLayout()
        copy = button("Másolás", None, "copy")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.text.toPlainText()))
        folder = button("Naplómappa", None, "folder")
        folder.clicked.connect(lambda: bus.path and open_path(bus.path.parent))
        clear = button("Törlés", "ghost", "trash", "muted")
        clear.clicked.connect(self.text.clear)
        row.addWidget(copy)
        row.addWidget(folder)
        row.addStretch(1)
        row.addWidget(clear)
        layout.addLayout(row)
        bus.message.connect(self._append)

    def _append(self, line: str) -> None:
        bar = self.text.verticalScrollBar()
        at_end = bar.value() >= bar.maximum() - 4
        self.text.appendPlainText(line)
        if at_end:
            bar.setValue(bar.maximum())

    def showEvent(self, event) -> None:  # noqa: N802
        theme.set_dark_title_bar(self, theme.manager.dark)
        super().showEvent(event)


class DetailsDialog(_Dialog):
    def __init__(self, title: str, message: str, details: str, warnings: list[str] = (), parent=None,
                 retry=None):
        super().__init__("Részletek", parent)
        self.resize(640, 420)
        self.root.addWidget(label(title, "h2", wrap=True))
        if message:
            self.root.addWidget(label(message, None, wrap=True))
        for warning in warnings:
            self.root.addWidget(label("⚠ " + warning, "warnText", wrap=True))
        if details:
            self.root.addWidget(label("Technikai részletek", "caption"))
            text = QPlainTextEdit(details)
            text.setObjectName("log")
            text.setReadOnly(True)
            self.root.addWidget(text, 1)
        row = QHBoxLayout()
        copy = button("Másolás", None, "copy")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(f"{title}\n{message}\n\n{details}"))
        row.addWidget(copy)
        row.addStretch(1)
        if retry:
            again = button("Újrapróbálás", "primary", "retry")
            again.clicked.connect(lambda: (retry(), self.accept()))
            row.addWidget(again)
        close = button("Bezárás")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        self.root.addLayout(row)
