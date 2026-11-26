"""Tworzenie, otwieranie i synchronizacja bibliotek PhotoSort.

Biblioteka to zwykły folder na dysku:

    <Biblioteka>/
        Do posortowania/
        <Folder tematyczny>/...
        .photosort/library.db, thumbnails/, staging/, settings.json

Stan na dysku jest źródłem prawdy — baza jest indeksem, który synchronizujemy
przy otwarciu (pliki dodane lub usunięte ręcznie w Eksploratorze są wykrywane).
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Callable

from app.constants import (
    DATA_DIR, DB_FILE, PARTIAL_SUFFIX, SETTINGS_FILE, STAGING_DIR, THUMBS_DIR,
    UNSORTED_FOLDER, UNSORTED_FOLDER_EN, UNSORTED_NAMES, media_kind,
)
from app.database.database import Database
from app.i18n import display_folder, is_english, tr
from app.utils.formatting import pl_sort_key
from app.utils.paths import file_creation_time, is_hidden_name, set_hidden, validate_folder_name


class LibraryError(Exception):
    """Błąd z komunikatem przeznaczonym dla użytkownika."""


@dataclass
class FolderInfo:
    name: str
    count: int
    photos: int
    videos: int
    is_unsorted: bool = False


def is_library(path: Path) -> bool:
    return (Path(path) / DATA_DIR / DB_FILE).is_file()


def _reserved(name: str) -> bool:
    """Nazwy folderu importu (polska i angielska) są zarezerwowane dla folderu importu."""
    return name.lower() in (n.lower() for n in UNSORTED_NAMES)


def rel_of(folder: str, filename: str) -> str:
    return f"{folder}/{filename}"


class Library:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.data_dir = self.root / DATA_DIR
        self.db_path = self.data_dir / DB_FILE
        self.thumbs_dir = self.data_dir / THUMBS_DIR
        self.staging_dir = self.data_dir / STAGING_DIR
        # nazwa folderu importu zależy od języka, w którym utworzono bibliotekę
        self.unsorted = self._detect_unsorted()
        self.unsorted_dir = self.root / self.unsorted
        self.db = Database(self.db_path)
        # Serializuje skan, przenoszenie i rejestrację importu — chroni indeks przed wyścigami.
        self.lock = threading.RLock()
        self._unreadable: set[str] = set()

    # ------------------------------------------------------------------ #
    # Tworzenie / otwieranie
    # ------------------------------------------------------------------ #
    @classmethod
    def create(cls, parent: Path, name: str) -> "Library":
        error = validate_folder_name(name)
        if error:
            raise LibraryError(error)
        root = Path(parent) / name.strip()
        if root.exists():
            # Nigdy nie nadpisujemy istniejących folderów ani bibliotek.
            raise FileExistsError(str(root))
        if not Path(parent).is_dir():
            raise LibraryError(tr("Lokalizacja nie istnieje: {path}", path=parent))
        root.mkdir()
        unsorted = UNSORTED_FOLDER_EN if is_english() else UNSORTED_FOLDER
        (root / unsorted).mkdir()
        data = root / DATA_DIR
        data.mkdir()
        (data / THUMBS_DIR).mkdir()
        (data / STAGING_DIR).mkdir()
        set_hidden(data)
        settings = {"name": name.strip(), "created": time.time(), "version": 1, "unsorted_folder": unsorted}
        (data / SETTINGS_FILE).write_text(json.dumps(settings, ensure_ascii=False, indent=2), "utf-8")
        lib = cls(root)
        lib.db.init_schema()
        return lib

    @classmethod
    def open(cls, root: Path) -> "Library":
        root = Path(root)
        if not root.is_dir():
            raise LibraryError(tr("Folder biblioteki nie istnieje:\n{path}", path=root))
        data = root / DATA_DIR
        if not (data / DB_FILE).is_file():
            raise LibraryError(tr("Wybrany folder nie jest biblioteką PhotoSort."))
        for sub in (THUMBS_DIR, STAGING_DIR):
            (data / sub).mkdir(exist_ok=True)
        lib = cls(root)
        lib.unsorted_dir.mkdir(exist_ok=True)
        lib.db.init_schema()
        lib.recover_interrupted_moves()
        lib.cleanup_partials()
        return lib

    def _detect_unsorted(self) -> str:
        """Nazwa folderu importu: zapisana w ustawieniach biblioteki albo wykryta na dysku.

        Biblioteki sprzed obsługi języka angielskiego zawsze używają „Do posortowania”.
        """
        try:
            saved = json.loads((self.data_dir / SETTINGS_FILE).read_text("utf-8")).get("unsorted_folder")
        except (OSError, ValueError, AttributeError):
            saved = None
        if saved in (UNSORTED_FOLDER, UNSORTED_FOLDER_EN):
            return saved
        if not (self.root / UNSORTED_FOLDER).is_dir() and (self.root / UNSORTED_FOLDER_EN).is_dir():
            return UNSORTED_FOLDER_EN
        return UNSORTED_FOLDER

    def is_unsorted(self, folder: str | None) -> bool:
        return bool(folder) and folder.lower() == self.unsorted.lower()

    @property
    def name(self) -> str:
        return self.root.name

    def open_db(self) -> Database:
        """Nowe połączenie do użycia w innym wątku."""
        return Database(self.db_path)

    def close(self) -> None:
        self.db.close()

    def abs_path(self, rel_path: str) -> Path:
        # ścieżki z bazy zawsze są względne wobec katalogu biblioteki — nie wychodź poza nią
        rel = PureWindowsPath(rel_path)
        if rel.anchor or rel.drive or ".." in rel.parts:
            raise LibraryError(f"Invalid path outside the library: {rel_path}")
        return self.root / Path(rel_path)

    def thumb_path(self, media_id: int) -> Path:
        return self.thumbs_dir / f"{media_id // 1000:03d}" / f"{media_id}.jpg"

    # ------------------------------------------------------------------ #
    # Ustawienia biblioteki (settings.json)
    # ------------------------------------------------------------------ #
    def read_settings(self) -> dict:
        try:
            return json.loads((self.data_dir / SETTINGS_FILE).read_text("utf-8"))
        except (OSError, ValueError):
            return {}

    # ------------------------------------------------------------------ #
    # Odzyskiwanie po przerwaniu pracy
    # ------------------------------------------------------------------ #
    def recover_interrupted_moves(self) -> int:
        """Domyka operacje przeniesienia przerwane awarią (stan 'pending')."""
        fixed = 0
        for mv in self.db.query("SELECT * FROM moves WHERE state='pending'"):
            src = self.abs_path(mv["src_rel"])
            dst = self.abs_path(mv["dst_rel"])
            if dst.exists() and not src.exists():
                folder = mv["dst_rel"].split("/", 1)[0]
                filename = os.path.basename(mv["dst_rel"])
                try:
                    self.db.execute("DELETE FROM media WHERE rel_path=? AND id<>?", (mv["dst_rel"], mv["media_id"]))
                    self.db.execute("UPDATE media SET rel_path=?, folder=?, filename=? WHERE id=?",
                                    (mv["dst_rel"], folder, filename, mv["media_id"]))
                except sqlite3.Error:
                    pass  # skan przy otwarciu i tak uzgodni indeks z dyskiem
                if mv["batch"] < 0:
                    # przerwane cofanie: dokończone — oryginalne przeniesienie jest cofnięte
                    self.db.execute("UPDATE moves SET state='undone' WHERE batch=? AND media_id=? AND state='done'",
                                    (-mv["batch"], mv["media_id"]))
                    self.db.execute("UPDATE moves SET state='undo' WHERE id=?", (mv["id"],))
                else:
                    self.db.execute("UPDATE moves SET state='done' WHERE id=?", (mv["id"],))
            else:
                # Plik źródłowy jest na miejscu — przeniesienie nie nastąpiło.
                self.db.execute("UPDATE moves SET state='failed' WHERE id=?", (mv["id"],))
            fixed += 1
        return fixed

    def cleanup_partials(self) -> None:
        """Usuwa niedokończone kopie z przerwanego importu (to tylko nasze kopie)."""
        for folder in [self.unsorted_dir, self.staging_dir]:
            if not folder.is_dir():
                continue
            for entry in os.scandir(folder):
                if entry.is_file() and entry.name.endswith(PARTIAL_SUFFIX):
                    try:
                        os.remove(entry.path)
                    except OSError:
                        pass
        # pliki w staging z przerwanego importu z urządzenia
        if self.staging_dir.is_dir():
            for entry in os.scandir(self.staging_dir):
                try:
                    if entry.is_file():
                        os.remove(entry.path)
                    elif entry.is_dir():
                        shutil.rmtree(entry.path, ignore_errors=True)
                except OSError:
                    pass

    # ------------------------------------------------------------------ #
    # Synchronizacja z dyskiem
    # ------------------------------------------------------------------ #
    def folder_dirs(self) -> list[str]:
        names = []
        try:
            for entry in os.scandir(self.root):
                if entry.is_dir(follow_symlinks=False) and not is_hidden_name(entry.name):
                    names.append(entry.name)
        except OSError:
            self._unreadable.add("")  # cały katalog biblioteki nieczytelny
        return names

    def iter_disk_media(self):
        """(rel_path, folder, filename, stat) dla każdego pliku multimedialnego w folderach."""
        for folder in self.folder_dirs():
            base = self.root / folder
            stack = [base]
            while stack:
                current = stack.pop()
                try:
                    entries = list(os.scandir(current))
                except OSError:
                    # folder chwilowo niedostępny (OneDrive, dysk sieciowy) — NIE traktuj
                    # jego plików jako usuniętych
                    self._unreadable.add(Path(current).relative_to(self.root).as_posix().lower() + "/")
                    continue
                for entry in entries:
                    if is_hidden_name(entry.name) or entry.name.endswith(PARTIAL_SUFFIX):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                        continue
                    if media_kind(os.path.splitext(entry.name)[1]) is None:
                        continue
                    try:
                        st = entry.stat()
                    except OSError:
                        continue
                    rel = Path(entry.path).relative_to(self.root).as_posix()
                    yield rel, folder, entry.name, st

    def scan(self, db: Database | None = None,
             progress: Callable[[int], None] | None = None) -> tuple[int, int, int]:
        """Porównuje dysk z bazą. Zwraca (dodane, usunięte, zmienione)."""
        db = db or self.db
        with self.lock:
            return self._scan(db, progress)

    def _scan(self, db: Database, progress) -> tuple[int, int, int]:
        self._unreadable = set()
        known = {r["rel_path"].lower(): (r["id"], r["size"], r["file_modified"], r["rel_path"])
                 for r in db.query("SELECT id, rel_path, size, file_modified FROM media")}
        seen: set[str] = set()
        added = changed = 0
        now = time.time()
        batch_new = []
        batch_upd = []
        for i, (rel, folder, filename, st) in enumerate(self.iter_disk_media()):
            key = rel.lower()
            seen.add(key)
            if key in known:
                mid, size, mtime, _rel = known[key]
                if size != st.st_size or (mtime is not None and abs((mtime or 0) - st.st_mtime) > 1):
                    batch_upd.append((st.st_size, st.st_mtime, mid))
            else:
                ext = os.path.splitext(filename)[1].lower()
                mod_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
                batch_new.append((rel, folder, filename, media_kind(ext), ext, st.st_size,
                                  file_creation_time(st), st.st_mtime, now, mod_iso))
            if progress and i % 500 == 0:
                progress(i)
        if batch_new:
            with db.transaction():
                db.executemany(
                    "INSERT OR IGNORE INTO media(rel_path, folder, filename, kind, ext, size, "
                    "file_created, file_modified, imported_at, sort_date) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    batch_new)
            added = len(batch_new)
        if batch_upd:
            with db.transaction():
                # Zawartość się zmieniła — hash i metadane do ponownego odczytu.
                db.executemany("UPDATE media SET size=?, file_modified=?, hash=NULL, meta_status=0 "
                               "WHERE id=?", batch_upd)
            changed = len(batch_upd)
        # Usuń z indeksu tylko wpisy, które NADAL wskazują na tę samą ścieżkę i których pliku
        # rzeczywiście brak — plik mógł zostać przeniesiony przez użytkownika w trakcie skanu.
        unreadable = self._unreadable
        if "" in unreadable:
            return added, 0, changed
        missing = [(mid, rel) for key, (mid, _s, _m, rel) in known.items()
                   if key not in seen and not any(key.startswith(u) for u in unreadable)
                   and not self.abs_path(rel).exists()]
        removed = 0
        if missing:
            with db.transaction():
                for mid, rel in missing:
                    removed += db.execute("DELETE FROM media WHERE id=? AND rel_path=?", (mid, rel)).rowcount
        return added, removed, changed

    # ------------------------------------------------------------------ #
    # Foldery
    # ------------------------------------------------------------------ #
    def folders(self) -> list[FolderInfo]:
        counts = {r["folder"].lower(): r for r in self.db.query(
            "SELECT folder, COUNT(*) AS n, SUM(kind='photo') AS p, SUM(kind='video') AS v "
            "FROM media GROUP BY folder")}
        result = []
        for name in self.folder_dirs():
            r = counts.get(name.lower())
            result.append(FolderInfo(
                name=name,
                count=r["n"] if r else 0,
                photos=(r["p"] or 0) if r else 0,
                videos=(r["v"] or 0) if r else 0,
                is_unsorted=self.is_unsorted(name),
            ))
        result.sort(key=lambda f: (not f.is_unsorted, pl_sort_key(f.name)))
        return result

    def create_folder(self, name: str) -> str:
        error = validate_folder_name(name)
        if error:
            raise LibraryError(error)
        name = name.strip()
        target = self.root / name
        if target.exists() or _reserved(name) or name.lower() in {d.lower() for d in self.folder_dirs()}:
            raise LibraryError(tr("Folder „{folder}” już istnieje.", folder=display_folder(name)))
        target.mkdir()
        return name

    def rename_folder(self, old: str, new: str) -> str:
        if self.is_unsorted(old):
            raise LibraryError(tr("Folderu „Do posortowania” nie można zmienić."))
        error = validate_folder_name(new)
        if error:
            raise LibraryError(error)
        new = new.strip()
        if new == old:
            return new
        src = self.root / old
        dst = self.root / new
        if new.lower() != old.lower() and (dst.exists() or _reserved(new)):
            raise LibraryError(tr("Folder „{folder}” już istnieje.", folder=display_folder(new)))
        try:
            os.rename(src, dst)
        except OSError as exc:
            raise LibraryError(tr("Nie udało się zmienić nazwy folderu:\n{error}",
                                  error=exc.strerror or exc)) from exc
        prefix_len = len(old) + 1
        with self.db.transaction() as db:
            db.execute("UPDATE media SET folder=?, rel_path=? || substr(rel_path, ?) "
                       "WHERE folder=? COLLATE NOCASE", (new, new + "/", prefix_len + 1, old))
            # Historia przeniesień wskazuje na nową nazwę, żeby „Cofnij” dalej działało.
            for col in ("src_rel", "dst_rel"):
                db.execute(f"UPDATE moves SET {col}=? || substr({col}, ?) "
                           f"WHERE {col} LIKE ? ESCAPE '\\'",
                           (new + "/", prefix_len + 1, _like_prefix(old)))
        return new

    def delete_folder(self, name: str) -> None:
        """Usuwa wyłącznie pusty folder."""
        if self.is_unsorted(name):
            raise LibraryError(tr("Folderu „Do posortowania” nie można usunąć."))
        target = self.root / name
        if not target.is_dir():
            raise LibraryError(tr("Folder nie istnieje."))
        # Pusty = brak jakichkolwiek plików (również innych niż zdjęcia) poza systemowymi.
        for _dirpath, _dirs, files in os.walk(target):
            real = [f for f in files if f.lower() not in {"thumbs.db", "desktop.ini"}]
            if real:
                raise LibraryError(tr("Można usunąć tylko pusty folder. "
                                      "Najpierw przenieś z niego zdjęcia i filmy."))
        try:
            shutil.rmtree(target)
        except OSError as exc:
            raise LibraryError(tr("Nie udało się usunąć folderu:\n{error}", error=exc)) from exc

    # ------------------------------------------------------------------ #
    # Statystyki
    # ------------------------------------------------------------------ #
    def stats(self) -> dict:
        r = self.db.query_one(
            "SELECT COUNT(*) AS total, SUM(kind='photo') AS photos, SUM(kind='video') AS videos, "
            "SUM(folder=? COLLATE NOCASE) AS unsorted FROM media", (self.unsorted,))
        total = r["total"] or 0
        unsorted = r["unsorted"] or 0
        sorted_ = total - unsorted
        folders = len([f for f in self.folder_dirs() if not self.is_unsorted(f)])
        return {
            "total": total,
            "photos": r["photos"] or 0,
            "videos": r["videos"] or 0,
            "sorted": sorted_,
            "unsorted": unsorted,
            "percent": (sorted_ * 100.0 / total) if total else 0.0,
            "folders": folders,
        }


def _like_prefix(folder: str) -> str:
    esc = folder.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return esc + "/%"
