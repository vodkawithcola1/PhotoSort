"""English translations shared by many modules (Polish text -> English text).

Plural helpers (count_pl / plural_pl) look up the singular ("one") and the
"many" form, e.g. "plik" -> "file", "plików" -> "files".
"""

MESSAGES: dict[str, str] = {
    "Brak danych": "No data",
    "Do posortowania": "To sort",
    "plik": "file",
    "plików": "files",
    "pliku": "file",
    "folder": "folder",
    "folderów": "folders",
    # main.py
    "Wystąpił nieoczekiwany błąd. Twoje pliki są bezpieczne.\n\n{error}\n\nSzczegóły zapisano w:\n{log}":
        "An unexpected error occurred. Your files are safe.\n\n{error}\n\nDetails were saved to:\n{log}",
}
