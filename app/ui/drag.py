"""Wspólna obsługa przeciągania multimediów (podgląd z licznikiem plików)."""
from __future__ import annotations

import json

from PySide6.QtCore import QMimeData, QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QDrag, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from app.constants import MIME_MEDIA_IDS
from app.ui import icons, theme


def ids_from_mime(mime: QMimeData) -> list[int]:
    if not mime.hasFormat(MIME_MEDIA_IDS):
        return []
    try:
        return [int(x) for x in json.loads(bytes(mime.data(MIME_MEDIA_IDS)).decode())]
    except (ValueError, TypeError):
        return []


def drag_pixmap(pixmaps: list[QPixmap | None], count: int, kinds: list[str] | None = None) -> QPixmap:
    size = 96
    pad = 14
    dpr = 2.0
    w = size + pad * 2 + 10
    canvas = QPixmap(int(w * dpr), int(w * dpr))
    canvas.setDevicePixelRatio(dpr)
    canvas.fill(Qt.GlobalColor.transparent)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    layers = min(3, max(1, count))
    for i in reversed(range(layers)):
        pm = pixmaps[i] if i < len(pixmaps) else None
        off = i * 5
        rect = QRectF(pad + off, pad + off, size, size)
        p.save()
        p.translate(rect.center())
        p.rotate(-4 * i)
        p.translate(-rect.center())
        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        p.fillPath(path, QColor(0, 0, 0, 40))
        p.setClipPath(path)
        p.fillRect(rect, theme.color("thumb_bg"))
        if pm is not None and not pm.isNull():
            sw, sh = pm.width(), pm.height()
            side = min(sw, sh)
            src = QRectF((sw - side) / 2, (sh - side) / 2, side, side)
            p.drawPixmap(rect, pm, src)
        else:
            kind = (kinds[i] if kinds and i < len(kinds) else "photo")
            ip = icons.pixmap("film" if kind == "video" else "photo", 36, theme.current()["text3"])
            p.drawPixmap(int(rect.center().x() - 18), int(rect.center().y() - 18), ip)
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 230), 2.5))
        p.drawPath(path)
        p.restore()
    if count > 1:
        text = str(count)
        f = QFont(theme.ui_font(10, QFont.Weight.Bold))
        p.setFont(f)
        tw = max(26, p.fontMetrics().horizontalAdvance(text) + 14)
        badge = QRectF(pad + size - tw / 2 + 4, pad - 9, tw, 26)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.color("accent"))
        p.drawRoundedRect(badge, 13, 13)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    return canvas


def start_media_drag(source: QWidget, ids: list[int], pixmaps: list[QPixmap | None],
                     kinds: list[str] | None = None) -> Qt.DropAction:
    mime = QMimeData()
    mime.setData(MIME_MEDIA_IDS, json.dumps(ids).encode())
    drag = QDrag(source)
    drag.setMimeData(mime)
    pm = drag_pixmap(pixmaps, len(ids), kinds)
    drag.setPixmap(pm)
    drag.setHotSpot(QPoint(int(pm.width() / pm.devicePixelRatio() / 2), int(pm.height() / pm.devicePixelRatio() / 2)))
    return drag.exec(Qt.DropAction.MoveAction)
