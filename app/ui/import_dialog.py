"""Okna importu: wybór źródła, urządzenie USB (telefon/aparat), postęp importu."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPlainTextEdit, QProgressBar, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from app.constants import MEDIA_EXTENSIONS, UNSORTED_FOLDER
from app.core.import_manager import ImportStats
from app.core.library_manager import Library
from app.core.workers import ImportWorker
from app.services import device_service
from app.ui import icons, theme
from app.utils.formatting import count_pl, format_int, human_size

DEVICE_HELP = """<b>Jak podłączyć telefon lub aparat</b>
<ol style="margin-left:-20px">
<li><b>iPhone:</b> podłącz kablem USB i <b>odblokuj</b> telefon. Na ekranie iPhone'a stuknij
<b>„Ufaj temu komputerowi”</b> (lub „Zezwól”) i wpisz kod.</li>
<li>Jeśli iPhone się nie pojawia, zainstaluj ze sklepu Microsoft Store aplikację
<b>„Urządzenia Apple”</b> (Apple Devices) lub iTunes — zawiera sterownik — a potem odłącz i podłącz telefon ponownie.</li>
<li><b>Android:</b> po podłączeniu rozwiń pasek powiadomień na telefonie i wybierz
<b>„Przesyłanie plików”</b> (MTP).</li>
<li><b>Aparat / karta SD / pendrive</b> z literą dysku (np. E:) — wybierz w poprzednim kroku
„Folder na komputerze lub pendrive”.</li>
</ol>
<p>PhotoSort wyłącznie <b>kopiuje</b> pliki — niczego nie usuwa ani nie zmienia na telefonie.</p>
<p style="color:gray">Wskazówka dla iPhone'a: w Ustawienia → Zdjęcia → „Przenieś na Mac lub PC” wybierz
„Zachowaj oryginały”, aby skopiować oryginalne pliki HEIC/MOV. Gdy import z telefonu nie działa,
możesz też skopiować zdjęcia aplikacją „Zdjęcia” systemu Windows, a następnie wskazać folder z kopiami.</p>"""


class ImportSourceDialog(QDialog):
    """Zwraca wybór: ('folder', [ścieżka]) | ('files', [...]) | ('device', None)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Importuj zdjęcia i filmy")
        self.setMinimumWidth(600)
        self.choice: tuple[str, list[Path] | None] | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 20)
        lay.setSpacing(12)
        t = QLabel("Importuj zdjęcia i filmy")
        t.setObjectName("Title")
        lay.addWidget(t)
        s = QLabel(f"Pliki zostaną <b>skopiowane</b> do folderu „{UNSORTED_FOLDER}”. Oryginały pozostaną "
                   "nietknięte, a duplikaty zostaną pominięte.")
        s.setObjectName("Muted")
        s.setWordWrap(True)
        lay.addWidget(s)
        lay.addSpacing(4)
        from app.ui.welcome import ChoiceButton
        for key, icon, title, sub in (
            ("device", "phone", "Telefon lub aparat (USB)",
             "Sortuj prosto z telefonu albo zaimportuj — iPhone, Android, aparat"),
            ("folder", "computer", "Folder na komputerze lub pendrive", "Folder, karta SD, dysk zewnętrzny"),
            ("files", "files", "Wybrane pliki", "Zaznacz pojedyncze zdjęcia lub filmy"),
        ):
            b = ChoiceButton(icon, title, sub)
            b.clicked.connect(lambda _=False, k=key: self._choose(k))
            lay.addWidget(b)
        self.recursive = QCheckBox("Uwzględnij podfoldery")
        self.recursive.setChecked(True)
        lay.addWidget(self.recursive)
        lim = QHBoxLayout()
        lim.setSpacing(8)
        self.use_limit = QCheckBox("Tylko")
        self.use_limit.setToolTip("Tryb próbny — np. aby sprawdzić import z telefonu bez kopiowania wszystkich zdjęć")
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(1, 100000)
        self.limit_spin.setValue(15)
        self.limit_spin.setEnabled(False)
        self.limit_spin.setFixedWidth(80)
        self.limit_spin.setToolTip("Wpisz liczbę lub zmień kółkiem myszy")
        self.use_limit.toggled.connect(self.limit_spin.setEnabled)
        lim_lbl = QLabel("najnowszych zdjęć i filmów (np. na próbę)")
        lim.addWidget(self.use_limit)
        lim.addWidget(self.limit_spin)
        lim.addWidget(lim_lbl)
        lim.addStretch(1)
        lay.addLayout(lim)
        lim_hint = QLabel("Dotyczy importu i trybu „Sortuj prosto z telefonu”. Zdjęcia, które już są "
                          "w bibliotece, nie liczą się do limitu — następnym razem dostaniesz kolejne.")
        lim_hint.setObjectName("Faint")
        lim_hint.setWordWrap(True)
        lay.addWidget(lim_hint)
        tip = QLabel("Możesz też po prostu przeciągnąć pliki lub foldery z Eksploratora do okna PhotoSort.")
        tip.setObjectName("Faint")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Anuluj")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        lay.addLayout(row)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.adjustSize()  # wysokość z uwzględnieniem zawijanego tekstu (różne skalowanie DPI)

    @property
    def limit(self) -> int | None:
        return self.limit_spin.value() if self.use_limit.isChecked() else None

    def _choose(self, key: str) -> None:
        if key == "device":
            self.choice = ("device", None)
            self.accept()
        elif key == "folder":
            d = QFileDialog.getExistingDirectory(self, "Wybierz folder ze zdjęciami i filmami")
            if d:
                self.choice = ("folder", [Path(d)])
                self.accept()
        else:
            exts = " ".join(f"*{e}" for e in sorted(MEDIA_EXTENSIONS))
            files, _ = QFileDialog.getOpenFileNames(self, "Wybierz zdjęcia i filmy", "",
                                                    f"Zdjęcia i filmy ({exts});;Wszystkie pliki (*.*)")
            if files:
                self.choice = ("files", [Path(f) for f in files])
                self.accept()


class DeviceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import z telefonu lub aparatu")
        self.setMinimumWidth(660)  # wysokość dobiera układ (sztywne minimum blokuje powiększanie okna)
        self.device: str | None = None
        self.mode = "import"     # import | browse (sortuj prosto z telefonu)
        self.folders: list[str] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 18)
        lay.setSpacing(10)
        t = QLabel("Telefon lub aparat (USB)")
        t.setObjectName("Title")
        lay.addWidget(t)
        # instrukcja zwinięta — rozwija się sama, gdy nie znaleziono telefonu
        self.help_btn = QPushButton("Jak podłączyć telefon?")
        self.help_btn.setObjectName("Link")
        self.help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.help_btn.clicked.connect(lambda: self._show_help(not self.help_.isVisible()))
        lay.addWidget(self.help_btn, 0, Qt.AlignmentFlag.AlignLeft)
        # pole z przewijaniem o stałej wysokości — długi tekst nie może nachodzić na resztę okna
        from PySide6.QtWidgets import QTextBrowser
        self.help_ = QTextBrowser()
        self.help_.setHtml(DEVICE_HELP)
        self.help_.setFixedHeight(230)
        self.help_.setOpenExternalLinks(False)
        self.help_.hide()
        lay.addWidget(self.help_)

        row = QHBoxLayout()
        dl = QLabel("Podłączone urządzenia")
        dl.setObjectName("SectionTitle")
        row.addWidget(dl)
        row.addStretch(1)
        self.refresh_btn = QPushButton("Odśwież")
        self.refresh_btn.setIcon(icons.icon("refresh", theme.current()["text"], 16))
        self.refresh_btn.clicked.connect(self.refresh)
        row.addWidget(self.refresh_btn)
        lay.addLayout(row)
        self.devices = QListWidget()
        self.devices.setObjectName("Plain")
        self.devices.setMaximumHeight(110)
        self.devices.currentItemChanged.connect(self._device_selected)
        lay.addWidget(self.devices)
        fl = QLabel("Foldery do zaimportowania")
        fl.setObjectName("SectionTitle")
        lay.addWidget(fl)
        self.folder_list = QListWidget()
        self.folder_list.setObjectName("Plain")
        lay.addWidget(self.folder_list, 1)
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        br = QHBoxLayout()
        br.addStretch(1)
        cancel = QPushButton("Anuluj")
        cancel.clicked.connect(self.reject)
        self.import_btn = QPushButton("Importuj do „Do posortowania”")
        self.import_btn.setToolTip("Skopiuj zdjęcia z telefonu na komputer (wszystkie lub N najnowszych), "
                                   "a potem sortuj je na komputerze")
        self.import_btn.setEnabled(False)
        self.import_btn.clicked.connect(lambda: self._start("import"))
        self.start = QPushButton("Sortuj prosto z telefonu")
        self.start.setObjectName("Primary")
        self.start.setToolTip("Przeglądaj zdjęcia z telefonu w PhotoSort. Na komputer trafią tylko te, które "
                              "przeciągniesz do folderu — od razu do właściwego folderu.")
        self.start.setEnabled(False)
        self.start.clicked.connect(lambda: self._start("browse"))
        br.addWidget(cancel)
        br.addWidget(self.import_btn)
        br.addWidget(self.start)
        lay.addLayout(br)
        mode_hint = QLabel("<b>Sortuj prosto z telefonu</b> — przeglądasz zdjęcia z telefonu, a na komputer "
                           "kopiowane są tylko te, które przeciągniesz do folderu. Pozostałe nie trafiają na dysk.")
        mode_hint.setObjectName("Muted")
        mode_hint.setWordWrap(True)
        lay.addWidget(mode_hint)
        self.folder_list.itemChanged.connect(lambda _i: self._update_start())

    def showEvent(self, e) -> None:
        super().showEvent(e)
        if self.devices.count() == 0:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(50, self.refresh)

    def refresh(self) -> None:
        self.devices.clear()
        self.folder_list.clear()
        if not device_service.available():
            self.status.setText("Obsługa urządzeń przenośnych jest niedostępna w tym systemie. "
                                "Skopiuj zdjęcia do folderu i wybierz „Folder na komputerze”.")
            return
        self.status.setText("Wyszukiwanie urządzeń…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            names = device_service.list_devices()
        except Exception as exc:
            names = []
            self.status.setText(f"Nie udało się odczytać listy urządzeń: {exc}")
        finally:
            QApplication.restoreOverrideCursor()
        c = theme.current()["accent"]
        for n in names:
            self.devices.addItem(QListWidgetItem(icons.icon("phone", c, 18), n))
        if names:
            self.status.setText("Wybierz urządzenie z listy.")
            self.devices.setCurrentRow(0)
        else:
            self.status.setText("Nie znaleziono telefonu ani aparatu. Sprawdź kabel, odblokuj telefon i "
                                "potwierdź dostęp na jego ekranie, a następnie kliknij „Odśwież”.")
            self._show_help(True)
        self._update_start()

    def _show_help(self, on: bool) -> None:
        self.help_.setVisible(on)
        self.help_btn.setText("Ukryj instrukcję" if on else "Jak podłączyć telefon?")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.adjustSize)

    def _device_selected(self, item) -> None:
        self.folder_list.clear()
        if item is None:
            return
        name = item.text()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            folders = device_service.list_device_folders(name)
        except Exception as exc:
            folders = []
            self.status.setText(f"Brak dostępu do urządzenia: {exc}")
        finally:
            QApplication.restoreOverrideCursor()
        if not folders:
            self.status.setText("Urządzenie nie udostępnia plików. Odblokuj telefon i zezwól na dostęp "
                                "(iPhone: „Ufaj temu komputerowi”; Android: „Przesyłanie plików”), potem „Odśwież”.")
        any_rec = any(r for _f, r in folders)
        for f, rec in folders:
            it = QListWidgetItem(f)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if (rec or not any_rec) else Qt.CheckState.Unchecked)
            self.folder_list.addItem(it)
        if folders:
            self.status.setText("Zaznaczono foldery, w których telefony zwykle przechowują zdjęcia (DCIM, Pictures…).")
        self._update_start()

    def _checked(self) -> list[str]:
        return [self.folder_list.item(i).text() for i in range(self.folder_list.count())
                if self.folder_list.item(i).checkState() == Qt.CheckState.Checked]

    def _update_start(self) -> None:
        ok = self.devices.currentItem() is not None and bool(self._checked())
        self.start.setEnabled(ok)
        self.import_btn.setEnabled(ok)

    def _start(self, mode: str = "import") -> None:
        self.mode = mode
        self.device = self.devices.currentItem().text()
        self.folders = self._checked()
        self.accept()


class ImportProgressDialog(QDialog):
    finished_ok = Signal(object)

    def __init__(self, library: Library, parent=None, paths: list[Path] | None = None, recursive: bool = True,
                 device: str | None = None, device_folders: list[str] | None = None,
                 limit: int | None = None):
        super().__init__(parent)
        self.limit = limit
        self.setWindowTitle("Import")
        self.setMinimumWidth(520)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 18)
        lay.setSpacing(10)
        self.title = QLabel("Importowanie…")
        self.title.setObjectName("Title")
        lay.addWidget(self.title)
        self.sub = QLabel("Przygotowywanie listy plików…")
        self.sub.setObjectName("Muted")
        self.sub.setWordWrap(True)
        lay.addWidget(self.sub)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        lay.addWidget(self.bar)
        self.counts = QLabel("")
        lay.addWidget(self.counts)
        self.current = QLabel("")
        self.current.setObjectName("Faint")
        lay.addWidget(self.current)
        self.errors = QPlainTextEdit()
        self.errors.setReadOnly(True)
        self.errors.setMaximumHeight(140)
        self.errors.hide()
        lay.addWidget(self.errors)
        row = QHBoxLayout()
        row.addStretch(1)
        self.cancel_btn = QPushButton("Przerwij")
        self.cancel_btn.clicked.connect(self._cancel)
        self.close_btn = QPushButton("Gotowe")
        self.close_btn.setObjectName("Primary")
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.hide()
        row.addWidget(self.cancel_btn)
        row.addWidget(self.close_btn)
        lay.addLayout(row)
        label = f"urządzenie: {device}" if device else ", ".join(str(p) for p in (paths or [])[:3])
        self.worker = ImportWorker(library, paths, recursive, device, device_folders, label, limit)
        self.worker.progress.connect(self._progress)
        self.worker.finished_import.connect(self._done)
        self.stats: ImportStats | None = None
        self.device = device

    def start(self) -> None:
        self.worker.start()

    def _cancel(self) -> None:
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("Przerywanie…")
        self.worker.cancel()

    def _progress(self, d: dict) -> None:
        total, done = d["total"], d["processed"]
        if d["phase"] == "scan":
            self.bar.setRange(0, 0)
            self.sub.setText(f"Wyszukiwanie zdjęć i filmów{' na urządzeniu' if self.device else ''}… "
                             f"znaleziono {format_int(total)}")
        else:
            if d.get("limit"):
                lim = min(d["limit"], max(total, 1))
                self.bar.setRange(0, lim)
                self.bar.setValue(min(d["copied"], lim))
                self.sub.setText(f"Tryb próbny: kopiowanie {format_int(d['copied'])} z {format_int(lim)} "
                                 f"najnowszych nowych plików (przejrzano {format_int(done)} z {format_int(total)})")
            else:
                self.bar.setRange(0, max(total, 1))
                self.bar.setValue(done)
                self.sub.setText(f"Kopiowanie {format_int(done)} z {format_int(total)}")
        self.counts.setText(f"Skopiowano: <b>{format_int(d['copied'])}</b>   ·   Pominięte duplikaty: "
                            f"<b>{format_int(d['duplicates'])}</b>   ·   Błędy: <b>{format_int(d['errors'])}</b>")
        self.current.setText(d.get("current") or "")

    def _done(self, stats: ImportStats) -> None:
        self.stats = stats
        self.bar.setRange(0, 1)
        self.bar.setValue(1)
        self.cancel_btn.hide()
        self.close_btn.show()
        self.current.setText("")
        dup = stats.duplicates + stats.skipped_known
        if stats.aborted_reason:
            self.title.setText("Import zatrzymany")
            self.sub.setText(stats.aborted_reason)
            self.sub.setObjectName("Error")
            self.sub.style().unpolish(self.sub)
            self.sub.style().polish(self.sub)
        elif stats.total == 0:
            self.title.setText("Nie znaleziono plików")
            self.sub.setText("We wskazanym miejscu nie ma obsługiwanych zdjęć ani filmów.")
        else:
            self.title.setText("Import zakończony")
            self.sub.setText(f"Dodano {count_pl(stats.copied, 'nowy plik', 'nowe pliki', 'nowych plików')} "
                             f"({human_size(stats.bytes_copied)}) do folderu „{UNSORTED_FOLDER}”."
                             + (f" Osiągnięto limit próbny ({stats.limit}) — pozostałe pliki nie zostały "
                                "skopiowane. Uruchom import ponownie, aby dodać kolejne." if stats.limit_reached else ""))
        self.counts.setText(f"Skopiowano: <b>{format_int(stats.copied)}</b>   ·   Pominięte duplikaty: "
                            f"<b>{format_int(dup)}</b>   ·   Błędy: <b>{format_int(len(stats.errors))}</b>")
        if stats.errors:
            self.errors.setPlainText("\n".join(stats.errors))
            self.errors.show()
        self.finished_ok.emit(stats)

    def reject(self) -> None:
        if self.worker.isRunning():
            self._cancel()
            return
        super().reject()
