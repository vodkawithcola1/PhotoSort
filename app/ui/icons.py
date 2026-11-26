"""Ikony liniowe (SVG) rysowane w kolorze motywu oraz logo PhotoSort."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from app.ui import theme

_S = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{c}" ' \
     'stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'

PATHS = {
    "import": '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
    "home": '<path d="M3 11 12 4l9 7"/><path d="M5 10v9a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1v-9"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "moon": '<path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/>',
    "undo": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    "bookmark": '<path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1z"/>',
    "bookmark_fill": '<path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1z" fill="{c}"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "folder_plus": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 10.5v5M9.5 13h5"/>',
    "inbox": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5h13l3.5 7v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6z"/>',
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "play": '<path d="M7 4.5v15a1 1 0 0 0 1.5.9l12-7.5a1 1 0 0 0 0-1.8l-12-7.5A1 1 0 0 0 7 4.5z" fill="{c}"/>',
    "pause": '<rect x="6" y="4" width="4" height="16" rx="1" fill="{c}"/><rect x="14" y="4" width="4" height="16" rx="1" fill="{c}"/>',
    "volume": '<path d="M11 5 6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/>',
    "mute": '<path d="M11 5 6 9H2v6h4l5 4z"/><path d="m22 9-6 6M16 9l6 6"/>',
    "fullscreen": '<path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3"/>',
    "exit_fullscreen": '<path d="M8 3v3a2 2 0 0 1-2 2H3M21 8h-3a2 2 0 0 1-2-2V3M3 16h3a2 2 0 0 1 2 2v3M16 21v-3a2 2 0 0 1 2-2h3"/>',
    "zoom_in": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M11 8v6M8 11h6"/>',
    "zoom_out": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M8 11h6"/>',
    "fit": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M8 9H7v1M16 9h1v1M8 15H7v-1M16 15h1v-1"/>',
    "rotate": '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
    "chevron_left": '<path d="m15 18-6-6 6-6"/>',
    "chevron_right": '<path d="m9 18 6-6-6-6"/>',
    "chevron_up": '<path d="m18 15-6-6-6 6"/>',
    "chevron_down": '<path d="m6 9 6 6 6-6"/>',
    "map_pin": '<path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>',
    "filter": '<path d="M3 5h18M6 12h12M10 19h4"/>',
    "film": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/>',
    "photo": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/>',
    "phone": '<rect x="6" y="2" width="12" height="20" rx="2.5"/><path d="M11 18h2"/>',
    "computer": '<rect x="2" y="4" width="20" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
    "files": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    "close": '<path d="M18 6 6 18M6 6l12 12"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "more": '<circle cx="5" cy="12" r="1.2" fill="{c}"/><circle cx="12" cy="12" r="1.2" fill="{c}"/><circle cx="19" cy="12" r="1.2" fill="{c}"/>',
    "check": '<path d="m5 12 5 5L20 7"/>',
    "camera": '<path d="M4 8a2 2 0 0 1 2-2h2l1.5-2h5L16 6h2a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/><circle cx="12" cy="13" r="3.5"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    "library": '<rect x="3" y="6" width="14" height="14" rx="2"/><path d="M7 3h11a3 3 0 0 1 3 3v11"/>',
    "open": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v1"/><path d="M3 7v10a2 2 0 0 0 2 2h12.5a2 2 0 0 0 1.9-1.4L21.8 12a1 1 0 0 0-1-1.3H8.3a2 2 0 0 0-1.9 1.4L3.5 19"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "same_day": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/><circle cx="12" cy="15.5" r="2" fill="{c}"/>',
    "expand": '<path d="m7 15 5-5 5 5"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-14.8-3.5M4 4v4h4"/><path d="M4 13a8 8 0 0 0 14.8 3.5M20 20v-4h-4"/>',
    "history": '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>',
    "warning": '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
}

_cache: dict[tuple, QIcon] = {}


def svg(name: str, color: str, width: float = 1.8) -> bytes:
    body = PATHS[name].replace("{c}", color)
    return _S.format(c=color, w=width, body=body).encode()


def pixmap(name: str, size: int = 20, color: str | None = None, width: float = 1.8, dpr: float = 2.0) -> QPixmap:
    color = color or theme.current()["text"]
    renderer = QSvgRenderer(QByteArray(svg(name, color, width)))
    img = QImage(int(size * dpr), int(size * dpr), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, size * dpr, size * dpr))
    p.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, color: str | None = None, size: int = 20, width: float = 1.8) -> QIcon:
    color = color or theme.current()["text"]
    key = (name, color, size, width)
    ic = _cache.get(key)
    if ic is None:
        ic = QIcon()
        ic.addPixmap(pixmap(name, size, color, width))
        _cache[key] = ic
    return ic


def clear_cache() -> None:
    _cache.clear()


# ---------------------------------------------------------------------- #
LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<defs>
 <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#FFB547"/><stop offset="0.5" stop-color="#FF5E7A"/><stop offset="1" stop-color="#6A5BFF"/>
 </linearGradient>
 <linearGradient id="h" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#FFFFFF" stop-opacity="0.95"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0.8"/>
 </linearGradient>
</defs>
<rect x="2" y="2" width="60" height="60" rx="15" fill="url(#g)"/>
<rect x="13" y="17" width="30" height="24" rx="5" fill="#FFFFFF" fill-opacity="0.35" transform="rotate(-10 28 29)"/>
<rect x="19" y="21" width="32" height="26" rx="5" fill="url(#h)"/>
<circle cx="27.5" cy="29" r="3.2" fill="#FF8A5B"/>
<path d="M21 44.5l9-9 6 6 4-4 9 7v0.5a2 2 0 0 1-2 2H23a2 2 0 0 1-2-2z" fill="#6A5BFF" fill-opacity="0.85"/>
</svg>"""


def logo_pixmap(size: int = 64, dpr: float = 2.0) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(LOGO_SVG.encode()))
    img = QImage(int(size * dpr), int(size * dpr), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p, QRectF(0, 0, size * dpr, size * dpr))
    p.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(dpr)
    return pm


def app_icon() -> QIcon:
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(logo_pixmap(s, 1.0))
    return ic


def size(s: int) -> QSize:
    return QSize(s, s)
