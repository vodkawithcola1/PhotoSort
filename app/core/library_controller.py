"""Kontroler otwartej biblioteki: kolejka, bieżący plik, przenoszenie, autozapis.

Tryb „Sortuj prosto z telefonu”: pliki z telefonu mają w kolejce UJEMNE identyfikatory
(-(idx+1)), dzięki czemu pasek miniatur, podgląd i przeciąganie działają tak samo jak dla
plików biblioteki. Przeciągnięcie takiego pliku na folder = skopiowanie go z telefonu
prosto do tego folderu.
"""
from __future__ import annotations

import bisect
import os
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap

from app.constants import SCOPE_ALL, SCOPE_DEVICE, UNSORTED_FOLDER
from app.core.import_manager import hash_file
from app.core.library_manager import Library, LibraryError
from app.core.media_manager import Filters, MediaManager, MoveResult
from app.core.session_manager import SessionManager, SessionState
from app.core.workers import MetadataWorker, ScanWorker
from app.i18n import display_folder, tr
from app.utils.formatting import count_pl


def dev_id(idx: int) -> int:
    return -(idx + 1)


def dev_idx(mid: int) -> int:
    return -mid - 1


class LibraryController(QObject):
    queue_reset = Signal()                 # nowa lista plików w kolejce
    queue_removed = Signal(list)           # usunięto z kolejki (id)
    current_changed = Signal(object)       # media_id albo None
    folders_changed = Signal()
    stats_changed = Signal(dict)
    undo_changed = Signal(bool, str)
    bookmarks_changed = Signal()
    meta_updated = Signal(list)
    meta_progress = Signal(int)
    scope_changed = Signal(str)
    toast = Signal(str, bool)              # tekst, czy pokazać „Cofnij”
    error = Signal(str)
    # tryb telefonu
    device_changed = Signal()              # start/koniec sesji, postęp skanowania, zmiana liczby plików
    device_thumb_ready = Signal(int)       # id (ujemne)
    device_fetched = Signal(int, str)      # id (ujemne), ścieżka kopii podglądu
    device_fetch_failed = Signal(int, str)
    device_fetch_progress = Signal(int, int)   # id (ujemne), % skopiowanego pliku

    def __init__(self, library: Library):
        super().__init__()
        self.lib = library
        self.mm = MediaManager(library)
        self.session = SessionManager(library.db)
        self.state: SessionState = self.session.load()
        if self.state.scope != SCOPE_ALL and not (library.root / self.state.scope).is_dir():
            self.state.scope = UNSORTED_FOLDER
        self.filters = Filters.from_dict(self.state.filters)
        self.ids: list[int] = []
        self.rows: dict[int, tuple] = {}
        self.index: int = -1
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self.save_now)

        self.meta_worker = MetadataWorker(library)
        self.meta_worker.updated.connect(self._on_meta_updated)
        self.meta_worker.progress.connect(self.meta_progress)
        self.meta_worker.start()
        self.scan_worker: ScanWorker | None = None

        # sesja telefonu
        self.device = None                   # DeviceBrowser
        self.device_name = ""
        self.device_status = "none"          # none | scanning | ready | error
        self.device_scan_count = 0
        self.device_scan_text = ""
        self.device_scan_since = 0.0         # kiedy zaczął się bieżący krok (np. otwieranie folderu)
        self.device_found = 0                # ile nowych plików znaleziono w bieżącym wczytywaniu
        self.device_error = ""
        self.device_limit: int | None = None
        self.device_more = False             # czy na telefonie są jeszcze kolejne pliki do wczytania
        self.device_entries: dict = {}       # idx -> DeviceEntry
        self.device_order: list[int] = []    # idx plików jeszcze nieprzypisanych (od najnowszych)
        self.device_thumbs: dict[int, QPixmap] = {}
        self._device_thumb_failed: set[int] = set()
        self._scope_before_device = UNSORTED_FOLDER
        self._pending_device: dict[int, dict] = {}
        # stos cofania w tej sesji: {"type": "move", "batch": n} | {"type": "device", ...}
        self._undo_tokens: list[dict] = []

    # ------------------------------------------------------------------ #
    # Start / zamykanie
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        """Ładuje kolejkę natychmiast z bazy, a w tle synchronizuje z dyskiem."""
        self.reload(restore=True)
        self.rescan()

    def rescan(self) -> None:
        if self.scan_worker and self.scan_worker.isRunning():
            return
        self.scan_worker = ScanWorker(self.lib)
        self.scan_worker.done.connect(self._on_scan_done)
        self.scan_worker.start()

    def _on_scan_done(self, added: int, removed: int, changed: int) -> None:
        if (added or removed or changed) and self.scope != SCOPE_DEVICE:
            self.reload(restore=False, keep_current=True)
        self.folders_changed.emit()
        self.emit_stats()
        self.meta_worker.wake()

    def shutdown(self) -> None:
        self.close_device(switch_scope=False)
        self.save_now()
        self.meta_worker.stop()
        self.meta_worker.wait(4000)
        if self.scan_worker:
            self.scan_worker.wait(4000)

    # ------------------------------------------------------------------ #
    # Kolejka
    # ------------------------------------------------------------------ #
    @property
    def scope(self) -> str:
        return self.state.scope

    @property
    def current_id(self) -> int | None:
        if 0 <= self.index < len(self.ids):
            return self.ids[self.index]
        return None

    def reload(self, restore: bool = False, keep_current: bool = True) -> None:
        prev_id = self.current_id
        prev_index = self.index
        if self.scope == SCOPE_DEVICE:
            self._build_device_queue()
        else:
            self.ids = self.mm.query_ids(self.scope, self.filters, self.state.sort, self.state.ascending)
            self.rows = self.mm.light_rows(self.ids) if len(self.ids) < 2000 else self.mm.light_rows()
        target_id = None
        if restore:
            target_id = self.state.positions.get(self.scope, self.state.current_id)
        elif keep_current:
            target_id = prev_id
        idx = -1
        if target_id is not None:
            try:
                idx = self.ids.index(int(target_id))
            except ValueError:
                idx = -1
        if idx < 0 and self.ids:
            fallback = 0 if self.scope == SCOPE_DEVICE and restore else (
                self.state.current_index if restore else prev_index)
            idx = min(max(fallback, 0), len(self.ids) - 1)
        self.index = idx
        self.queue_reset.emit()
        self.current_changed.emit(self.current_id)
        self.emit_stats()
        self.emit_undo()
        self.schedule_save()

    def _build_device_queue(self) -> None:
        f = self.filters
        text = f.text.strip().lower()
        ids, rows = [], {}
        for idx in self.device_order:
            e = self.device_entries.get(idx)
            if e is None:
                continue
            if f.kind in ("photo", "video") and e.kind != f.kind:
                continue
            if text and text not in e.name.lower():
                continue
            # filtry dat i rozmiaru — według daty pliku z telefonu
            d = e.date[:10]
            if f.same_day and d != f.same_day:
                continue
            if f.year and d[:4] != f"{int(f.year):04d}":
                continue
            if f.month and d[5:7] != f"{int(f.month):02d}":
                continue
            if f.date_from and (not d or d < f.date_from):
                continue
            if f.date_to and (not d or d > f.date_to):
                continue
            if f.min_size_mb and e.size < f.min_size_mb * 1048576:
                continue
            if f.max_size_mb and e.size > f.max_size_mb * 1048576:
                continue
            mid = dev_id(idx)
            ids.append(mid)
            rows[mid] = (e.name, e.kind, None, SCOPE_DEVICE, "")
        self.ids, self.rows = ids, rows

    def set_scope(self, scope: str) -> None:
        if scope == self.scope:
            return
        if scope == SCOPE_DEVICE and self.device is None:
            return
        # zapamiętaj pozycję w opuszczanym folderze
        if self.current_id is not None:
            self.state.positions[self.scope] = self.current_id
        if scope == SCOPE_DEVICE and self.scope != SCOPE_DEVICE:
            self._scope_before_device = self.scope
            # dla plików z telefonu nie znamy jeszcze dat ani lokalizacji — zacznij bez filtrów
            self.filters = Filters()
        self.state.scope = scope
        if scope != SCOPE_ALL:
            # filtry statusu/folderu dotyczą tylko widoku „Wszystkie”
            self.filters.status = "all"
            self.filters.folder = ""
        self.state.filters = self.filters.to_dict()
        self.state.scroll = 0
        self.scope_changed.emit(scope)
        self.reload(restore=True)

    def set_filters(self, filters: Filters) -> None:
        self.filters = filters
        self.state.filters = filters.to_dict()
        self.reload(keep_current=True)

    def set_sort(self, sort: str, ascending: bool) -> None:
        self.state.sort = sort
        self.state.ascending = ascending
        self.reload(keep_current=True)

    def set_index(self, index: int) -> None:
        if not self.ids:
            self.index = -1
            self.current_changed.emit(None)
            return
        index = max(0, min(index, len(self.ids) - 1))
        if index == self.index:
            return
        self.index = index
        cid = self.current_id
        if cid is not None:
            self.state.positions[self.scope] = cid
        self.current_changed.emit(cid)
        self.schedule_save()

    def select_id(self, media_id: int) -> None:
        try:
            self.set_index(self.ids.index(media_id))
        except ValueError:
            pass

    def next(self) -> None:
        self.set_index(self.index + 1)

    def prev(self) -> None:
        self.set_index(self.index - 1)

    def go_to_media(self, media_id: int) -> None:
        """Przejście do pliku (np. z zakładki) — otwiera jego folder."""
        row = self.mm.get(media_id)
        if row is None:
            self.error.emit(tr("Ten plik nie jest już dostępny w bibliotece."))
            return
        if self.scope != SCOPE_ALL and row["folder"].lower() != self.scope.lower():
            self.state.positions[row["folder"]] = media_id
            if self.current_id is not None:
                self.state.positions[self.scope] = self.current_id
            self.state.scope = row["folder"]
            self.scope_changed.emit(row["folder"])
        if media_id not in self.ids:
            # filtr ukrywa plik — wyczyść filtry
            self.filters = Filters()
            self.state.filters = {}
        self.state.positions[self.scope] = media_id
        self.reload(restore=True)

    # ------------------------------------------------------------------ #
    # Przenoszenie (biblioteka) i kopiowanie (z telefonu)
    # ------------------------------------------------------------------ #
    def move(self, ids: list[int], folder: str) -> MoveResult | None:
        ids = [i for i in ids if i is not None]
        if not ids:
            return None
        device_ids = [i for i in ids if i < 0]
        lib_ids = [i for i in ids if i >= 0]
        res = MoveResult()
        if device_ids:
            self._copy_from_device(device_ids, folder)
            res.moved.extend(device_ids)
        if not lib_ids:
            return res
        try:
            lres = self.mm.move(lib_ids, folder)
        except LibraryError as exc:
            self.error.emit(str(exc))
            return res if res.moved else None
        self.state.last_target = folder
        if lres.moved:
            self._undo_tokens.append({"type": "move", "batch": lres.batch})
            self._after_move(lres.moved, folder)
            n = len(lres.moved)
            self.toast.emit(tr("Przeniesiono {files} do „{folder}”", files=count_pl(n, 'plik', 'pliki', 'plików'),
                               folder=display_folder(folder)), True)
        if lres.errors:
            self.error.emit(tr("Nie udało się przenieść niektórych plików. Pliki źródłowe pozostały "
                               "na swoim miejscu.") + "\n\n" + "\n".join(lres.errors[:12]))
        self.save_now()
        res.moved.extend(lres.moved)
        res.errors.extend(lres.errors)
        res.batch = lres.batch
        return res

    def _after_move(self, moved: list[int], folder: str) -> None:
        moved_set = set(moved)
        if self.scope == SCOPE_ALL or self.scope.lower() == folder.lower():
            # pliki zostają w widoku — odśwież dane i przejdź dalej
            fresh = self.mm.light_rows(moved)
            self.rows.update(fresh)
            current = self.current_id
            self.queue_reset.emit()
            if current in moved_set and self.scope == SCOPE_ALL:
                self.set_index(self.index + 1)
            else:
                self.current_changed.emit(self.current_id)
        else:
            self._remove_from_queue(moved_set)
        self.folders_changed.emit()
        self.emit_stats()
        self.emit_undo()
        self.bookmarks_changed.emit()

    def _remove_from_queue(self, moved_set: set[int]) -> None:
        current = self.current_id
        old_index = self.index
        removed_before = sum(1 for i in self.ids[:max(old_index, 0)] if i in moved_set)
        self.ids = [i for i in self.ids if i not in moved_set]
        for m in moved_set:
            self.rows.pop(m, None)
        if current in moved_set:
            # następny dostępny plik: ten, który „wskoczył” na tę pozycję
            new_index = old_index - removed_before
        else:
            new_index = self.ids.index(current) if current in self.ids else old_index
        self.index = min(new_index, len(self.ids) - 1) if self.ids else -1
        self.queue_removed.emit(list(moved_set))
        cid = self.current_id
        if cid is not None:
            self.state.positions[self.scope] = cid
        self.current_changed.emit(cid)

    def undo(self) -> None:
        if self._undo_tokens and self._undo_tokens[-1]["type"] == "device":
            token = self._undo_tokens[-1]
            if token["pending"]:
                self.toast.emit(tr("Poczekaj, aż skończy się kopiowanie z telefonu"), False)
                return
            self._undo_tokens.pop()
            self._undo_device(token)
            return
        if self._undo_tokens:
            self._undo_tokens.pop()
        info = self.mm.last_batch_info()
        if not info:
            self.emit_undo()
            return
        res = self.mm.undo_last()
        if res.moved:
            first = res.moved[-1]
            self.reload(keep_current=True)
            # pokaż przywrócony plik, jeśli jest w bieżącym widoku
            if first in self.ids:
                self.select_id(first)
            self.folders_changed.emit()
            self.toast.emit(tr("Cofnięto przeniesienie ({files})",
                               files=count_pl(len(res.moved), 'plik', 'pliki', 'plików')), False)
        if res.errors:
            self.error.emit(tr("Nie udało się cofnąć wszystkich plików:") + "\n" + "\n".join(res.errors[:12]))
        self.emit_undo()
        self.emit_stats()
        self.bookmarks_changed.emit()
        self.save_now()

    def emit_undo(self) -> None:
        if self._undo_tokens and self._undo_tokens[-1]["type"] == "device":
            t = self._undo_tokens[-1]
            n = len(t["done"]) or len(t["idxs"])
            self.undo_changed.emit(True, tr("Cofnij skopiowanie {files} z telefonu do „{folder}” (Ctrl+Z) "
                                            "— zdjęcia zostają na telefonie",
                                            files=count_pl(n, 'pliku', 'plików', 'plików'),
                                            folder=display_folder(t['folder'])))
            return
        info = self.mm.last_batch_info()
        if info:
            _b, n, folder = info
            self.undo_changed.emit(True, tr("Cofnij przeniesienie {files} do „{folder}” (Ctrl+Z)",
                                            files=count_pl(n, 'pliku', 'plików', 'plików'),
                                            folder=display_folder(folder)))
        else:
            self.undo_changed.emit(False, tr("Brak operacji do cofnięcia"))

    # ------------------------------------------------------------------ #
    # Telefon: sesja „Sortuj prosto z telefonu”
    # ------------------------------------------------------------------ #
    def open_device(self, device: str, folders: list[str], limit: int | None = None) -> None:
        from app.services.device_browser import DeviceBrowser
        self.close_device(switch_scope=False)
        self.device_name = device
        self.device_limit = limit
        self.device_more = False
        self.device_status = "scanning"
        self.device_scan_count = 0
        self.device_scan_text = ""
        self.device_scan_since = time.time()
        self.device_found = 0
        self.device_error = ""
        self.device_entries = {}
        self.device_order = []
        self.device_thumbs = {}
        self._device_thumb_failed = set()
        b = DeviceBrowser(self.lib, device, folders, limit=limit)
        b.scan_progress.connect(self._on_dev_scan_progress)
        b.scan_status.connect(self._on_dev_scan_status)
        b.scan_found.connect(self._on_dev_scan_found)
        b.fetch_progress.connect(lambda idx, pct: self.device_fetch_progress.emit(dev_id(idx), pct))
        b.entries_added.connect(self._on_dev_entries)
        b.scan_finished.connect(self._on_dev_scan_finished)
        b.scan_failed.connect(self._on_dev_scan_failed)
        b.thumb_ready.connect(self._on_dev_thumb)
        b.thumb_failed.connect(lambda idx: self._device_thumb_failed.add(idx))
        b.fetched.connect(lambda idx, p: self.device_fetched.emit(dev_id(idx), p))
        b.fetch_failed.connect(lambda idx, msg: self.device_fetch_failed.emit(dev_id(idx), msg))
        b.imported.connect(self._on_dev_imported)
        b.disconnected.connect(self._on_dev_disconnected)
        self.device = b
        self.device_changed.emit()
        self.set_scope(SCOPE_DEVICE)

    def close_device(self, switch_scope: bool = True) -> None:
        if self.device is None:
            return
        b = self.device
        self.device = None
        try:
            b.blockSignals(True)
            b.close()      # usuwa tymczasowe kopie podglądu
        except Exception:
            pass
        self.device_status = "none"
        self.device_order = []
        self.device_entries = {}
        self.device_thumbs = {}
        self._pending_device = {}
        for t in self._undo_tokens:
            t["pending"] = 0
        self.device_changed.emit()
        if switch_scope and self.scope == SCOPE_DEVICE:
            target = self._scope_before_device
            if target != SCOPE_ALL and not (self.lib.root / target).is_dir():
                target = UNSORTED_FOLDER
            self.set_scope(target)
        elif self.scope == SCOPE_DEVICE:
            self.state.scope = UNSORTED_FOLDER

    def device_entry(self, mid: int):
        return self.device_entries.get(dev_idx(mid)) if mid is not None and mid < 0 else None

    def device_thumb(self, mid: int) -> QPixmap | None:
        idx = dev_idx(mid)
        pm = self.device_thumbs.get(idx)
        if pm is None and self.device is not None and idx not in self._device_thumb_failed:
            self.device.request_thumb(idx)
        return pm

    def device_cached(self, mid: int) -> Path | None:
        return self.device.cached_path(dev_idx(mid)) if self.device is not None else None

    def device_fetch(self, mid: int, current: bool = True) -> None:
        if self.device is not None:
            self.device.fetch(dev_idx(mid), current)

    def _on_dev_disconnected(self) -> None:
        self.device_status = "error"
        self.device_error = tr("Telefon został odłączony albo zablokowany. Zdjęcia, które zdążyłeś przeciągnąć do "
                               "folderów, są już na komputerze. Podłącz i odblokuj telefon, a potem otwórz go "
                               "ponownie: Importuj zdjęcia i filmy → Telefon lub aparat.")
        self.device_order = []
        self.device_changed.emit()
        if self.scope == SCOPE_DEVICE:
            self.reload(keep_current=False)

    def _on_dev_scan_status(self, text: str) -> None:
        self.device_scan_text = text
        self.device_scan_since = time.time()
        self.device_changed.emit()

    def _on_dev_scan_found(self, n: int) -> None:
        self.device_found = n
        self.device_changed.emit()

    def _on_dev_scan_progress(self, n: int) -> None:
        self.device_scan_count = n
        self.device_changed.emit()

    def _on_dev_entries(self, entries: list) -> None:
        was_empty = not self.ids
        for e in entries:
            self.device_entries[e.idx] = e
            self.device_order.append(e.idx)
        self.device_changed.emit()
        if self.scope == SCOPE_DEVICE:
            self.reload(restore=False, keep_current=not was_empty)
            if was_empty:
                self.set_index(0)

    def _on_dev_scan_finished(self, exhausted: bool) -> None:
        self.device_status = "ready"
        self.device_more = not exhausted
        self.device_changed.emit()
        if self.scope == SCOPE_DEVICE and self.current_id is None:
            self.current_changed.emit(None)

    def device_load_more(self) -> None:
        if self.device is not None and self.device_more:
            self.device_status = "scanning"
            self.device_scan_count = 0
            self.device_found = 0
            self.device_scan_text = ""
            self.device_scan_since = time.time()
            self.device.load_more(self.device_limit)
            self.device_changed.emit()
            if self.current_id is None:
                self.current_changed.emit(None)

    def _on_dev_scan_failed(self, msg: str) -> None:
        self.device_status = "error"
        self.device_error = msg
        self.device_changed.emit()
        if self.scope == SCOPE_DEVICE:
            self.reload(keep_current=False)

    def _on_dev_thumb(self, idx: int, img: QImage) -> None:
        self._device_thumb_failed.discard(idx)
        self.device_thumbs[idx] = QPixmap.fromImage(img)
        self.device_thumb_ready.emit(dev_id(idx))

    def _copy_from_device(self, mids: list[int], folder: str) -> None:
        if self.device is None:
            return
        if not (self.lib.root / folder).is_dir():
            self.error.emit(tr("Folder „{folder}” nie istnieje.", folder=display_folder(folder)))
            return
        idxs = [dev_idx(m) for m in mids if dev_idx(m) in self.device_entries
                and dev_idx(m) not in self._pending_device and dev_idx(m) in self.device_order]
        if not idxs:
            return
        token = {"type": "device", "folder": folder, "idxs": idxs, "done": [], "pending": len(idxs),
                 "failed": 0, "dups": 0}
        self._undo_tokens.append(token)
        for idx in idxs:
            self._pending_device[idx] = token
            self.device_order.remove(idx)
        self.state.last_target = folder
        # od razu pokaż następne zdjęcie; kopiowanie trwa w tle
        if self.scope == SCOPE_DEVICE:
            self._remove_from_queue({dev_id(i) for i in idxs})
        self.device.import_items(idxs, folder)
        self.device_changed.emit()
        self.emit_undo()

    def _on_dev_imported(self, idx: int, media_id, status: str, msg: str) -> None:
        token = self._pending_device.pop(idx, None)
        e = self.device_entries.get(idx)
        if token is None:
            return
        token["pending"] -= 1
        if status == "ok":
            token["done"].append((idx, media_id, e.key if e else ""))
        elif status == "dup":
            token["dups"] += 1
        else:
            token["failed"] += 1
            self._reinsert_device(idx)
            self.error.emit(tr("Nie udało się skopiować pliku z telefonu. Plik pozostał na liście telefonu.")
                            + "\n\n" + msg)
        if token["pending"] == 0:
            if not token["done"] and token in self._undo_tokens:
                self._undo_tokens.remove(token)
            parts = []
            if token["done"]:
                n = len(token["done"])
                parts.append(tr("Skopiowano z telefonu {files} do „{folder}”",
                                files=count_pl(n, 'plik', 'pliki', 'plików'),
                                folder=display_folder(token['folder'])))
            if token["dups"]:
                parts.append(tr("{files} już w bibliotece — pominięto",
                                files=count_pl(token['dups'], 'plik był', 'pliki były', 'plików było')))
            if parts:
                self.toast.emit(" · ".join(parts), bool(token["done"]))
            self.folders_changed.emit()
            self.emit_stats()
            self.meta_worker.wake()
        self.device_changed.emit()
        self.emit_undo()

    def _reinsert_device(self, idx: int) -> None:
        if idx in self.device_entries and idx not in self.device_order:
            bisect.insort(self.device_order, idx)
            if self.scope == SCOPE_DEVICE:
                self.reload(keep_current=True)

    def _undo_device(self, token: dict) -> None:
        """Cofa skopiowanie z telefonu: usuwa świeżą KOPIĘ z komputera (oryginał jest na telefonie)."""
        restored, problems = 0, []
        with self.lib.lock:
            for idx, mid, key in token["done"]:
                row = self.mm.get(mid)
                if row is None:
                    continue
                path = self.lib.abs_path(row["rel_path"])
                try:
                    # usuń tylko dokładnie ten plik, który został skopiowany (ta sama zawartość)
                    if path.exists() and row["hash"] and hash_file(path) == row["hash"]:
                        os.remove(path)
                    elif path.exists():
                        problems.append(tr("{name}: plik został zmieniony — nie usunięto", name=row['filename']))
                        continue
                except OSError as exc:
                    problems.append(f"{row['filename']}: {exc.strerror or exc}")
                    continue
                self.lib.db.execute("DELETE FROM media WHERE id=?", (mid,))
                if key:
                    self.lib.db.execute("DELETE FROM import_sources WHERE source_key=?", (key,))
                restored += 1
                if idx in self.device_entries and idx not in self.device_order:
                    bisect.insort(self.device_order, idx)
        if self.scope == SCOPE_DEVICE:
            self.reload(keep_current=False)
            first = token["done"][0][0] if token["done"] else None
            if first is not None:
                self.select_id(dev_id(first))
        else:
            self.reload(keep_current=True)
        self.folders_changed.emit()
        self.device_changed.emit()
        self.emit_stats()
        self.emit_undo()
        self.toast.emit(tr("Cofnięto: usunięto z komputera {copies} — zdjęcia są nadal na telefonie",
                           copies=count_pl(restored, 'kopię', 'kopie', 'kopii')), False)
        if problems:
            self.error.emit(tr("Nie wszystko udało się cofnąć:") + "\n" + "\n".join(problems[:12]))

    # ------------------------------------------------------------------ #
    # Foldery
    # ------------------------------------------------------------------ #
    def create_folder(self, name: str) -> str | None:
        try:
            name = self.lib.create_folder(name)
        except LibraryError as exc:
            self.error.emit(str(exc))
            return None
        self.folders_changed.emit()
        self.emit_stats()
        return name

    def rename_folder(self, old: str, new: str) -> bool:
        try:
            new = self.lib.rename_folder(old, new)
        except LibraryError as exc:
            self.error.emit(str(exc))
            return False
        if self.scope.lower() == old.lower():
            self.state.scope = new
            self.scope_changed.emit(new)
        if old in self.state.positions:
            self.state.positions[new] = self.state.positions.pop(old)
        if self.state.last_target == old:
            self.state.last_target = new
        for t in self._undo_tokens:
            if t["type"] == "device" and t["folder"] == old:
                t["folder"] = new
        self.reload(keep_current=True)
        self.folders_changed.emit()
        self.emit_undo()
        return True

    def delete_folder(self, name: str) -> bool:
        try:
            self.lib.delete_folder(name)
        except LibraryError as exc:
            self.error.emit(str(exc))
            return False
        self.state.positions.pop(name, None)
        if self.scope.lower() == name.lower():
            self.set_scope(UNSORTED_FOLDER)
        self.folders_changed.emit()
        self.emit_stats()
        return True

    # ------------------------------------------------------------------ #
    # Zakładki
    # ------------------------------------------------------------------ #
    def toggle_bookmark(self, media_id: int | None = None) -> bool:
        media_id = media_id if media_id is not None else self.current_id
        if media_id is None:
            return False
        if media_id < 0:
            self.toast.emit(tr("Zakładki działają dla zdjęć w bibliotece — najpierw przeciągnij zdjęcie do folderu"),
                            False)
            return False
        if self.mm.is_bookmarked(media_id):
            self.mm.remove_bookmark(media_id)
            state = False
            self.toast.emit(tr("Usunięto zakładkę"), False)
        else:
            self.mm.add_bookmark(media_id)
            state = True
            self.toast.emit(tr("Dodano zakładkę — znajdziesz ją w panelu po prawej"), False)
        self.bookmarks_changed.emit()
        return state

    # ------------------------------------------------------------------ #
    # Import / metadane / statystyki
    # ------------------------------------------------------------------ #
    def after_import(self, new_ids: list[int]) -> None:
        self.reload(keep_current=True)
        if self.current_id is None and self.ids:
            self.set_index(0)
        self.folders_changed.emit()
        self.meta_worker.wake()

    def request_meta(self, media_id: int) -> None:
        if media_id is not None and media_id >= 0:
            self.meta_worker.prioritize(media_id)

    def _on_meta_updated(self, ids: list) -> None:
        relevant = [i for i in ids if i in self.rows]
        if relevant:
            self.rows.update(self.mm.light_rows(relevant))
        self.meta_updated.emit(ids)

    def emit_stats(self) -> None:
        self.stats_changed.emit(self.lib.stats())

    # ------------------------------------------------------------------ #
    # Zapis postępu
    # ------------------------------------------------------------------ #
    def schedule_save(self) -> None:
        self._save_timer.start()

    def save_now(self) -> None:
        self._save_timer.stop()
        device_mode = self.scope == SCOPE_DEVICE
        saved_scope = self.state.scope
        if device_mode:
            # telefonu nie będzie przy następnym uruchomieniu — zapamiętaj poprzedni folder
            self.state.scope = self._scope_before_device
        else:
            self.state.current_id = self.current_id
            self.state.current_index = max(self.index, 0)
        self.state.filters = self.filters.to_dict()
        try:
            self.session.save(self.state)
        except Exception:
            pass
        finally:
            self.state.scope = saved_scope
