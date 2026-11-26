"""Testy warstwy core: biblioteka, import, przenoszenie, cofanie, odzyskiwanie."""
import hashlib
import os
from pathlib import Path

import pytest

from app.constants import UNSORTED_FOLDER, SCOPE_ALL
from app.core.import_manager import Importer, collect_media_files
from app.core.library_manager import Library, LibraryError, is_library
from app.core.media_manager import Filters, MediaManager
from app.core.session_manager import SessionManager, SessionState
from tests.conftest import make_jpeg


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def snapshot(folder: Path) -> dict:
    return {str(p.relative_to(folder)): (sha(p), p.stat().st_mtime) for p in folder.rglob("*") if p.is_file()}


# ---------------------------------------------------------------- biblioteka
def test_create_library_structure(library):
    root = library.root
    assert root.name == "Zdjęcia mamy"
    assert (root / UNSORTED_FOLDER).is_dir()
    assert (root / ".photosort" / "library.db").is_file()
    assert (root / ".photosort" / "thumbnails").is_dir()
    assert (root / ".photosort" / "settings.json").is_file()
    assert is_library(root)


def test_create_does_not_overwrite_existing(library):
    with pytest.raises(FileExistsError):
        Library.create(library.root.parent, "Zdjęcia mamy")


def test_invalid_library_name(tmp_path):
    with pytest.raises(LibraryError):
        Library.create(tmp_path, "zła:nazwa")


def test_open_non_library(tmp_path):
    (tmp_path / "x").mkdir()
    with pytest.raises(LibraryError):
        Library.open(tmp_path / "x")


# ---------------------------------------------------------------- import
def test_import_copies_and_keeps_originals(library, source_dir):
    before = snapshot(source_dir)
    files = collect_media_files([source_dir])
    assert len(files) == 4
    stats = Importer(library, library.db).import_paths(files)
    assert stats.copied == 4 and not stats.errors
    # oryginały nietknięte (zawartość i daty)
    assert snapshot(source_dir) == before
    unsorted = sorted(p.name for p in library.unsorted_dir.iterdir())
    assert unsorted == ["IMG_0001.JPG", "IMG_0002.JPG", "IMG_0003.JPG", "IMG_0004.MOV"]
    # kopia identyczna z oryginałem
    for name in unsorted:
        assert sha(library.unsorted_dir / name) == sha(next(source_dir.rglob(name)))
    # zachowana data modyfikacji
    src = next(source_dir.rglob("IMG_0001.JPG"))
    assert abs((library.unsorted_dir / "IMG_0001.JPG").stat().st_mtime - src.stat().st_mtime) < 2
    assert library.db.scalar("SELECT COUNT(*) FROM media") == 4


def test_import_detects_duplicates(library, source_dir, tmp_path):
    files = collect_media_files([source_dir])
    Importer(library, library.db).import_paths(files)
    # ponowny import tych samych plików
    s2 = Importer(library, library.db).import_paths(collect_media_files([source_dir]))
    assert s2.copied == 0 and s2.duplicates + s2.skipped_known == 4
    # ta sama zawartość pod inną nazwą i w innym miejscu
    other = tmp_path / "pendrive"
    other.mkdir()
    (other / "kopia.jpg").write_bytes(next(source_dir.rglob("IMG_0001.JPG")).read_bytes())
    s3 = Importer(library, library.db).import_paths(collect_media_files([other]))
    assert s3.duplicates == 1 and s3.copied == 0
    assert len(list(library.unsorted_dir.iterdir())) == 4
    # brak pozostałych plików tymczasowych
    assert not list(library.root.rglob("*.photosort-partial"))


def test_import_same_name_different_content_not_overwritten(library, tmp_path):
    a = make_jpeg(tmp_path / "a" / "IMG_1.JPG", color=(1, 2, 3))
    b = make_jpeg(tmp_path / "b" / "IMG_1.JPG", color=(200, 2, 3))
    Importer(library, library.db).import_paths([a, b])
    names = sorted(p.name for p in library.unsorted_dir.iterdir())
    assert names == ["IMG_1 (1).JPG", "IMG_1.JPG"]


def test_import_disk_full_is_reported(library, source_dir, monkeypatch):
    import shutil
    from collections import namedtuple
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda p: Usage(100, 100, 10))
    stats = Importer(library, library.db).import_paths(collect_media_files([source_dir]))
    assert stats.copied == 0
    assert stats.aborted_reason and "miejsca" in stats.aborted_reason
    assert not list(library.unsorted_dir.iterdir())


def test_import_cancel_leaves_no_partial(library, source_dir):
    calls = {"n": 0}

    def cancelled():
        calls["n"] += 1
        return calls["n"] > 3
    stats = Importer(library, library.db, is_cancelled=cancelled).import_paths(collect_media_files([source_dir]))
    assert stats.aborted_reason
    assert not list(library.root.rglob("*.photosort-partial"))


# ---------------------------------------------------------------- przenoszenie
def _imported(library, source_dir):
    Importer(library, library.db).import_paths(collect_media_files([source_dir]))
    mm = MediaManager(library)
    return mm, mm.query_ids(UNSORTED_FOLDER, Filters(), "name")


def test_move_and_undo(library, source_dir):
    mm, ids = _imported(library, source_dir)
    library.create_folder("Święta 2026")
    content = sha(library.unsorted_dir / "IMG_0001.JPG")
    res = mm.move([ids[0]], "Święta 2026")
    assert res.moved == [ids[0]] and not res.errors
    moved = library.root / "Święta 2026" / "IMG_0001.JPG"
    assert moved.is_file() and sha(moved) == content
    assert not (library.unsorted_dir / "IMG_0001.JPG").exists()
    assert mm.get(ids[0])["folder"] == "Święta 2026"
    assert len(mm.query_ids(UNSORTED_FOLDER, Filters())) == 3
    # cofnij
    undo = mm.undo_last()
    assert undo.moved == [ids[0]]
    assert (library.unsorted_dir / "IMG_0001.JPG").is_file()
    assert not moved.exists()
    assert mm.get(ids[0])["folder"] == UNSORTED_FOLDER
    assert not mm.can_undo()


def test_move_multiple_between_folders_and_name_conflict(library, source_dir):
    mm, ids = _imported(library, source_dir)
    library.create_folder("Rodzina")
    library.create_folder("Urodziny")
    # w folderze docelowym istnieje już plik o tej nazwie (inna zawartość)
    make_jpeg(library.root / "Urodziny" / "IMG_0002.JPG", color=(9, 9, 9))
    existing = sha(library.root / "Urodziny" / "IMG_0002.JPG")
    r1 = mm.move(ids[:3], "Rodzina")
    assert len(r1.moved) == 3
    r2 = mm.move([ids[1]], "Urodziny")
    assert r2.moved == [ids[1]]
    assert sha(library.root / "Urodziny" / "IMG_0002.JPG") == existing  # nie nadpisano
    assert (library.root / "Urodziny" / "IMG_0002 (1).JPG").is_file()
    # cofanie wraca do „Rodzina”, potem do „Do posortowania” (3 pliki naraz)
    mm.undo_last()
    assert (library.root / "Rodzina" / "IMG_0002.JPG").is_file()
    mm.undo_last()
    assert len(mm.query_ids(UNSORTED_FOLDER, Filters())) == 4


def test_failed_move_keeps_source(library, source_dir, monkeypatch):
    mm, ids = _imported(library, source_dir)
    library.create_folder("Inne")
    import app.core.media_manager as mmod

    def boom(src, dst):
        raise PermissionError(13, "Access denied")
    monkeypatch.setattr(mmod, "_safe_move", boom)
    res = mm.move([ids[0]], "Inne")
    assert res.errors and not res.moved
    assert (library.unsorted_dir / "IMG_0001.JPG").is_file()
    assert mm.get(ids[0])["folder"] == UNSORTED_FOLDER


def test_recovery_after_crash_during_move(library, source_dir):
    mm, ids = _imported(library, source_dir)
    library.create_folder("Inne")
    # symulacja: dziennik zapisany, plik przeniesiony, ale baza nie zaktualizowana (awaria)
    row = mm.get(ids[0])
    library.db.execute("INSERT INTO moves(batch, media_id, src_rel, dst_rel, ts, state) "
                       "VALUES(99, ?, ?, ?, 0, 'pending')", (ids[0], row["rel_path"], "Inne/" + row["filename"]))
    os.rename(library.abs_path(row["rel_path"]), library.root / "Inne" / row["filename"])
    root = library.root
    library.close()
    lib2 = Library.open(root)
    assert MediaManager(lib2).get(ids[0])["folder"] == "Inne"
    lib2.close()


# ---------------------------------------------------------------- foldery
def test_folder_operations(library, source_dir):
    mm, ids = _imported(library, source_dir)
    library.create_folder("Wakacje")
    with pytest.raises(LibraryError):
        library.create_folder("wakacje")
    mm.move([ids[0]], "Wakacje")
    new = library.rename_folder("Wakacje", "Wakacje Sarbinowo")
    assert new == "Wakacje Sarbinowo"
    assert (library.root / "Wakacje Sarbinowo" / "IMG_0001.JPG").is_file()
    assert mm.get(ids[0])["rel_path"] == "Wakacje Sarbinowo/IMG_0001.JPG"
    # cofnięcie działa także po zmianie nazwy folderu
    mm.undo_last()
    assert (library.unsorted_dir / "IMG_0001.JPG").is_file()
    # usuwanie: tylko pusty
    mm.move([ids[1]], "Wakacje Sarbinowo")
    with pytest.raises(LibraryError):
        library.delete_folder("Wakacje Sarbinowo")
    mm.undo_last()
    library.delete_folder("Wakacje Sarbinowo")
    assert not (library.root / "Wakacje Sarbinowo").exists()
    with pytest.raises(LibraryError):
        library.delete_folder(UNSORTED_FOLDER)
    folders = library.folders()
    assert folders[0].is_unsorted and folders[0].count == 4


def test_scan_detects_external_changes(library, source_dir):
    mm, ids = _imported(library, source_dir)
    # użytkownik ręcznie dorzuca plik i folder w Eksploratorze oraz usuwa jeden plik
    make_jpeg(library.root / "Nowy" / "x.jpg")
    os.remove(library.unsorted_dir / "IMG_0003.JPG")
    added, removed, changed = library.scan()
    assert added == 1 and removed == 1
    assert {f.name for f in library.folders()} == {UNSORTED_FOLDER, "Nowy"}


# ---------------------------------------------------------------- filtry, statystyki, sesja
def test_filters_and_stats(library, source_dir):
    from app.core.workers import apply_meta
    from app.services.geocode_service import Geocoder
    from app.services.metadata_service import MetadataReader
    mm, ids = _imported(library, source_dir)
    reader = MetadataReader(use_exiftool=False)
    for r in library.db.query("SELECT id, rel_path, file_modified FROM media"):
        apply_meta(library.db, r["id"], reader.read(library.abs_path(r["rel_path"])), r["file_modified"],
                   Geocoder.shared())
    f = Filters(kind="video")
    assert len(mm.query_ids(UNSORTED_FOLDER, f)) == 1
    assert len(mm.query_ids(UNSORTED_FOLDER, Filters(kind="photo"))) == 3
    assert len(mm.query_ids(UNSORTED_FOLDER, Filters(text="0002"))) == 1
    assert len(mm.query_ids(UNSORTED_FOLDER, Filters(same_day="2026-12-24"))) == 1
    assert len(mm.query_ids(UNSORTED_FOLDER, Filters(year=2026, month=1))) == 1
    assert len(mm.query_ids(UNSORTED_FOLDER, Filters(location="__gps__"))) == 2
    assert len(mm.query_ids(UNSORTED_FOLDER, Filters(location="Warszawa"))) == 1
    library.create_folder("Rodzina")
    mm.move(ids[:1], "Rodzina")
    assert len(mm.query_ids(SCOPE_ALL, Filters(status="sorted"))) == 1
    assert len(mm.query_ids(SCOPE_ALL, Filters(status="unsorted"))) == 3
    s = library.stats()
    assert s == {"total": 4, "photos": 3, "videos": 1, "sorted": 1, "unsorted": 3,
                 "percent": 25.0, "folders": 1}
    # sortowanie chronologiczne: 2025-08 film, 2026-01, potem pozostałe; plik bez daty
    # EXIF sortowany jest wg daty modyfikacji pliku
    order = [mm.get(i)["filename"] for i in mm.query_ids(SCOPE_ALL, Filters(), "date")]
    assert order[:2] == ["IMG_0004.MOV", "IMG_0002.JPG"]
    assert order.index("IMG_0002.JPG") < order.index("IMG_0001.JPG")
    desc = [mm.get(i)["filename"] for i in mm.query_ids(SCOPE_ALL, Filters(), "date", ascending=False)]
    assert desc == list(reversed(order))
    m = mm.get(mm.query_ids(SCOPE_ALL, Filters(text="0004"))[0])
    assert m["kind"] == "video" and abs(m["duration"] - 2.0) < 0.2 and m["fps"] == 25
    assert m["taken_source"] == "video" and abs(m["lat"] - 54.2486) < 1e-3
    assert m["place"] and m["place"].endswith("Polska")  # Sarbinowo -> okolice Mielna
    assert m["taken_at"].startswith("2025-08-01")


def test_session_and_bookmarks_persist(library, source_dir):
    mm, ids = _imported(library, source_dir)
    sm = SessionManager(library.db)
    st = SessionState(scope=UNSORTED_FOLDER, current_id=ids[2], current_index=2, sort="name",
                      filters={"kind": "photo"}, strip_expanded=True, scroll=120, last_target="Rodzina")
    sm.save(st)
    mm.add_bookmark(ids[1], "wrócić tu")
    root = library.root
    library.close()
    lib2 = Library.open(root)
    st2 = SessionManager(lib2.db).load()
    assert st2.current_id == ids[2] and st2.sort == "name" and st2.strip_expanded and st2.scroll == 120
    assert st2.filters == {"kind": "photo"}
    bms = MediaManager(lib2).bookmarks()
    assert len(bms) == 1 and bms[0]["media_id"] == ids[1]
    lib2.close()


# ---------------------------------------------------------------- regresje z przeglądu kodu
def test_scan_does_not_drop_rows_of_unreadable_folder(library, source_dir, monkeypatch):
    mm, ids = _imported(library, source_dir)
    real = os.scandir

    def flaky(path):
        if str(path).endswith(UNSORTED_FOLDER):
            raise PermissionError(13, "folder chwilowo niedostępny")
        return real(path)
    import app.core.library_manager as lm
    monkeypatch.setattr(lm.os, "scandir", flaky)
    added, removed, _ = library.scan()
    assert removed == 0
    assert library.db.scalar("SELECT COUNT(*) FROM media") == 4


def test_reimport_after_file_deleted_outside_app(library, source_dir):
    mm, ids = _imported(library, source_dir)
    os.remove(library.unsorted_dir / "IMG_0001.JPG")   # usunięte w Eksploratorze, bez skanu
    st = Importer(library, library.db).import_paths(collect_media_files([source_dir]))
    assert st.copied == 1                                # plik wraca do biblioteki
    assert (library.unsorted_dir / "IMG_0001.JPG").is_file()
    assert library.db.scalar("SELECT COUNT(*) FROM media") == 4


def test_insert_returns_correct_id_on_stale_row(library, tmp_path):
    a = make_jpeg(tmp_path / "x" / "IMG_9.JPG", color=(1, 1, 1))
    Importer(library, library.db).import_paths([a])
    stale_id = library.db.scalar("SELECT id FROM media")
    os.remove(library.unsorted_dir / "IMG_9.JPG")
    b = make_jpeg(tmp_path / "y" / "IMG_9.JPG", color=(250, 1, 1))
    imp = Importer(library, library.db)
    imp.import_paths([b])
    assert imp.stats.copied == 1
    row = library.db.query_one("SELECT * FROM media WHERE id=?", (imp.stats.new_ids[0],))
    assert row is not None and row["filename"] == "IMG_9.JPG"
    assert row["hash"] == sha(library.unsorted_dir / "IMG_9.JPG")


def test_recovery_of_interrupted_undo(library, source_dir):
    mm, ids = _imported(library, source_dir)
    library.create_folder("Inne")
    res = mm.move([ids[0]], "Inne")
    row = mm.get(ids[0])
    # symulacja awarii w trakcie cofania: plik wrócił na dysku, baza nie zaktualizowana
    library.db.execute("INSERT INTO moves(batch, media_id, src_rel, dst_rel, ts, state) VALUES(?,?,?,?,0,'pending')",
                       (-res.batch, ids[0], row["rel_path"], f"{UNSORTED_FOLDER}/{row['filename']}"))
    os.rename(library.abs_path(row["rel_path"]), library.unsorted_dir / row["filename"])
    root = library.root
    library.close()
    lib2 = Library.open(root)
    mm2 = MediaManager(lib2)
    r = mm2.get(ids[0])
    assert r["folder"] == UNSORTED_FOLDER and r["filename"] == row["filename"]
    assert not mm2.can_undo()      # oryginalne przeniesienie oznaczone jako cofnięte
    lib2.close()


# ---------------------------------------------------------------- tryb próbny (limit)
def test_import_limit_takes_newest_and_continues(library, tmp_path):
    src = tmp_path / "telefon2"
    for i in range(20):
        p = make_jpeg(src / f"IMG_{i:04d}.JPG", color=(i * 12, 10, 10))
        os.utime(p, (1_700_000_000 + i * 100, 1_700_000_000 + i * 100))  # IMG_0019 najnowszy
    st = Importer(library, library.db).import_paths(collect_media_files([src]), limit=5)
    assert st.copied == 5 and st.limit_reached
    assert sorted(p.name for p in library.unsorted_dir.iterdir()) == [f"IMG_{i:04d}.JPG" for i in range(15, 20)]
    # drugi import próbny bierze KOLEJNE 5 (już zaimportowane się nie liczą)
    st2 = Importer(library, library.db).import_paths(collect_media_files([src]), limit=5)
    assert st2.copied == 5
    assert len(list(library.unsorted_dir.iterdir())) == 10
    assert (library.unsorted_dir / "IMG_0010.JPG").is_file()
    # bez limitu — reszta
    st3 = Importer(library, library.db).import_paths(collect_media_files([src]))
    assert st3.copied == 10 and not st3.limit_reached


def test_abs_path_stays_inside_library(library):
    from app.core.library_manager import LibraryError
    assert library.abs_path("Rodzina/IMG_0001.JPG") == library.root / "Rodzina" / "IMG_0001.JPG"
    for bad in ("../poza.jpg", "C:/Windows/win.ini", r"\serwer\udzial\x.jpg", r"A\..\..\x.jpg"):
        with pytest.raises(LibraryError):
            library.abs_path(bad)
