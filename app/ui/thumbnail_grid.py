"""Kolejka multimediów: wirtualizowany pasek / siatka miniatur z przeciąganiem."""
from __future__ import annotations

from PySide6.QtCore import (QAbstractListModel, QItemSelectionModel, QModelIndex, QPoint, QRect, QRectF,
                            QSize, Qt, Signal)
from PySide6.QtGui import QAction, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QListView, QMenu, QStyle,
                               QStyledItemDelegate, QStyleOptionViewItem)

from app.core.library_controller import LibraryController
from app.services.thumbnail_service import ThumbnailService
from app.ui import icons, theme
from app.ui.drag import start_media_drag
from app.utils.formatting import human_duration

ID_ROLE = Qt.ItemDataRole.UserRole + 1


class QueueModel(QAbstractListModel):
    def __init__(self, ctrl: LibraryController, thumbs: ThumbnailService):
        super().__init__()
        self.ctrl = ctrl
        self.thumbs = thumbs
        self._row_of: dict[int, int] = {}
        ctrl.queue_reset.connect(self.reset)
        ctrl.queue_removed.connect(lambda _ids: self.reset())
        ctrl.meta_updated.connect(self._meta_updated)
        thumbs.ready.connect(self._thumb_ready)
        thumbs.failed.connect(self._thumb_ready)
        ctrl.device_thumb_ready.connect(self._thumb_ready)

    def reset(self) -> None:
        self.beginResetModel()
        self._row_of = {mid: i for i, mid in enumerate(self.ctrl.ids)}
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.ctrl.ids)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.ctrl.ids):
            return None
        mid = self.ctrl.ids[index.row()]
        if role == ID_ROLE:
            return mid
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            row = self.ctrl.rows.get(mid)
            return row[0] if row else ""
        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled

    def row_of(self, media_id: int) -> int:
        return self._row_of.get(media_id, -1)

    def _thumb_ready(self, media_id: int) -> None:
        r = self._row_of.get(media_id)
        if r is not None and r < len(self.ctrl.ids):
            idx = self.index(r)
            self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])

    def _meta_updated(self, ids: list) -> None:
        for mid in ids:
            self._thumb_ready(mid)


class ThumbDelegate(QStyledItemDelegate):
    def __init__(self, view: "ThumbnailView"):
        super().__init__(view)
        self.view = view

    def sizeHint(self, option, index) -> QSize:
        return self.view.gridSize()

    def paint(self, p: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        ctrl = self.view.ctrl
        thumbs = self.view.thumbs
        mid = index.data(ID_ROLE)
        if mid is None:
            return
        row = ctrl.rows.get(mid)
        kind = row[1] if row else "photo"
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(option.rect).adjusted(4, 4, -4, -4)
        path = QPainterPath()
        path.addRoundedRect(r, 9, 9)
        p.setClipPath(path)
        p.fillRect(r, theme.color("thumb_bg"))
        pm = ctrl.device_thumb(mid) if mid < 0 else thumbs.get(mid)
        if pm is not None and not pm.isNull():
            sw, sh = pm.width(), pm.height()
            tr = r.width() / r.height()
            if sw / sh > tr:
                nw = sh * tr
                src = QRectF((sw - nw) / 2, 0, nw, sh)
            else:
                nh = sw / tr
                src = QRectF(0, (sh - nh) / 2, sw, nh)
            p.drawPixmap(r, pm, src)
        else:
            if row and mid >= 0 and not thumbs.has_failed(mid):
                lib = ctrl.lib
                thumbs.request(mid, lib.abs_path(row[4]), kind, lib.thumb_path(mid))
            isz = int(min(r.width(), r.height()) * 0.32)
            ip = icons.pixmap("film" if kind == "video" else "photo", isz, theme.current()["text3"])
            p.drawPixmap(int(r.center().x() - isz / 2), int(r.center().y() - isz / 2), ip)

        if kind == "video":
            grad = QLinearGradient(r.bottomLeft(), r.bottomLeft() - QPoint(0, 30))
            grad.setColorAt(0, QColor(0, 0, 0, 150))
            grad.setColorAt(1, QColor(0, 0, 0, 0))
            p.fillRect(QRectF(r.left(), r.bottom() - 30, r.width(), 30), grad)
            play = icons.pixmap("play", 12, "#FFFFFF")
            p.drawPixmap(int(r.left() + 7), int(r.bottom() - 18), play)
            dur = row[2] if row else None
            if dur:
                p.setPen(QColor("#FFFFFF"))
                f = theme.ui_font(8, QFont.Weight.DemiBold)
                p.setFont(f)
                p.drawText(QRectF(r.left(), r.bottom() - 21, r.width() - 7, 18),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, human_duration(dur))
        p.setClipping(False)

        is_current = mid == ctrl.current_id
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if hovered and not is_current:
            p.fillPath(path, QColor(255, 255, 255, 40))
        if selected and len(self.view.selectionModel().selectedIndexes()) > 1:
            # znacznik zaznaczenia (wielokrotny wybór)
            c = QRectF(r.right() - 24, r.top() + 6, 18, 18)
            p.setPen(QPen(QColor("#FFFFFF"), 1.5))
            p.setBrush(theme.color("accent"))
            p.drawEllipse(c)
            ck = icons.pixmap("check", 12, "#FFFFFF", 2.6)
            p.drawPixmap(int(c.left() + 3), int(c.top() + 3), ck)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(theme.color("accent"), 2))
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 8, 8)
        if is_current:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(theme.color("accent"), 3))
            p.drawRoundedRect(r.adjusted(-1.5, -1.5, 1.5, 1.5), 10.5, 10.5)
        p.restore()


class ThumbnailView(QListView):
    expand_requested = Signal()

    def __init__(self, ctrl: LibraryController, thumbs: ThumbnailService, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.thumbs = thumbs
        self.model_ = QueueModel(ctrl, thumbs)
        self.setModel(self.model_)
        self.setItemDelegate(ThumbDelegate(self))
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setMovement(QListView.Movement.Static)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setLayoutMode(QListView.LayoutMode.Batched)
        self.setBatchSize(400)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setMouseTracking(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.clicked.connect(self._on_clicked)
        self.grid_mode = False
        self.set_grid_mode(False)
        ctrl.current_changed.connect(self._sync_current)
        ctrl.queue_reset.connect(lambda: self._sync_current(ctrl.current_id, center=True))
        ctrl.queue_removed.connect(lambda _ids: self._sync_current(ctrl.current_id))
        self.move_to_folder = None  # callback(ids, folder) ustawiany przez widok biblioteki
        self.folders_provider = None

    # -- tryby ------------------------------------------------------------
    def set_grid_mode(self, grid: bool) -> None:
        self.grid_mode = grid
        if grid:
            self.setFlow(QListView.Flow.LeftToRight)
            self.setWrapping(True)
            self.setGridSize(QSize(136, 136))
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            self.setFlow(QListView.Flow.LeftToRight)
            self.setWrapping(False)
            self.setGridSize(QSize(92, 92))
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scheduleDelayedItemsLayout()
        self._sync_current(self.ctrl.current_id, center=True)

    def scroll_value(self) -> int:
        bar = self.verticalScrollBar() if self.grid_mode else self.horizontalScrollBar()
        return bar.value()

    def set_scroll_value(self, v: int) -> None:
        bar = self.verticalScrollBar() if self.grid_mode else self.horizontalScrollBar()
        bar.setValue(v)

    # -- synchronizacja z kontrolerem --------------------------------------
    def _sync_current(self, media_id, center: bool = False) -> None:
        if media_id is None:
            self.viewport().update()
            return
        row = self.model_.row_of(media_id)
        if row < 0:
            return
        idx = self.model_.index(row)
        sm = self.selectionModel()
        if not idx in sm.selectedIndexes() or len(sm.selectedIndexes()) <= 1:
            sm.setCurrentIndex(idx, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        else:
            sm.setCurrentIndex(idx, QItemSelectionModel.SelectionFlag.NoUpdate)
        hint = QAbstractItemView.ScrollHint.PositionAtCenter if center else QAbstractItemView.ScrollHint.EnsureVisible
        self.scrollTo(idx, hint)
        self.viewport().update()

    def _on_clicked(self, index: QModelIndex) -> None:
        mods = QApplication.keyboardModifiers()
        if mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            self.viewport().update()
            return
        self.ctrl.set_index(index.row())

    def selected_ids(self) -> list[int]:
        rows = sorted(i.row() for i in self.selectionModel().selectedIndexes())
        return [self.ctrl.ids[r] for r in rows if r < len(self.ctrl.ids)]

    # -- przeciąganie -----------------------------------------------------
    def mousePressEvent(self, e) -> None:
        self._press_pos = e.position().toPoint()
        super().mousePressEvent(e)

    def startDrag(self, supportedActions) -> None:
        idx = self.currentIndex()
        sel = self.selected_ids()
        pressed = self.indexAt(getattr(self, "_press_pos", QPoint(-1, -1)))
        pid = pressed.data(ID_ROLE) if pressed.isValid() else (idx.data(ID_ROLE) if idx.isValid() else None)
        ids = sel if (pid in sel and len(sel) > 1) else ([pid] if pid is not None else sel)
        if not ids:
            return
        pms = [self.ctrl.device_thumb(i) if i < 0 else self.thumbs.get(i) for i in ids[:3]]
        kinds = [(self.ctrl.rows.get(i) or ("", "photo"))[1] for i in ids[:3]]
        start_media_drag(self, ids, pms, kinds)

    # -- klawiatura / kółko -------------------------------------------------
    def keyPressEvent(self, e) -> None:
        key = e.key()
        if e.modifiers() == Qt.KeyboardModifier.NoModifier:
            if key == Qt.Key.Key_Right:
                self.ctrl.next()
                return
            if key == Qt.Key.Key_Left:
                self.ctrl.prev()
                return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            idx = self.currentIndex()
            if idx.isValid():
                self.ctrl.set_index(idx.row())
            return
        super().keyPressEvent(e)

    def wheelEvent(self, e) -> None:
        if not self.grid_mode and abs(e.angleDelta().y()) > abs(e.angleDelta().x()):
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() - e.angleDelta().y())
            e.accept()
            return
        super().wheelEvent(e)

    # -- menu kontekstowe ---------------------------------------------------
    def _menu(self, pos: QPoint) -> None:
        idx = self.indexAt(pos)
        if not idx.isValid():
            return
        ids = self.selected_ids()
        mid = idx.data(ID_ROLE)
        if mid not in ids:
            ids = [mid]
        m = QMenu(self)
        from_device = mid < 0
        if from_device:
            title = "Skopiuj z telefonu do" if len(ids) == 1 else "Skopiuj zaznaczone z telefonu do"
        else:
            title = "Przenieś zaznaczone do" if len(ids) > 1 else "Przenieś do"
        sub = m.addMenu(icons.icon("folder"), title)
        folders = self.folders_provider() if self.folders_provider else []
        for name in folders:
            if self.ctrl.scope.lower() == name.lower():
                continue
            act = QAction(name, sub)
            act.triggered.connect(lambda _=False, n=name, i=list(ids): self.move_to_folder and self.move_to_folder(i, n))
            sub.addAction(act)
        if not folders:
            sub.setEnabled(False)
        if from_device:
            m.addSeparator()
            sa = m.addAction("Zaznacz wszystko")
            sa.triggered.connect(self.selectAll)
            m.exec(self.viewport().mapToGlobal(pos))
            return
        m.addSeparator()
        bm = m.addAction(icons.icon("bookmark"), "Dodaj / usuń zakładkę")
        bm.triggered.connect(lambda: self.ctrl.toggle_bookmark(mid))
        reveal = m.addAction(icons.icon("open"), "Pokaż w Eksploratorze")

        def _reveal():
            from app.utils.paths import reveal_in_explorer
            row = self.ctrl.rows.get(mid)
            if row:
                reveal_in_explorer(self.ctrl.lib.abs_path(row[4]))
        reveal.triggered.connect(_reveal)
        m.addSeparator()
        sa = m.addAction("Zaznacz wszystko")
        sa.triggered.connect(self.selectAll)
        m.exec(self.viewport().mapToGlobal(pos))
