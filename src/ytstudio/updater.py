"""A yt-dlp ellenőrzött frissítése a hivatalos GitHub-kiadásokból.

* Csatornák: stable (yt-dlp/yt-dlp) és nightly (yt-dlp/yt-dlp-nightly-builds).
* Integritás: SHA-256 a GitHub API ``digest`` mezőjéből és/vagy a kiadás
  hivatalos ``SHA2-256SUMS`` fájljából; ha mindkettő elérhető, egyezniük kell.
* Biztonsági mentés: a korábbi ``yt-dlp.exe`` ``yt-dlp.exe.bak`` néven megmarad,
  hibás frissítés után automatikusan, később kézzel is visszaállítható.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen
import hashlib
import json
import os
import re
import subprocess
import sys

from .i18n import tr
from . import APP_REPO, __version__

CHANNELS = {
    "stable": "yt-dlp/yt-dlp",
    "nightly": "yt-dlp/yt-dlp-nightly-builds",
}
ASSET = "yt-dlp.exe"
UA = f"YTDLPStudio/{__version__} (+https://github.com/yt-dlp/yt-dlp)"
_ALLOWED_DOWNLOAD_PREFIXES = tuple(f"https://github.com/{repo}/releases/download/" for repo in CHANNELS.values())


@dataclass(frozen=True)
class Release:
    channel: str
    tag: str
    date: str
    asset_url: str
    asset_name: str
    sha256: str | None
    checksum_url: str | None
    size: int = 0
    page_url: str = ""


def _get_bytes(url: str, limit: int) -> bytes:
    if not url.startswith("https://"):
        raise ValueError(tr("Csak HTTPS-kapcsolat támogatott."))
    request = Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    with urlopen(request, timeout=30) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError(tr("A válasz meghaladta a megengedett méretet."))
    return data


def parse_release(raw: dict, channel: str) -> Release:
    assets = raw.get("assets") or []
    exe = next((a for a in assets if a.get("name") == ASSET), None)
    if not exe:
        raise RuntimeError(tr("A hivatalos kiadás nem tartalmaz yt-dlp.exe fájlt."))
    url = str(exe.get("browser_download_url") or "")
    if not url.startswith(_ALLOWED_DOWNLOAD_PREFIXES):
        raise RuntimeError(tr("A letöltési cím nem a hivatalos yt-dlp kiadási oldalra mutat."))
    check = next((a for a in assets if a.get("name") in ("SHA2-256SUMS", "SHA2-256SUMS.txt")), None)
    digest = str(exe.get("digest") or "")
    sha256 = digest[7:].lower() if re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest) else None
    return Release(channel, str(raw.get("tag_name") or "?"), str(raw.get("published_at") or "")[:10],
                   url, ASSET, sha256, str(check["browser_download_url"]) if check else None,
                   int(exe.get("size") or 0), str(raw.get("html_url") or ""))


def fetch_latest(channel: str = "stable") -> Release:
    if channel not in CHANNELS:
        raise ValueError(tr("Ismeretlen frissítési csatorna."))
    api = f"https://api.github.com/repos/{CHANNELS[channel]}/releases/latest"
    raw = json.loads(_get_bytes(api, 3_000_000).decode("utf-8"))
    return parse_release(raw, channel)


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", version or ""))


def is_newer(candidate: str, current: str) -> bool:
    if not current or not version_key(current):
        return True
    return version_key(candidate) > version_key(current)


def expected_checksum(release: Release) -> str:
    """Hivatalos SHA-256; ha két forrás is van, egyezniük kell."""
    from_list = None
    if release.checksum_url:
        sums = _get_bytes(release.checksum_url, 1_000_000).decode("utf-8", errors="replace")
        for row in sums.splitlines():
            found = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(.+)", row.strip())
            if found and found.group(2).strip() == release.asset_name:
                from_list = found.group(1).lower()
                break
    if release.sha256 and from_list and release.sha256 != from_list:
        raise RuntimeError(tr("A kiadás két hivatalos ellenőrzőösszege eltér; a frissítés megszakadt."))
    checksum = release.sha256 or from_list
    if not checksum:
        raise RuntimeError(tr("A kiadáshoz nem található hivatalos SHA-256 ellenőrzőösszeg; a frissítés megszakadt."))
    return checksum


def _download_verified(url: str, destination: Path, expected_sha: str, notify, limit: int = 300_000_000) -> None:
    if not url.startswith(_ALLOWED_DOWNLOAD_PREFIXES):
        raise ValueError(tr("Nem hivatalos GitHub-letöltési cím."))
    digest = hashlib.sha256()
    received = 0
    request = Request(url, headers={"User-Agent": UA})
    with urlopen(request, timeout=60) as response, destination.open("wb") as output:
        total = int(response.headers.get("Content-Length") or 0)
        last = -1
        while chunk := response.read(1024 * 256):
            received += len(chunk)
            if received > limit:
                raise RuntimeError(tr("A letöltött fájl mérete gyanúsan nagy; megszakítva."))
            output.write(chunk)
            digest.update(chunk)
            if total:
                percent = received * 100 // total
                if percent // 10 != last // 10:
                    last = percent
                    notify(tr("Letöltés: {percent}%").format(percent=percent))
    if digest.hexdigest().lower() != expected_sha.lower():
        destination.unlink(missing_ok=True)
        raise RuntimeError(tr("A letöltött yt-dlp SHA-256 ellenőrzése sikertelen; a régi verzió marad."))
    notify(tr("SHA-256 ellenőrzés sikeres."))


def _run_version(exe: Path) -> str:
    process = subprocess.run([str(exe), "--version"], stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False,
                             creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0))
    if process.returncode != 0:
        raise RuntimeError(tr("Az új yt-dlp nem indul el megfelelően."))
    return process.stdout.decode(errors="replace").strip()


def backup_path(exe_path: Path) -> Path:
    return exe_path.with_name(exe_path.name + ".bak")


def backup_version(exe_path: Path) -> str:
    try:
        return backup_path(exe_path).with_suffix(".bak.version").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def install_release(release: Release, exe_path: Path, current_version: str = "", notify=lambda _: None) -> str:
    """Telepíti a kiadást; hiba esetén visszaállítja az előző verziót.

    Csak akkor hívható, ha egyetlen yt-dlp-folyamat sem fut.
    """
    expected = expected_checksum(release)
    exe_path.parent.mkdir(parents=True, exist_ok=True)
    temp = exe_path.with_name(exe_path.name + ".download")
    backup = backup_path(exe_path)
    temp.unlink(missing_ok=True)
    try:
        notify(tr("Letöltés: yt-dlp {tag} ({channel})").format(tag=release.tag, channel=release.channel))
        _download_verified(release.asset_url, temp, expected, notify)
        _run_version(temp)
        # A jelenlegi verzió előbb ideiglenes helyre kerül; a korábbi mentés csak
        # sikeres telepítés után cserélődik, így egy hibás frissítés nem törli.
        rollback = exe_path.with_name(exe_path.name + ".rollback")
        had_old = exe_path.exists()
        if had_old:
            os.replace(exe_path, rollback)
        try:
            os.replace(temp, exe_path)
            version = _run_version(exe_path)
        except Exception:
            exe_path.unlink(missing_ok=True)
            if had_old:
                os.replace(rollback, exe_path)
            raise
        if had_old:
            os.replace(rollback, backup)
            backup.with_suffix(".bak.version").write_text(current_version or "ismeretlen", encoding="utf-8")
        notify(tr("Frissítés kész: {version}").format(version=version))
        return version
    finally:
        temp.unlink(missing_ok=True)


def restore_backup(exe_path: Path, notify=lambda _: None) -> str:
    """Visszaállítja az előző (biztonsági mentett) yt-dlp-t; a jelenlegi lesz a mentés."""
    backup = backup_path(exe_path)
    if not backup.is_file():
        raise RuntimeError(tr("Nincs visszaállítható korábbi yt-dlp-verzió."))
    _run_version(backup)
    swap = exe_path.with_name(exe_path.name + ".swap")
    old_version = backup_version(exe_path)
    current = ""
    try:
        current = _run_version(exe_path) if exe_path.exists() else ""
    except Exception:  # noqa: BLE001 - a hibás jelenlegi verziót is cserélni kell
        current = tr("hibás")
    if exe_path.exists():
        os.replace(exe_path, swap)
    os.replace(backup, exe_path)
    if swap.exists():
        os.replace(swap, backup)
        backup.with_suffix(".bak.version").write_text(current or "ismeretlen", encoding="utf-8")
    version = _run_version(exe_path)
    notify(tr("Visszaállítva: {version}").format(version=version or old_version))
    return version


def fetch_app_release() -> tuple[str, str] | None:
    """A YTDLP Studio saját legújabb kiadása (verzió, oldal), ha a tároló be van állítva."""
    if not APP_REPO or not re.fullmatch(r"[\w.-]+/[\w.-]+", APP_REPO):
        return None
    raw = json.loads(_get_bytes(f"https://api.github.com/repos/{APP_REPO}/releases/latest", 3_000_000))
    tag = str(raw.get("tag_name") or "").lstrip("v")
    page = str(raw.get("html_url") or "")
    if not page.startswith(f"https://github.com/{APP_REPO}/"):
        page = f"https://github.com/{APP_REPO}/releases"
    return tag, page
