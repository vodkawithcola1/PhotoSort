"""Panel informacji o zdjęciu lub filmie (pod głównym podglądem)."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QToolButton,
                               QVBoxLayout, QWidget)

from app.services.geocode_service import map_url
from app.ui import icons, theme
from app.utils.formatting import (NO_DATA, date_pl, datetime_pl, human_duration, human_size, parse_iso, time_pl,
                                  ts_to_dt)

SOURCE_TEXT = {
    "exif": "z metadanych zdjęcia (EXIF)",
    "video": "z metadanych filmu",
    "exiftool": "z metadanych (ExifTool)",
    "filename": "odczytana z nazwy pliku",
}

FORMAT_NAMES = {
    ".jpg": "JPEG", ".jpeg": "JPEG", ".jpe": "JPEG", ".heic": "HEIC", ".heif": "HEIF", ".png": "PNG",
    ".webp": "WebP", ".tif": "TIFF", ".tiff": "TIFF", ".bmp": "BMP", ".gif": "GIF", ".mp4": "MP4",
    ".mov": "MOV (QuickTime)", ".avi": "AVI", ".mkv": "MKV", ".m4v": "M4V", ".wmv": "WMV", ".3gp": "3GP",
}


def device_name(make: str | None, model: str | None) -> str | None:
    """„Apple” + „iPhone 15 Pro” -> „Apple iPhone 15 Pro”; pomija markę powtórzoną w modelu."""
    if model and make and make.split()[0].lower() in model.lower():
        return model
    return " ".join(x for x in (make, model) if x) or None


class MetadataPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MetaPanel")
        self.row = None
        self.expanded = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 8, 6, 2)
        lay.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.name = QLabel()
        self.name.setObjectName("MetaName")
        self.name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.when = QLabel()
        self.when.setObjectName("Muted")
        top.addWidget(self.name)
        top.addWidget(self.when)
        self.when.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        top.addStretch(1)
        self.chips_box = QHBoxLayout()
        self.chips_box.setSpacing(6)
        top.addLayout(self.chips_box)
        self.btn_map = QPushButton("Pokaż na mapie")
        self.btn_map.setObjectName("Link")
        self.btn_map.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_map.clicked.connect(self._open_map)
        top.addWidget(self.btn_map)
        self.btn_more = QToolButton()
        self.btn_more.setToolTip("Więcej informacji")
        self.btn_more.setCheckable(True)
        self.btn_more.toggled.connect(self._toggle)
        top.addWidget(self.btn_more)
        lay.addLayout(top)

        self.details = QWidget()
        self.grid = QGridLayout(self.details)
        self.grid.setContentsMargins(0, 4, 0, 4)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(5)
        self.details.hide()
        lay.addWidget(self.details)
        self._chip_widgets: list[QWidget] = []
        self.refresh_theme()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._fit_chips()

    def _fit_chips(self) -> None:
        """Ukrywa mniej ważne informacje, gdy okno jest wąskie (zamiast ucinać tekst)."""
        for w in (self.name, self.when, self.btn_map, self.btn_more, *self._chip_widgets):
            w.ensurePolished()
        used = (self.name.sizeHint().width() + self.when.sizeHint().width() + self.btn_more.sizeHint().width()
                + (self.btn_map.sizeHint().width() if not self.btn_map.isHidden() else 0) + 60)
        avail = self.width() - used - 10 * 4  # odstępy między elementami
        order = sorted(self._chip_widgets, key=lambda w: w.property("prio") or 0)
        for w in order:
            need = w.sizeHint().width() + 6
            fits = need <= avail
            w.setVisible(fits)
            if fits:
                avail -= need

    def refresh_theme(self) -> None:
        self.btn_more.setIcon(icons.icon("info", theme.current()["text2"], 18))

    def _toggle(self, on: bool) -> None:
        self.expanded = on
        self.details.setVisible(on)

    def clear(self) -> None:
        self.row = None
        self.name.setText("")
        self.when.setText("")
        self._set_chips([])
        self.btn_map.hide()
        self.btn_more.hide()
        self._fill_grid([])

    def set_device_entry(self, e, device_name: str) -> None:
        """Plik jeszcze na telefonie — pokazujemy to, co wiadomo bez kopiowania."""
        self.row = None
        self.btn_more.show()
        self.btn_more.setChecked(False)
        self.name.setText(e.name)
        self.name.setToolTip(f"{device_name}/{e.rel}")
        from app.utils.formatting import datetime_pl
        dt = None
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(e.modified.strip()).astimezone().replace(tzinfo=None) if e.modified else None
        except (ValueError, OSError):
            dt = None
        self.when.setText(f"na telefonie · {datetime_pl(dt)}" if dt else "na telefonie")
        chips = [("phone", device_name)]
        if e.size:
            chips.append((None, human_size(e.size)))
        chips.append((None, FORMAT_NAMES.get(os.path.splitext(e.name)[1].lower(),
                                             os.path.splitext(e.name)[1].upper().lstrip("."))))
        self._set_chips(chips)
        self.btn_map.hide()
        self._fill_grid([
            ("Plik", e.name), ("Na telefonie", f"{device_name}/{e.rel}"),
            ("Data na telefonie", datetime_pl(dt) if dt else NO_DATA), ("Rozmiar", human_size(e.size or None)),
            ("Status", "jeszcze nie skopiowany — przeciągnij do folderu, aby zapisać na komputerze"),
        ])

    def set_row(self, row) -> None:
        self.row = row
        if row is None:
            self.clear()
            return
        self.btn_more.show()
        taken = parse_iso(row["taken_at"])
        self.name.setText(row["filename"])
        self.name.setToolTip(row["rel_path"])
        if taken:
            self.when.setText(f"{date_pl(taken)}  ·  {taken.strftime('%H:%M')}")
        elif row["meta_status"] == 0:
            self.when.setText("Odczytywanie informacji…")
        else:
            self.when.setText("Data wykonania: brak danych")

        chips = []
        if row["place"]:
            chips.append(("map_pin", row["place"]))
        elif row["lat"] is not None:
            chips.append(("map_pin", f"{row['lat']:.4f}, {row['lon']:.4f}"))
        cam = device_name(row["make"], row["model"])
        if cam:
            chips.append(("camera", cam))
        if row["width"] and row["height"]:
            mp = row["width"] * row["height"] / 1_000_000
            res = f"{row['width']}×{row['height']}"
            chips.append((None, res + (f"  ({mp:.0f} MP)".replace(".", ",") if row["kind"] == "photo" and mp >= 1 else "")))
        if row["kind"] == "video" and row["duration"]:
            chips.append(("clock", human_duration(row["duration"]) + (f"  ·  {row['fps']:g} kl/s" if row["fps"] else "")))
        chips.append((None, human_size(row["size"])))
        chips.append((None, FORMAT_NAMES.get((row["ext"] or "").lower(), (row["ext"] or "").upper().lstrip("."))))
        self._set_chips(chips)
        self.btn_map.setVisible(row["lat"] is not None)

        src = SOURCE_TEXT.get(row["taken_source"] or "", "")
        items = [
            ("Data wykonania", (date_pl(taken) + (f"  ({src})" if src else "")) if taken else NO_DATA),
            ("Godzina wykonania", time_pl(taken) if taken else NO_DATA),
            ("Utworzenie pliku (Windows)", datetime_pl(ts_to_dt(row["file_created"]))),
            ("Modyfikacja pliku (Windows)", datetime_pl(ts_to_dt(row["file_modified"]))),
            ("Import do biblioteki (PhotoSort)", datetime_pl(ts_to_dt(row["imported_at"]))),
            ("Lokalizacja", row["place"] or NO_DATA),
            ("Współrzędne GPS", f"{row['lat']:.6f}, {row['lon']:.6f}" if row["lat"] is not None else NO_DATA),
            ("Urządzenie", device_name(row["make"], row["model"]) or NO_DATA),
            ("Rozdzielczość", f"{row['width']} × {row['height']} px" if row["width"] else NO_DATA),
            ("Rozmiar pliku", human_size(row["size"])),
            ("Format", FORMAT_NAMES.get((row["ext"] or "").lower(), row["ext"] or NO_DATA)),
            ("Folder", row["folder"]),
        ]
        if row["kind"] == "video":
            items.insert(10, ("Długość filmu", human_duration(row["duration"]) if row["duration"] else NO_DATA))
            items.insert(11, ("Klatki na sekundę", f"{row['fps']:g}" if row["fps"] else NO_DATA))
        self._fill_grid(items)

    def _set_chips(self, chips) -> None:
        for w in self._chip_widgets:
            # usuń natychmiast z układu (samo deleteLater zostawiało je na chwilę widoczne — podwójne „chipy”)
            w.hide()
            self.chips_box.removeWidget(w)
            w.deleteLater()
        self._chip_widgets = []
        c = theme.current()["text2"]
        for prio, (icon_name, text) in enumerate(chips):
            if icon_name:
                w = _IconChip(icon_name, text, c)
            else:
                w = QLabel(text)
                w.setObjectName("Chip")
                w.setContentsMargins(9, 3, 9, 3)
                w.setToolTip(text)
            w.setProperty("prio", prio)
            w.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)  # chowamy zamiast ściskać
            self.chips_box.addWidget(w)
            self._chip_widgets.append(w)
        self._fit_chips()
        QTimer.singleShot(0, self._fit_chips)  # ponownie, gdy style i czcionki są już nałożone

    def _fill_grid(self, items) -> None:
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        cols = 3
        for i, (k, v) in enumerate(items):
            r, c = divmod(i, cols)
            kl = QLabel(k)
            kl.setObjectName("MetaKey")
            vl = QLabel(str(v))
            vl.setObjectName("MetaValue")
            vl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            box = QVBoxLayout()
            box.setSpacing(0)
            box.addWidget(kl)
            box.addWidget(vl)
            holder = QWidget()
            holder.setLayout(box)
            box.setContentsMargins(0, 0, 0, 0)
            self.grid.addWidget(holder, r, c)

    def _open_map(self) -> None:
        if self.row is not None and self.row["lat"] is not None:
            QDesktopServices.openUrl(QUrl(map_url(self.row["lat"], self.row["lon"])))


class _IconChip(QFrame):
    def __init__(self, icon_name: str, text: str, color: str):
        super().__init__()
        self.setObjectName("IconChip")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 2, 9, 2)
        lay.setSpacing(5)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, 13, color))
        ic.setStyleSheet("background: transparent; padding: 0;")
        t = QLabel(text)
        t.setStyleSheet("background: transparent; padding: 0;")
        t.setObjectName("Muted")
        lay.addWidget(ic)
        lay.addWidget(t)
        self.setToolTip(text)
        self.setStyleSheet(f"#IconChip {{ background: {theme.current()['surface2']}; border-radius: 9px; }}")
