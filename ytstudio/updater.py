"""Verified, rollback-capable yt-dlp updater using its official GitHub releases."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

API_URL = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
UA = "YTDLPStudio/0.1 (+https://github.com/yt-dlp/yt-dlp)"


@dataclass(frozen=True)
class Release:
    tag: str
    date: str
    asset_url: str
    asset_name: str
    sha256: str | None
    checksum_url: str | None


def _get_bytes(url: str, limit: int | None = None) -> bytes:
    if not url.startswith("https://"):
        raise ValueError("Csak HTTPS-kapcsolat támogatott.")
    request = Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    with urlopen(request, timeout=30) as response:
        if limit is not None:
            data = response.read(limit + 1)
            if len(data) > limit:
                raise ValueError("A válasz meghaladta a megengedett méretet.")
            return data
        return response.read()


def fetch_latest() -> Release:
    raw = json.loads(_get_bytes(API_URL, 2_000_000).decode("utf-8"))
    assets = raw.get("assets") or []
    exe = next((a for a in assets if a.get("name") == "yt-dlp.exe"), None)
    if not exe:
        raise RuntimeError("A hivatalos kiadás nem tartalmaz yt-dlp.exe állományt.")
    check = next((a for a in assets if a.get("name") in {"SHA2-256SUMS", "SHA2-256SUMS.txt"}), None)
    digest = exe.get("digest") or ""
    sha256 = digest[7:].lower() if re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest) else None
    return Release(str(raw.get("tag_name") or "?"), str(raw.get("published_at") or "")[:10],
                   str(exe["browser_download_url"]), "yt-dlp.exe", sha256,
                   str(check["browser_download_url"]) if check else None)


def _checksum_from_release(release: Release) -> str:
    if release.sha256:
        return release.sha256
    if not release.checksum_url:
        raise RuntimeError("A kiadáshoz nem található hivatalos SHA-256 ellenőrzőösszeg; a frissítés megszakadt.")
    sums = _get_bytes(release.checksum_url, 1_000_000).decode("utf-8")
    for row in sums.splitlines():
        # standard SHA256SUMS: hexadecimal + whitespace + [*]filename
        result = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(.+)", row.strip())
        if result and result.group(2).strip() == release.asset_name:
            return result.group(1).lower()
    raise RuntimeError("Nem található a yt-dlp.exe SHA-256 értéke a hivatalos listában.")


def _download_and_verify(url: str, destination: Path, expected_sha: str,
                         notify=lambda _: None) -> None:
    if not url.startswith("https://github.com/") and not url.startswith("https://objects.githubusercontent.com/"):
        raise ValueError("Nem hivatalos GitHub-letöltési cím.")
    digest = hashlib.sha256()
    request = Request(url, headers={"User-Agent": UA})
    with urlopen(request, timeout=60) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
    if digest.hexdigest().lower() != expected_sha.lower():
        destination.unlink(missing_ok=True)
        raise RuntimeError("A letöltött yt-dlp fájl SHA-256 ellenőrzése sikertelen.")
    notify("SHA-256 ellenőrzés sikeres.")


def install_release(release: Release, exe_path: Path, notify=lambda _: None) -> None:
    """Only call when no yt-dlp job is running. Roll back on failed verification."""
    expected = _checksum_from_release(release)
    exe_path.parent.mkdir(parents=True, exist_ok=True)
    temp = exe_path.with_suffix(".exe.download")
    backup = exe_path.with_suffix(".exe.bak")
    temp.unlink(missing_ok=True)
    try:
        notify(f"Letöltés: {release.tag}")
        _download_and_verify(release.asset_url, temp, expected, notify)
        old_exists = exe_path.exists()
        backup.unlink(missing_ok=True)
        if old_exists:
            os.replace(exe_path, backup)
        try:
            os.replace(temp, exe_path)
            process = subprocess.run([str(exe_path), "--version"],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     timeout=20, check=False,
                                     creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0))
            if process.returncode != 0:
                raise RuntimeError("Az új yt-dlp nem indítható el megfelelően.")
        except Exception:
            exe_path.unlink(missing_ok=True)
            if old_exists:
                os.replace(backup, exe_path)
            raise
        # Keep backup for one subsequent recovery; no premature deletion.
        notify(f"Frissítés kész: {process.stdout.decode(errors='replace').strip()}")
    finally:
        temp.unlink(missing_ok=True)
