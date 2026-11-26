"""Import „z urządzenia” przez powłokę Windows (Shell.Application / CopyHere).

Prawdziwego telefonu nie da się podłączyć w testach automatycznych, więc jako
„urządzenie” podstawiamy zwykły folder widziany przez powłokę Windows. Testuje
to wyliczanie plików, kopiowanie CopyHere, oczekiwanie na zakończenie kopii,
import z kopii tymczasowej, pomijanie duplikatów i nietykalność oryginałów.
"""
import hashlib
import sys

import pytest

from app.constants import UNSORTED_FOLDER
from app.core.import_manager import Importer
from app.services import device_service

pytestmark = pytest.mark.skipif(sys.platform != "win32" or not device_service.available(),
                                reason="wymaga Windows i pywin32")


def test_device_import_via_shell_copy(library, source_dir, monkeypatch):
    def fake_find(shell, name):
        return shell.NameSpace(str(source_dir))
    monkeypatch.setattr(device_service, "_find_device", fake_find)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source_dir.rglob("*") if p.is_file()}

    progress = []
    imp = Importer(library, library.db)
    device_service.import_from_device("Apple iPhone", ["DCIM"], imp, library.staging_dir,
                                      lambda ph, d, t: progress.append((ph, d, t)), lambda: False)
    st = imp.stats
    assert not st.errors, st.errors
    assert st.total == 4 and st.copied == 4
    names = sorted(p.name for p in library.unsorted_dir.iterdir())
    assert names == ["IMG_0001.JPG", "IMG_0002.JPG", "IMG_0003.JPG", "IMG_0004.MOV"]
    # staging posprzątany, oryginały nietknięte
    assert not any(library.staging_dir.iterdir())
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source_dir.rglob("*") if p.is_file()}
    assert after == before

    # drugi import z „telefonu”: wszystko pominięte bez kopiowania
    imp2 = Importer(library, library.db)
    device_service.import_from_device("Apple iPhone", ["DCIM"], imp2, library.staging_dir,
                                      lambda *a: None, lambda: False)
    assert imp2.stats.copied == 0 and imp2.stats.skipped_known == 4
    assert library.db.scalar("SELECT COUNT(*) FROM media WHERE folder=?", (UNSORTED_FOLDER,)) == 4


def test_device_import_with_limit(library, tmp_path, monkeypatch):
    from tests.conftest import make_jpeg
    phone = tmp_path / "phone"
    for i in range(8):
        make_jpeg(phone / "DCIM" / "100APPLE" / f"IMG_{i:04d}.JPG", color=(i * 30, 5, 5))
    monkeypatch.setattr(device_service, "_find_device", lambda shell, name: shell.NameSpace(str(phone)))
    imp = Importer(library, library.db)
    device_service.import_from_device("Apple iPhone", ["DCIM"], imp, library.staging_dir,
                                      lambda *a: None, lambda: False, limit=3)
    assert imp.stats.copied == 3 and imp.stats.limit_reached and not imp.stats.errors
    assert len(list(library.unsorted_dir.iterdir())) == 3
    imp2 = Importer(library, library.db)
    device_service.import_from_device("Apple iPhone", ["DCIM"], imp2, library.staging_dir,
                                      lambda *a: None, lambda: False, limit=3)
    assert imp2.stats.copied == 3 and imp2.stats.skipped_known == 3
    assert len(list(library.unsorted_dir.iterdir())) == 6
