"""Nagłówek kolejki: wyszukiwanie, typ, sortowanie, filtry, „ten sam dzień”, rozwinięcie siatki."""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QDate, QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDateEdit, QDoubleSpinBox, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QToolButton,
                               QVBoxLayout, QWidget)

from app.constants import SCOPE_ALL, SCOPE_DEVICE
from app.core.library_controller import LibraryController
from app.core.media_manager import Filters
from app.i18n import display_folder, tr
from app.ui import icons, theme
from app.utils.formatting import count_pl, date_pl, month_names, parse_iso

SORT_OPTIONS = [("date", "Data wykonania"), ("name", "Nazwa pliku"), ("imported", "Data importu"),
                ("size", "Rozmiar pliku")]


class FiltersPopup(QFrame):
    applied = Signal(object)

    def __init__(self, ctrl: LibraryController, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.ctrl = ctrl
        self.setObjectName("Popup")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)
        t = QLabel(tr("Filtry"))
        t.setObjectName("H2")
        lay.addWidget(t)
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(8)
        r = 0

        g.addWidget(self._k(tr("Rok")), r, 0)
        self.year = QComboBox()
        g.addWidget(self.year, r, 1)
        g.addWidget(self._k(tr("Miesiąc")), r, 2)
        self.month = QComboBox()
        self.month.addItem(tr("Dowolny"), 0)
        for i, m in enumerate(month_names(), 1):
            self.month.addItem(m.capitalize(), i)
        g.addWidget(self.month, r, 3)
        r += 1

        self.use_range = QCheckBox(tr("Zakres dat"))
        g.addWidget(self.use_range, r, 0)
        self.d_from = QDateEdit()
        self.d_to = QDateEdit()
        for d in (self.d_from, self.d_to):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd.MM.yyyy")
            d.setDate(QDate.currentDate())
        self.use_range.toggled.connect(lambda on: (self.d_from.setEnabled(on), self.d_to.setEnabled(on)))
        g.addWidget(self.d_from, r, 1)
        g.addWidget(self._k(tr("do")), r, 2)
        g.addWidget(self.d_to, r, 3)
        r += 1

        g.addWidget(self._k(tr("Rozmiar od (MB)")), r, 0)
        self.min_size = QDoubleSpinBox()
        self.max_size = QDoubleSpinBox()
        for s in (self.min_size, self.max_size):
            s.setRange(0, 100000)
            s.setDecimals(1)
            s.setSpecialValueText("—")
        g.addWidget(self.min_size, r, 1)
        g.addWidget(self._k(tr("do (MB)")), r, 2)
        g.addWidget(self.max_size, r, 3)
        r += 1

        self.loc_label = self._k(tr("Lokalizacja"))
        g.addWidget(self.loc_label, r, 0)
        self.loc_mode = QComboBox()
        self.loc_mode.addItem(tr("Dowolna"), "")
        self.loc_mode.addItem(tr("Tylko z lokalizacją GPS"), "__gps__")
        self.loc_mode.addItem(tr("Bez lokalizacji"), "__nogps__")
        self.loc_mode.addItem(tr("Miejscowość…"), "__text__")
        g.addWidget(self.loc_mode, r, 1)
        self.loc_text = QLineEdit()
        self.loc_text.setPlaceholderText(tr("np. Kraków"))
        g.addWidget(self.loc_text, r, 2, 1, 2)
        self.loc_mode.currentIndexChanged.connect(
            lambda: self.loc_text.setEnabled(self.loc_mode.currentData() == "__text__"))
        r += 1

        self.status_label = self._k(tr("Status"))
        g.addWidget(self.status_label, r, 0)
        self.status = QComboBox()
        self.status.addItem(tr("Wszystkie"), "all")
        self.status.addItem(tr("Posortowane"), "sorted")
        self.status.addItem(tr("Nieposortowane"), "unsorted")
        g.addWidget(self.status, r, 1)
        self.folder_label = self._k(tr("Folder"))
        g.addWidget(self.folder_label, r, 2)
        self.folder = QComboBox()
        g.addWidget(self.folder, r, 3)
        r += 1
        lay.addLayout(g)

        row = QHBoxLayout()
        clear = QPushButton(tr("Wyczyść filtry"))
        clear.clicked.connect(self._clear)
        row.addWidget(clear)
        row.addStretch(1)
        ok = QPushButton(tr("Zastosuj"))
        ok.setObjectName("Primary")
        ok.clicked.connect(self._apply)
        row.addWidget(ok)
        lay.addLayout(row)

    def _k(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setObjectName("Muted")
        return l

    def load(self, f: Filters) -> None:
        device = self.ctrl.scope == SCOPE_DEVICE
        self.year.clear()
        self.year.addItem(tr("Dowolny"), 0)
        if device:
            years = sorted({int(e.date[:4]) for e in self.ctrl.device_entries.values() if e.date[:4].isdigit()},
                           reverse=True)
        else:
            years = self.ctrl.mm.years()
        for y in years:
            self.year.addItem(str(y), y)
        for w in (self.loc_label, self.loc_mode, self.loc_text):
            w.setVisible(not device)
        self.year.setCurrentIndex(max(0, self.year.findData(f.year)))
        self.month.setCurrentIndex(max(0, self.month.findData(f.month)))
        self.use_range.setChecked(bool(f.date_from or f.date_to))
        if f.date_from:
            self.d_from.setDate(QDate.fromString(f.date_from, "yyyy-MM-dd"))
        if f.date_to:
            self.d_to.setDate(QDate.fromString(f.date_to, "yyyy-MM-dd"))
        self.d_from.setEnabled(self.use_range.isChecked())
        self.d_to.setEnabled(self.use_range.isChecked())
        self.min_size.setValue(f.min_size_mb or 0)
        self.max_size.setValue(f.max_size_mb or 0)
        if f.location in ("", "__gps__", "__nogps__"):
            self.loc_mode.setCurrentIndex(self.loc_mode.findData(f.location))
            self.loc_text.setText("")
        else:
            self.loc_mode.setCurrentIndex(self.loc_mode.findData("__text__"))
            self.loc_text.setText(f.location)
        self.loc_text.setEnabled(self.loc_mode.currentData() == "__text__")
        all_scope = self.ctrl.scope == SCOPE_ALL
        for w in (self.status, self.status_label, self.folder, self.folder_label):
            w.setVisible(all_scope)
        self.status.setCurrentIndex(max(0, self.status.findData(f.status)))
        self.folder.clear()
        self.folder.addItem(tr("Dowolny"), "")
        for name in self.ctrl.lib.folder_dirs():
            self.folder.addItem(display_folder(name), name)
        self.folder.setCurrentIndex(max(0, self.folder.findData(f.folder)))
        self._base = f

    def _collect(self) -> Filters:
        f = replace(self._base)
        f.year = self.year.currentData() or 0
        f.month = self.month.currentData() or 0
        if self.use_range.isChecked():
            a, b = self.d_from.date(), self.d_to.date()
            if a > b:
                a, b = b, a
            f.date_from, f.date_to = a.toString("yyyy-MM-dd"), b.toString("yyyy-MM-dd")
        else:
            f.date_from = f.date_to = ""
        f.min_size_mb = self.min_size.value()
        f.max_size_mb = self.max_size.value()
        mode = self.loc_mode.currentData()
        f.location = self.loc_text.text().strip() if mode == "__text__" else mode
        if self.ctrl.scope == SCOPE_ALL:
            f.status = self.status.currentData()
            f.folder = self.folder.currentData()
        return f

    def _apply(self) -> None:
        self.applied.emit(self._collect())
        self.close()

    def _clear(self) -> None:
        f = Filters(text=self._base.text, kind=self._base.kind)
        self.applied.emit(f)
        self.close()


class QueueHeader(QWidget):
    toggle_expand = Signal()

    def __init__(self, ctrl: LibraryController, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 2, 4, 2)
        outer.setSpacing(6)
        lay = QHBoxLayout()
        lay.setSpacing(6)
        outer.addLayout(lay)
        self._row1 = lay
        # drugi wiersz — używany tylko przy wąskim oknie
        self.row2 = QWidget()
        self._row2 = QHBoxLayout(self.row2)
        self._row2.setContentsMargins(0, 0, 0, 0)
        self._row2.setSpacing(6)
        self._row2.addStretch(1)
        outer.addWidget(self.row2)
        self.row2.hide()
        self._level = 0
        self.title = QLabel()
        self.title.setObjectName("H2")
        self.count = QLabel()
        self.count.setObjectName("Muted")
        lay.addWidget(self.title)
        lay.addWidget(self.count)
        lay.addStretch(1)

        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText(tr("Szukaj po nazwie pliku"))
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(210)
        self.search_icon = QLabel(self.search)
        self.search_icon.setGeometry(9, 8, 16, 16)
        self.search_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(self._apply_search)
        self.search.textChanged.connect(lambda _t: self._search_timer.start())
        lay.addWidget(self.search)

        self.kind_group = QButtonGroup(self)
        self.kind_btns = {}
        for key, text in (("all", tr("Wszystko")), ("photo", tr("Zdjęcia")), ("video", tr("Filmy"))):
            b = QToolButton()
            b.setText(text)
            b.setObjectName("Pill")
            b.setCheckable(True)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            self.kind_group.addButton(b)
            self.kind_btns[key] = b
            b.clicked.connect(lambda _=False, k=key: self._set_kind(k))
            lay.addWidget(b)

        self.sort = QComboBox()
        for key, text in SORT_OPTIONS:
            self.sort.addItem(tr(text), key)  # i18n: ignore
        self.sort.setToolTip(tr("Sortowanie"))
        self.sort.activated.connect(self._sort_changed)
        lay.addWidget(self.sort)
        self.order = QToolButton()
        self.order.clicked.connect(self._toggle_order)
        lay.addWidget(self.order)

        self.same_day = QToolButton()
        self.same_day.setObjectName("Pill")
        self.same_day.setText(tr("Ten sam dzień"))
        self.same_day.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.same_day.setCheckable(True)
        self.same_day.setToolTip(tr("Pokaż wszystkie zdjęcia i filmy z dnia, w którym wykonano bieżący plik"))
        self.same_day.clicked.connect(self._toggle_same_day)
        lay.addWidget(self.same_day)

        self.filters_btn = QToolButton()
        self.filters_btn.setObjectName("Pill")
        self.filters_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.filters_btn.setText(tr("Filtry"))
        self.filters_btn.clicked.connect(self._open_filters)
        lay.addWidget(self.filters_btn)

        self.expand_btn = QToolButton()
        self.expand_btn.setToolTip(tr("Rozwiń / zwiń siatkę miniatur"))
        self.expand_btn.clicked.connect(self.toggle_expand)
        lay.addWidget(self.expand_btn)

        # pasek aktywnych filtrów
        self.chips = QWidget()
        cl = QHBoxLayout(self.chips)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)
        self.chips_text = QLabel()
        self.chips_text.setObjectName("FilterChip")
        cl.addWidget(self.chips_text)
        clear = QPushButton(tr("Wyczyść filtry"))
        clear.setObjectName("Link")
        clear.setCursor(Qt.CursorShape.PointingHandCursor)
        clear.clicked.connect(lambda: self.ctrl.set_filters(Filters()))
        cl.addWidget(clear)
        cl.addStretch(1)
        outer.addWidget(self.chips)

        self.popup = FiltersPopup(ctrl, self)
        self.popup.applied.connect(self.ctrl.set_filters)
        ctrl.queue_reset.connect(self.sync)
        ctrl.queue_removed.connect(lambda _ids: self.sync())
        ctrl.scope_changed.connect(lambda _s: self.sync())
        self.expanded = False
        self.refresh_theme()
        self.sync()

    def refresh_theme(self) -> None:
        c = theme.current()
        self.search_icon.setPixmap(icons.pixmap("search", 16, c["text3"]))
        self.same_day.setIcon(icons.icon("same_day", c["text2"], 16))
        self.filters_btn.setIcon(icons.icon("filter", c["text2"], 16))
        self.expand_btn.setIcon(icons.icon("chevron_down" if self.expanded else "chevron_up", c["text"], 20))
        self.order.setIcon(icons.icon("chevron_up" if self.ctrl.state.ascending else "chevron_down", c["text2"], 16))
        self.order.setToolTip(tr("Rosnąco (od najstarszych)") if self.ctrl.state.ascending
                               else tr("Malejąco (od najnowszych)"))

    def set_compact(self, level: int) -> None:
        """0 = pełny, 1 = węższy, 2 = wąski (sortowanie i filtry w drugim wierszu)."""
        if level != self._level:
            movable = [self.sort, self.order, self.same_day, self.filters_btn]
            if level == 2:
                for w in movable:
                    self._row2.addWidget(w)
            else:
                pos = self._row1.indexOf(self.expand_btn)
                for i, w in enumerate(movable):
                    self._row1.insertWidget(pos + i, w)
            self.row2.setVisible(level == 2)
            self._level = level
        self.search.setFixedWidth({0: 210, 1: 160, 2: 130}[level])
        self.same_day.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly if level == 1
                                         else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

    def set_expanded(self, on: bool) -> None:
        self.expanded = on
        self.refresh_theme()

    def sync(self) -> None:
        ctrl = self.ctrl
        scope = ctrl.scope
        device = scope == SCOPE_DEVICE
        if device:
            self.title.setText(tr("Telefon"))   # pełna nazwa urządzenia jest w nawigacji u góry
            self.title.setToolTip(ctrl.device_name)
        else:
            self.title.setText(tr("Wszystkie multimedia") if scope == SCOPE_ALL else display_folder(scope))
        self.update_position()
        # w trybie telefonu: lista od najnowszych, bez filtrów dat/lokalizacji (metadane nieznane przed kopiowaniem)
        for w in (self.sort, self.order):
            w.setEnabled(not device)
        self.sort.setToolTip(tr("Zdjęcia z telefonu są ułożone od najnowszych") if device else tr("Sortowanie"))
        f = ctrl.filters
        for k, b in self.kind_btns.items():
            b.setChecked(f.kind == k)
        if self.search.text() != f.text:
            self.search.blockSignals(True)
            self.search.setText(f.text)
            self.search.blockSignals(False)
        self.sort.setCurrentIndex(max(0, self.sort.findData(ctrl.state.sort)))
        self.same_day.setChecked(bool(f.same_day))
        n_adv = f.active_count() - (1 if f.kind != "all" else 0) - (1 if f.same_day else 0)
        self.filters_btn.setText(tr("Filtry ({n})", n=n_adv) if n_adv else tr("Filtry"))
        self.filters_btn.setChecked(bool(n_adv))
        self.filters_btn.setCheckable(True)
        desc = describe_filters(f)
        self.chips.setVisible(bool(desc))
        self.chips_text.setText("  ·  ".join(desc))
        self.refresh_theme()

    def update_position(self) -> None:
        ctrl = self.ctrl
        n = len(ctrl.ids)
        suffix = ""
        if ctrl.scope == SCOPE_DEVICE:
            suffix = tr(" na telefonie")
            if ctrl.device_status == "scanning":
                if ctrl.device_limit:
                    suffix += tr(" · wczytywanie {found}/{limit}…",
                                 found=min(ctrl.device_found, ctrl.device_limit), limit=ctrl.device_limit)
                else:
                    suffix += tr(" · wczytywanie…")
            elif ctrl.device_more:
                suffix += tr(" (są kolejne)")
            if not n:
                self.count.setText(tr("wczytywanie…") if ctrl.device_status == "scanning" else tr("brak nowych plików"))
                return
        if not n:
            self.count.setText(tr("brak plików"))
            return
        files = count_pl(n, 'plik', 'pliki', 'plików')
        if ctrl.index >= 0:
            self.count.setText(tr("{pos} z {files}{suffix}", pos=ctrl.index + 1, files=files, suffix=suffix))
        else:
            self.count.setText(f"{files}{suffix}")

    def _apply_search(self) -> None:
        f = replace(self.ctrl.filters, text=self.search.text())
        if f != self.ctrl.filters:
            self.ctrl.set_filters(f)

    def _set_kind(self, k: str) -> None:
        self.ctrl.set_filters(replace(self.ctrl.filters, kind=k))

    def _sort_changed(self) -> None:
        self.ctrl.set_sort(self.sort.currentData(), self.ctrl.state.ascending)

    def _toggle_order(self) -> None:
        self.ctrl.set_sort(self.ctrl.state.sort, not self.ctrl.state.ascending)

    def _toggle_same_day(self) -> None:
        f = self.ctrl.filters
        if f.same_day:
            self.ctrl.set_filters(replace(f, same_day=""))
            return
        cid = self.ctrl.current_id
        if cid is not None and cid < 0:
            e = self.ctrl.device_entry(cid)
            day = e.date[:10] if e is not None else ""
        else:
            row = self.ctrl.mm.get(cid) if cid is not None else None
            day = row["sort_date"][:10] if row is not None and row["sort_date"] else ""
        if not day:
            self.same_day.setChecked(False)
            return
        self.ctrl.set_filters(replace(f, same_day=day))

    def _open_filters(self) -> None:
        self.popup.load(self.ctrl.filters)
        self.popup.layout().invalidate()
        self.popup.layout().activate()
        self.popup.resize(self.popup.sizeHint())   # bez pustego miejsca po ukrytych wierszach
        g = self.filters_btn.mapToGlobal(QPoint(0, self.filters_btn.height() + 6))
        x = min(g.x(), self.mapToGlobal(QPoint(self.width(), 0)).x() - self.popup.width())
        y = g.y() - self.popup.height() - self.filters_btn.height() - 12  # nad paskiem (kolejka jest na dole)
        self.popup.move(x, max(0, y))
        self.popup.show()
        self.sync()


def describe_filters(f: Filters) -> list[str]:
    out = []
    months = month_names()
    if f.same_day:
        out.append(tr("z dnia {date}", date=date_pl(parse_iso(f.same_day + " 00:00:00"))))
    if f.year and f.month:
        out.append(f"{months[f.month - 1]} {f.year}")
    elif f.year:
        out.append(tr("rok {year}", year=f.year))
    elif f.month:
        out.append(tr("{month} (każdy rok)", month=months[f.month - 1]))
    if f.date_from or f.date_to:
        a = date_pl(parse_iso(f.date_from + " 00:00:00")) if f.date_from else "…"
        b = date_pl(parse_iso(f.date_to + " 00:00:00")) if f.date_to else "…"
        out.append(f"{a} – {b}")
    if f.min_size_mb or f.max_size_mb:
        a = f"{f.min_size_mb:g}" if f.min_size_mb else "0"
        b = f"{f.max_size_mb:g}" if f.max_size_mb else "∞"
        out.append(tr("rozmiar {low}–{high} MB", low=a, high=b))
    if f.location == "__gps__":
        out.append(tr("z lokalizacją GPS"))
    elif f.location == "__nogps__":
        out.append(tr("bez lokalizacji"))
    elif f.location:
        out.append(tr("miejsce: {place}", place=f.location))
    if f.status == "sorted":
        out.append(tr("posortowane"))
    elif f.status == "unsorted":
        out.append(tr("nieposortowane"))
    if f.folder:
        out.append(tr("folder: {folder}", folder=display_folder(f.folder)))
    if f.kind == "photo":
        out.append(tr("tylko zdjęcia"))
    elif f.kind == "video":
        out.append(tr("tylko filmy"))
    if f.text:
        out.append(tr("nazwa zawiera „{text}”", text=f.text))
    return out
