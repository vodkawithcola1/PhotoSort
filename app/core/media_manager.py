"""Zapytania o multimedia, bezpieczne przenoszenie plików, cofanie i zakładki."""
from __future__ import annotations

import errno
import os
import shutil
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

from app.constants import SCOPE_ALL, UNSORTED_FOLDER
from app.core.library_manager import Library, LibraryError, rel_of
from app.utils.paths import unique_path


@dataclass
class Filters:
    text: str = ""                 # fragment nazwy pliku
    kind: str = "all"              # all | photo | video
    date_from: str = ""            # YYYY-MM-DD
    date_to: str = ""              # YYYY-MM-DD
    year: int = 0
    month: int = 0                 # 1..12 (wymaga year albo działa dla każdego roku)
    same_day: str = ""             # YYYY-MM-DD — wszystko z tego samego dnia
    min_size_mb: float = 0
    max_size_mb: float = 0
    status: str = "all"            # all | sorted | unsorted (widok całej biblioteki)
    location: str = ""             # "" | "__gps__" | fragment nazwy miejsca
    folder: str = ""               # filtr folderu w widoku całej biblioteki

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "Filters":
        f = cls()
        if d:
            for k, v in d.items():
                if hasattr(f, k):
                    setattr(f, k, v)
        return f

    def is_active(self) -> bool:
        return self != Filters()

    def active_count(self) -> int:
        default = Filters()
        return sum(1 for k, v in asdict(self).items() if v != getattr(default, k) and k != "text")


SORTS = {
    "date": "sort_date {d}, filename {d}, id {d}",
    "name": "filename COLLATE NOCASE {d}, id {d}",
    "imported": "imported_at {d}, id {d}",
    "size": "size {d}, id {d}",
}


@dataclass
class MoveResult:
    moved: list[int] = field(default_factory=list)
    skipped: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    batch: int | None = None


class MediaManager:
    def __init__(self, library: Library):
        self.lib = library
        self.db = library.db

    # ------------------------------------------------------------------ #
    # Zapytania
    # ------------------------------------------------------------------ #
    def query_ids(self, scope: str, filters: Filters, sort: str = "date", ascending: bool = True) -> list[int]:
        where, params = self._where(scope, filters)
        order = SORTS.get(sort, SORTS["date"]).format(d="ASC" if ascending else "DESC")
        sql = f"SELECT id FROM media WHERE {where} ORDER BY {order}"
        return [r[0] for r in self.db.query(sql, params)]

    def _where(self, scope: str, f: Filters) -> tuple[str, list]:
        clauses: list[str] = []
        params: list = []
        if scope != SCOPE_ALL:
            clauses.append("folder = ? COLLATE NOCASE")
            params.append(scope)
        else:
            if f.status == "sorted":
                clauses.append("folder <> ? COLLATE NOCASE")
                params.append(UNSORTED_FOLDER)
            elif f.status == "unsorted":
                clauses.append("folder = ? COLLATE NOCASE")
                params.append(UNSORTED_FOLDER)
            if f.folder:
                clauses.append("folder = ? COLLATE NOCASE")
                params.append(f.folder)
        if f.text.strip():
            clauses.append("filename LIKE ? ESCAPE '\\'")
            params.append("%" + _esc_like(f.text.strip()) + "%")
        if f.kind in ("photo", "video"):
            clauses.append("kind = ?")
            params.append(f.kind)
        if f.same_day:
            clauses.append("substr(sort_date, 1, 10) = ?")
            params.append(f.same_day)
        if f.date_from:
            clauses.append("substr(sort_date, 1, 10) >= ?")
            params.append(f.date_from)
        if f.date_to:
            clauses.append("substr(sort_date, 1, 10) <= ?")
            params.append(f.date_to)
        if f.year:
            clauses.append("substr(sort_date, 1, 4) = ?")
            params.append(f"{int(f.year):04d}")
        if f.month:
            clauses.append("substr(sort_date, 6, 2) = ?")
            params.append(f"{int(f.month):02d}")
        if f.min_size_mb:
            clauses.append("size >= ?")
            params.append(int(f.min_size_mb * 1024 * 1024))
        if f.max_size_mb:
            clauses.append("size <= ?")
            params.append(int(f.max_size_mb * 1024 * 1024))
        if f.location == "__gps__":
            clauses.append("lat IS NOT NULL")
        elif f.location == "__nogps__":
            clauses.append("lat IS NULL")
        elif f.location:
            clauses.append("place LIKE ? ESCAPE '\\'")
            params.append("%" + _esc_like(f.location) + "%")
        return (" AND ".join(clauses) or "1=1"), params

    def light_rows(self, ids: list[int] | None = None) -> dict[int, tuple]:
        """Lekkie dane do miniatur: id -> (filename, kind, duration, folder, rel_path)."""
        sql = "SELECT id, filename, kind, duration, folder, rel_path FROM media"
        if ids is None:
            rows = self.db.query(sql)
        else:
            rows = []
            for i in range(0, len(ids), 900):
                chunk = ids[i:i + 900]
                rows += self.db.query(sql + f" WHERE id IN ({','.join('?' * len(chunk))})", chunk)
        return {r[0]: tuple(r[1:]) for r in rows}

    def get(self, media_id: int):
        return self.db.query_one("SELECT * FROM media WHERE id=?", (media_id,))

    def years(self) -> list[int]:
        rows = self.db.query("SELECT DISTINCT substr(sort_date,1,4) FROM media WHERE sort_date IS NOT NULL "
                             "ORDER BY 1 DESC")
        return [int(r[0]) for r in rows if r[0] and r[0].isdigit()]

    # ------------------------------------------------------------------ #
    # Przenoszenie
    # ------------------------------------------------------------------ #
    def _next_batch(self) -> int:
        return (self.db.scalar("SELECT MAX(batch) FROM moves") or 0) + 1

    def move(self, ids: list[int], target_folder: str) -> MoveResult:
        """Przenosi pliki do folderu biblioteki. Plik źródłowy nie jest nigdy usuwany,
        jeżeli przeniesienie się nie powiodło."""
        with self.lib.lock:
            return self._move(ids, target_folder)

    def _move(self, ids: list[int], target_folder: str) -> MoveResult:
        result = MoveResult()
        target_dir = self.lib.root / target_folder
        if not target_dir.is_dir():
            raise LibraryError(f"Folder „{target_folder}” nie istnieje.")
        batch = self._next_batch()
        for mid in ids:
            row = self.get(mid)
            if row is None:
                result.skipped.append(mid)
                continue
            if row["folder"].lower() == target_folder.lower():
                result.skipped.append(mid)
                continue
            src_rel = row["rel_path"]
            ok, err = self._move_one(mid, src_rel, target_folder, row["filename"], batch)
            if ok:
                result.moved.append(mid)
            else:
                result.errors.append(f"{row['filename']}: {err}")
        if result.moved:
            result.batch = batch
        return result

    def _move_one(self, mid: int, src_rel: str, target_folder: str, filename: str,
                  batch: int, state_after: str = "done") -> tuple[bool, str]:
        src = self.lib.abs_path(src_rel)
        if not src.exists():
            return False, "plik nie istnieje na dysku (mógł zostać usunięty poza programem)"
        target_dir = self.lib.root / target_folder
        for _attempt in range(5):
            dst = unique_path(target_dir, filename)
            dst_rel = rel_of(target_folder, dst.name)
            # 1) zapis w dzienniku PRZED operacją na dysku
            cur = self.db.execute(
                "INSERT INTO moves(batch, media_id, src_rel, dst_rel, ts, state) VALUES(?,?,?,?,?, 'pending')",
                (batch, mid, src_rel, dst_rel, time.time()))
            move_id = cur.lastrowid
            try:
                _safe_move(src, dst)
            except FileExistsError:
                self.db.execute("UPDATE moves SET state='failed' WHERE id=?", (move_id,))
                continue  # ktoś utworzył plik o tej nazwie w międzyczasie — kolejna nazwa
            except OSError as exc:
                self.db.execute("UPDATE moves SET state='failed' WHERE id=?", (move_id,))
                return False, _os_error_text(exc)
            # 2) aktualizacja indeksu po udanej operacji
            #    (ewentualny nieaktualny wpis o tej samej ścieżce jest usuwany, by nie zablokować UNIQUE)
            try:
                with self.db.transaction() as db:
                    db.execute("DELETE FROM media WHERE rel_path=? AND id<>?", (dst_rel, mid))
                    db.execute("UPDATE media SET rel_path=?, folder=?, filename=? WHERE id=?",
                               (dst_rel, target_folder, dst.name, mid))
                    db.execute("UPDATE moves SET state=? WHERE id=?", (state_after, move_id))
            except Exception:
                # plik JEST już przeniesiony; wpis 'pending' zostanie domknięty przy następnym otwarciu
                return True, ""
            return True, ""
        return False, "nie udało się nadać unikalnej nazwy"

    def can_undo(self) -> bool:
        return self.db.scalar("SELECT 1 FROM moves WHERE state='done' LIMIT 1") is not None

    def last_batch_info(self) -> tuple[int, int, str] | None:
        """(batch, liczba plików, folder docelowy) ostatniej operacji do cofnięcia."""
        row = self.db.query_one("SELECT batch FROM moves WHERE state='done' ORDER BY batch DESC LIMIT 1")
        if not row:
            return None
        b = row[0]
        rows = self.db.query("SELECT dst_rel FROM moves WHERE batch=? AND state='done'", (b,))
        return b, len(rows), rows[0][0].split("/", 1)[0] if rows else ""

    def undo_last(self) -> MoveResult:
        """Cofa ostatnią operację przeniesienia (wszystkie pliki z tej operacji)."""
        with self.lib.lock:
            return self._undo_last()

    def _undo_last(self) -> MoveResult:
        result = MoveResult()
        info = self.last_batch_info()
        if not info:
            return result
        batch = info[0]
        undo_batch = -batch  # wpisy cofnięcia mają ujemny numer, by nie trafiły na stos cofania
        moves = self.db.query("SELECT * FROM moves WHERE batch=? AND state='done' ORDER BY id DESC", (batch,))
        for mv in moves:
            row = self.get(mv["media_id"])
            if row is None or row["rel_path"].lower() != mv["dst_rel"].lower():
                # plik został w międzyczasie przeniesiony gdzie indziej — nie ruszamy go
                self.db.execute("UPDATE moves SET state='undone' WHERE id=?", (mv["id"],))
                result.skipped.append(mv["media_id"])
                continue
            src_folder, src_name = mv["src_rel"].split("/", 1)
            src_dir = self.lib.root / src_folder
            if not src_dir.is_dir():
                src_dir.mkdir(parents=True, exist_ok=True)
            # przywróć oryginalną nazwę pliku (bez ewentualnego " (1)")
            target_folder = src_folder
            sub = os.path.dirname(src_name)
            if sub:
                # plik pochodził z podfolderu folderu tematycznego
                target_folder = f"{src_folder}/{sub}"
                (self.lib.root / target_folder).mkdir(parents=True, exist_ok=True)
            ok, err = self._move_one(mv["media_id"], mv["dst_rel"], target_folder,
                                     os.path.basename(src_name), undo_batch, state_after="undo")
            if ok:
                if sub:
                    # w indeksie folder to zawsze pierwszy człon ścieżki
                    self.db.execute("UPDATE media SET folder=? WHERE id=?", (src_folder, mv["media_id"]))
                self.db.execute("UPDATE moves SET state='undone' WHERE id=?", (mv["id"],))
                result.moved.append(mv["media_id"])
            else:
                result.errors.append(f"{row['filename']}: {err}")
        return result

    def history(self, limit: int = 200) -> list:
        return self.db.query("SELECT * FROM moves WHERE state IN ('done','undone') ORDER BY id DESC LIMIT ?",
                             (limit,))

    # ------------------------------------------------------------------ #
    # Zakładki
    # ------------------------------------------------------------------ #
    def add_bookmark(self, media_id: int, label: str = "") -> None:
        self.db.execute("INSERT INTO bookmarks(media_id, label, created) VALUES(?,?,?) "
                        "ON CONFLICT(media_id) DO UPDATE SET label=excluded.label",
                        (media_id, label, time.time()))

    def remove_bookmark(self, media_id: int) -> None:
        self.db.execute("DELETE FROM bookmarks WHERE media_id=?", (media_id,))

    def is_bookmarked(self, media_id: int) -> bool:
        return self.db.scalar("SELECT 1 FROM bookmarks WHERE media_id=?", (media_id,)) is not None

    def bookmarks(self) -> list:
        return self.db.query(
            "SELECT b.id, b.media_id, b.label, b.created, m.filename, m.folder, m.kind "
            "FROM bookmarks b JOIN media m ON m.id=b.media_id ORDER BY b.created DESC")


# ---------------------------------------------------------------------- #
def _safe_move(src: Path, dst: Path) -> None:
    """Przeniesienie bez ryzyka nadpisania.

    W obrębie jednego dysku os.rename jest atomowe, a na Windows zgłasza błąd,
    gdy plik docelowy istnieje (nic nie zostanie nadpisane). Gdy biblioteka jest
    rozłożona na różne dyski (np. folder-dowiązanie), kopiujemy, weryfikujemy
    rozmiar i dopiero wtedy usuwamy źródło.
    """
    if dst.exists():
        raise FileExistsError(str(dst))
    try:
        os.rename(src, dst)
        return
    except FileExistsError:
        raise
    except OSError as exc:
        if exc.errno != errno.EXDEV and getattr(exc, "winerror", None) != 17:
            raise
    tmp = dst.with_name(dst.name + ".photosort-partial")
    try:
        shutil.copy2(src, tmp)
        if os.path.getsize(tmp) != os.path.getsize(src):
            raise OSError("weryfikacja kopii nie powiodła się")
        os.rename(tmp, dst)
    except BaseException:
        try:
            if tmp.exists():
                os.remove(tmp)
        except OSError:
            pass
        raise
    try:
        os.remove(src)
    except OSError:
        # źródła nie da się usunąć (np. zablokowane) — wycofaj NASZĄ kopię, aby stan był spójny
        try:
            os.remove(dst)
        except OSError:
            pass
        raise


def _os_error_text(exc: OSError) -> str:
    if exc.errno == errno.ENOSPC or getattr(exc, "winerror", None) in (39, 112):
        return "brak miejsca na dysku"
    if getattr(exc, "winerror", None) == 32 or exc.errno == errno.EACCES:
        return "plik jest używany przez inny program lub brak uprawnień"
    return exc.strerror or str(exc)


def _esc_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
