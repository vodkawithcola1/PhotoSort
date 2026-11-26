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
