"""Tryb „Sortuj prosto z telefonu” — pełny przepływ przez kontroler.

Telefon jest podstawiony zwykłym folderem widzianym przez powłokę Windows (ten sam
mechanizm CopyHere / miniatur powłoki, którego używa prawdziwe urządzenie MTP).
"""
import hashlib
import os
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.services import device_service  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform != "win32" or not device_service.available(),
                                reason="wymaga Windows i pywin32")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.constants import SCOPE_DEVICE, UNSORTED_FOLDER  # noqa: E402
from app.core.import_manager import Importer  # noqa: E402
from app.core.library_controller import LibraryController  # noqa: E402
from tests.conftest import make_jpeg, make_mp4  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def wait(app, cond, timeout=30.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def snapshot(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob("*") if p.is_file()}


def test_browse_and_sort_straight_from_phone(qapp, library, tmp_path, monkeypatch):
    phone = tmp_path / "phone"
    cam = phone / "DCIM" / "100APPLE"
    for i in range(7):
        p = make_jpeg(cam / f"IMG_{i:04d}.JPG", color=(i * 35, 80, 120))
        os.utime(p, (1_700_000_000 + i * 60, 1_700_000_000 + i * 60))
    make_mp4(cam / "IMG_0100.MOV", seconds=1)
    monkeypatch.setattr(device_service, "_find_device", lambda shell, name: shell.NameSpace(str(phone)))
    before = snapshot(phone)
    library.create_folder("Rodzina")

    # wcześniej zaimportowano 1 zdjęcie z tego telefonu — ma się nie pokazać w trybie przeglądania
    imp = Importer(library, library.db)
    device_service.import_from_device("Apple iPhone", ["DCIM"], imp, library.staging_dir,
                                      lambda *a: None, lambda: False, limit=1)
    assert imp.stats.copied == 1

    ctrl = LibraryController(library)
    ctrl.start()
    ctrl.open_device("Apple iPhone", ["DCIM"])
    assert ctrl.scope == SCOPE_DEVICE
    assert wait(qapp, lambda: ctrl.device_status == "ready"), ctrl.device_error
    assert len(ctrl.device_order) == 7 and len(ctrl.ids) == 7       # 8 na telefonie − 1 już w bibliotece
    assert all(i < 0 for i in ctrl.ids)
    # nic nie zostało skopiowane do biblioteki przez samo przeglądanie
    assert library.db.scalar("SELECT COUNT(*) FROM media") == 1

    # miniatura z powłoki Windows (bez kopiowania pliku)
    first = ctrl.ids[0]
    assert ctrl.device_thumb(first) is None
    assert wait(qapp, lambda: ctrl.device_thumb(first) is not None)
    assert not any(ctrl.lib.staging_dir.rglob("*.JPG"))

    # podgląd: kopia tylko oglądanego pliku do pamięci podręcznej
    got = {}
    ctrl.device_fetched.connect(lambda mid, p: got.setdefault(mid, p))
    ctrl.device_fetch(first)
    assert wait(qapp, lambda: first in got)
    assert os.path.isfile(got[first]) and "device-cache" in got[first]

    # przeciągnięcie 2 zdjęć na „Rodzina” -> kopiowane prosto do folderu
    a, b = ctrl.ids[0], ctrl.ids[1]
    name_a, name_b = ctrl.device_entry(a).name, ctrl.device_entry(b).name
    ctrl.move([a, b], "Rodzina")
    assert len(ctrl.ids) == 5 and ctrl.current_id not in (a, b)       # od razu następne zdjęcie
    assert wait(qapp, lambda: not ctrl._pending_device)
    assert (library.root / "Rodzina" / name_a).is_file()
    assert (library.root / "Rodzina" / name_b).is_file()
    assert library.db.scalar("SELECT COUNT(*) FROM media WHERE folder='Rodzina'") == 2
    assert library.db.scalar("SELECT COUNT(*) FROM media WHERE folder=?", (UNSORTED_FOLDER,)) == 1
    # kopia identyczna z oryginałem
    assert snapshot(library.root / "Rodzina")[name_a] == before[name_a]

    # Ctrl+Z: usuwa kopie z komputera, zdjęcia wracają na listę telefonu
    ctrl.undo()
    assert not (library.root / "Rodzina" / name_a).exists()
    assert not (library.root / "Rodzina" / name_b).exists()
    assert len(ctrl.device_order) == 7 and len(ctrl.ids) == 7
    assert library.db.scalar("SELECT COUNT(*) FROM media WHERE folder='Rodzina'") == 0

    # skopiuj jedno, zakończ sesję
    c = ctrl.ids[0]
    name_c = ctrl.device_entry(c).name
    ctrl.move([c], "Rodzina")
    assert wait(qapp, lambda: not ctrl._pending_device)
    ctrl.close_device()
    assert ctrl.scope == UNSORTED_FOLDER
    assert not (library.staging_dir / "device-cache").exists()     # pamięć podręczna wyczyszczona
    assert (library.root / "Rodzina" / name_c).is_file()

    # ponowne otwarcie: skopiowane wcześniej zdjęcia już się nie pokazują
    ctrl.open_device("Apple iPhone", ["DCIM"])
    assert wait(qapp, lambda: ctrl.device_status == "ready")
    assert len(ctrl.device_order) == 6
    ctrl.shutdown()

    # telefon nietknięty
    assert snapshot(phone) == before


def test_device_duplicate_by_content_is_skipped(qapp, library, tmp_path, monkeypatch):
    """Zdjęcie, które już jest w bibliotece (np. zaimportowane z folderu), nie jest kopiowane drugi raz."""
    phone = tmp_path / "phone"
    p = make_jpeg(phone / "DCIM" / "IMG_0001.JPG", color=(10, 200, 30))
    other = tmp_path / "pendrive"
    other.mkdir()
    (other / "kopia.jpg").write_bytes(p.read_bytes())
    Importer(library, library.db).import_paths([other / "kopia.jpg"])
    library.create_folder("Inne")
    monkeypatch.setattr(device_service, "_find_device", lambda shell, name: shell.NameSpace(str(phone)))
    ctrl = LibraryController(library)
    ctrl.start()
    toasts = []
    ctrl.toast.connect(lambda t, u: toasts.append(t))
    ctrl.open_device("Telefon", ["DCIM"])
    assert wait(qapp, lambda: ctrl.device_status == "ready")
    ctrl.move([ctrl.ids[0]], "Inne")
    assert wait(qapp, lambda: not ctrl._pending_device)
    assert not list((library.root / "Inne").iterdir())
    assert any("już w bibliotece" in t for t in toasts)
    ctrl.shutdown()


def test_browse_with_limit_stops_early_and_loads_more(qapp, library, tmp_path, monkeypatch):
    phone = tmp_path / "phone"
    n = 0
    for folder in ("100APPLE", "101APPLE"):
        for _ in range(30):
            n += 1
            make_jpeg(phone / "DCIM" / folder / f"IMG_{n:04d}.JPG", color=(n * 4 % 255, 60, 90), size=(64, 48))
            ts = 1_760_000_000 + n * 3600          # każde kolejne zdjęcie godzinę później
            os.utime(phone / "DCIM" / folder / f"IMG_{n:04d}.JPG", (ts, ts))
    (phone / "DCIM" / "101APPLE" / "IMG_0060.AAE").write_text("<plist/>")   # plik edycji iPhone'a — pomijany
    monkeypatch.setattr(device_service, "_find_device", lambda shell, name: shell.NameSpace(str(phone)))
    library.create_folder("Rodzina")
    ctrl = LibraryController(library)
    ctrl.start()
    ctrl.open_device("Apple iPhone", ["DCIM"], limit=5)
    assert wait(qapp, lambda: ctrl.device_status == "ready")
    names = [ctrl.device_entry(m).name for m in ctrl.ids]
    assert names == ["IMG_0060.JPG", "IMG_0059.JPG", "IMG_0058.JPG", "IMG_0057.JPG", "IMG_0056.JPG"]
    assert ctrl.device_more
    assert ctrl.device._examined < 15          # nie przeglądał całego telefonu (60 plików)
    # skopiuj 2, potem „pokaż kolejne”
    ctrl.move(ctrl.ids[:2], "Rodzina")
    assert wait(qapp, lambda: not ctrl._pending_device)
    ctrl.device_load_more()
    assert wait(qapp, lambda: ctrl.device_status == "ready" and len(ctrl.ids) == 8)
    names = [ctrl.device_entry(m).name for m in ctrl.ids]
    assert names[-5:] == ["IMG_0055.JPG", "IMG_0054.JPG", "IMG_0053.JPG", "IMG_0052.JPG", "IMG_0051.JPG"]
    ctrl.close_device()
    # ponownie z limitem 5: dwa skopiowane są pomijane
    ctrl.open_device("Apple iPhone", ["DCIM"], limit=5)
    assert wait(qapp, lambda: ctrl.device_status == "ready")
    names = [ctrl.device_entry(m).name for m in ctrl.ids]
    assert names == ["IMG_0058.JPG", "IMG_0057.JPG", "IMG_0056.JPG", "IMG_0055.JPG", "IMG_0054.JPG"]
    ctrl.shutdown()


def test_newest_by_real_date_across_folders(qapp, library, tmp_path, monkeypatch):
    """„Screenshots” (marzec) nie może wyprzedzić „Camera” (listopad) tylko dlatego, że S > C;
    ukryte miniatury systemowe (.thumbnails) są pomijane."""
    import datetime as dt
    phone = tmp_path / "phone"

    def mk(path, when):
        make_jpeg(path, size=(48, 36), color=(hash(path.name) % 255, 50, 50))
        ts = dt.datetime(*when).timestamp()
        os.utime(path, (ts, ts))

    for i in range(5):
        mk(phone / "DCIM" / "Camera" / f"IMG_202611{10 + i:02d}_120000.jpg", (2026, 11, 10 + i, 12, 0))
    for i in range(5):
        mk(phone / "DCIM" / "Screenshots" / f"Screenshot_202603{10 + i:02d}.jpg", (2026, 3, 10 + i, 9, 0))
    for i in range(3):
        mk(phone / "DCIM" / ".thumbnails" / f"{9000 + i}.jpg", (2026, 11, 20, 8, i))
    monkeypatch.setattr(device_service, "_find_device", lambda shell, name: shell.NameSpace(str(phone)))
    ctrl = LibraryController(library)
    ctrl.start()
    ctrl.open_device("Telefon", ["DCIM"], limit=3)
    assert wait(qapp, lambda: ctrl.device_status == "ready")
    names = [ctrl.device_entry(m).name for m in ctrl.ids]
    assert names == ["IMG_20261114_120000.jpg", "IMG_20261113_120000.jpg", "IMG_20261112_120000.jpg"]
    assert ctrl.device_entry(ctrl.ids[0]).date.startswith("2026-11-14")
    # kolejne partie: reszta aparatu, potem zrzuty ekranu z marca; .thumbnails nigdy
    ctrl.device_load_more()
    assert wait(qapp, lambda: ctrl.device_status == "ready" and len(ctrl.ids) == 6)
    ctrl.device_load_more()
    assert wait(qapp, lambda: ctrl.device_status == "ready" and len(ctrl.ids) == 9)
    ctrl.device_load_more()
    assert wait(qapp, lambda: ctrl.device_status == "ready" and not ctrl.device_more)
    names = [ctrl.device_entry(m).name for m in ctrl.ids]
    assert len(names) == 10 and not any(n[0].isdigit() for n in names)       # bez .thumbnails
    assert names[5].startswith("Screenshot_20260314")
    # „Ten sam dzień” i filtr miesiąca działają w trybie telefonu (data z telefonu)
    from dataclasses import replace
    ctrl.set_filters(replace(ctrl.filters, same_day="2026-03-12"))
    assert [ctrl.device_entry(m).name for m in ctrl.ids] == ["Screenshot_20260312.jpg"]
    ctrl.set_filters(replace(ctrl.filters, same_day="", year=2026, month=11))
    assert len(ctrl.ids) == 5
    ctrl.shutdown()


def test_limit_opens_only_needed_folders(qapp, library, tmp_path, monkeypatch):
    phone = tmp_path / "phone"
    n = 0
    for f in range(100, 110):
        for _ in range(30):
            n += 1
            p = phone / "DCIM" / f"{f}APPLE" / f"IMG_{n:04d}.JPG"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"\xff\xd8\xff\xd9")
            os.utime(p, (1_700_000_000 + n * 600,) * 2)
    monkeypatch.setattr(device_service, "_find_device", lambda shell, name: shell.NameSpace(str(phone)))
    ctrl = LibraryController(library)
    ctrl.start()
    opened = []
    ctrl.open_device("Apple iPhone", ["DCIM"], limit=5)
    ctrl.device.scan_status.connect(lambda t: opened.append(t) if "Otwieram folder" in t else None)
    assert wait(qapp, lambda: ctrl.device_status == "ready")
    names = [ctrl.device_entry(m).name for m in ctrl.ids]
    assert names == ["IMG_0300.JPG", "IMG_0299.JPG", "IMG_0298.JPG", "IMG_0297.JPG", "IMG_0296.JPG"]
    assert ctrl.device._examined <= 10, ctrl.device._examined
    assert all("100APPLE" not in t for t in opened)   # starsze foldery nie były otwierane
    # odłączenie telefonu -> czytelny komunikat zamiast „uszkodzonych” plików
    ctrl._on_dev_disconnected()
    assert ctrl.device_status == "error" and ctrl.ids == [] and "odłączony" in ctrl.device_error
    ctrl.shutdown()


def test_iphone_month_folders_open_only_newest(qapp, library, tmp_path, monkeypatch):
    """iPhone: „Internal Storage/202611_a” itd. Użytkownik zaznacza WSZYSTKIE miesiące (w dowolnej
    kolejności) — otwierane mają być tylko foldery z najnowszego miesiąca, nie cały telefon."""
    import datetime as dt
    phone = tmp_path / "phone"
    store = phone / "Internal Storage"
    months = ["202503_a", "202509_a", "202610_a", "202611_a", "202611_b", "202605_b"]
    n = 0
    for m in months:
        y, mo = int(m[:4]), int(m[4:6])
        for d in range(1, 9):
            n += 1
            p = store / m / f"IMG_{n:04d}.JPG"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"\xff\xd8\xff\xd9")
            # 202611_b zawiera zdjęcia przeplatane z 202611_a (dni parzyste)
            day = d * 2 if m.endswith("_b") else d * 2 - 1
            ts = dt.datetime(y, mo, day, 12, 0).timestamp()
            os.utime(p, (ts, ts))
    monkeypatch.setattr(device_service, "_find_device", lambda shell, name: shell.NameSpace(str(phone)))
    ctrl = LibraryController(library)
    ctrl.start()
    selected = [f"Internal Storage/{m}" for m in ("202503_a", "202611_a", "202605_b", "202610_a",
                                                  "202611_b", "202509_a")]
    opened = []
    ctrl.open_device("Apple iPhone", selected, limit=6)
    ctrl.device.scan_status.connect(lambda t: opened.append(t) if "Otwieram folder" in t else None)
    assert wait(qapp, lambda: ctrl.device_status == "ready")
    dates = [ctrl.device_entry(m).date[:10] for m in ctrl.ids]
    assert dates == ["2026-11-16", "2026-11-15", "2026-11-14", "2026-11-13", "2026-11-12", "2026-11-11"]
    assert ctrl.device_found == 6
    assert not any(m in t for t in opened for m in ("202503_a", "202509_a", "202605_b", "202610_a"))
    # kolejna partia sięga do października dopiero, gdy listopad się skończy
    ctrl.device_load_more(); ctrl.device_load_more()
    assert wait(qapp, lambda: ctrl.device_status == "ready" and len(ctrl.ids) == 18)
    assert ctrl.device_entry(ctrl.ids[16]).date.startswith("2026-10")
    ctrl.shutdown()


def test_preview_copy_reports_progress_and_fixes_heic_extension(qapp, library, tmp_path, monkeypatch):
    phone = tmp_path / "phone"
    cam = phone / "DCIM" / "100APPLE"
    make_jpeg(cam / "IMG_0001.JPG", size=(2400, 1800))
    # iPhone w trybie „Automatycznie”: nazwa .HEIC, zawartość JPEG
    (cam / "IMG_0002.HEIC").write_bytes((cam / "IMG_0001.JPG").read_bytes())
    os.utime(cam / "IMG_0002.HEIC", (1_800_000_000, 1_800_000_000))
    monkeypatch.setattr(device_service, "_find_device", lambda shell, name: shell.NameSpace(str(phone)))
    ctrl = LibraryController(library)
    ctrl.start()
    ctrl.open_device("Apple iPhone", ["DCIM"])
    assert wait(qapp, lambda: ctrl.device_status == "ready")
    got, prog = {}, []
    ctrl.device_fetched.connect(lambda mid, p: got.setdefault(mid, p))
    ctrl.device_fetch_progress.connect(lambda mid, pct: prog.append(pct))
    for mid in ctrl.ids:
        ctrl.device_fetch(mid)
        assert wait(qapp, lambda: mid in got)
    assert prog and prog[-1] == 100
    heic = next(m for m in ctrl.ids if ctrl.device_entry(m).name == "IMG_0002.HEIC")
    assert got[heic].endswith("IMG_0002.JPG")
    from app.services.thumbnail_service import load_display_image
    from pathlib import Path
    assert not load_display_image(Path(got[heic])).isNull()
    ctrl.shutdown()


def test_newest_found_when_listing_is_not_chronological(qapp, library, tmp_path, monkeypatch):
    """iPhone podaje pliki w kolejności nazw, nie dat: zdjęcia z aparatu (IMG_…), zrzuty ekranu
    (.PNG) i pliki zapisane z aplikacji (AMTZ3252.JPG, GARX2551.MP4) są przemieszane."""
    import datetime as dt
    cam = tmp_path / "phone" / "Internal Storage" / "202611_a"
    files = {  # nazwa: dzień listopada
        "AMTZ3252.JPG": 12, "GARX2551.MP4": 11, "IMG_2150.HEIC": 2, "IMG_2151.PNG": 3,
        "IMG_2152.HEIC": 4, "IMG_2153.HEIC": 5, "IMG_2154.HEIC": 6, "IMG_2155.HEIC": 7,
        "IMG_2156.HEIC": 10, "ZZZZ0001.JPG": 1,
    }
    for name, day in files.items():
        p = cam / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if name.endswith(".MP4"):
            make_mp4(p, seconds=1)
        else:
            p.write_bytes(b"\xff\xd8\xff\xd9")
        ts = dt.datetime(2026, 11, day, 12, 0).timestamp()
        os.utime(p, (ts, ts))
    monkeypatch.setattr(device_service, "_find_device",
                        lambda shell, name: shell.NameSpace(str(tmp_path / "phone")))
    ctrl = LibraryController(library)
    ctrl.start()
    ctrl.open_device("Apple iPhone", ["Internal Storage/202611_a"], limit=4)
    assert wait(qapp, lambda: ctrl.device_status == "ready")
    names = [ctrl.device_entry(m).name for m in ctrl.ids]
    assert names == ["AMTZ3252.JPG", "GARX2551.MP4", "IMG_2156.HEIC", "IMG_2155.HEIC"]
    ctrl.shutdown()


def test_video_thumbnail_made_locally_when_phone_gives_none(qapp, library, tmp_path, monkeypatch):
    """iPhone nie udostępnia miniatur filmów — robimy je z kopii filmu."""
    from app.services import shell_thumbs
    cam = tmp_path / "phone" / "DCIM"
    make_mp4(cam / "GARX2551.MP4", seconds=1)
    monkeypatch.setattr(device_service, "_find_device",
                        lambda shell, name: shell.NameSpace(str(tmp_path / "phone")))
    monkeypatch.setattr(shell_thumbs, "shell_thumbnail", lambda *a, **k: None)
    ctrl = LibraryController(library)
    ctrl.start()
    ctrl.open_device("Apple iPhone", ["DCIM"])
    assert wait(qapp, lambda: ctrl.device_status == "ready")
    mid = ctrl.ids[0]
    assert ctrl.device_entry(mid).kind == "video"
    ctrl.device_thumb(mid)
    assert wait(qapp, lambda: ctrl.device_thumbs.get(-mid - 1) is not None)
    ctrl.shutdown()
