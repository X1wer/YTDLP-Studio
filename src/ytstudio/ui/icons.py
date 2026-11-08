"""Saját, egységes vonalas ikonkészlet (SVG), témaszínre színezve."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# 24×24-es rácson rajzolt útvonalak; a "stroke" helyére kerül a szín.
_PATHS = {
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1.2 1.2"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1.2-1.2"/>',
    "paste": '<rect x="6" y="4" width="12" height="17" rx="2"/><path d="M9 4.5V3.5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v1"/><path d="M9.5 11h5M9.5 15h5"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.3-4.3"/>',
    "download": '<path d="M12 4v11"/><path d="m7 10.5 5 5 5-5"/><path d="M5 20h14"/>',
    "queue": '<path d="M4 6h11M4 12h11M4 18h7"/><path d="M17 15v6M14 18h6"/>',
    "folder": '<path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>',
    "folder-open": '<path d="M3.5 18V7.5a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2V11"/><path d="M3.5 18l2.6-6.2a1.5 1.5 0 0 1 1.4-.8H21l-2.8 6.6a1.5 1.5 0 0 1-1.4.9H3.5z"/>',
    "play": '<path d="M8 5.5v13l10.5-6.5z" fill="{c}"/>',
    "pause": '<path d="M8.5 5.5v13M15.5 5.5v13" stroke-width="2.6"/>',
    "stop": '<rect x="6.5" y="6.5" width="11" height="11" rx="2" fill="{c}"/>',
    "close": '<path d="M6 6l12 12M18 6 6 18"/>',
    "retry": '<path d="M20 12a8 8 0 1 1-2.6-5.9"/><path d="M20 4v5h-5"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    "tools": '<path d="M14.7 6.3a4 4 0 0 0-5.3 5.3L3.5 17.5a1.4 1.4 0 0 0 2 2l5.9-5.9a4 4 0 0 0 5.3-5.3l-2.5 2.5-2-.5-.5-2z"/>',
    "log": '<rect x="4" y="3.5" width="16" height="17" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>',
    "moon": '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
    "auto-theme": '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="{c}"/>',
    "video": '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="m16 10.5 5-3v9l-5-3"/>',
    "audio": '<path d="M9 18V6l11-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/>',
    "subtitles": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 12.5h4M13 12.5h4M7 15.5h7M16 15.5h1"/>',
    "scissors": '<circle cx="6" cy="7" r="2.5"/><circle cx="6" cy="17" r="2.5"/><path d="M8 8.5 20 17M8 15.5 20 7"/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="m8 12.5 3 3 5-6"/>',
    "alert": '<path d="M12 3.5 2.5 20h19z"/><path d="M12 10v4.5M12 17.2v.3"/>',
    "error": '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v6M12 16.5v.3"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.8v.3"/>',
    "external": '<path d="M14 4h6v6"/><path d="M20 4 11 13"/><path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-right": '<path d="m9 6 6 6-6 6"/>',
    "list": '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1" fill="{c}"/><circle cx="4.5" cy="12" r="1" fill="{c}"/><circle cx="4.5" cy="18" r="1" fill="{c}"/>',
    "star": '<path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/>',
    "trash": '<path d="M4 7h16M9.5 7V4.5h5V7M6.5 7l1 12.5a1.5 1.5 0 0 0 1.5 1.5h6a1.5 1.5 0 0 0 1.5-1.5l1-12.5"/>',
    "copy": '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    "clear": '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
    "update": '<path d="M12 3v12"/><path d="m7.5 10.5 4.5 4.5 4.5-4.5"/><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
    "restore": '<path d="M4 12a8 8 0 1 0 2.6-5.9"/><path d="M4 4v5h5"/><path d="M12 8v4l3 2"/>',
    "film": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/>',
    "volume": '<path d="M4 9.5h3.5L12 6v12l-4.5-3.5H4z"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/>',
    "mute": '<path d="M4 9.5h3.5L12 6v12l-4.5-3.5H4z"/><path d="m16 9.5 5 5M21 9.5l-5 5"/>',
    "mark-in": '<path d="M7 4v16"/><path d="m11 8 5 4-5 4z" fill="{c}"/>',
    "mark-out": '<path d="M17 4v16"/><path d="m13 8-5 4 5 4z" fill="{c}"/>',
}


def svg(name: str, color: str, stroke: float = 1.8) -> str:
    body = _PATHS.get(name, _PATHS["info"]).replace("{c}", color)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


_cache: dict[tuple, QIcon] = {}


def pixmap(name: str, color: str, size: int = 20, ratio: float = 2.0) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg(name, color).encode("utf-8")))
    px = int(size * ratio)
    image = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, px, px))
    painter.end()
    result = QPixmap.fromImage(image)
    result.setDevicePixelRatio(ratio)
    return result


def icon(name: str, color: str, disabled: str | None = None, size: int = 20) -> QIcon:
    key = (name, color, disabled, size)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    result = QIcon()
    result.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal)
    if disabled:
        result.addPixmap(pixmap(name, disabled, size), QIcon.Mode.Disabled)
    _cache[key] = result
    return result


def write_svg(path, name: str, color: str, stroke: float = 2.6) -> None:
    path.write_text(svg(name, color, stroke), encoding="utf-8")


def icon_size(px: int = 18) -> QSize:
    return QSize(px, px)
