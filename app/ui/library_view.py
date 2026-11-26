"""Główny widok otwartej biblioteki."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPoint, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QComboBox, QFrame, QGraphicsOpacityEffect,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar,
                               QPushButton, QTextEdit, QPlainTextEdit, QToolButton, QVBoxLayout, QWidget)

from app.constants import SCOPE_ALL, SCOPE_DEVICE, UNSORTED_FOLDER
from app.core.library_controller import LibraryController
from app.i18n import display_folder, is_english, tr
from app.services.thumbnail_service import ThumbnailService
from app.ui import icons, theme
from app.ui.drag import start_media_drag
from app.ui.filter_bar import QueueHeader
from app.ui.folder_panel import FolderPanel
from app.ui.media_viewer import ImageLoader, MediaViewer
from app.ui.metadata_panel import MetadataPanel
from app.ui.thumbnail_grid import ThumbnailView
from app.utils.formatting import format_int


class Toast(QFrame):
    undo_clicked = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("Toast")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 10, 8)
        lay.setSpacing(10)
        self.icon = QLabel()
        self.text = QLabel()
        self.undo = QPushButton(tr("Cofnij"))
        self.undo.setObjectName("Link")
        self.undo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.undo.clicked.connect(self.undo_clicked)
        lay.addWidget(self.icon)
        lay.addWidget(self.text)
        lay.addWidget(self.undo)
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(220)
        self.anim.valueChanged.connect(lambda v: self.effect.setOpacity(float(v)))
        self.anim.finished.connect(self._anim_done)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.fade_out)
        self.hide()

    def show_message(self, text: str, undo: bool) -> None:
        self.icon.setPixmap(icons.pixmap("check", 16, theme.current()["success"], 2.4))
        self.text.setText(text)
        self.undo.setVisible(undo)
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self.anim.stop()
        self.anim.setStartValue(self.effect.opacity() if self.isVisible() else 0.0)
        self.anim.setEndValue(1.0)
        self._hiding = False
        self.anim.start()
        self.timer.start(4500)

    def fade_out(self) -> None:
        self._hiding = True
        self.anim.stop()
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.start()

    def _anim_done(self) -> None:
        if getattr(self, "_hiding", False):
            self.hide()

    def reposition(self) -> None:
        p = self.parentWidget()
        if p:
            self.move(int((p.width() - self.width()) / 2), 16)


class SortProgress(QToolButton):
    """Wskaźnik postępu sortowania w pasku górnym (kliknięcie = statystyki)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setToolTip(tr("Postęp sortowania — kliknij, aby zobaczyć statystyki"))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 5, 10, 5)
        lay.setSpacing(4)
        self.label = QLabel()
        self.label.setObjectName("Muted")
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.bar = QProgressBar()
        self.bar.setObjectName("Thin")
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1000)
        self.bar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self.label)
        lay.addWidget(self.bar)
        self.setFixedSize(250, 46)
        self.stats: dict = {}

    def set_compact(self, on: bool) -> None:
        self._compact = on
        self.setFixedSize(150 if on else 250, 46)
        if self.stats:
            self.set_stats(self.stats)

    def set_stats(self, s: dict) -> None:
        self.stats = s
        pct = s["percent"]
        pct_txt = f"{pct:.0f}%"
        left = format_int(s["unsorted"])
        txt = tr("{percent} posortowano", percent=pct_txt) if s["total"] else tr("Brak plików")
        if s["total"] and not getattr(self, "_compact", False):
            txt += "  ·  " + tr("zostało {count}", count=left)
        self.label.setText(txt)
        self.setToolTip(tr("{percent} posortowano, zostało {count}. Kliknij, aby zobaczyć statystyki.",
                           percent=pct_txt, count=left))
        self.bar.setValue(int(pct * 10))


class StatsPopup(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("Popup")
        self.lay = QGridLayout(self)
        self.lay.setContentsMargins(20, 16, 20, 16)
        self.lay.setHorizontalSpacing(26)
        self.lay.setVerticalSpacing(10)

    def show_stats(self, s: dict, at: QPoint) -> None:
        while self.lay.count():
            it = self.lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        t = QLabel(tr("Statystyki biblioteki"))
        t.setObjectName("H2")
        self.lay.addWidget(t, 0, 0, 1, 2)
        bar = QProgressBar()
        bar.setRange(0, 1000)
        bar.setValue(int(s["percent"] * 10))
        bar.setTextVisible(False)
        self.lay.addWidget(bar, 1, 0, 1, 2)
        done = f"{s['percent']:.1f}%"
        items = [(tr("Wszystkie multimedia"), s["total"]), (tr("Zdjęcia"), s["photos"]), (tr("Filmy"), s["videos"]),
                 (tr("Posortowane"), s["sorted"]), (display_folder(UNSORTED_FOLDER), s["unsorted"]),
                 (tr("Ukończono"), done if is_english() else done.replace(".", ",")),
                 (tr("Foldery tematyczne"), s["folders"])]
        for i, (k, v) in enumerate(items, start=2):
            kl = QLabel(k)
            kl.setObjectName("Muted")
            vl = QLabel(format_int(v) if isinstance(v, int) else str(v))
            vl.setObjectName("MetaName")
            vl.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.lay.addWidget(kl, i, 0)
            self.lay.addWidget(vl, i, 1)
        self.adjustSize()
        self.move(max(0, at.x() - self.width() + (self.parentWidget().progress.width() if self.parentWidget() else 0)), at.y())
        self.show()


class TopBar(QFrame):
    home = Signal()
    import_clicked = Signal()
    settings = Signal()
    theme_toggle = Signal()

    def __init__(self, ctrl: LibraryController, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.setObjectName("TopBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 4)
        lay.setSpacing(6)
        self.logo = QLabel()
        self.logo.setPixmap(icons.logo_pixmap(30))
        lay.addWidget(self.logo)
        name = QLabel("PhotoSort")
        name.setObjectName("AppName")
        self.app_name = name
        lay.addWidget(name)
        lay.addSpacing(14)
        self.crumb_root = QPushButton(ctrl.lib.name)
        self.crumb_root.setObjectName("Crumb")
        self.crumb_root.setCursor(Qt.CursorShape.PointingHandCursor)
        self.crumb_root.setToolTip(tr("{path}\nKliknij, aby wrócić do kolejki „{folder}”",
                                      path=ctrl.lib.root, folder=display_folder(UNSORTED_FOLDER)))
        self.crumb_root.clicked.connect(lambda: ctrl.set_scope(ctrl.lib.unsorted))
        self.crumb_sep = QLabel()
        self.crumb_cur = QLabel()
        self.crumb_cur.setObjectName("CrumbCurrent")
        for w in (self.crumb_root, self.crumb_sep, self.crumb_cur):
            lay.addWidget(w)
        self.back_btn = QPushButton(tr("Wróć do sortowania"))
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.clicked.connect(lambda: ctrl.set_scope(ctrl.lib.unsorted))
        lay.addSpacing(8)
        lay.addWidget(self.back_btn)
        lay.addStretch(1)
        self.progress = SortProgress()
        self.progress.clicked.connect(self._show_stats)
        lay.addWidget(self.progress)
        lay.addSpacing(6)
        self.btn_undo = self._tool("undo", tr("Cofnij ostatnie przeniesienie (Ctrl+Z)"), ctrl.undo)
        self.btn_bookmark = self._tool("bookmark", tr("Dodaj zakładkę do bieżącego pliku (Ctrl+D)"),
                                       lambda: ctrl.toggle_bookmark())
        self.btn_bookmark.setCheckable(True)
        for b in (self.btn_undo, self.btn_bookmark):
            lay.addWidget(b)
        self.btn_import = QPushButton(tr("Importuj zdjęcia i filmy"))
        self.btn_import.setObjectName("Primary")
        self.btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import.clicked.connect(self.import_clicked)
        lay.addSpacing(4)
        lay.addWidget(self.btn_import)
        lay.addSpacing(4)
        self.btn_theme = self._tool("moon", tr("Jasny / ciemny motyw"), self.theme_toggle.emit)
        self.btn_settings = self._tool("settings", tr("Ustawienia"), self.settings.emit)
        self.btn_home = self._tool("home", tr("Ekran główny (zmień bibliotekę)"), self.home.emit)
        for b in (self.btn_theme, self.btn_settings, self.btn_home):
            lay.addWidget(b)
        self.stats_popup = StatsPopup(self)
        ctrl.stats_changed.connect(self.progress.set_stats)
        ctrl.undo_changed.connect(self._undo_state)
        ctrl.scope_changed.connect(self._scope)
        ctrl.current_changed.connect(self._bookmark_state)
        ctrl.bookmarks_changed.connect(lambda: self._bookmark_state(ctrl.current_id))
        self._scope(ctrl.scope)

    def set_compact(self, level: int) -> None:
        self.app_name.setVisible(level == 0)
        self.btn_import.setText({0: tr("Importuj zdjęcia i filmy"), 1: tr("Importuj"), 2: ""}[level])
        self.btn_import.setToolTip(tr("Importuj zdjęcia i filmy (Ctrl+I)"))
        self.back_btn.setText(tr("Wróć do sortowania") if level == 0 else tr("Wróć"))
        self.progress.set_compact(level > 0)

    def _tool(self, icon: str, tip: str, fn) -> QToolButton:
        b = QToolButton()
        b.setToolTip(tip)
        b.setProperty("icon_name", icon)
        b.setIconSize(icons.size(20))
        b.clicked.connect(fn)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    def refresh_theme(self) -> None:
        c = theme.current()
        for b in (self.btn_undo, self.btn_settings, self.btn_home):
            b.setIcon(icons.icon(b.property("icon_name"), c["text"] if b.isEnabled() else c["text3"], 20))
        self.btn_theme.setIcon(icons.icon("sun" if c["name"] == "dark" else "moon", c["text"], 20))
        self.btn_import.setIcon(icons.icon("import", "#FFFFFF", 18))
        self.crumb_sep.setPixmap(icons.pixmap("chevron_right", 16, c["text3"]))
        self._bookmark_state(self.ctrl.current_id)

    def _undo_state(self, enabled: bool, tip: str) -> None:
        self.btn_undo.setEnabled(enabled)
        self.btn_undo.setToolTip(tip)
        c = theme.current()
        self.btn_undo.setIcon(icons.icon("undo", c["text"] if enabled else c["text3"], 20))

    def _bookmark_state(self, mid) -> None:
        on = mid is not None and mid >= 0 and self.ctrl.mm.is_bookmarked(mid)
        self.btn_bookmark.setChecked(on)
        self.btn_bookmark.setEnabled(mid is not None and mid >= 0)
        c = theme.current()
        self.btn_bookmark.setIcon(icons.icon("bookmark_fill" if on else "bookmark", c["accent"] if on else c["text"], 20))
        self.btn_bookmark.setToolTip(tr("Usuń zakładkę (Ctrl+D)") if on
                                     else tr("Dodaj zakładkę do bieżącego pliku (Ctrl+D)"))

    def _scope(self, scope: str) -> None:
        if scope == SCOPE_DEVICE:
            text = tr("Telefon: {name}", name=self.ctrl.device_name)
        else:
            text = tr("Wszystkie multimedia") if scope == SCOPE_ALL else display_folder(scope)
        self.crumb_cur.setText(text)
        self.back_btn.setVisible(not self.ctrl.lib.is_unsorted(scope))

    def _show_stats(self) -> None:
        if self.progress.stats:
            self.stats_popup.show_stats(self.progress.stats,
                                        self.progress.mapToGlobal(QPoint(0, self.progress.height() + 6)))


class LibraryView(QWidget):
    home = Signal()
    import_clicked = Signal()
    settings = Signal()
    theme_toggle = Signal()
    fullscreen_toggle = Signal()

    STRIP_H = 104

    def __init__(self, ctrl: LibraryController, thumbs: ThumbnailService, parent=None):
        super().__init__(parent)
        self.setObjectName("LibraryView")
        self.ctrl = ctrl
        self.thumbs = thumbs
        self.loader = ImageLoader()
        self.immersive = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.top = TopBar(ctrl)
        self.top.home.connect(self.home)
        self.top.import_clicked.connect(self.import_clicked)
        self.top.settings.connect(self.settings)
        self.top.theme_toggle.connect(self.theme_toggle)
        root.addWidget(self.top)

        body = QHBoxLayout()
        body.setContentsMargins(14, 8, 14, 14)
        body.setSpacing(12)
        root.addLayout(body, 1)

        left = QVBoxLayout()
        left.setSpacing(8)
        self.viewer_card = QFrame()
        self.viewer_card.setObjectName("ViewerCard")
        vc = QVBoxLayout(self.viewer_card)
        vc.setContentsMargins(0, 0, 0, 0)
        self.viewer = MediaViewer()
        vc.addWidget(self.viewer)
        left.addWidget(self.viewer_card, 1)
        self.meta = MetadataPanel()
        left.addWidget(self.meta)

        self.queue_card = QFrame()
        self.queue_card.setObjectName("QueuePanel")
        qc = QVBoxLayout(self.queue_card)
        qc.setContentsMargins(10, 8, 10, 8)
        qc.setSpacing(4)
        self.header = QueueHeader(ctrl)
        self.header.toggle_expand.connect(self.toggle_strip)
        qc.addWidget(self.header)
        self.thumbs_view = ThumbnailView(ctrl, thumbs)
        self.thumbs_view.setFixedHeight(self.STRIP_H)
        qc.addWidget(self.thumbs_view)
        left.addWidget(self.queue_card)
        body.addLayout(left, 1)

        self.folders = FolderPanel(ctrl)
        body.addWidget(self.folders)
        self.thumbs_view.folders_provider = self.folders.folder_names
        self.thumbs_view.move_to_folder = self._move_from_menu

        self.toast = Toast(self.viewer_card)
        self.toast.undo_clicked.connect(lambda: (self.toast.fade_out(), ctrl.undo()))

        self._strip_anim = QVariantAnimation(self)
        self._strip_anim.setDuration(240)
        self._strip_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._strip_anim.valueChanged.connect(lambda v: self.thumbs_view.setFixedHeight(int(v)))

        # sygnały
        ctrl.current_changed.connect(self.show_current)
        ctrl.toast.connect(self.toast.show_message)
        ctrl.error.connect(self._error)
        ctrl.meta_updated.connect(self._meta_updated)
        ctrl.current_changed.connect(lambda _m: self.header.update_position())
        self.viewer.prev_requested.connect(ctrl.prev)
        self.viewer.next_requested.connect(ctrl.next)
        self.viewer.drag_requested.connect(self._drag_current)
        self.viewer.fullscreen_requested.connect(self.fullscreen_toggle)
        self.viewer.empty_action.connect(self._empty_action)
        self.loader.loaded.connect(self._image_loaded)
        self.loader.failed.connect(self._image_failed)
        self.thumbs.ready.connect(self._thumb_ready)
        ctrl.device_thumb_ready.connect(self._thumb_ready)
        ctrl.device_fetched.connect(self._device_fetched)
        ctrl.device_fetch_failed.connect(self._device_fetch_failed)
        ctrl.device_fetch_progress.connect(self._device_fetch_progress)
        ctrl.device_changed.connect(self._device_changed)
        # odświeżanie licznika czasu na ekranie wczytywania z telefonu
        self._scan_tick = QTimer(self)
        self._scan_tick.setInterval(1000)
        self._scan_tick.timeout.connect(self._scan_tick_update)
        self._scan_tick.start()

        sc = QShortcut(QKeySequence.StandardKey.Undo, self)
        sc.activated.connect(ctrl.undo)
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(lambda: ctrl.toggle_bookmark())
        QShortcut(QKeySequence("F11"), self).activated.connect(self.fullscreen_toggle)
        QShortcut(QKeySequence("Ctrl+I"), self).activated.connect(self.import_clicked)
        QApplication.instance().installEventFilter(self)

        if ctrl.state.strip_expanded:
            QTimer.singleShot(0, lambda: self.set_strip_expanded(True, animate=False))
        self.refresh_theme()

    # ------------------------------------------------------------------ #
    def refresh_theme(self) -> None:
        self.top.refresh_theme()
        self.viewer.refresh_theme()
        self.meta.refresh_theme()
        self.header.refresh_theme()
        self.folders.refresh_theme()
        self.thumbs_view.viewport().update()
        self.show_current(self.ctrl.current_id)

    def shutdown(self) -> None:
        QApplication.instance().removeEventFilter(self)
        self.viewer.video.stop()
        self.ctrl.state.strip_expanded = self.thumbs_view.grid_mode
        self.ctrl.state.scroll = self.thumbs_view.scroll_value()
        self.loader.shutdown()

    def restore_scroll(self) -> None:
        v = self.ctrl.state.scroll
        if v:
            QTimer.singleShot(150, lambda: self.thumbs_view.set_scroll_value(v))

    # ------------------------------------------------------------------ #
    # Wyświetlanie bieżącego pliku
    # ------------------------------------------------------------------ #
    def show_current(self, mid) -> None:
        ctrl = self.ctrl
        if mid is None:
            self.meta.clear()
            self._show_empty()
            return
        if mid < 0:
            self._show_device_item(mid)
            return
        row = ctrl.mm.get(mid)
        if row is None:
            self._show_empty()
            return
        self.meta.set_row(row)
        if row["meta_status"] == 0:
            ctrl.request_meta(mid)
        path = ctrl.lib.abs_path(row["rel_path"])
        self.viewer.set_nav(ctrl.index > 0, ctrl.index < len(ctrl.ids) - 1)
        if not path.exists():
            self.viewer.show_empty("warning", tr("Plik jest niedostępny"),
                                   tr("Plik mógł zostać przeniesiony lub usunięty poza programem PhotoSort. "
                                      "Biblioteka zostanie odświeżona."))
            ctrl.rescan()
            return
        pm = self.thumbs.get(mid)
        if row["kind"] == "video":
            cached = self.loader.cached(mid)
            poster = cached if cached is not None else (pm.toImage() if pm is not None else None)
            if self.viewer.current_id != mid or not self.viewer.is_video():
                self.viewer.show_video(mid, path, poster, row["duration"])
            if cached is None:
                self.loader.request(mid, path, "video", self._prefetch_list())
        else:
            cached = self.loader.cached(mid)
            if cached is not None:
                self.viewer.show_photo(mid, cached, True)
                self.loader.prefetch(self._prefetch_list())
            else:
                if self.viewer.current_id != mid:
                    self.viewer.show_photo(mid, pm, False)
                self.loader.request(mid, path, "photo", self._prefetch_list())

    # -- pliki z telefonu ------------------------------------------------------
    def _show_device_item(self, mid: int) -> None:
        ctrl = self.ctrl
        e = ctrl.device_entry(mid)
        if e is None:
            self._show_empty()
            return
        self.meta.set_device_entry(e, ctrl.device_name)
        self.viewer.set_nav(ctrl.index > 0, ctrl.index < len(ctrl.ids) - 1)
        cached = ctrl.device_cached(mid)
        if cached is not None:
            self._device_fetched(mid, str(cached))
        else:
            pm = ctrl.device_thumb(mid)
            if e.kind == "photo" and pm is not None:
                if self.viewer.current_id != mid:
                    self.viewer.show_photo(mid, pm, False)   # miniatura, zanim dojdzie pełne zdjęcie
            elif self.viewer.current_id != mid or e.kind == "video":
                self.viewer.show_empty("film" if e.kind == "video" else "phone",
                                       tr("Wczytywanie z telefonu…"),
                                       f"{e.name}" + (f" ({e.size / 1048576:.0f} MB)".replace(".", ",")
                                                      if e.size > 1048576 else ""))
                self.viewer.empty.set_progress(-1, tr("Czekam na telefon…"))
                self.viewer.current_id = mid
            ctrl.device_fetch(mid, current=True)
        # wyprzedzająco: dwa kolejne zdjęcia (filmów nie — bywają duże)
        for off in (1, 2):
            i = ctrl.index + off
            if 0 <= i < len(ctrl.ids):
                nxt = ctrl.ids[i]
                ne = ctrl.device_entry(nxt)
                if ne is not None and ne.kind == "photo":
                    ctrl.device_fetch(nxt, current=False)

    def _device_fetched(self, mid: int, path: str) -> None:
        if mid != self.ctrl.current_id:
            return
        e = self.ctrl.device_entry(mid)
        if e is None:
            return
        p = Path(path)
        if e.kind == "video":
            if self.viewer.current_id != mid or not self.viewer.is_video():
                pm = self.ctrl.device_thumb(mid)
                self.viewer.show_video(mid, p, pm.toImage() if pm is not None else None, None)
        else:
            cached = self.loader.cached(mid)
            if cached is not None:
                self.viewer.show_photo(mid, cached, True)
            else:
                self.loader.request(mid, p, "photo")

    def _device_fetch_progress(self, mid: int, pct: int) -> None:
        if mid != self.ctrl.current_id or self.viewer.current_id != mid or not self.viewer.showing_empty():
            return
        if pct >= 100:
            self.viewer.empty.set_progress(100, tr("Otwieranie…"))
        else:
            self.viewer.empty.set_progress(pct, tr("Kopiowanie z telefonu: {percent}%", percent=pct))

    def _scan_tick_update(self) -> None:
        ctrl = self.ctrl
        if (ctrl.scope == SCOPE_DEVICE and ctrl.device_status == "scanning" and ctrl.current_id is None
                and self.isVisible()):
            self._show_empty()

    def _device_fetch_failed(self, mid: int, msg: str) -> None:
        if mid != self.ctrl.current_id:
            return
        self.viewer.show_empty("warning", tr("Nie udało się wczytać pliku z telefonu"),
                               msg + "\n" + tr("Możesz nadal przeciągnąć miniaturę do folderu — program "
                                               "spróbuje skopiować plik ponownie."))
        self.viewer.current_id = mid

    def _empty_action(self) -> None:
        if self.ctrl.scope == SCOPE_DEVICE:
            if self.ctrl.device_status in ("scanning", "error"):
                self.ctrl.close_device()        # „Przerwij” / „Zakończ”
            else:
                self.ctrl.device_load_more()
        else:
            self.import_clicked.emit()

    def _device_changed(self) -> None:
        if self.ctrl.scope == SCOPE_DEVICE and self.ctrl.current_id is None:
            self._show_empty()
        self.top._scope(self.ctrl.scope)
        self.header.sync()

    def _prefetch_list(self):
        out = []
        ctrl = self.ctrl
        for off in (1, -1, 2):
            i = ctrl.index + off
            if 0 <= i < len(ctrl.ids):
                mid = ctrl.ids[i]
                row = ctrl.rows.get(mid)
                if row and row[1] == "photo" and mid >= 0:
                    out.append((mid, ctrl.lib.abs_path(row[4]), "photo"))
        return out

    def _image_loaded(self, mid: int, img: QImage) -> None:
        if mid != self.ctrl.current_id:
            return
        if self.viewer.is_video():
            self.viewer.video.set_poster(img)
        else:
            self.viewer.show_photo(mid, img, True)

    def _image_failed(self, mid: int, err: str) -> None:
        if mid != self.ctrl.current_id or self.viewer.is_video():
            return
        self.viewer.show_empty("warning", tr("Nie można wyświetlić tego zdjęcia"),
                               tr("Plik może być uszkodzony lub zapisany w nieobsługiwanym formacie. "
                                  "Możesz go nadal przenieść do folderu (przeciągnij miniaturę)."))
        self.viewer.current_id = mid

    def _thumb_ready(self, mid: int) -> None:
        # miniatura jako tymczasowy podgląd, zanim wczyta się pełny obraz
        if mid == self.ctrl.current_id and self.viewer.current_id == mid and not self.viewer.is_video():
            pm = self.ctrl.device_thumb(mid) if mid < 0 else self.thumbs.get(mid)
            if self.loader.cached(mid) is None and self.viewer.image.item.pixmap().isNull() and pm is not None:
                self.viewer.show_photo(mid, pm, False)
        elif mid < 0 and mid == self.ctrl.current_id and self.viewer.current_id == mid and self.viewer.is_video():
            pm = self.ctrl.device_thumb(mid)
            if pm is not None:
                self.viewer.video.set_poster(pm.toImage())   # miniatura dotarła po pliku filmu
        elif mid < 0 and mid == self.ctrl.current_id and self.viewer.current_id == mid \
                and self.viewer.stack.currentWidget() is self.viewer.empty and self.loader.cached(mid) is None:
            e = self.ctrl.device_entry(mid)
            if e is not None and e.kind == "photo":
                self.viewer.current_id = None
                self.viewer.show_photo(mid, self.ctrl.device_thumb(mid), False)

    def _meta_updated(self, ids: list) -> None:
        cid = self.ctrl.current_id
        if cid in ids and cid is not None and cid >= 0:
            self.meta.set_row(self.ctrl.mm.get(cid))

    def _show_empty(self) -> None:
        ctrl = self.ctrl
        if ctrl.scope == SCOPE_DEVICE:
            self.meta.clear()
            if ctrl.device_status == "scanning":
                import time
                what = (tr("Szukam {count} najnowszych zdjęć, których nie ma jeszcze w bibliotece",
                           count=ctrl.device_limit)
                        if ctrl.device_limit else tr("Szukam zdjęć, których nie ma jeszcze w bibliotece "
                                                     "(pojawią się od najnowszych)"))
                step = ctrl.device_scan_text or tr("Łączenie z telefonem…")
                step = (step.replace("Otwieram folder telefonu: ", "Otwieram folder: ")  # i18n: ignore
                        .replace("Opening phone folder: ", "Opening folder: ").split("  (")[0])
                secs = int(time.time() - ctrl.device_scan_since) if ctrl.device_scan_since else 0
                slow = ("\n" + tr("Duże foldery iPhone'a (kilkaset zdjęć) otwierają się nawet 1–2 minuty — "
                                  "to normalne.") if secs >= 15 else "")
                self.viewer.show_empty("phone", tr("Wczytywanie zdjęć z telefonu…"),
                                       tr("{what}. Nie odłączaj telefonu i nie blokuj ekranu. Nic nie jest "
                                          "kopiowane na komputer.", what=what), tr("Przerwij"))
                found, limit = ctrl.device_found, ctrl.device_limit
                info = f"{step} · {secs} s{slow}\n" + tr("Sprawdzono {count} plików", count=ctrl.device_scan_count)
                if limit and found:
                    self.viewer.empty.set_progress(found * 100 // limit,
                                                   tr("Znaleziono {found} z {limit} ({percent}%)",
                                                      found=found, limit=limit, percent=found * 100 // limit)
                                                   + "\n" + info)
                else:
                    self.viewer.empty.set_progress(-1, (tr("Znaleziono {found}", found=found) + "\n" if found else "")
                                                   + info)
            elif ctrl.device_status == "error":
                self.viewer.show_empty("warning", tr("Brak połączenia z telefonem"), ctrl.device_error,
                                       tr("Zakończ przeglądanie telefonu"))
            elif ctrl.filters.is_active():
                self.viewer.show_empty("search", tr("Brak plików pasujących do filtrów"),
                                       tr("Zmień lub wyczyść filtry."))
            elif ctrl.device_more:
                n = ctrl.device_limit or 15
                self.viewer.show_empty("check", tr("Ta partia jest przejrzana"),
                                       tr("Na telefonie są jeszcze starsze zdjęcia. Wczytać kolejne?"),
                                       tr("Pokaż kolejne {count} zdjęć z telefonu", count=n))
            else:
                self.viewer.show_empty("check", tr("Na telefonie nie ma już nowych zdjęć"),
                                       tr("Wszystkie zdjęcia i filmy z wybranych folderów telefonu są już "
                                          "w bibliotece."))
            return
        stats = ctrl.lib.stats()
        if ctrl.filters.is_active():
            self.viewer.show_empty("search", tr("Brak plików pasujących do filtrów"),
                                   tr("Zmień lub wyczyść filtry, aby zobaczyć więcej zdjęć i filmów."))
        elif ctrl.lib.is_unsorted(ctrl.scope):
            if stats["total"] == 0:
                self.viewer.show_empty("import", tr("Zacznij od zaimportowania zdjęć"),
                                       tr("Podłącz telefon, aparat lub pendrive albo wskaż folder na komputerze. "
                                          "Pliki zostaną skopiowane — oryginały pozostaną nietknięte."),
                                       tr("Importuj zdjęcia i filmy"))
            else:
                self.viewer.show_empty("check", tr("Wszystko posortowane!"),
                                       tr("Brak plików w folderze „{folder}”. Możesz przeglądać foldery "
                                          "po prawej stronie albo zaimportować kolejne zdjęcia.",
                                          folder=display_folder(UNSORTED_FOLDER)),
                                       tr("Importuj zdjęcia i filmy"))
        elif ctrl.scope == SCOPE_ALL:
            self.viewer.show_empty("photo", tr("Biblioteka jest pusta"),
                                   tr("Zaimportuj zdjęcia i filmy, aby zacząć."), tr("Importuj zdjęcia i filmy"))
        else:
            self.viewer.show_empty("folder", tr("Ten folder jest pusty"),
                                   tr("Przeciągnij tu zdjęcia lub filmy z kolejki, aby je posortować."))

    # ------------------------------------------------------------------ #
    # Przeciąganie z dużego podglądu
    # ------------------------------------------------------------------ #
    def _drag_current(self) -> None:
        mid = self.ctrl.current_id
        if mid is None:
            return
        if self.viewer.is_video():
            self.viewer.video.player.pause()
        row = self.ctrl.rows.get(mid)
        kind = row[1] if row else "photo"
        pm = self.ctrl.device_thumb(mid) if mid < 0 else self.thumbs.get(mid)
        start_media_drag(self.viewer, [mid], [pm], [kind])

    def _move_from_menu(self, ids: list, folder: str) -> None:
        res = self.ctrl.move(ids, folder)
        if res and res.moved:
            self.folders.list.flash_folder(folder)

    # ------------------------------------------------------------------ #
    # Pasek / siatka miniatur
    # ------------------------------------------------------------------ #
    def toggle_strip(self) -> None:
        self.set_strip_expanded(not self.thumbs_view.grid_mode)

    def set_strip_expanded(self, on: bool, animate: bool = True) -> None:
        target = max(self.STRIP_H, int(self.height() * 0.5)) if on else self.STRIP_H
        self.thumbs_view.set_grid_mode(on)
        self.header.set_expanded(on)
        self.meta.setVisible(not on and not self.immersive)
        self.ctrl.state.strip_expanded = on
        self.ctrl.schedule_save()
        if animate:
            self._strip_anim.stop()
            self._strip_anim.setStartValue(self.thumbs_view.height())
            self._strip_anim.setEndValue(target)
            self._strip_anim.start()
        else:
            self.thumbs_view.setFixedHeight(target)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        w = self.width()
        self.top.set_compact(0 if w >= 1380 else 1 if w >= 1150 else 2)
        self.header.set_compact(0 if w >= 1450 else 1 if w >= 1250 else 2)
        if self.thumbs_view.grid_mode and self._strip_anim.state() != QVariantAnimation.State.Running:
            self.thumbs_view.setFixedHeight(max(self.STRIP_H, int(self.height() * 0.5)))
        self.toast.reposition()

    # ------------------------------------------------------------------ #
    # Pełny ekran / klawiatura
    # ------------------------------------------------------------------ #
    def set_immersive(self, on: bool) -> None:
        self.immersive = on
        for w in (self.top, self.folders, self.queue_card):
            w.setVisible(not on)
        self.meta.setVisible(not on and not self.thumbs_view.grid_mode)
        lay = self.layout().itemAt(1).layout()
        lay.setContentsMargins(*((0, 0, 0, 0) if on else (14, 8, 14, 14)))
        self.viewer_card.setStyleSheet("#ViewerCard { border-radius: 0; background: #000; }" if on else "")
        self.viewer.tb_buttons["fullscreen"].setIcon(
            icons.icon("exit_fullscreen" if on else "fullscreen", theme.current()["text"], 18))

    def eventFilter(self, obj: QObject, e: QEvent) -> bool:
        if e.type() != QEvent.Type.KeyPress or not self.isVisible() or not self.window().isActiveWindow():
            return False
        fw = QApplication.focusWidget()
        if isinstance(fw, (QLineEdit, QAbstractSpinBox, QComboBox, QTextEdit, QPlainTextEdit)):
            return False
        if QApplication.activePopupWidget() or QApplication.activeModalWidget():
            return False
        if fw is self.thumbs_view and e.key() not in (Qt.Key.Key_Space, Qt.Key.Key_Escape):
            return False  # siatka miniatur obsługuje strzałki sama
        key = e.key()
        mods = e.modifiers()
        if mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
            return False
        v = self.viewer
        if key in (Qt.Key.Key_Right, Qt.Key.Key_PageDown):
            self.ctrl.next()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_PageUp):
            self.ctrl.prev()
        elif key == Qt.Key.Key_Home:
            self.ctrl.set_index(0)
        elif key == Qt.Key.Key_End:
            self.ctrl.set_index(len(self.ctrl.ids) - 1)
        elif key == Qt.Key.Key_Space and v.is_video():
            v.video.toggle_play()
        elif key == Qt.Key.Key_Escape and self.immersive:
            self.fullscreen_toggle.emit()
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal) and not v.is_video():
            v.image.zoom(1.25)
        elif key == Qt.Key.Key_Minus and not v.is_video():
            v.image.zoom(1 / 1.25)
        elif key == Qt.Key.Key_0 and not v.is_video():
            v.image.fit()
        elif key == Qt.Key.Key_R and not v.is_video():
            v.rotate()
        elif key == Qt.Key.Key_M and v.is_video():
            v.video.toggle_mute()
        else:
            return False
        return True

    def _error(self, text: str) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("PhotoSort")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(text)
        box.exec()
