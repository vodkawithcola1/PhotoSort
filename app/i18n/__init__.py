"""Interface language support (Polish / English).

The source code is written in Polish: every user-visible text is wrapped in
``tr("…")`` with the Polish text as the key. When the language is English the
key is looked up in the catalogs in ``app/i18n/en/`` (missing entries fall back
to Polish, so nothing ever breaks).

    tr("Zamknij")                                  -> "Close"
    tr("Zaimportowano {n} plików", n=count)        -> "Imported 5 files"

Placeholders use ``str.format`` names and must be identical in the Polish key
and in the English value. The language is chosen once at start-up
(``set_language``); changing it requires restarting the program.
"""
from __future__ import annotations

LANGUAGES = {"pl": "Polski", "en": "English"}
DEFAULT_LANGUAGE = "pl"

_lang = DEFAULT_LANGUAGE
_catalog: dict[str, str] = {}


def _load_catalog() -> dict[str, str]:
    from app.i18n.en import CATALOG
    return CATALOG


def set_language(lang: str | None) -> str:
    global _lang, _catalog
    _lang = lang if lang in LANGUAGES else DEFAULT_LANGUAGE
    _catalog = _load_catalog() if _lang == "en" else {}
    return _lang


def language() -> str:
    return _lang


def is_english() -> bool:
    return _lang == "en"


def tr(text: str, /, **kwargs) -> str:
    """Translate a Polish UI text into the current language and fill placeholders."""
    out = _catalog.get(text, text) if _catalog else text
    if kwargs:
        try:
            out = out.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            out = text.format(**kwargs)
    return out


def system_language() -> str:
    """Language suggested by the operating system (Polish system → pl, anything else → en)."""
    try:
        from PySide6.QtCore import QLocale
        name = QLocale.system().name().lower()
    except Exception:  # pragma: no cover
        import locale
        name = (locale.getlocale()[0] or "").lower()
    return "pl" if name.startswith("pl") else "en"


def display_folder(name: str) -> str:
    """Name of a library folder as shown in the interface.

    The special import folder keeps its Polish name on disk (existing libraries
    depend on it) but is shown translated in the English interface.
    """
    from app.constants import UNSORTED_FOLDER
    if name and name.lower() == UNSORTED_FOLDER.lower():
        return tr(UNSORTED_FOLDER)  # i18n: ignore
    return name
