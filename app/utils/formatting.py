"""Formatowanie wartości do wyświetlenia (po polsku lub po angielsku — patrz app.i18n)."""
from __future__ import annotations

from datetime import datetime

from app.i18n import is_english, tr

MONTHS_PL = [
    "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
    "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
]
MONTHS_PL_GEN = [
    "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
    "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
]
MONTHS_EN = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_NO_DATA_PL = "Brak danych"


def no_data() -> str:
    return tr(_NO_DATA_PL)  # i18n: ignore


# Uwaga: stała jest po polsku — w interfejsie używaj no_data() (tłumaczone w chwili użycia).
NO_DATA = _NO_DATA_PL


def month_names() -> list[str]:
    """Nazwy miesięcy w mianowniku w bieżącym języku (styczeń… / January…)."""
    return MONTHS_EN if is_english() else MONTHS_PL


def human_size(size: int | None) -> str:
    if size is None:
        return no_data()
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            text = f"{value:.1f} {unit}"
            return text if is_english() else text.replace(".", ",")
        value /= 1024
    return f"{size} B"


def human_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return no_data()
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def date_pl(dt: datetime | None) -> str:
    if dt is None:
        return no_data()
    if is_english():
        return f"{dt.day} {MONTHS_EN[dt.month - 1]} {dt.year}"
    return f"{dt.day} {MONTHS_PL_GEN[dt.month - 1]} {dt.year}"


def time_pl(dt: datetime | None) -> str:
    if dt is None:
        return no_data()
    return dt.strftime("%H:%M:%S")


def datetime_pl(dt: datetime | None) -> str:
    if dt is None:
        return no_data()
    return f"{date_pl(dt)}, {dt.strftime('%H:%M')}"


def ts_to_dt(ts: float | None) -> datetime | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts)
    except (OSError, OverflowError, ValueError):
        return None


def plural_pl(n: int, one: str, few: str, many: str) -> str:
    """plural_pl(5, 'plik', 'pliki', 'plików') -> 'plików'

    W wersji angielskiej zwraca tr(one) dla 1 i tr(many) dla pozostałych liczb
    (więc formy `one` i `many` muszą być w katalogu tłumaczeń).
    """
    if is_english():
        return tr(one) if n == 1 else tr(many)  # i18n: ignore
    if n == 1:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def count_pl(n: int, one: str, few: str, many: str) -> str:
    return f"{format_int(n)} {plural_pl(n, one, few, many)}"


def format_int(n: int) -> str:
    return f"{n:,}" if is_english() else f"{n:,}".replace(",", " ")


_PL_ORDER = str.maketrans({"ą": "a\x7f", "ć": "c\x7f", "ę": "e\x7f", "ł": "l\x7f", "ń": "n\x7f",
                           "ó": "o\x7f", "ś": "s\x7f", "ź": "z\x7e", "ż": "z\x7f"})


def pl_sort_key(text: str) -> str:
    """Klucz sortowania alfabetycznego zgodny z polskim alfabetem (ą po a, ś po s…)."""
    return text.lower().translate(_PL_ORDER)
