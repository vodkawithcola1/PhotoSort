"""Panel folderów po prawej: przeglądanie folderów i cel przeciągania."""
from __future__ import annotations

from PySide6.QtCore import QModelIndex, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QPushButton, QStyle, QStyledItemDelegate,
                               QToolButton, QVBoxLayout)

from app.constants import MIME_MEDIA_IDS, SCOPE_ALL, SCOPE_DEVICE
from app.core.library_controller import LibraryController
from app.i18n import display_folder, tr
from app.ui import icons, theme
from app.ui.dialogs import TextPrompt, confirm
from app.ui.drag import ids_from_mime
from app.utils.formatting import count_pl, format_int
from app.utils.paths import reveal_in_explorer

NAME_ROLE = Qt.ItemDataRole.UserRole + 1
COUNT_ROLE = Qt.ItemDataRole.UserRole + 2
KIND_ROLE = Qt.ItemDataRole.UserRole + 3   # unsorted | all | folder | header


class FolderDelegate(QStyledItemDelegate):
    def __init__(self, view: "FolderList"):
        super().__init__(view)
        self.view = view

    def sizeHint(self, option, index) -> QSize:
        if index.data(KIND_ROLE) == "header":
            return QSize(10, 30)
        return QSize(10, 42)

    def paint(self, p: QPainter, option, index: QModelIndex) -> None:
        kind = index.data(KIND_ROLE)
        t = theme.current()
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(option.rect).adjusted(6, 2, -6, -2)
        if kind == "header":
            p.setPen(QColor(t["text2"]))
            p.setFont(theme.ui_font(8.5, QFont.Weight.DemiBold))
            p.drawText(r.adjusted(8, 0, 0, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                       index.data(Qt.ItemDataRole.DisplayRole))
            p.restore()
            return
        name = index.data(NAME_ROLE)
        count = index.data(COUNT_ROLE) or 0
        is_drop = index.row() == self.view.drop_row
        is_scope = name == self.view.current_scope
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        path = QPainterPath()
        path.addRoundedRect(r, 9, 9)
        text_color = QColor(t["text"])
        icon_color = t["accent"]
        if is_drop:
            p.fillPath(path, theme.color("accent"))
            text_color = QColor("#FFFFFF")
            icon_color = "#FFFFFF"
        elif is_scope:
            p.fillPath(path, theme.color("accent_soft"))
        elif hovered:
            p.fillPath(path, theme.color("hover"))
        flash = self.view.flash.get(index.row())
        if flash:
            c = theme.color("success")
            c.setAlphaF(0.35 * flash)
            p.fillPath(path, c)
        ic = {"unsorted": "inbox", "all": "grid", "device": "phone"}.get(kind, "folder")
        p.drawPixmap(int(r.left() + 10), int(r.center().y() - 10), icons.pixmap(ic, 20, icon_color))
        # licznik
        p.setFont(theme.ui_font(9))
        cnt = format_int(count)
        fm = p.fontMetrics()
        cw = fm.horizontalAdvance(cnt) + 14
        crect = QRectF(r.right() - cw - 8, r.center().y() - 10, cw, 20)
        if kind not in ("all", "device") or count:
            p.setPen(Qt.PenStyle.NoPen)
            bg = QColor(255, 255, 255, 60) if is_drop else theme.color("surface2")
            p.setBrush(bg)
            p.drawRoundedRect(crect, 10, 10)
            p.setPen(text_color if is_drop else QColor(t["text2"]))
            p.drawText(crect, Qt.AlignmentFlag.AlignCenter, cnt)
        # nazwa
        p.setPen(text_color)
        f = theme.ui_font(10, QFont.Weight.DemiBold if (is_scope or kind == "unsorted") else QFont.Weight.Normal)
        p.setFont(f)
        name_rect = QRectF(r.left() + 40, r.top(), crect.left() - r.left() - 46, r.height())
        elided = p.fontMetrics().elidedText(index.data(Qt.ItemDataRole.DisplayRole), Qt.TextElideMode.ElideRight,
                                            int(name_rect.width()))
        p.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)
        if is_drop:
            p.setPen(QPen(QColor(255, 255, 255, 180), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        p.restore()


class FolderList(QListWidget):
    dropped = Signal(list, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setItemDelegate(FolderDelegate(self))
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setMouseTracking(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.drop_row = -1
        self.current_scope = ""   # ustawiane przez FolderPanel na zakres kontrolera
        self.flash: dict[int, float] = {}
        self._anims = []

    def _target_row(self, pos) -> int:
        item = self.itemAt(pos)
        if item is None or item.data(KIND_ROLE) not in ("unsorted", "folder"):
            return -1
        if item.data(NAME_ROLE) == self.current_scope:
            return -1  # nie można przenieść do folderu, z którego pochodzą pliki
        return self.row(item)

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasFormat(MIME_MEDIA_IDS):
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e) -> None:
        if not e.mimeData().hasFormat(MIME_MEDIA_IDS):
            e.ignore()
            return
        row = self._target_row(e.position().toPoint())
        if row != self.drop_row:
            self.drop_row = row
            self.viewport().update()
        # automatyczne przewijanie przy krawędziach
        y = e.position().y()
        if y < 30:
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - 8)
        elif y > self.viewport().height() - 30:
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() + 8)
        if row >= 0:
            e.setDropAction(Qt.DropAction.MoveAction)
            e.accept()
        else:
            e.ignore()

    def dragLeaveEvent(self, e) -> None:
        self.drop_row = -1
        self.viewport().update()

    def dropEvent(self, e) -> None:
        row = self._target_row(e.position().toPoint())
        self.drop_row = -1
        self.viewport().update()
        ids = ids_from_mime(e.mimeData())
        if row < 0 or not ids:
            e.ignore()
            return
        e.setDropAction(Qt.DropAction.MoveAction)
        e.accept()
        self.dropped.emit(ids, self.item(row).data(NAME_ROLE))

    def flash_folder(self, name: str) -> None:
        for i in range(self.count()):
            if self.item(i).data(NAME_ROLE) == name:
                anim = QVariantAnimation(self)
                anim.setDuration(700)
                anim.setStartValue(1.0)
                anim.setEndValue(0.0)
                row = i

                def step(v, row=row):
                    self.flash[row] = float(v)
                    self.viewport().update()

                anim.valueChanged.connect(step)
                anim.finished.connect(lambda row=row, a=anim: (self.flash.pop(row, None), self._anims.remove(a)
                                                              if a in self._anims else None))
                self._anims.append(anim)
                anim.start()
                break


class NewFolderDrop(QPushButton):
    """Przycisk „Nowy folder” — przyjmuje też upuszczone pliki (tworzy folder i przenosi)."""
    dropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(tr("Nowy folder"), parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(38)

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasFormat(MIME_MEDIA_IDS):
            e.acceptProposedAction()
            self.setText(tr("Upuść, aby utworzyć nowy folder"))
            self.setObjectName("Primary")
            self.style().unpolish(self)
            self.style().polish(self)
        else:
            e.ignore()

    def dragLeaveEvent(self, e) -> None:
        self._reset()

    def dropEvent(self, e) -> None:
        self._reset()
        ids = ids_from_mime(e.mimeData())
        if ids:
            e.acceptProposedAction()
            self.dropped.emit(ids)

    def _reset(self) -> None:
        self.setText(tr("Nowy folder"))
        self.setObjectName("")
        self.style().unpolish(self)
        self.style().polish(self)


class FolderPanel(QFrame):
    def __init__(self, ctrl: LibraryController, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.setObjectName("SidePanel")
        self.setFixedWidth(290)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 14, 10, 12)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.setContentsMargins(8, 0, 2, 0)
        t = QLabel(tr("Foldery"))
        t.setObjectName("H2")
        head.addWidget(t)
        head.addStretch(1)
        self.btn_add = QToolButton()
        self.btn_add.setToolTip(tr("Utwórz nowy folder"))
        self.btn_add.clicked.connect(self.new_folder)
        head.addWidget(self.btn_add)
        lay.addLayout(head)

        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText(tr("Szukaj folderu"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        self.search_icon = QLabel(self.search)
        self.search_icon.setGeometry(9, 8, 16, 16)
        self.search_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self.search)

        self.list = FolderList()
        self.list.itemClicked.connect(self._clicked)
        self.list.dropped.connect(self._dropped)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.list, 3)

        self.btn_new = NewFolderDrop()
        self.btn_new.clicked.connect(self.new_folder)
        self.btn_new.dropped.connect(self._drop_new)
        lay.addWidget(self.btn_new)

        sep = QFrame()
        sep.setObjectName("Separator")
        lay.addWidget(sep)

        bh = QHBoxLayout()
        bh.setContentsMargins(8, 2, 2, 0)
        self.bm_title = QLabel(tr("ZAKŁADKI"))
        self.bm_title.setObjectName("SectionTitle")
        bh.addWidget(self.bm_title)
        bh.addStretch(1)
        self.bm_toggle = QToolButton()
        self.bm_toggle.setToolTip(tr("Pokaż / ukryj zakładki"))
        self.bm_toggle.clicked.connect(self._toggle_bm)
        bh.addWidget(self.bm_toggle)
        lay.addLayout(bh)
        self.bm_list = QListWidget()
        self.bm_list.setObjectName("Plain")
        self.bm_list.setMaximumHeight(170)
        self.bm_list.itemClicked.connect(lambda it: self.ctrl.go_to_media(it.data(Qt.ItemDataRole.UserRole)))
        self.bm_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.bm_list.customContextMenuRequested.connect(self._bm_menu)
        self.bm_empty = QLabel(tr("Kliknij ikonę zakładki na górze, aby oznaczyć zdjęcie, do którego chcesz wrócić."))
        self.bm_empty.setObjectName("Faint")
        self.bm_empty.setWordWrap(True)
        self.bm_empty.setContentsMargins(8, 0, 8, 0)
        lay.addWidget(self.bm_list)
        lay.addWidget(self.bm_empty)

        self.footer = QLabel()
        self.footer.setObjectName("Faint")
        self.footer.setContentsMargins(8, 4, 8, 0)
        self.footer.setWordWrap(True)
        lay.addWidget(self.footer)

        ctrl.folders_changed.connect(self.refresh)
        ctrl.device_changed.connect(self.refresh)
        ctrl.scope_changed.connect(self._scope_changed)
        ctrl.bookmarks_changed.connect(self.refresh_bookmarks)
        ctrl.stats_changed.connect(self._stats)
        self.list.current_scope = ctrl.scope
        self._bm_visible = True
        self.refresh_theme()
        self.refresh()
        self.refresh_bookmarks()

    def refresh_theme(self) -> None:
        c = theme.current()
        self.btn_add.setIcon(icons.icon("folder_plus", c["text"], 20))
        self.btn_new.setIcon(icons.icon("plus", c["text"], 16))
        self.search_icon.setPixmap(icons.pixmap("search", 16, c["text3"]))
        self.bm_toggle.setIcon(icons.icon("chevron_up" if self._bm_visible else "chevron_down", c["text2"], 16))
        self.list.viewport().update()

    def folder_names(self) -> list[str]:
        return [f.name for f in self.ctrl.lib.folders()]

    def refresh(self) -> None:
        q = self.search.text().strip().lower()
        folders = self.ctrl.lib.folders()
        total = sum(f.count for f in folders)
        sb = self.list.verticalScrollBar().value()
        self.list.clear()

        def add(text, name, count, kind):
            it = QListWidgetItem(text)
            it.setData(NAME_ROLE, name)
            it.setData(COUNT_ROLE, count)
            it.setData(KIND_ROLE, kind)
            if kind == "header":
                it.setFlags(Qt.ItemFlag.NoItemFlags)
            else:
                it.setToolTip(f"{text} — {count_pl(count, 'plik', 'pliki', 'plików')}")
            self.list.addItem(it)

        topic = [f for f in folders if not f.is_unsorted]
        if not q and self.ctrl.device is not None:
            status = self.ctrl.device_status
            n = len(self.ctrl.device_order)
            label = tr("Telefon: {name}", name=self.ctrl.device_name)
            add(label, SCOPE_DEVICE, n, "device")
            it = self.list.item(self.list.count() - 1)
            it.setToolTip(tr("Zdjęcia na telefonie, których jeszcze nie ma w bibliotece. Przeciągnij zdjęcie "
                             "na folder, aby skopiować je prosto do tego folderu.") + "\n"
                          + (tr("Wczytywanie listy…") if status == "scanning"
                             else tr("Do przejrzenia: {count}", count=n)))
        if not q:
            for f in folders:
                if f.is_unsorted:
                    add(display_folder(f.name), f.name, f.count, "unsorted")
            add(tr("Wszystkie multimedia"), SCOPE_ALL, total, "all")
            add(tr("FOLDERY TEMATYCZNE") if topic else "", None, 0, "header")
        for f in topic:
            if q and q not in f.name.lower():
                continue
            add(f.name, f.name, f.count, "folder")
        if not topic and not q:
            hint = QListWidgetItem(tr("Utwórz pierwszy folder, np. „Święta 2026”"))
            hint.setData(KIND_ROLE, "header")
            hint.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(hint)
        self.list.verticalScrollBar().setValue(sb)

    def _scope_changed(self, scope: str) -> None:
        self.list.current_scope = scope
        self.list.viewport().update()

    def _stats(self, s: dict) -> None:
        self.footer.setText(tr("{photos} · {videos} · {folders}",
                               photos=count_pl(s['photos'], 'zdjęcie', 'zdjęcia', 'zdjęć'),
                               videos=count_pl(s['videos'], 'film', 'filmy', 'filmów'),
                               folders=count_pl(s['folders'], 'folder', 'foldery', 'folderów')))

    # -- akcje ------------------------------------------------------------
    def _clicked(self, item: QListWidgetItem) -> None:
        kind = item.data(KIND_ROLE)
        if kind in ("unsorted", "all", "folder", "device"):
            self.ctrl.set_scope(item.data(NAME_ROLE))

    def _dropped(self, ids: list, folder: str) -> None:
        res = self.ctrl.move(ids, folder)
        if res and res.moved:
            self.list.flash_folder(folder)

    def _drop_new(self, ids: list) -> None:
        name = TextPrompt.ask(self, tr("Nowy folder"),
                              tr("Utwórz folder i przenieś do niego {files}.",
                                 files=count_pl(len(ids), 'plik', 'pliki', 'plików')),
                              "", tr("Utwórz i przenieś"))
        if name:
            created = self.ctrl.create_folder(name)
            if created:
                self._dropped(ids, created)

    def new_folder(self) -> None:
        name = TextPrompt.ask(self, tr("Nowy folder"), tr("Podaj nazwę folderu, np. „Wakacje Sarbinowo”."), "",
                              tr("Utwórz"))
        if name:
            self.ctrl.create_folder(name)

    def _menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is not None and item.data(KIND_ROLE) == "device":
            m = QMenu(self)
            m.addAction(icons.icon("open"), tr("Pokaż zdjęcia z telefonu")).triggered.connect(
                lambda: self.ctrl.set_scope(SCOPE_DEVICE))
            m.addAction(icons.icon("close"), tr("Zakończ przeglądanie telefonu")).triggered.connect(
                lambda: self.ctrl.close_device())
            m.exec(self.list.viewport().mapToGlobal(pos))
            return
        if item is None or item.data(KIND_ROLE) not in ("unsorted", "folder", "all"):
            return
        name = item.data(NAME_ROLE)
        kind = item.data(KIND_ROLE)
        m = QMenu(self)
        m.addAction(icons.icon("open"), tr("Otwórz")).triggered.connect(lambda: self.ctrl.set_scope(name))
        if kind == "folder":
            m.addAction(icons.icon("edit"), tr("Zmień nazwę…")).triggered.connect(lambda: self._rename(name))
            de = m.addAction(icons.icon("trash"), tr("Usuń pusty folder"))
            de.setEnabled((item.data(COUNT_ROLE) or 0) == 0)
            de.triggered.connect(lambda: self._delete(name))
        if kind != "all":
            m.addSeparator()
            m.addAction(icons.icon("computer"), tr("Pokaż w Eksploratorze")).triggered.connect(
                lambda: reveal_in_explorer(self.ctrl.lib.root / name))
        m.exec(self.list.viewport().mapToGlobal(pos))

    def _rename(self, name: str) -> None:
        new = TextPrompt.ask(self, tr("Zmień nazwę folderu"), tr("Nowa nazwa dla „{name}”:", name=name), name,
                             tr("Zmień nazwę"))
        if new and new != name:
            self.ctrl.rename_folder(name, new)

    def _delete(self, name: str) -> None:
        if confirm(self, tr("Usuń folder"), tr("Usunąć pusty folder „{name}”?", name=display_folder(name)), tr("Usuń")):
            self.ctrl.delete_folder(name)

    # -- zakładki ---------------------------------------------------------
    def refresh_bookmarks(self) -> None:
        self.bm_list.clear()
        rows = self.ctrl.mm.bookmarks()
        for r in rows:
            it = QListWidgetItem(icons.icon("bookmark_fill", theme.current()["accent"], 16),
                                 f"{r['filename']}  ·  {display_folder(r['folder'])}")
            it.setData(Qt.ItemDataRole.UserRole, r["media_id"])
            it.setToolTip(tr("{filename}\nFolder: {folder}\nKliknij, aby przejść do tego pliku.",
                             filename=r['filename'], folder=display_folder(r['folder'])))
            self.bm_list.addItem(it)
        self.bm_title.setText(tr("ZAKŁADKI ({count})", count=len(rows)) if rows else tr("ZAKŁADKI"))
        self.bm_list.setVisible(self._bm_visible and bool(rows))
        self.bm_empty.setVisible(self._bm_visible and not rows)
        self.bm_list.setFixedHeight(min(170, 34 * len(rows) + 6) if rows else 0)

    def _toggle_bm(self) -> None:
        self._bm_visible = not self._bm_visible
        self.refresh_theme()
        self.refresh_bookmarks()

    def _bm_menu(self, pos) -> None:
        it = self.bm_list.itemAt(pos)
        if not it:
            return
        mid = it.data(Qt.ItemDataRole.UserRole)
        m = QMenu(self)
        m.addAction(tr("Przejdź do pliku")).triggered.connect(lambda: self.ctrl.go_to_media(mid))
        m.addAction(icons.icon("trash"), tr("Usuń zakładkę")).triggered.connect(lambda: self.ctrl.toggle_bookmark(mid))
        m.exec(self.bm_list.viewport().mapToGlobal(pos))
