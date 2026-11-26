"""Generowanie i buforowanie miniatur oraz ładowanie dużych podglądów.

* Miniatury zapisywane są na dysku w .photosort/thumbnails (JPEG), więc po
  ponownym uruchomieniu nie trzeba ich generować.
* Generowanie odbywa się w kilku wątkach tła; najnowsze żądania (widoczne
  na ekranie) obsługiwane są w pierwszej kolejności (stos LIFO).
* W pamięci trzymamy ograniczoną liczbę gotowych QPixmap (LRU).
"""
from __future__ import annotations

import os
import threading
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QImage, QImageReader, QPixmap

from app.constants import THUMB_SIZE

try:
    from PIL import Image, ImageOps
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:  # pragma: no cover
        pass
except Exception:  # pragma: no cover
    Image = None  # type: ignore

try:
    import av
except Exception:  # pragma: no cover
    av = None  # type: ignore

# Formaty, które Qt czyta natywnie (szybciej niż Pillow); HEIC zawsze przez Pillow.
QT_NATIVE = {".jpg", ".jpeg", ".jpe", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"}


# ---------------------------------------------------------------------- #
# Generowanie (bez Qt GUI — bezpieczne w wątkach)
# ---------------------------------------------------------------------- #
def video_frame_image(path: Path, at_fraction: float = 0.1, max_seek: float = 1.0):
    """Zwraca klatkę filmu jako PIL.Image (z uwzględnieniem obrotu) albo None."""
    if av is None:
        return None
    with av.open(str(path)) as container:
        if not container.streams.video:
            return None
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        duration = (container.duration or 0) / 1_000_000
        target = min(max_seek, duration * at_fraction) if duration else 0
        if target > 0:
            try:
                container.seek(int(target * 1_000_000), any_frame=False, backward=True)
            except Exception:
                pass
        for frame in container.decode(stream):
            img = frame.to_image()
            rot = int(getattr(frame, "rotation", 0) or 0)
            if rot:
                # rotation w FFmpeg = obrót przeciwnie do ruchu wskazówek zegara
                img = img.rotate(rot, expand=True)
            return img
    return None


def pil_open_oriented(path: Path):
    im = Image.open(path)
    try:
        im.seek(0)
    except Exception:
        pass
    return im


def make_thumbnail(src: Path, kind: str, dst: Path, size: int = THUMB_SIZE) -> bool:
    if Image is None:
        return False
    img = None
    if kind == "video":
        img = video_frame_image(src)
        if img is None:
            return False
    else:
        im = pil_open_oriented(src)
        try:
            if im.format == "JPEG":
                im.draft("RGB", (size * 2, size * 2))
            im = ImageOps.exif_transpose(im) or im
            img = im
            img.thumbnail((size, size), Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS)
            if img.mode not in ("RGB",):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                rgba = img.convert("RGBA")
                bg.paste(rgba, mask=rgba.split()[3])
                img = bg
        finally:
            pass
    if kind == "video":
        img.thumbnail((size, size))
        img = img.convert("RGB")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp")
    img.save(tmp, "JPEG", quality=82, optimize=False)
    os.replace(tmp, dst)
    return True


def pil_to_qimage(img) -> QImage:
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    if img.mode == "RGB":
        data = img.tobytes("raw", "RGB")
        qimg = QImage(data, img.width, img.height, img.width * 3, QImage.Format.Format_RGB888)
    else:
        data = img.tobytes("raw", "RGBA")
        qimg = QImage(data, img.width, img.height, img.width * 4, QImage.Format.Format_RGBA8888)
    return qimg.copy()  # odłączenie od bufora Pythona


def load_display_image(path: Path, max_side: int = 7000) -> QImage:
    """Ładuje zdjęcie do podglądu z prawidłową orientacją EXIF."""
    ext = path.suffix.lower()
    if ext in QT_NATIVE:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid() and max(size.width(), size.height()) > max_side:
            reader.setScaledSize(size.scaled(QSize(max_side, max_side), Qt.AspectRatioMode.KeepAspectRatio))
        img = reader.read()
        if not img.isNull():
            return img
    if Image is None:
        return QImage()
    with Image.open(path) as im:
        im.seek(0) if hasattr(im, "seek") else None
        im = ImageOps.exif_transpose(im) or im
        if max(im.size) > max_side:
            im.thumbnail((max_side, max_side))
        return pil_to_qimage(im)


# ---------------------------------------------------------------------- #
# Qt: asynchroniczne ładowanie miniatur
# ---------------------------------------------------------------------- #
class ThumbnailService(QObject):
    ready = Signal(int)          # media_id — miniatura dostępna w cache
    failed = Signal(int)

    def __init__(self, threads: int = 3, memory_items: int = 2500):
        super().__init__()
        self._cache: OrderedDict[int, QPixmap] = OrderedDict()
        self._images: dict[int, QImage] = {}
        self._failed: set[int] = set()
        self._limit = memory_items
        self._stack: list[tuple[int, Path, str, Path]] = []
        self._pending: set[int] = set()
        self._cond = threading.Condition()
        self._stop = False
        self._generation = 0
        self._threads = [threading.Thread(target=self._run, daemon=True, name=f"thumb-{i}")
                         for i in range(threads)]
        for t in self._threads:
            t.start()
        self._img_lock = threading.Lock()
        self.ready.connect(self._promote)

    # wywoływane w wątku GUI
    def get(self, media_id: int) -> QPixmap | None:
        pm = self._cache.get(media_id)
        if pm is not None:
            self._cache.move_to_end(media_id)
        return pm

    def has_failed(self, media_id: int) -> bool:
        return media_id in self._failed

    def request(self, media_id: int, src: Path, kind: str, thumb: Path) -> None:
        if media_id in self._cache or media_id in self._failed:
            return
        with self._cond:
            if media_id in self._pending:
                # przesuń na szczyt stosu (obecnie widoczne)
                for i, item in enumerate(self._stack):
                    if item[0] == media_id:
                        self._stack.append(self._stack.pop(i))
                        break
                return
            self._pending.add(media_id)
            self._stack.append((media_id, src, kind, thumb))
            if len(self._stack) > 4000:  # porzuć najstarsze, dawno przewinięte żądania
                drop = self._stack[:1000]
                del self._stack[:1000]
                for d in drop:
                    self._pending.discard(d[0])
            self._cond.notify()

    def invalidate(self, media_id: int) -> None:
        self._cache.pop(media_id, None)
        self._failed.discard(media_id)

    def clear(self) -> None:
        with self._cond:
            self._stack.clear()
            self._pending.clear()
            self._generation += 1
        self._cache.clear()
        self._failed.clear()

    def shutdown(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify_all()

    # wątki robocze
    def _run(self) -> None:
        while True:
            with self._cond:
                while not self._stack and not self._stop:
                    self._cond.wait()
                if self._stop:
                    return
                media_id, src, kind, thumb = self._stack.pop()
                gen = self._generation
            ok = False
            img = QImage()
            try:
                fresh = thumb.is_file() and thumb.stat().st_mtime >= src.stat().st_mtime
                if not fresh:
                    ok = make_thumbnail(src, kind, thumb)
                else:
                    ok = True
                if ok:
                    img = QImage(str(thumb))
                    ok = not img.isNull()
            except Exception:
                ok = False
            with self._cond:
                self._pending.discard(media_id)
                if gen != self._generation:
                    continue
            if ok:
                with self._img_lock:
                    self._images[media_id] = img
                self.ready.emit(media_id)
            else:
                self._failed.add(media_id)
                self.failed.emit(media_id)

    def _promote(self, media_id: int) -> None:
        with self._img_lock:
            img = self._images.pop(media_id, None)
        if img is None:
            return
        self._cache[media_id] = QPixmap.fromImage(img)
        while len(self._cache) > self._limit:
            self._cache.popitem(last=False)
