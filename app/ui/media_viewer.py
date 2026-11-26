"""Duży podgląd: zdjęcia (zoom, przesuwanie, obrót) i wbudowany odtwarzacz filmów."""
from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import (QEasingCurve, QObject, QPointF, QRectF, QSizeF, Qt, QTimer, QUrl,
                            QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QDesktopServices, QImage, QPainter, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView,
                               QHBoxLayout, QLabel, QProgressBar, QPushButton, QSlider, QStackedWidget, QToolButton,
                               QVBoxLayout, QWidget)

from app.services.thumbnail_service import load_display_image, pil_to_qimage, video_frame_image
from app.ui import icons, theme
from app.ui.wrap_fix import refit
from app.utils.formatting import human_duration


# ---------------------------------------------------------------------- #
# Asynchroniczne ładowanie dużych obrazów (z buforem i wyprzedzaniem)
# ---------------------------------------------------------------------- #
class ImageLoader(QObject):
    loaded = Signal(int, QImage)
    failed = Signal(int, str)

    def __init__(self, cache_size: int = 5):
        super().__init__()
        self._cache: OrderedDict[int, QImage] = OrderedDict()
        self._cache_size = cache_size
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._wanted: tuple[int, Path, str] | None = None
        self._prefetch: list[tuple[int, Path, str]] = []
        self._stop = False
        self._t = threading.Thread(target=self._run, daemon=True, name="image-loader")
        self._t.start()

    def cached(self, media_id: int) -> QImage | None:
        with self._lock:
            img = self._cache.get(media_id)
            if img is not None:
                self._cache.move_to_end(media_id)
            return img

    def request(self, media_id: int, path: Path, kind: str, prefetch: list[tuple[int, Path, str]] = ()) -> None:
        with self._cond:
            self._wanted = (media_id, path, kind)
            self._prefetch = [p for p in prefetch if p[0] not in self._cache]
            self._cond.notify()

    def prefetch(self, items: list[tuple[int, Path, str]]) -> None:
        """Wczytuje sąsiednie zdjęcia z wyprzedzeniem (bez zmiany bieżącego)."""
        with self._cond:
            self._prefetch = [p for p in items if p[0] not in self._cache]
            if self._prefetch:
                self._cond.notify()

    def invalidate(self, media_id: int) -> None:
        with self._lock:
            self._cache.pop(media_id, None)

    def shutdown(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify()

    def _run(self) -> None:
        while True:
            with self._cond:
                while self._wanted is None and not self._prefetch and not self._stop:
                    self._cond.wait()
                if self._stop:
                    return
                if self._wanted is not None:
                    job, primary = self._wanted, True
                    self._wanted = None
                else:
                    job, primary = self._prefetch.pop(0), False
                cached = self._cache.get(job[0])
            if cached is not None:
                if primary:
                    self.loaded.emit(job[0], cached)
                continue
            mid, path, kind = job
            try:
                if kind == "video":
                    pil = video_frame_image(path, at_fraction=0.0, max_seek=0.0)
                    if pil is None:
                        raise ValueError("brak klatki")
                    pil.thumbnail((1920, 1920))
                    img = pil_to_qimage(pil)
                else:
                    img = load_display_image(path)
                if img.isNull():
                    raise ValueError("nie udało się odczytać obrazu")
            except Exception as exc:
                if primary:
                    self.failed.emit(mid, str(exc))
                continue
            with self._lock:
                self._cache[mid] = img
                while len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)
            if primary:
                self.loaded.emit(mid, img)


# ---------------------------------------------------------------------- #
class _DragMixin:
    """Wykrywa rozpoczęcie przeciągania (naciśnięcie + ruch) na podglądzie."""
    drag_threshold = 8

    def _drag_press(self, e) -> None:
        self._press = e.position() if e.button() == Qt.MouseButton.LeftButton else None

    def _drag_move(self, e) -> bool:
        p = getattr(self, "_press", None)
        if p is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            return False
        if (e.position() - p).manhattanLength() >= max(self.drag_threshold, QApplication.startDragDistance()):
            self._press = None
            self.drag_requested.emit()
            return True
        return False


class ImageView(QGraphicsView, _DragMixin):
    drag_requested = Signal()
    zoom_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.item = QGraphicsPixmapItem()
        self.item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene().addItem(self.item)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setStyleSheet("background: transparent;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fit_mode = True
        self.rotation = 0
        self._press = None
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(160)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.valueChanged.connect(lambda v: self.item.setOpacity(float(v)))

    def set_image(self, img: QImage | QPixmap | None, fade: bool = True, keep_view: bool = False) -> None:
        if img is None:
            self.item.setPixmap(QPixmap())
            return
        pm = QPixmap.fromImage(img) if isinstance(img, QImage) else img
        self.item.setPixmap(pm)
        self.item.setTransformOriginPoint(self.item.boundingRect().center())
        self.scene().setSceneRect(self.item.sceneBoundingRect())
        if not keep_view:
            self.fit_mode = True
        self._apply_rotation()
        if self.fit_mode:
            self.fit()
        if fade:
            self._fade.stop()
            self.item.setOpacity(0.0)
            self._fade.start()
        else:
            self.item.setOpacity(1.0)

    def set_rotation(self, deg: int) -> None:
        self.rotation = deg % 360
        self._apply_rotation()
        self.fit()

    def _apply_rotation(self) -> None:
        self.item.setRotation(self.rotation)
        self.scene().setSceneRect(self.item.sceneBoundingRect())

    def fit(self) -> None:
        self.fit_mode = True
        if self.item.pixmap().isNull():
            return
        self.resetTransform()
        r = self.item.sceneBoundingRect()
        vw, vh = self.viewport().width() - 24, self.viewport().height() - 24
        if r.width() <= 0 or r.height() <= 0 or vw <= 0 or vh <= 0:
            return
        s = min(vw / r.width(), vh / r.height())
        self.scale(s, s)
        self.centerOn(r.center())
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.zoom_changed.emit(s)

    def current_scale(self) -> float:
        return self.transform().m11() if self.rotation % 180 == 0 else abs(self.transform().m12()) or self.transform().m11()

    def fit_scale(self) -> float:
        r = self.item.sceneBoundingRect()
        vw, vh = self.viewport().width() - 24, self.viewport().height() - 24
        if r.width() <= 0 or r.height() <= 0:
            return 1.0
        return min(vw / r.width(), vh / r.height())

    def zoom(self, factor: float) -> None:
        if self.item.pixmap().isNull():
            return
        cur = self.transform().m11()
        fit = self.fit_scale()
        new = max(fit * 0.5, min(cur * factor, max(8.0, fit * 2)))
        if new <= fit * 1.001:
            self.fit()
            return
        self.fit_mode = False
        f = new / cur
        self.scale(f, f)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.zoom_changed.emit(new)

    def actual_size(self) -> None:
        self.resetTransform()
        self.fit_mode = False
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.zoom_changed.emit(1.0)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if self.fit_mode:
            self.fit()

    def wheelEvent(self, e) -> None:
        d = e.angleDelta().y()
        if d:
            self.zoom(1.15 if d > 0 else 1 / 1.15)
        e.accept()

    def mouseDoubleClickEvent(self, e) -> None:
        if self.fit_mode:
            self.actual_size()
        else:
            self.fit()

    def mousePressEvent(self, e) -> None:
        if self.fit_mode:
            self._drag_press(e)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        if self.fit_mode:
            self._drag_move(e)
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        self._press = None
        super().mouseReleaseEvent(e)


# ---------------------------------------------------------------------- #
class VideoSurface(QGraphicsView, _DragMixin):
    drag_requested = Signal()
    clicked = Signal()
    double_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.video = QGraphicsVideoItem()
        self.scene().addItem(self.video)
        self.poster = QGraphicsPixmapItem()
        self.poster.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene().addItem(self.poster)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHints(QPainter.RenderHint.SmoothPixmapTransform)
        self.setStyleSheet("background: transparent;")
        self.video.nativeSizeChanged.connect(lambda _s: self._layout())
        self._press = None

    def set_poster(self, img: QImage | None) -> None:
        self.poster.setPixmap(QPixmap.fromImage(img) if img is not None and not img.isNull() else QPixmap())
        self.poster.setVisible(img is not None)
        self._layout()

    def show_poster(self, show: bool) -> None:
        self.poster.setVisible(show and not self.poster.pixmap().isNull())

    def _layout(self) -> None:
        vw, vh = self.viewport().width(), self.viewport().height()
        self.scene().setSceneRect(0, 0, vw, vh)
        self.video.setSize(QSizeF(vw, vh))
        self.video.setPos(0, 0)
        pm = self.poster.pixmap()
        if not pm.isNull():
            s = min(vw / pm.width(), vh / pm.height())
            self.poster.setScale(s)
            self.poster.setPos((vw - pm.width() * s) / 2, (vh - pm.height() * s) / 2)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._layout()

    def mousePressEvent(self, e) -> None:
        self._drag_press(e)
        self._click_pending = True

    def mouseMoveEvent(self, e) -> None:
        if self._drag_move(e):
            self._click_pending = False

    def mouseReleaseEvent(self, e) -> None:
        if getattr(self, "_click_pending", False) and e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        self._click_pending = False
        self._press = None

    def mouseDoubleClickEvent(self, e) -> None:
        self.double_clicked.emit()

    def wheelEvent(self, e) -> None:
        e.accept()


class VideoView(QWidget):
    drag_requested = Signal()
    fullscreen_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.8)
        self.player.setAudioOutput(self.audio)
        self.surface = VideoSurface(self)
        self.player.setVideoOutput(self.surface.video)
        self.path: Path | None = None
        self._seeking = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.surface, 1)

        self.error_box = QWidget(self)
        eb = QVBoxLayout(self.error_box)
        eb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_icon = QLabel()
        self.error_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_title = QLabel("Nie można odtworzyć tego filmu")
        self.error_title.setObjectName("EmptyTitle")
        self.error_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_text = QLabel()
        self.error_text.setObjectName("Muted")
        self.error_text.setWordWrap(True)
        self.error_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_btn = QPushButton("Otwórz w domyślnym odtwarzaczu Windows")
        self.error_btn.clicked.connect(self._open_external)
        eb.addWidget(self.error_icon)
        eb.addWidget(self.error_title)
        eb.addWidget(self.error_text)
        eb.addWidget(self.error_btn, 0, Qt.AlignmentFlag.AlignCenter)
        self.error_box.hide()

        # pasek sterowania
        self.controls = QWidget(self)
        self.controls.setObjectName("VideoControls")
        cl = QHBoxLayout(self.controls)
        cl.setContentsMargins(12, 6, 12, 8)
        cl.setSpacing(8)
        self.btn_play = QToolButton()
        self.btn_play.setToolTip("Odtwórz / pauza (spacja)")
        self.btn_play.clicked.connect(self.toggle_play)
        self.lbl_pos = QLabel("0:00")
        self.lbl_pos.setObjectName("Muted")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.slider.sliderReleased.connect(self._seek_release)
        self.slider.sliderMoved.connect(lambda v: self.lbl_pos.setText(human_duration(v / 1000)))
        self.lbl_dur = QLabel("0:00")
        self.lbl_dur.setObjectName("Muted")
        self.btn_mute = QToolButton()
        self.btn_mute.setToolTip("Wycisz")
        self.btn_mute.clicked.connect(self.toggle_mute)
        self.vol = QSlider(Qt.Orientation.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(80)
        self.vol.setFixedWidth(90)
        self.vol.setToolTip("Głośność")
        self.vol.valueChanged.connect(lambda v: (self.audio.setVolume(v / 100), self._update_icons()))
        self.btn_full = QToolButton()
        self.btn_full.setToolTip("Pełny ekran (F11)")
        self.btn_full.clicked.connect(self.fullscreen_requested)
        for w in (self.btn_play, self.lbl_pos):
            cl.addWidget(w)
        cl.addWidget(self.slider, 1)
        for w in (self.lbl_dur, self.btn_mute, self.vol, self.btn_full):
            cl.addWidget(w)
        lay.addWidget(self.controls)

        self.player.positionChanged.connect(self._on_pos)
        self.player.durationChanged.connect(self._on_dur)
        self.player.playbackStateChanged.connect(lambda _s: self._update_icons())
        self.player.errorOccurred.connect(self._on_error)
        self.player.mediaStatusChanged.connect(self._on_status)
        self.surface.drag_requested.connect(self.drag_requested)
        self.surface.clicked.connect(self.toggle_play)
        self.surface.double_clicked.connect(self.fullscreen_requested)
        self._update_icons()

    # -- API ---------------------------------------------------------------
    def load(self, path: Path, poster: QImage | None = None, known_duration: float | None = None) -> None:
        self.stop()
        self.path = path
        self.error_box.hide()
        self.controls.show()
        self.surface.show()
        self.surface.set_poster(poster)
        self.surface.show_poster(True)
        self.slider.setRange(0, int((known_duration or 0) * 1000))
        self.slider.setValue(0)
        self.lbl_pos.setText("0:00")
        self.lbl_dur.setText(human_duration(known_duration) if known_duration else "0:00")
        # film NIE startuje automatycznie
        self.player.setSource(QUrl.fromLocalFile(str(path)))

    def set_poster(self, img: QImage) -> None:
        if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self.surface.set_poster(img)
            self.surface.show_poster(self.player.position() == 0)

    def stop(self) -> None:
        self.player.stop()
        self.player.setSource(QUrl())

    def toggle_play(self) -> None:
        if self.error_box.isVisible():
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.surface.show_poster(False)
            self.player.play()

    def toggle_mute(self) -> None:
        self.audio.setMuted(not self.audio.isMuted())
        self._update_icons()

    def seek_relative(self, seconds: float) -> None:
        self.player.setPosition(max(0, self.player.position() + int(seconds * 1000)))

    # -- zdarzenia ---------------------------------------------------------
    def _seek_release(self) -> None:
        self._seeking = False
        self.surface.show_poster(False)
        self.player.setPosition(self.slider.value())

    def _on_pos(self, pos: int) -> None:
        if not self._seeking:
            self.slider.setValue(pos)
            self.lbl_pos.setText(human_duration(pos / 1000))

    def _on_dur(self, dur: int) -> None:
        if dur > 0:
            self.slider.setRange(0, dur)
            self.lbl_dur.setText(human_duration(dur / 1000))

    def _on_status(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.player.setPosition(0)
            self.player.pause()
            self.surface.show_poster(True)
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._on_error(None, "")

    def _on_error(self, _err, msg: str = "") -> None:
        self.surface.show_poster(False)
        self.controls.hide()  # nie ma czego odtwarzać; bez tego pasek „wskakuje” na środek
        self.error_icon.setPixmap(icons.pixmap("warning", 40, theme.current()["text3"]))
        self.error_text.setFixedWidth(min(520, max(260, self.width() - 60)))
        self.error_text.setText(
            "Ten format lub kodek nie jest obsługiwany przez wbudowany odtwarzacz.\n"
            "Plik jest bezpieczny — możesz go nadal przenosić do folderów."
            + (f"\n\nSzczegóły: {msg}" if msg else ""))
        refit(self.error_text)
        self.error_box.show()
        self.error_box.setGeometry(self.rect())
        self.error_box.raise_()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        ctrl_h = self.controls.height() if self.controls.isVisible() else 0
        self.error_box.setGeometry(0, 0, self.width(), self.height() - ctrl_h)

    def _open_external(self) -> None:
        if self.path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.path)))

    def _update_icons(self) -> None:
        c = theme.current()["text"]
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.btn_play.setIcon(icons.icon("pause" if playing else "play", c, 20))
        muted = self.audio.isMuted() or self.vol.value() == 0
        self.btn_mute.setIcon(icons.icon("mute" if muted else "volume", c, 20))
        self.btn_full.setIcon(icons.icon("fullscreen", c, 20))

    def refresh_theme(self) -> None:
        self._update_icons()


# ---------------------------------------------------------------------- #
class EmptyState(QWidget):
    action = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(10)
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel()
        self.title.setObjectName("EmptyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text = QLabel()
        self.text.setObjectName("Muted")
        self.text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text.setWordWrap(True)
        self.text.setFixedWidth(460)
        self.btn = QPushButton()
        self.btn.setObjectName("Primary")
        self.btn.clicked.connect(self.action)
        self.bar = QProgressBar()
        self.bar.setFixedWidth(360)
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 100)
        self.bar.hide()
        self.bar_text = QLabel()
        self.bar_text.setObjectName("Muted")
        self.bar_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bar_text.hide()
        lay.addWidget(self.icon)
        lay.addWidget(self.title)
        lay.addWidget(self.text, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addSpacing(4)
        lay.addWidget(self.bar, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.bar_text, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addSpacing(6)
        lay.addWidget(self.btn, 0, Qt.AlignmentFlag.AlignCenter)
        self._icon_name = "photo"

    def set(self, icon: str, title: str, text: str, button: str | None = None) -> None:
        self._icon_name = icon
        self.icon.setPixmap(icons.pixmap(icon, 52, theme.current()["text3"], 1.4))
        self.title.setText(title)
        self.text.setText(text)
        refit(self.text)
        self.btn.setVisible(bool(button))
        if button:
            self.btn.setText(button)
        self.set_progress(None)

    def set_progress(self, percent: int | None, label: str = "") -> None:
        """Pasek postępu pod opisem: None — ukryty, -1 — „trwa” (bez procentów), 0–100 — %."""
        if percent is None:
            self.bar.hide()
            self.bar_text.hide()
            return
        if percent < 0:
            self.bar.setRange(0, 0)
        else:
            self.bar.setRange(0, 100)
            self.bar.setValue(max(0, min(100, int(percent))))
        self.bar.show()
        self.bar_text.setText(label)
        self.bar_text.setVisible(bool(label))


class MediaViewer(QWidget):
    """Przełącza zdjęcie / film / pusty stan i rysuje przyciski nakładki."""
    drag_requested = Signal()
    prev_requested = Signal()
    next_requested = Signal()
    fullscreen_requested = Signal()
    empty_action = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stack = QStackedWidget(self)
        self.image = ImageView()
        self.video = VideoView()
        self.empty = EmptyState()
        self.loading = QLabel()
        self.stack.addWidget(self.image)
        self.stack.addWidget(self.video)
        self.stack.addWidget(self.empty)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)
        self.image.drag_requested.connect(self.drag_requested)
        self.video.drag_requested.connect(self.drag_requested)
        self.video.fullscreen_requested.connect(self.fullscreen_requested)
        self.empty.action.connect(self.empty_action)

        self.btn_prev = self._overlay("chevron_left", "Poprzedni (←)", self.prev_requested.emit)
        self.btn_next = self._overlay("chevron_right", "Następny (→)", self.next_requested.emit)

        self.toolbar = QFrame(self)
        self.toolbar.setObjectName("Toast")
        tl = QHBoxLayout(self.toolbar)
        tl.setContentsMargins(6, 4, 6, 4)
        tl.setSpacing(2)
        self.tb_buttons = {}
        for name, tip, fn in (("zoom_out", "Pomniejsz (−)", lambda: self.image.zoom(1 / 1.25)),
                              ("fit", "Dopasuj do okna (0)", self.image.fit),
                              ("zoom_in", "Powiększ (+)", lambda: self.image.zoom(1.25)),
                              ("rotate", "Obróć podgląd (R)", self.rotate),
                              ("fullscreen", "Pełny ekran (F11)", self.fullscreen_requested.emit)):
            b = QToolButton()
            b.setToolTip(tip)
            b.clicked.connect(fn)
            tl.addWidget(b)
            self.tb_buttons[name] = b
        self.zoom_label = QLabel("")
        self.zoom_label.setObjectName("Muted")
        self.zoom_label.setMinimumWidth(42)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tl.insertWidget(1, self.zoom_label)
        self.image.zoom_changed.connect(lambda s: self.zoom_label.setText(f"{round(s * 100)}%"))
        self.rotations: dict[int, int] = {}
        self.current_id: int | None = None
        self.refresh_theme()
        self.setMouseTracking(True)

    def _overlay(self, icon: str, tip: str, fn) -> QToolButton:
        b = QToolButton(self)
        b.setObjectName("OverlayBtn")
        b.setToolTip(tip)
        b.setIconSize(icons.size(22))
        b.setProperty("icon_name", icon)
        b.clicked.connect(fn)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    def refresh_theme(self) -> None:
        c = theme.current()["text"]
        for b in (self.btn_prev, self.btn_next):
            b.setIcon(icons.icon(b.property("icon_name"), c, 22))
        for name, b in self.tb_buttons.items():
            b.setIcon(icons.icon(name, c, 18))
        self.video.refresh_theme()
        self.empty.set(self.empty._icon_name, self.empty.title.text(), self.empty.text.text(),
                       self.empty.btn.text() if self.empty.btn.isVisibleTo(self.empty) else None)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        h = self.height()
        bottom_pad = self.video.controls.height() if self.stack.currentWidget() is self.video else 0
        self.btn_prev.setGeometry(14, int((h - bottom_pad) / 2 - 20), 40, 40)
        self.btn_next.setGeometry(self.width() - 54, int((h - bottom_pad) / 2 - 20), 40, 40)
        tb = self.toolbar.sizeHint()
        self.toolbar.setGeometry(int((self.width() - tb.width()) / 2), h - tb.height() - 14, tb.width(), tb.height())
        self.btn_prev.raise_()
        self.btn_next.raise_()
        self.toolbar.raise_()

    def set_nav(self, has_prev: bool, has_next: bool) -> None:
        self.btn_prev.setVisible(has_prev)
        self.btn_next.setVisible(has_next)

    def show_empty(self, icon: str, title: str, text: str, button: str | None = None) -> None:
        if self.stack.currentWidget() is self.empty and self.current_id is None \
                and (icon, title, text) == (self.empty._icon_name, self.empty.title.text(), self.empty.text.text()) \
                and (button or "") == (self.empty.btn.text() if self.empty.btn.isVisibleTo(self.empty) else ""):
            return      # bez zmian — nie migaj (wywoływane m.in. co sekundę podczas wczytywania)
        self.video.stop()
        self.current_id = None
        self.empty.set(icon, title, text, button)
        self.stack.setCurrentWidget(self.empty)
        self.toolbar.hide()
        self.set_nav(False, False)

    def show_photo(self, media_id: int, img: QImage | QPixmap | None, final: bool) -> None:
        if self.stack.currentWidget() is self.video:
            self.video.stop()
        same = media_id == self.current_id
        self.current_id = media_id
        self.stack.setCurrentWidget(self.image)
        self.image.rotation = self.rotations.get(media_id, 0)
        # przy podmianie miniatury na pełny obraz zachowaj powiększenie, bez ponownego „fade”
        self.image.set_image(img, fade=not same, keep_view=same and not self.image.fit_mode)
        self.toolbar.show()
        self._relayout()

    def show_video(self, media_id: int, path: Path, poster: QImage | None, duration: float | None) -> None:
        self.current_id = media_id
        self.stack.setCurrentWidget(self.video)
        self.video.load(path, poster, duration)
        self.toolbar.hide()
        self._relayout()

    def _relayout(self) -> None:
        from PySide6.QtGui import QResizeEvent
        self.resizeEvent(QResizeEvent(self.size(), self.size()))

    def rotate(self) -> None:
        if self.current_id is None or self.stack.currentWidget() is not self.image:
            return
        r = (self.rotations.get(self.current_id, 0) + 90) % 360
        self.rotations[self.current_id] = r
        self.image.set_rotation(r)

    def showing_empty(self) -> bool:
        return self.stack.currentWidget() is self.empty

    def is_video(self) -> bool:
        return self.stack.currentWidget() is self.video
