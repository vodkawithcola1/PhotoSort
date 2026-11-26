"""English translations (Polish text -> English text): media viewer, metadata panel, thumbnail strip."""

MESSAGES: dict[str, str] = {
    # media_viewer.py
    "Nie można odtworzyć tego filmu": "Can't play this video",
    "Otwórz w domyślnym odtwarzaczu Windows": "Open in the default Windows player",
    "Odtwórz / pauza (spacja)": "Play / pause (Space)",
    "Wycisz": "Mute",
    "Głośność": "Volume",
    "Pełny ekran (F11)": "Full screen (F11)",
    "Ten format lub kodek nie jest obsługiwany przez wbudowany odtwarzacz.\n"
    "Plik jest bezpieczny — możesz go nadal przenosić do folderów.":
        "This format or codec isn't supported by the built-in player.\n"
        "The file is safe — you can still move it to folders.",
    "\n\nSzczegóły: {details}": "\n\nDetails: {details}",
    "Poprzedni (←)": "Previous (←)",
    "Następny (→)": "Next (→)",
    "Pomniejsz (−)": "Zoom out (−)",
    "Dopasuj do okna (0)": "Fit to window (0)",
    "Powiększ (+)": "Zoom in (+)",
    "Obróć podgląd (R)": "Rotate preview (R)",
    # metadata_panel.py
    "Pokaż na mapie": "Show on map",
    "Więcej informacji": "More information",
    "na telefonie · {date}": "on phone · {date}",
    "na telefonie": "on phone",
    "Plik": "File",
    "Na telefonie": "On phone",
    "Data na telefonie": "Date on phone",
    "Rozmiar": "Size",
    "Status": "Status",
    "jeszcze nie skopiowany — przeciągnij do folderu, aby zapisać na komputerze":
        "not copied yet — drag it to a folder to save it on the computer",
    "Odczytywanie informacji…": "Reading information…",
    "Data wykonania: brak danych": "Date taken: no data",
    "  ·  {fps} kl/s": "  ·  {fps} fps",
    # SOURCE_TEXT values (translated at use site)
    "z metadanych zdjęcia (EXIF)": "from photo metadata (EXIF)",
    "z metadanych filmu": "from video metadata",
    "z metadanych (ExifTool)": "from metadata (ExifTool)",
    "odczytana z nazwy pliku": "read from the file name",
    # metadata labels
    "Data wykonania": "Date taken",
    "Godzina wykonania": "Time taken",
    "Utworzenie pliku (Windows)": "File created (Windows)",
    "Modyfikacja pliku (Windows)": "File modified (Windows)",
    "Import do biblioteki (PhotoSort)": "Imported to library (PhotoSort)",
    "Lokalizacja": "Location",
    "Współrzędne GPS": "GPS coordinates",
    "Urządzenie": "Device",
    "Rozdzielczość": "Resolution",
    "Rozmiar pliku": "File size",
    "Format": "Format",
    "Folder": "Folder",
    "Długość filmu": "Video length",
    "Klatki na sekundę": "Frames per second",
    # thumbnail_grid.py
    "Skopiuj z telefonu do": "Copy from phone to",
    "Skopiuj zaznaczone z telefonu do": "Copy selected from phone to",
    "Przenieś zaznaczone do": "Move selected to",
    "Przenieś do": "Move to",
    "Zaznacz wszystko": "Select all",
    "Dodaj / usuń zakładkę": "Add / remove bookmark",
    "Pokaż w Eksploratorze": "Show in Explorer",
}
