"""Tryb „Sortuj prosto z telefonu”.

Zdjęcia NIE są importowane hurtowo. Program:
  * wczytuje z telefonu listę plików (bez kopiowania),
  * pokazuje miniatury dostarczane przez telefon (mechanizm Eksploratora Windows),
  * do dużego podglądu kopiuje TYLKO oglądany plik (i dwa kolejne z wyprzedzeniem) do
    tymczasowej pamięci podręcznej .photosort/staging/device-cache, którą ogranicza i czyści,
  * po przeciągnięciu na folder kopiuje plik prosto do tego folderu biblioteki.

Wszystkie obiekty COM powłoki Windows żyją w jednym wątku roboczym (wymóg COM),
dlatego interfejs zleca mu zadania przez kolejki i dostaje wyniki sygnałami Qt.
Na telefonie wykonywane jest wyłącznie kopiowanie (CopyHere) — nigdy przenoszenie ani usuwanie.
"""
from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from app.constants import DISK_SPACE_MARGIN, media_kind
from app.core.import_manager import Importer
from app.core.library_manager import Library
from app.services import device_service as ds

_log = logging.getLogger("photosort.device")

CACHE_MAX_FILES = 40
CACHE_MAX_BYTES = 1500 * 1024 * 1024
THUMB_FALLBACK_MAX = 40 * 1024 * 1024   # zdjęcie bez miniatury z telefonu: kopiuj tylko, gdy < 40 MB
VIDEO_THUMB_FALLBACK_MAX = 60 * 1024 * 1024   # film bez miniatury (iPhone ich nie daje): kopiuj, gdy < 60 MB


@dataclass
class DeviceEntry:
    idx: int
    rel: str
    name: str
    size: int
    modified: str
    kind: str
    key: str
    date: str = ""      # data pliku z telefonu, czas lokalny "YYYY-MM-DD HH:MM:SS" ("" gdy brak)


class DeviceBrowser(QObject):
    scan_progress = Signal(int)         # ile plików telefonu sprawdzono
    scan_status = Signal(str)           # co się teraz dzieje (np. który folder jest czytany)
    scan_found = Signal(int)            # ile NOWYCH plików znaleziono w bieżącym wczytywaniu
    entries_added = Signal(list)        # list[DeviceEntry] — kolejne nowe pliki (od najnowszych)
    scan_finished = Signal(bool)        # True = przejrzano cały telefon (nie ma „kolejnych”)
    scan_failed = Signal(str)
    thumb_ready = Signal(int, QImage)
    thumb_failed = Signal(int)
    fetched = Signal(int, str)          # idx, ścieżka lokalnej kopii podglądu
    fetch_failed = Signal(int, str)
    fetch_progress = Signal(int, int)   # idx, % skopiowanego pliku podglądu
    imported = Signal(int, object, str, str)   # idx, media_id|None, status(ok|dup|error), komunikat
    disconnected = Signal()             # telefon zniknął z „Ten komputer” (odłączony / zablokowany)

    def __init__(self, library: Library, device: str, folders: list[str], only_new: bool = True,
                 limit: int | None = None):
        """limit: pokaż tylko N najnowszych NOWYCH plików (kolejne — przez load_more).
        Bez limitu pliki pojawiają się partiami w trakcie przeglądania telefonu."""
        super().__init__()
        self.lib = library
        self.device = device
        self.folders = folders
        self.only_new = only_new
        self.limit = limit
        self._more: deque = deque()
        self._gen = None
        self._next_idx = 0
        self._examined = 0
        self._any_media = False
        self._last_presence_check = 0.0
        self._gone = False
        self.cache_dir = library.staging_dir / "device-cache"
        self._stop = threading.Event()
        self._cond = threading.Condition()
        self._imports: deque = deque()
        self._fetch: deque = deque()
        self._thumbs: list[int] = []
        self._thumb_set: set[int] = set()
        self._has_thumb: set[int] = set()
        self._cache: OrderedDict[int, Path] = OrderedDict()
        self._pinned: set[int] = set()       # obecnie oglądany plik nie jest usuwany z cache
        self._lock = threading.Lock()
        self.entries: dict[int, DeviceEntry] = {}
        self._items: dict[int, object] = {}  # obiekty COM — używane wyłącznie w wątku roboczym
        ds.reset_copy_mode()
        self._thread = threading.Thread(target=self._run, daemon=True, name="device-browser")
        self._thread.start()

    # ------------------------------------------------------------------ #
    # API (wątek GUI)
    # ------------------------------------------------------------------ #
    def request_thumb(self, idx: int) -> None:
        with self._cond:
            if idx in self._thumb_set:
                return
            self._thumb_set.add(idx)
            self._thumbs.append(idx)
            if len(self._thumbs) > 300:   # porzuć dawno przewinięte
                for old in self._thumbs[:100]:
                    self._thumb_set.discard(old)
                del self._thumbs[:100]
            self._cond.notify()

    def cached_path(self, idx: int) -> Path | None:
        with self._lock:
            p = self._cache.get(idx)
        return p if p is not None and p.exists() else None

    def fetch(self, idx: int, current: bool = True) -> None:
        """Kopia pliku do podglądu. current=True: najwyższy priorytet (oglądany plik)."""
        with self._cond:
            if current:
                self._pinned = {idx}
                if idx in self._fetch:
                    self._fetch.remove(idx)
                self._fetch.appendleft(idx)
            elif idx not in self._fetch:
                self._fetch.append(idx)
                while len(self._fetch) > 4:
                    self._fetch.pop()
            self._cond.notify()

    def load_more(self, n: int | None = None) -> None:
        """Wczytaj kolejne N nowych plików z telefonu (kontynuacja od miejsca zatrzymania)."""
        with self._cond:
            self._more.append(n or self.limit)
            self._cond.notify()

    def import_items(self, idxs: list[int], folder: str) -> None:
        with self._cond:
            for i in idxs:
                self._imports.append((i, folder))
            self._cond.notify()

    def close(self) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        self._thread.join(timeout=10)
        shutil.rmtree(self.cache_dir, ignore_errors=True)

    # ------------------------------------------------------------------ #
    # Wątek roboczy
    # ------------------------------------------------------------------ #
    def _run(self) -> None:
        if not ds.available():
            self.scan_failed.emit("Obsługa urządzeń przenośnych jest niedostępna w tym systemie.")
            return
        db = self.lib.open_db()
        try:
            with ds._Com():
                shell = ds._shell()
                self._gen = ds.iter_newest(shell, self.device, self.folders, self._stop.is_set,
                                           self._on_examined, self.scan_status.emit)
                self._shell, self._db = shell, db
                self._handle("more", self.limit)
                while not self._stop.is_set():
                    job = self._next_job()
                    if job is None:
                        continue
                    self._handle(*job)
        except Exception as exc:
            self.scan_failed.emit(f"Błąd połączenia z urządzeniem: {exc}")
        finally:
            db.close()

    def _handle(self, kind: str, payload) -> None:
        shell, db = self._shell, self._db
        try:
            if kind == "import":
                self._do_import(shell, db, *payload)
            elif kind == "more":
                self._load(db, payload)
            elif kind == "fetch":
                self._do_fetch(shell, payload)
            else:
                self._do_thumb(shell, payload)
        except Exception as exc:  # pojedynczy błąd nie zatrzymuje przeglądania
            _log.warning("%s %s: %s", kind, payload, exc)
            self._check_presence(shell)
            if kind == "import":
                self.imported.emit(payload[0], None, "error", str(exc))
            elif kind == "more":
                self.scan_failed.emit(f"Błąd odczytu telefonu: {exc}")
            elif kind == "fetch":
                self.fetch_failed.emit(payload, str(exc))
            else:
                self.thumb_failed.emit(payload)

    def _serve_pending(self) -> None:
        """W trakcie wczytywania listy: obsłuż czekające podglądy, miniatury i kopiowanie,
        żeby już znalezione zdjęcia dało się oglądać, zanim otworzy się kolejny duży folder."""
        while not self._stop.is_set():
            job = self._next_job(block=False, with_more=False)
            if job is None:
                return
            self._handle(*job)

    def _check_presence(self, shell) -> bool:
        """Czy telefon nadal jest podłączony? (sprawdzane po błędzie, najwyżej co 3 s)"""
        if self._gone:
            return False
        now = time.time()
        if now - self._last_presence_check < 3:
            return True
        self._last_presence_check = now
        try:
            present = ds._find_device(shell, self.device) is not None
        except Exception:
            present = False
        if not present:
            self._gone = True
            self.disconnected.emit()
        return present

    def _next_job(self, block: bool = True, with_more: bool = True):
        with self._cond:
            def ready() -> bool:
                return bool(self._imports or self._fetch or self._thumbs or (with_more and self._more))
            while block and not ready() and not self._stop.is_set():
                self._cond.wait(1.0)
            if self._stop.is_set() or not ready():
                return None
            if self._imports:
                return "import", self._imports.popleft()
            if self._fetch:
                return "fetch", self._fetch.popleft()
            if with_more and self._more:
                return "more", self._more.popleft()
            idx = self._thumbs.pop()          # LIFO — najpierw widoczne na ekranie
            self._thumb_set.discard(idx)
            return "thumb", idx

    def _on_examined(self, n: int) -> None:
        self._examined = n
        self.scan_progress.emit(n)

    def _load(self, db, limit: int | None) -> None:
        """Pobiera z generatora kolejne NOWE pliki (od najnowszych): `limit` sztuk albo wszystkie."""
        if self._gen is None:
            return
        log = _log
        t0 = time.time()
        log.info("wczytywanie z %s, foldery %s, limit %s", self.device, self.folders, limit)
        checker = Importer(self.lib, db)
        prefix = f"wpd:{self.device}/"
        # ścieżki plików z tego telefonu, które były już kiedyś importowane (szybki wstępny filtr)
        known_rels = {k[len(prefix):].split("|", 1)[0].lower() for (k,) in
                      db.query("SELECT source_key FROM import_sources WHERE source_key LIKE ?", (prefix + "%",))}
        batch: list[DeviceEntry] = []
        found = 0
        exhausted = False
        self.scan_found.emit(0)
        while not self._stop.is_set():
            if limit and found >= limit:
                break
            if found:
                self._serve_pending()
            try:
                f = next(self._gen)
            except StopIteration:
                exhausted = True
                break
            self._any_media = True
            key = f"{prefix}{f.rel}|{f.size}|{f.modified}"
            if self.only_new and f.rel.lower() in known_rels and checker.is_known_source(key):
                continue
            idx = self._next_idx
            self._next_idx += 1
            kind = media_kind(os.path.splitext(f.name)[1]) or "photo"
            ts = ds._parse_ts(f.modified)
            date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts > 0 else ""
            e = DeviceEntry(idx, f.rel, f.name, f.size, f.modified, kind, key, date)
            self.entries[idx] = e
            self._items[idx] = f.item
            batch.append(e)
            found += 1
            self.scan_found.emit(found)
            # pokazuj pliki partiami (pierwszy od razu), żeby można było od razu zacząć sortować
            if len(batch) >= (1 if self._next_idx <= 1 else 5 if self._next_idx <= 30 else 25):
                self.entries_added.emit(batch)
                batch = []
        log.info("wczytano %d nowych plików (sprawdzono %d) w %.1fs, koniec listy: %s",
                 found, self._examined, time.time() - t0, exhausted)
        if self._stop.is_set():
            return
        if batch:
            self.entries_added.emit(batch)
        if exhausted and not self._any_media:
            self.scan_failed.emit("Nie znaleziono zdjęć ani filmów we wskazanych folderach telefonu. "
                                  "Odblokuj telefon i sprawdź, czy zezwolono na dostęp do plików.")
            return
        self.scan_finished.emit(exhausted)

    # -- miniatury -----------------------------------------------------------
    def _do_thumb(self, shell, idx: int) -> None:
        from app.services.shell_thumbs import shell_thumbnail
        item = self._items.get(idx)
        e = self.entries.get(idx)
        if item is None or e is None:
            return
        img = None
        try:
            img = shell_thumbnail(str(item.Path), 256)
        except Exception:
            img = None
        limit = VIDEO_THUMB_FALLBACK_MAX if e.kind == "video" else THUMB_FALLBACK_MAX
        if (img is None or img.isNull()) and (0 < e.size <= limit or self.cached_path(idx) is not None):
            # telefon nie dał miniatury — skopiuj plik do cache i zrób miniaturę lokalnie
            try:
                path = self._copy_to_cache(shell, idx)
            except Exception as exc:
                _log.warning("miniatura %s: %s", e.name, exc)
                path = None
            if path is not None:
                img = self._local_thumb(idx, path, e.kind)
        if img is not None and not img.isNull():
            self._has_thumb.add(idx)
            self.thumb_ready.emit(idx, img)
        else:
            self.thumb_failed.emit(idx)
            self._check_presence(shell)

    def _local_thumb(self, idx: int, path: Path, kind: str) -> QImage | None:
        from app.services.thumbnail_service import make_thumbnail
        tmp = self.cache_dir / f"thumb_{idx}.jpg"
        try:
            if make_thumbnail(path, kind, tmp):
                return QImage(str(tmp))
        except Exception as exc:
            _log.warning("miniatura z kopii %s: %s", path.name, exc)
        finally:
            tmp.unlink(missing_ok=True)
        return None

    # -- podgląd -------------------------------------------------------------
    def _do_fetch(self, shell, idx: int) -> None:
        path = self._copy_to_cache(shell, idx, lambda pct: self.fetch_progress.emit(idx, pct))
        if path is None:
            if not self._stop.is_set() and self._check_presence(shell):
                self.fetch_failed.emit(idx, "Nie udało się skopiować pliku z telefonu "
                                            "(telefon zablokowany lub odłączony?).")
            return
        self.fetch_progress.emit(idx, 100)
        self.fetched.emit(idx, str(path))
        e = self.entries.get(idx)
        if idx not in self._has_thumb and e is not None:
            # np. duży film bez miniatury z telefonu — skoro jest już kopia, zrób miniaturę z niej
            img = self._local_thumb(idx, path, e.kind)
            if img is not None and not img.isNull():
                self._has_thumb.add(idx)
                self.thumb_ready.emit(idx, img)

    def _copy_to_cache(self, shell, idx: int, progress=None) -> Path | None:
        existing = self.cached_path(idx)
        if existing is not None:
            with self._lock:
                self._cache.move_to_end(idx)
            return existing
        item = self._items.get(idx)
        e = self.entries.get(idx)
        if item is None or e is None:
            return None
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(self.cache_dir).free < e.size + DISK_SPACE_MARGIN:
            raise OSError("Brak miejsca na dysku.")
        slot = self.cache_dir / f"{idx:06d}"
        shutil.rmtree(slot, ignore_errors=True)
        if slot.exists():      # stara kopia zablokowana (np. otwarta w odtwarzaczu) — nowy slot
            slot = self.cache_dir / f"{idx:06d}_{int(time.time() * 1000)}"
        slot.mkdir()
        try:
            # tylko KOPIOWANIE z telefonu
            path = ds.copy_item(shell, item, e.name, e.size, slot, self._stop.is_set, progress)
        except BaseException:
            shutil.rmtree(slot, ignore_errors=True)
            raise
        if path is None:
            shutil.rmtree(slot, ignore_errors=True)
            return None
        with self._lock:
            self._cache[idx] = path
            self._evict()
        return path

    def _evict(self) -> None:
        """Ogranicza pamięć podręczną (wywoływane z blokadą)."""
        def total() -> int:
            s = 0
            for p in self._cache.values():
                try:
                    s += p.stat().st_size
                except OSError:
                    pass
            return s
        while len(self._cache) > CACHE_MAX_FILES or (len(self._cache) > 3 and total() > CACHE_MAX_BYTES):
            victim = next((k for k in self._cache if k not in self._pinned), None)
            if victim is None:
                break
            p = self._cache.pop(victim)
            shutil.rmtree(p.parent, ignore_errors=True)

    # -- kopiowanie do folderu -------------------------------------------------
    def _do_import(self, shell, db, idx: int, folder: str) -> None:
        e = self.entries.get(idx)
        if e is None:
            self.imported.emit(idx, None, "error", "Nieznany plik.")
            return
        path = self._copy_to_cache(shell, idx)
        if path is None:
            if self._stop.is_set():
                return
            self._check_presence(shell)
            self.imported.emit(idx, None, "error",
                               f"{e.name}: nie udało się skopiować z telefonu (telefon zablokowany lub odłączony?)")
            return
        with self._lock:
            self._cache.pop(idx, None)     # plik zostanie „skonsumowany” przez import
        importer = Importer(self.lib, db, dest_folder=folder)
        mid = importer.import_file(path, source_key=e.key, consume=True)
        shutil.rmtree(path.parent, ignore_errors=True)
        if mid is not None:
            self.imported.emit(idx, mid, "ok", "")
        else:
            where = importer.duplicate_of or ""
            self.imported.emit(idx, None, "dup", where)
