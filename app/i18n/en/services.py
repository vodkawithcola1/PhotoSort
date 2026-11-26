"""English translations (Polish text -> English text) for app/services/."""

MESSAGES: dict[str, str] = {
    # geocode_service.py
    "okolice: {place}": "near {place}",
    # device_browser.py
    "Obsługa urządzeń przenośnych jest niedostępna w tym systemie.":
        "Portable device support is not available on this system.",
    "Błąd połączenia z urządzeniem: {error}": "Device connection error: {error}",
    "Błąd odczytu telefonu: {error}": "Error reading the phone: {error}",
    "Nie znaleziono zdjęć ani filmów we wskazanych folderach telefonu. "
    "Odblokuj telefon i sprawdź, czy zezwolono na dostęp do plików.":
        "No photos or videos were found in the selected phone folders. "
        "Unlock the phone and check that access to files has been allowed.",
    "Nie udało się skopiować pliku z telefonu (telefon zablokowany lub odłączony?).":
        "Could not copy the file from the phone (is the phone locked or disconnected?).",
    "Brak miejsca na dysku.": "Not enough disk space.",
    "Nieznany plik.": "Unknown file.",
    # device_browser.py, device_service.py
    "{name}: nie udało się skopiować z telefonu (telefon zablokowany lub odłączony?)":
        "{name}: could not copy from the phone (is the phone locked or disconnected?)",
    # device_service.py
    "Czytam daty plików: {folder}  ({done} z {total})": "Reading file dates: {folder}  ({done} of {total})",
    "Otwieram folder telefonu: {folder}  (otwarte foldery: {count})":
        "Opening phone folder: {folder}  (folders opened: {count})",
    "telefon zwrócił pusty plik": "the phone returned an empty file",
    "Brak miejsca na dysku — import został zatrzymany.": "Not enough disk space — the import was stopped.",
    "{name}: nieobsługiwany format": "{name}: unsupported format",
    "Import przerwany przez użytkownika.": "Import cancelled by the user.",
    "Nie znaleziono folderu na urządzeniu: {folder} (odblokuj telefon i sprawdź połączenie).":
        "Folder not found on the device: {folder} (unlock the phone and check the connection).",
}
