"""Testy interfejsu (Qt offscreen): przeciąganie, przeglądanie folderów, zapis postępu, filmy."""
import json
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.constants import MIME_MEDIA_IDS, SCOPE_ALL, UNSORTED_FOLDER  # noqa: E402
from app.core.import_manager import Importer, collect_media_files  # noqa: E402
from app.core.library_manager import Library  # noqa: E402
from app.core.session_manager import AppSettings  # noqa: E402
from tests.conftest import make_jpeg, make_mp4  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.ui import theme
    theme.apply(app, "light")
    yield app


def wait_until(app, cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def build_library(tmp_path, n_photos=6):
    src = tmp_path / "src"
    for i in range(n_photos):
        make_jpeg(src / f"IMG_{i:04d}.JPG", color=(i * 30 % 255, 90, 160), date=f"2026:03:0{i + 1} 10:00:00")
    make_mp4(src / "VID_0001.MP4", seconds=2)
    desk = tmp_path / "Pulpit"
    desk.mkdir()
    lib = Library.create(desk, "Zdjęcia mamy")
    Importer(lib, lib.db).import_paths(collect_media_files([src]))
    for n in ("Święta 2026", "Wakacje Sarbinowo", "Rodzina"):
        lib.create_folder(n)
    root = lib.root
    lib.close()
    return root, src


def open_window(qapp, root, tmp_path):
    from app.ui.main_window import MainWindow
    settings = AppSettings(tmp_path / "appsettings.json")
    win = MainWindow(settings)
    win.resize(1400, 900)
    win.show()
    win.open_library(root)
    assert wait_until(qapp, lambda: win.ctrl.scan_worker is not None and win.ctrl.scan_worker.isFinished())
    return win


def drop_on_folder(qapp, win, ids, folder):
    """Symuluje upuszczenie przeciąganych plików na folder w panelu."""
    lst = win.view.folders.list
    item = next(lst.item(i) for i in range(lst.count()) if lst.item(i).text() == folder)
    pos = lst.visualItemRect(item).center()
    mime = QMimeData()
    mime.setData(MIME_MEDIA_IDS, json.dumps(ids).encode())
    ev = QDropEvent(QPointF(pos), Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier)
    lst.dropEvent(ev)
    qapp.processEvents()
    return ev.isAccepted()


def test_drag_drop_flow_and_resume(qapp, tmp_path, monkeypatch):
    root, src = build_library(tmp_path)
    src_snapshot = {p.name: p.read_bytes() for p in src.iterdir()}
    win = open_window(qapp, root, tmp_path)
    ctrl = win.ctrl
    assert ctrl.scope == UNSORTED_FOLDER
    assert len(ctrl.ids) == 7
    first, second = ctrl.ids[0], ctrl.ids[1]

    # 1) przeciągnięcie głównego zdjęcia: podgląd startuje drag z bieżącym id
    captured = {}
    import app.ui.library_view as lv
    monkeypatch.setattr(lv, "start_media_drag", lambda w, ids, pms, kinds=None: captured.setdefault("ids", ids))
    win.view._drag_current()
    assert captured["ids"] == [first]

    # 2) upuszczenie na folder „Święta 2026” -> plik fizycznie przeniesiony
    name = ctrl.rows[first][0]
    assert drop_on_folder(qapp, win, [first], "Święta 2026")
    assert (root / "Święta 2026" / name).is_file()
    assert not (root / UNSORTED_FOLDER / name).exists()
    assert first not in ctrl.ids and len(ctrl.ids) == 6
    assert ctrl.current_id == second            # automatycznie następny plik
    assert win.view.viewer.current_id == second
    counts = {f.name: f.count for f in ctrl.lib.folders()}
    assert counts["Święta 2026"] == 1 and counts[UNSORTED_FOLDER] == 6

    # 3) upuszczenie na folder źródłowy jest ignorowane
    assert not drop_on_folder(qapp, win, [second], UNSORTED_FOLDER)

    # 4) Ctrl+Z / Cofnij
    ctrl.undo()
    assert (root / UNSORTED_FOLDER / name).is_file()
    assert len(ctrl.ids) == 7

    # 5) wiele plików naraz z miniatur
    ids3 = ctrl.ids[:3]
    assert drop_on_folder(qapp, win, ids3, "Wakacje Sarbinowo")
    assert len(list((root / "Wakacje Sarbinowo").iterdir())) == 3

    # 6) wejście do folderu i przeglądanie jego zawartości
    lst = win.view.folders.list
    item = next(lst.item(i) for i in range(lst.count()) if lst.item(i).text() == "Wakacje Sarbinowo")
    lst.itemClicked.emit(item)
    qapp.processEvents()
    assert ctrl.scope == "Wakacje Sarbinowo"
    assert sorted(ctrl.ids) == sorted(ids3)
    assert win.view.top.crumb_cur.text() == "Wakacje Sarbinowo"
    assert win.view.viewer.current_id in ids3
    # chronologicznie (domyślne sortowanie wg daty wykonania)
    dates = [ctrl.mm.get(i)["sort_date"] for i in ctrl.ids]
    assert dates == sorted(dates)

    # 7) przeniesienie z folderu do innego folderu
    ctrl.set_index(1)
    moving = ctrl.current_id
    assert drop_on_folder(qapp, win, [moving], "Rodzina")
    assert ctrl.mm.get(moving)["folder"] == "Rodzina"
    assert len(ctrl.ids) == 2
    remembered = ctrl.current_id

    # 8) zakładka
    ctrl.toggle_bookmark(remembered)

    # 9) zamknięcie i ponowne otwarcie — ten sam folder i plik
    win.close()
    qapp.processEvents()
    win2 = open_window(qapp, root, tmp_path)
    assert win2.ctrl.scope == "Wakacje Sarbinowo"
    assert win2.ctrl.current_id == remembered
    assert win2.view.viewer.current_id == remembered
    assert [b["media_id"] for b in win2.ctrl.mm.bookmarks()] == [remembered]
    # powrót do głównej kolejki zachowuje pozycję z tamtego folderu
    win2.ctrl.set_scope(UNSORTED_FOLDER)
    assert len(win2.ctrl.ids) == 4   # 7 zaimportowanych − 3 przeniesione do „Wakacje Sarbinowo”
    win2.close()
    qapp.processEvents()

    # oryginały nietknięte
    assert {p.name: p.read_bytes() for p in src.iterdir()} == src_snapshot


def test_video_plays(qapp, tmp_path):
    from PySide6.QtMultimedia import QMediaPlayer
    from app.ui.media_viewer import VideoView
    path = make_mp4(tmp_path / "film.mp4", seconds=2)
    v = VideoView()
    v.resize(640, 480)
    v.show()
    v.load(path, None, 2.0)
    assert wait_until(qapp, lambda: v.player.mediaStatus() in (QMediaPlayer.MediaStatus.LoadedMedia,
                                                                 QMediaPlayer.MediaStatus.InvalidMedia), 10)
    assert v.player.mediaStatus() == QMediaPlayer.MediaStatus.LoadedMedia
    assert v.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState  # bez autostartu
    assert v.player.duration() > 1500
    v.toggle_play()
    assert wait_until(qapp, lambda: v.player.position() > 300, 10)
    v.toggle_play()
    assert v.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
    v.stop()
    v.close()


def test_broken_video_shows_message(qapp, tmp_path):
    from app.ui.media_viewer import VideoView
    bad = tmp_path / "zepsuty.mov"
    bad.write_bytes(b"\x00\x01nie-film" * 200)
    v = VideoView()
    v.resize(640, 480)
    v.show()
    v.load(bad, None, None)
    assert wait_until(qapp, lambda: v.error_box.isVisible(), 10)
    v.stop()
    v.close()


def test_large_queue_performance(qapp, tmp_path):
    """50 000 rekordów: przeładowanie kolejki i rysowanie miniatur muszą być szybkie."""
    desk = tmp_path / "P"
    desk.mkdir()
    lib = Library.create(desk, "Duża")
    rows = [(f"{UNSORTED_FOLDER}/IMG_{i:06d}.JPG", UNSORTED_FOLDER, f"IMG_{i:06d}.JPG", "photo" if i % 7 else "video",
             ".jpg", 1000, 0, 0, 0, f"2020-01-01 {i % 24:02d}:00:00", 1) for i in range(50_000)]
    lib.db.executemany("INSERT INTO media(rel_path, folder, filename, kind, ext, size, file_created, file_modified,"
                       " imported_at, sort_date, meta_status) VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows)
    from app.core.library_controller import LibraryController
    from app.services.thumbnail_service import ThumbnailService
    from app.ui.thumbnail_grid import ThumbnailView
    ctrl = LibraryController(lib)
    t0 = time.perf_counter()
    ctrl.reload(restore=True)
    t_reload = time.perf_counter() - t0
    assert len(ctrl.ids) == 50_000
    thumbs = ThumbnailService(threads=1)
    view = ThumbnailView(ctrl, thumbs)
    view.resize(1200, 600)
    view.set_grid_mode(True)
    view.show()
    qapp.processEvents()
    t0 = time.perf_counter()
    for idx in (0, 10_000, 25_000, 49_999):
        ctrl.set_index(idx)
        view.grab()
        qapp.processEvents()
    t_paint = time.perf_counter() - t0
    thumbs.shutdown()
    ctrl.shutdown()
    lib.close()
    print(f"\nreload 50k: {t_reload:.3f}s, 4x skok+render: {t_paint:.3f}s")
    assert t_reload < 2.0
    assert t_paint < 3.0
