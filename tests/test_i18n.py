"""Interface language: English catalog completeness and runtime switching."""
from datetime import datetime

import pytest

from app import i18n
from app.utils import formatting as fmt


def test_catalog_covers_source():
    import tools.i18n_check as chk
    assert chk.main([]) == 0, "run: python tools/i18n_check.py"


@pytest.fixture
def english():
    i18n.set_language("en")
    yield
    i18n.set_language("pl")


def test_english_formatting(english):
    assert fmt.date_pl(datetime(2024, 5, 1)) == "1 May 2024"
    assert fmt.human_size(1536) == "1.5 KB"
    assert fmt.format_int(12345) == "12,345"
    assert fmt.count_pl(1, "plik", "pliki", "plików") == "1 file"
    assert fmt.count_pl(5, "plik", "pliki", "plików") == "5 files"
    assert fmt.no_data() == "No data"


def test_polish_is_default():
    i18n.set_language("pl")
    assert i18n.tr("Brak danych") == "Brak danych"
    assert fmt.count_pl(5, "plik", "pliki", "plików") == "5 plików"
    assert fmt.human_size(1536) == "1,5 KB"


def test_unknown_language_falls_back_to_polish():
    assert i18n.set_language("xx") == "pl"


def test_english_library_uses_to_sort_folder(english, tmp_path):
    import json

    from app.core.import_manager import Importer, collect_media_files
    from app.core.library_manager import Library, LibraryError
    from app.core.media_manager import Filters, MediaManager
    from tests.conftest import make_jpeg

    make_jpeg(tmp_path / "src" / "IMG_1.JPG")
    lib = Library.create(tmp_path, "Family")
    assert lib.unsorted == "To sort"
    assert (lib.root / "To sort").is_dir() and not (lib.root / "Do posortowania").exists()
    Importer(lib, lib.db).import_paths(collect_media_files([tmp_path / "src"]))
    assert (lib.root / "To sort" / "IMG_1.JPG").is_file()
    assert MediaManager(lib).query_ids("To sort", Filters())
    assert lib.stats()["unsorted"] == 1
    assert i18n.display_folder("To sort") == "To sort"
    with pytest.raises(LibraryError):
        lib.rename_folder("To sort", "Inbox")
    with pytest.raises(LibraryError):
        lib.create_folder("Do posortowania")   # the other language's import-folder name is reserved too
    lib.close()

    # the library keeps its folder name when reopened in Polish
    i18n.set_language("pl")
    lib2 = Library.open(lib.root)
    assert lib2.unsorted == "To sort" and not (lib.root / "Do posortowania").exists()
    assert i18n.display_folder("To sort") == "Do posortowania"
    lib2.close()

    # a library without the saved setting is detected from the folder on disk
    settings = lib.root / ".photosort" / "settings.json"
    data = json.loads(settings.read_text("utf-8"))
    data.pop("unsorted_folder")
    settings.write_text(json.dumps(data), "utf-8")
    lib3 = Library.open(lib.root)
    assert lib3.unsorted == "To sort"
    lib3.close()


def test_polish_library_keeps_do_posortowania(tmp_path):
    from app.core.library_manager import Library
    i18n.set_language("pl")
    lib = Library.create(tmp_path, "Rodzina")
    assert lib.unsorted == "Do posortowania" and lib.unsorted_dir.is_dir()
    lib.close()
