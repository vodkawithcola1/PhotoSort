"""Ustawienia programu i biblioteki (celowo nieliczne)."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QDialog, QHBoxLayout, QLabel, QListWidget, QPushButton,
                               QRadioButton, QVBoxLayout)

from app.constants import APP_NAME, APP_VERSION
from app.core.library_controller import LibraryController
from app.services.metadata_service import find_exiftool
from app.ui import theme
from app.utils.paths import reveal_in_explorer


class SettingsDialog(QDialog):
    theme_selected = Signal(str)

    def __init__(self, ctrl: LibraryController | None, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.setWindowTitle("Ustawienia")
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 20)
        lay.setSpacing(10)
        t = QLabel("Ustawienia")
        t.setObjectName("Title")
        lay.addWidget(t)

        lay.addWidget(self._section("WYGLĄD"))
        row = QHBoxLayout()
        self.group = QButtonGroup(self)
        for key, text in (("light", "Jasny motyw"), ("dark", "Ciemny motyw")):
            rb = QRadioButton(text)
            rb.setChecked(theme.current()["name"] == key)
            rb.toggled.connect(lambda on, k=key: on and self.theme_selected.emit(k))
            self.group.addButton(rb)
            row.addWidget(rb)
        row.addStretch(1)
        lay.addLayout(row)

        if ctrl is not None:
            lay.addWidget(self._section("BIBLIOTEKA"))
            info = QLabel(f"<b>{ctrl.lib.name}</b><br><span style='color:gray'>{ctrl.lib.root}</span>")
            info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            info.setWordWrap(True)
            lay.addWidget(info)
            br = QHBoxLayout()
            b1 = QPushButton("Otwórz folder biblioteki")
            b1.clicked.connect(lambda: reveal_in_explorer(ctrl.lib.root))
            b2 = QPushButton("Odśwież (wykryj zmiany na dysku)")
            b2.setToolTip("Wykrywa pliki i foldery dodane lub usunięte poza programem PhotoSort")
            b2.clicked.connect(self._rescan)
            br.addWidget(b1)
            br.addWidget(b2)
            br.addStretch(1)
            lay.addLayout(br)
            self.rescan_info = QLabel("")
            self.rescan_info.setObjectName("Muted")
            lay.addWidget(self.rescan_info)

            lay.addWidget(self._section("HISTORIA PRZENIESIEŃ"))
            hist = QListWidget()
            hist.setObjectName("Plain")
            hist.setMaximumHeight(180)
            for mv in ctrl.mm.history(300):
                when = time.strftime("%d.%m.%Y %H:%M", time.localtime(mv["ts"]))
                src = mv["src_rel"].split("/", 1)[0]
                dst_folder, name = mv["dst_rel"].split("/", 1)
                state = "  (cofnięte)" if mv["state"] == "undone" else ""
                hist.addItem(f"{when}   {name}:  {src}  →  {dst_folder}{state}")
            if hist.count() == 0:
                hist.addItem("Brak przeniesionych plików.")
            lay.addWidget(hist)

        lay.addWidget(self._section("INFORMACJE"))
        exe = find_exiftool()
        meta_txt = (f"Odczyt metadanych: wbudowany (Pillow, pillow-heif, FFmpeg)"
                    + (f" + ExifTool ({exe})" if exe else ". ExifTool nie jest wymagany — jeśli umieścisz "
                       "exiftool.exe w folderze „tools” obok programu, zostanie użyty automatycznie."))
        about = QLabel(f"{APP_NAME} {APP_VERSION}<br>{meta_txt}<br>"
                       "Miasta i kraje ustalane są offline na podstawie danych GeoNames (CC BY 4.0, geonames.org). "
                       "Przycisk „Pokaż na mapie” otwiera OpenStreetMap w przeglądarce.<br>"
                       "Program nie wysyła żadnych danych przez internet.")
        about.setWordWrap(True)
        about.setObjectName("Muted")
        lay.addWidget(about)

        row2 = QHBoxLayout()
        row2.addStretch(1)
        close = QPushButton("Zamknij")
        close.setObjectName("Primary")
        close.clicked.connect(self.accept)
        row2.addWidget(close)
        lay.addLayout(row2)

    def _section(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setObjectName("SectionTitle")
        l.setContentsMargins(0, 8, 0, 0)
        return l

    def _rescan(self) -> None:
        if self.ctrl:
            self.ctrl.rescan()
            self.rescan_info.setText("Odświeżanie biblioteki w tle…")
