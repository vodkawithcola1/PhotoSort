"""Wątki tła Qt: skanowanie biblioteki, odczyt metadanych, import."""
from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.core.import_manager import Importer, ImportStats, collect_media_files
from app.core.library_manager import Library
from app.i18n import tr
from app.services.geocode_service import Geocoder
from app.services.metadata_service import MediaMeta, MetadataReader


def apply_meta(db, media_id: int, meta: MediaMeta, file_modified: float | None, geocoder: Geocoder | None) -> None:
    sort_date = meta.taken_at
    if not sort_date and file_modified:
        sort_date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(file_modified))
    place = None
    if meta.lat is not None and meta.lon is not None and geocoder is not None:
        try:
            place = geocoder.lookup(meta.lat, meta.lon)
        except Exception:
            place = None
    status = 2 if meta.extra.get("error") else 1
    db.execute(
        "UPDATE media SET taken_at=?, taken_source=?, sort_date=?, width=?, height=?, duration=?, fps=?, "
        "make=?, model=?, lat=?, lon=?, place=?, orientation=?, meta_status=? WHERE id=?",
        (meta.taken_at, meta.taken_source, sort_date, meta.width, meta.height, meta.duration, meta.fps,
         meta.make, meta.model, meta.lat, meta.lon, place, meta.orientation, status, media_id))


class ScanWorker(QThread):
    done = Signal(int, int, int)
    failed = Signal(str)

    def __init__(self, library: Library):
        super().__init__()
        self.lib = library

    def run(self) -> None:
        db = self.lib.open_db()
        try:
            added, removed, changed = self.lib.scan(db)
            self.done.emit(added, removed, changed)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            db.close()


class MetadataWorker(QThread):
    """Odczytuje metadane plików oczekujących (meta_status=0) w tle."""
    updated = Signal(list)       # lista id z nowymi metadanymi
    progress = Signal(int)       # liczba pozostałych

    def __init__(self, library: Library):
        super().__init__()
        self.lib = library
        self._cond = threading.Condition()
        self._priority: list[int] = []
        self._stop = False
        self._wake = True

    def prioritize(self, media_id: int) -> None:
        with self._cond:
            if media_id not in self._priority:
                self._priority.append(media_id)
            self._wake = True
            self._cond.notify()

    def wake(self) -> None:
        with self._cond:
            self._wake = True
            self._cond.notify()

    def stop(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify()

    def run(self) -> None:
        db = self.lib.open_db()
        reader = MetadataReader()
        geocoder = Geocoder.shared()
        try:
            while True:
                with self._cond:
                    while not self._wake and not self._stop:
                        self._cond.wait(5.0)
                    if self._stop:
                        return
                    self._wake = False
                while not self._stop:
                    with self._cond:
                        prio = self._priority[:]
                        self._priority.clear()
                    rows = []
                    if prio:
                        rows = db.query(f"SELECT id, rel_path, file_modified FROM media WHERE meta_status=0 "
                                        f"AND id IN ({','.join('?' * len(prio))})", prio)
                    rows += db.query("SELECT id, rel_path, file_modified FROM media WHERE meta_status=0 "
                                     "ORDER BY id LIMIT 40")
                    if not rows:
                        break
                    done = []
                    seen = set()
                    for r in rows:
                        if self._stop or r["id"] in seen:
                            continue
                        seen.add(r["id"])
                        path = self.lib.abs_path(r["rel_path"])
                        try:
                            meta = reader.read(path) if path.exists() else MediaMeta(extra={"error": "missing"})
                            apply_meta(db, r["id"], meta, r["file_modified"], geocoder)
                        except Exception:
                            db.execute("UPDATE media SET meta_status=2 WHERE id=?", (r["id"],))
                        done.append(r["id"])
                        # plik priorytetowy — od razu do interfejsu
                        if r["id"] in prio:
                            self.updated.emit([r["id"]])
                    if done:
                        self.updated.emit(done)
                        remaining = db.scalar("SELECT COUNT(*) FROM media WHERE meta_status=0") or 0
                        self.progress.emit(remaining)
        finally:
            reader.close()
            db.close()


class ImportWorker(QThread):
    progress = Signal(dict)
    finished_import = Signal(object)    # ImportStats

    def __init__(self, library: Library, paths: list[Path] | None = None, recursive: bool = True,
                 device: str | None = None, device_folders: list[str] | None = None, label: str = "",
                 limit: int | None = None):
        super().__init__()
        self.limit = limit
        self.lib = library
        self.paths = paths or []
        self.recursive = recursive
        self.device = device
        self.device_folders = device_folders or []
        self.label = label
        self._cancel = threading.Event()
        self._last_emit = 0.0

    def cancel(self) -> None:
        self._cancel.set()

    def _emit(self, stats: ImportStats, phase: str, current: str = "", force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_emit < 0.08:
            return
        self._last_emit = now
        self.progress.emit({
            "phase": phase, "total": stats.total, "processed": stats.processed,
            "copied": stats.copied, "duplicates": stats.duplicates + stats.skipped_known,
            "errors": len(stats.errors), "current": current, "limit": stats.limit,
        })

    def run(self) -> None:
        db = self.lib.open_db()
        importer = Importer(self.lib, db, is_cancelled=self._cancel.is_set)
        stats = importer.stats
        try:
            if self.device:
                from app.services import device_service

                def prog(phase: str, done: int, total: int) -> None:
                    if phase == "scan":
                        stats.total = done
                        self._emit(stats, "scan")
                    else:
                        self._emit(stats, "copy")

                device_service.import_from_device(self.device, self.device_folders, importer,
                                                  self.lib.staging_dir, prog, self._cancel.is_set,
                                                  limit=self.limit)
            else:
                self._emit(stats, "scan", force=True)
                files = collect_media_files(self.paths, self.recursive, self.lib.root)
                # nie importuj plików, które już leżą w bibliotece
                root = str(self.lib.root.resolve()).lower()
                files = [f for f in files if not str(f.resolve()).lower().startswith(root + "\\")]
                importer.progress = lambda s, name: self._emit(s, "copy", name)
                importer.import_paths(files, self.label, limit=self.limit)
        except Exception as exc:
            stats.errors.append(tr("Nieoczekiwany błąd importu: {error}", error=exc))
        finally:
            self._emit(stats, "done", force=True)
            db.close()
            self.finished_import.emit(stats)
