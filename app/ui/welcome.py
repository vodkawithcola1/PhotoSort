"""Ekran powitalny oraz okno tworzenia nowej biblioteki."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QPushButton, QSizePolicy, QToolButton, QVBoxLayout,
                               QWidget)

from app.constants import APP_NAME
from app.core.library_manager import is_library
from app.ui import icons, theme
from app.utils.paths import desktop_dir, validate_folder_name


class NewLibraryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nowa biblioteka")
        self.setMinimumWidth(520)
        self.location = desktop_dir()
        self.result_path: Path | None = None
        self.open_existing: Path | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 20)
        lay.setSpacing(10)
        t = QLabel("Nowa biblioteka")
        t.setObjectName("Title")
        lay.addWidget(t)
        s = QLabel("Biblioteka to folder, w którym będą Twoje posortowane zdjęcia i filmy.")
        s.setObjectName("Muted")
        s.setWordWrap(True)
        lay.addWidget(s)
        lay.addSpacing(4)
        k = QLabel("Nazwa biblioteki")
        k.setObjectName("SectionTitle")
        lay.addWidget(k)
        self.name = QLineEdit()
        self.name.setPlaceholderText("np. Zdjęcia mamy")
        self.name.textChanged.connect(self._update)
        lay.addWidget(self.name)
        k2 = QLabel("Lokalizacja")
        k2.setObjectName("SectionTitle")
        lay.addWidget(k2)
        row = QHBoxLayout()
        self.loc_label = QLabel()
        self.loc_label.setWordWrap(True)
        row.addWidget(self.loc_label, 1)
        ch = QPushButton("Zmień…")
        ch.clicked.connect(self._choose)
        row.addWidget(ch)
        lay.addLayout(row)
        self.preview = QLabel()
        self.preview.setObjectName("Muted")
        self.preview.setWordWrap(True)
        lay.addWidget(self.preview)
        self.err = QLabel()
        self.err.setObjectName("Error")
        self.err.setWordWrap(True)
        lay.addWidget(self.err)
        self.open_btn = QPushButton("Otwórz istniejącą bibliotekę")
        self.open_btn.hide()
        self.open_btn.clicked.connect(self._open_existing)
        lay.addWidget(self.open_btn, 0, Qt.AlignmentFlag.AlignLeft)
        br = QHBoxLayout()
        br.addStretch(1)
        cancel = QPushButton("Anuluj")
        cancel.clicked.connect(self.reject)
        self.ok = QPushButton("Utwórz bibliotekę")
        self.ok.setObjectName("Primary")
        self.ok.setDefault(True)
        self.ok.clicked.connect(self._create)
        br.addWidget(cancel)
        br.addWidget(self.ok)
        lay.addLayout(br)
        self._update()

    def _choose(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Gdzie utworzyć bibliotekę?", str(self.location))
        if d:
            self.location = Path(d)
            self._update()

    def _target(self) -> Path:
        return self.location / self.name.text().strip()

    def _update(self) -> None:
        loc = str(self.location)
        is_desk = os.path.normcase(loc) == os.path.normcase(str(desktop_dir()))
        self.loc_label.setText(("Pulpit  —  " if is_desk else "") + loc)
        name = self.name.text().strip()
        self.open_btn.hide()
        if not name:
            self.preview.setText("")
            self.err.setText("")
            self.ok.setEnabled(False)
            return
        msg = validate_folder_name(name)
        target = self._target()
        if msg is None and target.exists():
            if is_library(target):
                msg = f"Biblioteka „{name}” już istnieje w tej lokalizacji. Możesz ją otworzyć albo wybrać inną nazwę."
                self.open_btn.show()
            else:
                msg = f"Folder „{name}” już istnieje w tej lokalizacji. Wybierz inną nazwę — " \
                      f"PhotoSort nie nadpisuje istniejących folderów."
        self.err.setText(msg or "")
        self.preview.setText(f"Zostanie utworzony folder:\n{target}" if msg is None else "")
        self.ok.setEnabled(msg is None)

    def _open_existing(self) -> None:
        self.open_existing = self._target()
        self.accept()

    def _create(self) -> None:
        self._update()
        if self.ok.isEnabled():
            self.result_path = self._target()
            self.accept()


class ChoiceButton(QFrame):
    """Duży klikalny kafelek z ikoną, pogrubionym tytułem i wyszarzonym opisem.

    Celowo QFrame, a nie QPushButton: przycisk Qt ignoruje wewnętrzny układ przy
    wyliczaniu wysokości, przez co przy innym skalowaniu DPI tekst był ucinany.
    """
    clicked = Signal()

    def __init__(self, icon: str, title: str, sub: str):
        super().__init__()
        self.setObjectName("ChoiceCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.icon_name = icon
        self._pressed = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 10, 18, 10)
        lay.setSpacing(14)
        self.ic = QLabel()
        self.ic.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self.ic)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.t = QLabel()
        self.t.setObjectName("MetaName")
        self.s = QLabel()
        self.s.setObjectName("Muted")
        for w in (self.t, self.s):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            w.setStyleSheet("background: transparent;")
            col.addWidget(w)
        lay.addLayout(col, 1)
        self.arrow = QLabel()
        self.arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self.arrow)
        self.set_text(title, sub)
        self.refresh_theme()

    def set_text(self, title: str, sub: str) -> None:
        self.t.setText(title)
        self.s.setText(sub)
        self.s.setVisible(bool(sub))
        self.setMinimumHeight(self.layout().sizeHint().height())

    def refresh_theme(self) -> None:
        c = theme.current()
        self.ic.setPixmap(icons.pixmap(self.icon_name, 26, c["accent"]))
        self.arrow.setPixmap(icons.pixmap("chevron_right", 18, c["text3"]))

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            e.accept()

    def mouseReleaseEvent(self, e) -> None:
        if self._pressed and e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        self._pressed = False

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
        else:
            super().keyPressEvent(e)


class WelcomeScreen(QWidget):
    new_library = Signal()
    open_library = Signal()
    open_path = Signal(str)
    remove_recent = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WelcomeScreen")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 30, 40, 30)
        outer.addStretch(2)
        center = QHBoxLayout()
        center.addStretch(1)
        col = QVBoxLayout()
        col.setSpacing(10)
        self.logo = QLabel()
        self.logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo.setPixmap(icons.logo_pixmap(96))
        col.addWidget(self.logo)
        h = QLabel(APP_NAME)
        h.setObjectName("H1")
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(h)
        sub = QLabel("Porządkuj rodzinne zdjęcia i filmy — po prostu przeciągnij je do folderu.")
        sub.setObjectName("Muted")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(sub)
        col.addSpacing(22)

        self.btn_last = self._choice("history", "Otwórz ostatnio używaną bibliotekę", "")
        self.btn_last.clicked.connect(lambda: self._recent and self.open_path.emit(self._recent[0]))
        self.btn_new = self._choice("plus", "Utwórz nową bibliotekę", "Nowy folder na Pulpicie (lub w innym miejscu)")
        self.btn_new.clicked.connect(self.new_library)
        self.btn_open = self._choice("open", "Otwórz istniejącą bibliotekę", "Wskaż folder biblioteki PhotoSort")
        self.btn_open.clicked.connect(self.open_library)
        for b in (self.btn_last, self.btn_new, self.btn_open):
            col.addWidget(b)
        col.addSpacing(18)
        self.recent_title = QLabel("OSTATNIE BIBLIOTEKI")
        self.recent_title.setObjectName("SectionTitle")
        col.addWidget(self.recent_title)
        self.recent_list = QListWidget()
        self.recent_list.setObjectName("Plain")
        self.recent_list.setMaximumHeight(170)
        self.recent_list.itemClicked.connect(lambda it: self.open_path.emit(it.data(Qt.ItemDataRole.UserRole)))
        self.recent_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.recent_list.customContextMenuRequested.connect(self._recent_menu)
        col.addWidget(self.recent_list)
        wrap = QWidget()
        wrap.setLayout(col)
        wrap.setFixedWidth(500)
        center.addWidget(wrap)
        center.addStretch(1)
        outer.addLayout(center)
        outer.addStretch(3)
        foot = QHBoxLayout()
        self.theme_btn = QToolButton()
        self.theme_btn.setToolTip("Jasny / ciemny motyw")
        foot.addStretch(1)
        foot.addWidget(self.theme_btn)
        outer.addLayout(foot)
        self._recent: list[str] = []

    def _choice(self, icon: str, title: str, sub: str) -> "ChoiceButton":
        return ChoiceButton(icon, title, sub)

    def _set_choice_text(self, b: "ChoiceButton", title: str, sub: str) -> None:
        b.set_text(title, sub)

    def refresh_theme(self) -> None:
        c = theme.current()
        for b in (self.btn_last, self.btn_new, self.btn_open):
            b.refresh_theme()
        self.theme_btn.setIcon(icons.icon("sun" if c["name"] == "dark" else "moon", c["text2"], 20))
        self.set_recent(self._recent)

    def set_recent(self, paths: list[str]) -> None:
        self._recent = [p for p in paths if is_library(Path(p))]
        self.recent_list.clear()
        c = theme.current()
        for p in self._recent:
            it = QListWidgetItem(icons.icon("library", c["text2"], 18), f"{Path(p).name}\n{p}")
            it.setData(Qt.ItemDataRole.UserRole, p)
            it.setToolTip(p)
            self.recent_list.addItem(it)
        has = bool(self._recent)
        self.btn_last.setVisible(has)
        if has:
            self._set_choice_text(self.btn_last, f"Otwórz „{Path(self._recent[0]).name}”",
                                  "Kontynuuj dokładnie tam, gdzie skończyłeś")
        self.recent_title.setVisible(len(self._recent) > 1)
        self.recent_list.setVisible(len(self._recent) > 1)

    def _recent_menu(self, pos) -> None:
        it = self.recent_list.itemAt(pos)
        if not it:
            return
        m = QMenu(self)
        m.addAction("Usuń z listy (pliki pozostaną na dysku)").triggered.connect(
            lambda: self.remove_recent.emit(it.data(Qt.ItemDataRole.UserRole)))
        m.exec(self.recent_list.viewport().mapToGlobal(pos))
