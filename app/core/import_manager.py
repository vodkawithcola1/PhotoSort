"""Import zdjęć i filmów do folderu „Do posortowania”.

Zasady bezpieczeństwa:
  * oryginały są wyłącznie CZYTANE (open 'rb') — nigdy nie są przenoszone,
    modyfikowane ani usuwane,
  * kopia powstaje najpierw jako plik tymczasowy *.photosort-partial, jest
    zapisywana na dysk (fsync), weryfikowana rozmiarem i dopiero wtedy
    otrzymuje docelową nazwę — przerwany import nie zostawia uszkodzonych plików,
  * istniejące pliki nigdy nie są nadpisywane (IMG_001 (1).JPG),
  * duplikaty wykrywane są po zawartości (SHA-256),
  * przed każdym plikiem sprawdzane jest wolne miejsce na dysku.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from app.constants import DISK_SPACE_MARGIN, PARTIAL_SUFFIX, UNSORTED_FOLDER, media_kind
from app.core.library_manager import Library, rel_of
from app.database.database import Database
from app.utils.paths import copy_creation_time, file_creation_time, is_hidden_name, unique_path

CHUNK = 4 * 1024 * 1024


class ImportCancelled(Exception):
    pass


class DiskFullError(Exception):
    pass


@dataclass
class ImportStats:
    total: int = 0
    processed: int = 0
    copied: int = 0
    duplicates: int = 0
    skipped_known: int = 0
    errors: list[str] = field(default_factory=list)
    new_ids: list[int] = field(default_factory=list)
    limit: int | None = None          # tryb próbny: zatrzymaj po N nowych plikach
    limit_reached: bool = False
    bytes_copied: int = 0
    aborted_reason: str | None = None


def collect_media_files(paths: Iterable[Path], recursive: bool = True,
                        library_root: Path | None = None) -> list[Path]:
    """Zbiera pliki multimedialne ze wskazanych plików/folderów."""
    found: list[Path] = []
    seen: set[str] = set()
    lib_root = os.path.normcase(str(library_root)) if library_root else None
    for p in paths:
        p = Path(p)
        if p.is_file():
            if media_kind(p.suffix) and os.path.normcase(str(p)) not in seen:
                seen.add(os.path.normcase(str(p)))
                found.append(p)
            continue
        if not p.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(p):
            # nie importuj z samej biblioteki ani z folderów systemowych
            dirnames[:] = [d for d in dirnames if not is_hidden_name(d) and d not in ("$RECYCLE.BIN", "System Volume Information")
                           and not (lib_root and os.path.normcase(os.path.join(dirpath, d)) == lib_root)]
            for fn in filenames:
                if is_hidden_name(fn) or fn.endswith(PARTIAL_SUFFIX):
                    continue
                if media_kind(os.path.splitext(fn)[1]):
                    full = os.path.join(dirpath, fn)
                    key = os.path.normcase(full)
                    if key not in seen:
                        seen.add(key)
                        found.append(Path(full))
            if not recursive:
                break
    return found


def sort_newest_first(files: list[Path]) -> list[Path]:
    def mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0
    return sorted(files, key=mtime, reverse=True)


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


class Importer:
    def __init__(self, library: Library, db: Database | None = None,
                 progress: Callable[[ImportStats, str], None] | None = None,
                 is_cancelled: Callable[[], bool] | None = None, dest_folder: str = UNSORTED_FOLDER):
        """dest_folder: folder biblioteki, do którego trafiają kopie (domyślnie „Do posortowania”;
        w trybie „Sortuj z telefonu” — od razu folder tematyczny)."""
        self.lib = library
        self.dest_folder = dest_folder
        self.duplicate_of: str | None = None   # ścieżka pliku w bibliotece przy wykrytym duplikacie
        self.db = db or library.open_db()
        self.progress = progress or (lambda s, name: None)
        self.is_cancelled = is_cancelled or (lambda: False)
        self.stats = ImportStats()
        self.dest_dir = library.root / dest_folder
        self.dest_dir.mkdir(exist_ok=True)

    # ------------------------------------------------------------------ #
    def import_paths(self, files: list[Path], source_label: str = "", limit: int | None = None) -> ImportStats:
        """limit: zaimportuj najwyżej N NOWYCH plików, zaczynając od najnowszych (duplikaty
        i pliki zaimportowane wcześniej nie liczą się do limitu)."""
        if limit:
            self.stats.limit = limit
            files = sort_newest_first(files)
        self.stats.total = len(files)
        import_id = self.db.execute("INSERT INTO imports(started, source) VALUES(?, ?)",
                                    (time.time(), source_label)).lastrowid
        try:
            for src in files:
                if self.stats.limit and self.stats.copied >= self.stats.limit:
                    self.stats.limit_reached = True
                    break
                if self.is_cancelled():
                    self.stats.aborted_reason = "Import przerwany przez użytkownika."
                    break
                self.progress(self.stats, src.name)
                try:
                    self.import_file(src)
                except DiskFullError as exc:
                    self.stats.aborted_reason = str(exc)
                    self.stats.errors.append(f"{src.name}: {exc}")
                    break
                except Exception as exc:  # pojedynczy błąd nie przerywa importu
                    self.stats.errors.append(f"{src}: {_err_text(exc)}")
                self.stats.processed += 1
            self.progress(self.stats, "")
        finally:
            self.db.execute("UPDATE imports SET finished=?, copied=?, duplicates=?, errors=? WHERE id=?",
                            (time.time(), self.stats.copied, self.stats.duplicates + self.stats.skipped_known,
                             len(self.stats.errors), import_id))
        return self.stats

    # ------------------------------------------------------------------ #
    def import_file(self, src: Path, source_key: str | None = None, consume: bool = False) -> int | None:
        """Kopiuje jeden plik. consume=True: plik jest NASZĄ kopią tymczasową
        (np. ze stagingu urządzenia) i może zostać przeniesiony/usunięty."""
        st = src.stat()
        kind = media_kind(src.suffix)
        if kind is None:
            raise ValueError("nieobsługiwany format")
        if source_key is None:
            source_key = f"{os.path.normcase(str(src.resolve()))}|{st.st_size}|{int(st.st_mtime)}"
        # 1) ten sam plik już kiedyś zaimportowany i nadal jest w bibliotece
        if self.is_known_source(source_key):
            self.stats.skipped_known += 1
            if consume:
                _remove_quiet(src)
            return None

        if consume:
            return self._consume(src, st, kind, source_key)

        # 2) miejsce na dysku
        free = shutil.disk_usage(self.dest_dir).free
        if free < st.st_size + DISK_SPACE_MARGIN:
            raise DiskFullError("Brak miejsca na dysku — import został zatrzymany. "
                                "Zwolnij miejsce i uruchom import ponownie.")

        # 3) kopiowanie do pliku tymczasowego z jednoczesnym liczeniem skrótu
        partial = unique_path(self.dest_dir, src.name + PARTIAL_SUFFIX)
        h = hashlib.sha256()
        try:
            with open(src, "rb") as fin, open(partial, "xb") as fout:
                while True:
                    if self.is_cancelled():
                        raise ImportCancelled()
                    chunk = fin.read(CHUNK)
                    if not chunk:
                        break
                    h.update(chunk)
                    fout.write(chunk)
                fout.flush()
                os.fsync(fout.fileno())
            if os.path.getsize(partial) != st.st_size:
                raise OSError("rozmiar kopii nie zgadza się z oryginałem")
        except ImportCancelled:
            _remove_quiet(partial)
            raise
        except OSError as exc:
            _remove_quiet(partial)
            if _is_disk_full(exc):
                raise DiskFullError("Brak miejsca na dysku — import został zatrzymany.") from exc
            raise
        digest = h.hexdigest()

        # 4) duplikat? (porównanie zawartości)
        if self._is_duplicate(digest, st.st_size):
            _remove_quiet(partial)  # usuwamy wyłącznie naszą kopię tymczasową
            self._remember_source(source_key, digest)
            self.stats.duplicates += 1
            return None

        # 5) nadanie docelowej nazwy (bez nadpisywania)
        with self.lib.lock:
            final = self._finalize(partial, src.name)
            media_id = self._insert(final, kind, digest, str(src))
        try:
            os.utime(final, (st.st_atime, st.st_mtime))
            copy_creation_time(src, final)
        except OSError:
            pass
        self._remember_source(source_key, digest)
        self.stats.copied += 1
        self.stats.bytes_copied += st.st_size
        self.stats.new_ids.append(media_id)
        return media_id

    def _consume(self, staged: Path, st: os.stat_result, kind: str, source_key: str) -> int | None:
        digest = hash_file(staged)
        if self._is_duplicate(digest, st.st_size):
            _remove_quiet(staged)
            self._remember_source(source_key, digest)
            self.stats.duplicates += 1
            return None
        with self.lib.lock:
            final = self._finalize(staged, staged.name)
            media_id = self._insert(final, kind, digest, source_key.split("|")[0])
        self._remember_source(source_key, digest)
        self.stats.copied += 1
        self.stats.bytes_copied += st.st_size
        self.stats.new_ids.append(media_id)
        return media_id

    def _finalize(self, tmp: Path, name: str) -> Path:
        for _ in range(20):
            final = unique_path(self.dest_dir, name)
            try:
                if tmp.parent == self.dest_dir or tmp.drive == final.drive:
                    os.rename(tmp, final)  # Windows: błąd, gdy plik istnieje — nic nie nadpisujemy
                else:
                    shutil.move(str(tmp), str(final))
                return final
            except FileExistsError:
                continue
        raise OSError("nie udało się nadać unikalnej nazwy pliku")

    def _existing(self, rows) -> bool:
        """Czy któryś z wpisów indeksu ma plik faktycznie obecny na dysku (usuwa nieaktualne)."""
        found = False
        for r in rows:
            if self.lib.abs_path(r["rel_path"]).exists():
                found = True
                self.duplicate_of = r["rel_path"]
            else:
                self.db.execute("DELETE FROM media WHERE id=?", (r["id"],))
        return found

    def is_known_source(self, source_key: str) -> bool:
        rows = self.db.query("SELECT m.id, m.rel_path FROM import_sources s JOIN media m ON m.hash = s.hash "
                             "WHERE s.source_key=?", (source_key,))
        return self._existing(rows)

    def _is_duplicate(self, digest: str, size: int) -> bool:
        if self._existing(self.db.query("SELECT id, rel_path FROM media WHERE hash=?", (digest,))):
            return True
        # pliki w bibliotece bez policzonego skrótu, ale o tym samym rozmiarze
        for row in self.db.query("SELECT id, rel_path FROM media WHERE size=? AND hash IS NULL", (size,)):
            path = self.lib.abs_path(row["rel_path"])
            try:
                other = hash_file(path)
            except OSError:
                continue
            self.db.execute("UPDATE media SET hash=? WHERE id=?", (other, row["id"]))
            if other == digest:
                self.duplicate_of = row["rel_path"]
                return True
        return False

    def _remember_source(self, source_key: str, digest: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO import_sources(source_key, hash, ts) VALUES(?,?,?)",
                        (source_key, digest, time.time()))

    def _insert(self, final: Path, kind: str, digest: str, source: str) -> int:
        st = final.stat()
        rel = rel_of(self.dest_folder, final.name)
        mod_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
        cur = self.db.execute(
            "INSERT INTO media(rel_path, folder, filename, kind, ext, size, file_created, file_modified, "
            "imported_at, source_path, hash, sort_date, meta_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0) "
            "ON CONFLICT(rel_path) DO UPDATE SET size=excluded.size, hash=excluded.hash, "
            "imported_at=excluded.imported_at, source_path=excluded.source_path, meta_status=0",
            (rel, self.dest_folder, final.name, kind, final.suffix.lower(), st.st_size,
             file_creation_time(st), st.st_mtime, time.time(), source, digest, mod_iso))
        # lastrowid nie jest wiarygodne przy ON CONFLICT DO UPDATE — zawsze odczytaj id
        return self.db.scalar("SELECT id FROM media WHERE rel_path=?", (rel,))


def _remove_quiet(path: Path) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _is_disk_full(exc: OSError) -> bool:
    import errno
    return exc.errno == errno.ENOSPC or getattr(exc, "winerror", None) in (39, 112)


def _err_text(exc: Exception) -> str:
    if isinstance(exc, PermissionError):
        return "brak dostępu do pliku (może być używany przez inny program)"
    if isinstance(exc, FileNotFoundError):
        return "plik nie istnieje lub urządzenie zostało odłączone"
    if isinstance(exc, OSError):
        return exc.strerror or str(exc)
    return str(exc)
