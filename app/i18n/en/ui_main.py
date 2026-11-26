"""English translations (Polish text -> English text).

Main window, welcome screen, settings, common dialogs and the library view.
"""

MESSAGES: dict[str, str] = {
    # dialogs.py
    "Anuluj": "Cancel",
    "Zapisz": "Save",
    "Tak": "Yes",

    # main_window.py
    "Folder „{name}” już istnieje. Wybierz inną nazwę.": "The folder “{name}” already exists. Choose another name.",
    "Nie udało się utworzyć biblioteki:\n{error}": "Could not create the library:\n{error}",
    "Wskaż folder biblioteki PhotoSort": "Choose a PhotoSort library folder",
    "Ten folder nie jest biblioteką PhotoSort:\n{path}\n\n"
    "Aby uporządkować zdjęcia z tego folderu, utwórz nową bibliotekę i użyj „Importuj zdjęcia i filmy”.":
        "This folder is not a PhotoSort library:\n{path}\n\n"
        "To organize the photos in this folder, create a new library and use “Import photos and videos”.",
    "Trwa już import. Poczekaj na jego zakończenie.": "An import is already running. Please wait for it to finish.",
    "Zaimportować {items} do biblioteki?\n\n"
    "Pliki zostaną skopiowane do folderu „{folder}”. Oryginały pozostaną na swoim miejscu.":
        "Import {items} into the library?\n\n"
        "The files will be copied to the “{folder}” folder. The originals will stay where they are.",
    "element": "item",
    "elementów": "items",
    "Import": "Import",
    "Importuj": "Import",
    "Język interfejsu zmieni się po ponownym uruchomieniu programu.\n\nUruchomić program ponownie teraz?":
        "The interface language will change after the program restarts.\n\nRestart now?",
    "Uruchom ponownie": "Restart",
    "Później": "Later",
    "Nowy język zostanie użyty przy następnym uruchomieniu programu.":
        "The new language will be used the next time you start the program.",
    "Trwa import. Przerwać import i zamknąć program?\nSkopiowane do tej pory pliki zostaną zachowane.":
        "An import is in progress. Stop it and close the program?\nFiles copied so far will be kept.",
    "Przerwij i zamknij": "Stop and close",
    "Trwa kopiowanie zdjęć z telefonu do folderów.\n"
    "Zamknąć program teraz? Niedokończone kopie zostaną pominięte (zdjęcia zostaną na telefonie).":
        "Photos are still being copied from the phone to folders.\n"
        "Close the program now? Unfinished copies will be skipped (the photos stay on the phone).",
    "Zamknij": "Close",

    # welcome.py
    "Nowa biblioteka": "New library",
    "Biblioteka to folder, w którym będą Twoje posortowane zdjęcia i filmy.":
        "A library is a folder that will hold your sorted photos and videos.",
    "Nazwa biblioteki": "Library name",
    "np. Zdjęcia mamy": "e.g. Mom's photos",
    "Lokalizacja": "Location",
    "Zmień…": "Change…",
    "Otwórz istniejącą bibliotekę": "Open an existing library",
    "Utwórz bibliotekę": "Create library",
    "Gdzie utworzyć bibliotekę?": "Where should the library be created?",
    "Pulpit": "Desktop",
    "Biblioteka „{name}” już istnieje w tej lokalizacji. Możesz ją otworzyć albo wybrać inną nazwę.":
        "A library named “{name}” already exists here. You can open it or choose another name.",
    "Folder „{name}” już istnieje w tej lokalizacji. Wybierz inną nazwę — "
    "PhotoSort nie nadpisuje istniejących folderów.":
        "A folder named “{name}” already exists here. Choose another name — "
        "PhotoSort never overwrites existing folders.",
    "Zostanie utworzony folder:\n{path}": "This folder will be created:\n{path}",
    "Porządkuj rodzinne zdjęcia i filmy — po prostu przeciągnij je do folderu.":
        "Organize your family photos and videos — just drag them into a folder.",
    "Otwórz ostatnio używaną bibliotekę": "Open the last used library",
    "Utwórz nową bibliotekę": "Create a new library",
    "Nowy folder na Pulpicie (lub w innym miejscu)": "A new folder on the Desktop (or elsewhere)",
    "OSTATNIE BIBLIOTEKI": "RECENT LIBRARIES",
    "Jasny / ciemny motyw": "Light / dark theme",
    "Otwórz „{name}”": "Open “{name}”",
    "Kontynuuj dokładnie tam, gdzie skończyłeś": "Pick up exactly where you left off",
    "Usuń z listy (pliki pozostaną na dysku)": "Remove from list (files stay on disk)",

    # settings_dialog.py
    "Ustawienia": "Settings",
    "WYGLĄD": "APPEARANCE",
    "Jasny motyw": "Light theme",
    "Ciemny motyw": "Dark theme",
    "BIBLIOTEKA": "LIBRARY",
    "Otwórz folder biblioteki": "Open library folder",
    "Odśwież (wykryj zmiany na dysku)": "Refresh (detect changes on disk)",
    "Wykrywa pliki i foldery dodane lub usunięte poza programem PhotoSort":
        "Detects files and folders added or removed outside PhotoSort",
    "HISTORIA PRZENIESIEŃ": "MOVE HISTORY",
    "(cofnięte)": "(undone)",
    "Brak przeniesionych plików.": "No files have been moved yet.",
    "INFORMACJE": "ABOUT",
    "Odczyt metadanych: wbudowany (Pillow, pillow-heif, FFmpeg) + ExifTool ({path})":
        "Metadata reading: built-in (Pillow, pillow-heif, FFmpeg) + ExifTool ({path})",
    "Odczyt metadanych: wbudowany (Pillow, pillow-heif, FFmpeg). ExifTool nie jest wymagany — jeśli umieścisz "
    "exiftool.exe w folderze „tools” obok programu, zostanie użyty automatycznie.":
        "Metadata reading: built-in (Pillow, pillow-heif, FFmpeg). ExifTool is not required — if you put "
        "exiftool.exe in the “tools” folder next to the program, it will be used automatically.",
    "Miasta i kraje ustalane są offline na podstawie danych GeoNames (CC BY 4.0, geonames.org). "
    "Przycisk „Pokaż na mapie” otwiera OpenStreetMap w przeglądarce.<br>"
    "Program nie wysyła żadnych danych przez internet.":
        "Cities and countries are determined offline from GeoNames data (CC BY 4.0, geonames.org). "
        "The “Show on map” button opens OpenStreetMap in your browser.<br>"
        "The program never sends any data over the internet.",
    "Odświeżanie biblioteki w tle…": "Refreshing the library in the background…",

    # library_view.py
    "Cofnij": "Undo",
    "Postęp sortowania — kliknij, aby zobaczyć statystyki": "Sorting progress — click to see statistics",
    "{percent} posortowano": "{percent} sorted",
    "Brak plików": "No files",
    "zostało {count}": "{count} left",
    "{percent} posortowano, zostało {count}. Kliknij, aby zobaczyć statystyki.":
        "{percent} sorted, {count} left. Click to see statistics.",
    "Statystyki biblioteki": "Library statistics",
    "Wszystkie multimedia": "All media",
    "Zdjęcia": "Photos",
    "Filmy": "Videos",
    "Posortowane": "Sorted",
    "Ukończono": "Completed",
    "Foldery tematyczne": "Topic folders",
    "{path}\nKliknij, aby wrócić do kolejki „{folder}”": "{path}\nClick to return to the “{folder}” queue",
    "Wróć do sortowania": "Back to sorting",
    "Wróć": "Back",
    "Cofnij ostatnie przeniesienie (Ctrl+Z)": "Undo last move (Ctrl+Z)",
    "Dodaj zakładkę do bieżącego pliku (Ctrl+D)": "Bookmark the current file (Ctrl+D)",
    "Usuń zakładkę (Ctrl+D)": "Remove bookmark (Ctrl+D)",
    "Importuj zdjęcia i filmy": "Import photos and videos",
    "Importuj zdjęcia i filmy (Ctrl+I)": "Import photos and videos (Ctrl+I)",
    "Ekran główny (zmień bibliotekę)": "Home screen (switch library)",
    "Telefon: {name}": "Phone: {name}",
    "Plik jest niedostępny": "The file is unavailable",
    "Plik mógł zostać przeniesiony lub usunięty poza programem PhotoSort. Biblioteka zostanie odświeżona.":
        "The file may have been moved or deleted outside PhotoSort. The library will be refreshed.",
    "Wczytywanie z telefonu…": "Loading from the phone…",
    "Czekam na telefon…": "Waiting for the phone…",
    "Otwieranie…": "Opening…",
    "Kopiowanie z telefonu: {percent}%": "Copying from the phone: {percent}%",
    "Nie udało się wczytać pliku z telefonu": "Could not load the file from the phone",
    "Możesz nadal przeciągnąć miniaturę do folderu — program spróbuje skopiować plik ponownie.":
        "You can still drag the thumbnail into a folder — the program will try to copy the file again.",
    "Nie można wyświetlić tego zdjęcia": "This photo can't be displayed",
    "Plik może być uszkodzony lub zapisany w nieobsługiwanym formacie. "
    "Możesz go nadal przenieść do folderu (przeciągnij miniaturę).":
        "The file may be damaged or in an unsupported format. "
        "You can still move it to a folder (drag the thumbnail).",
    "Szukam {count} najnowszych zdjęć, których nie ma jeszcze w bibliotece":
        "Looking for the {count} newest photos that aren't in the library yet",
    "Szukam zdjęć, których nie ma jeszcze w bibliotece (pojawią się od najnowszych)":
        "Looking for photos that aren't in the library yet (newest appear first)",
    "Łączenie z telefonem…": "Connecting to the phone…",
    "Duże foldery iPhone'a (kilkaset zdjęć) otwierają się nawet 1–2 minuty — to normalne.":
        "Large iPhone folders (hundreds of photos) can take 1–2 minutes to open — this is normal.",
    "Wczytywanie zdjęć z telefonu…": "Loading photos from the phone…",
    "{what}. Nie odłączaj telefonu i nie blokuj ekranu. Nic nie jest kopiowane na komputer.":
        "{what}. Don't disconnect the phone or lock its screen. Nothing is copied to the computer.",
    "Przerwij": "Stop",
    "Sprawdzono {count} plików": "Checked {count} files",
    "Znaleziono {found} z {limit} ({percent}%)": "Found {found} of {limit} ({percent}%)",
    "Znaleziono {found}": "Found {found}",
    "Brak połączenia z telefonem": "No connection to the phone",
    "Zakończ przeglądanie telefonu": "Stop browsing the phone",
    "Brak plików pasujących do filtrów": "No files match the filters",
    "Zmień lub wyczyść filtry.": "Change or clear the filters.",
    "Ta partia jest przejrzana": "This batch is done",
    "Na telefonie są jeszcze starsze zdjęcia. Wczytać kolejne?":
        "There are older photos on the phone. Load more?",
    "Pokaż kolejne {count} zdjęć z telefonu": "Show the next {count} photos from the phone",
    "Na telefonie nie ma już nowych zdjęć": "No more new photos on the phone",
    "Wszystkie zdjęcia i filmy z wybranych folderów telefonu są już w bibliotece.":
        "All photos and videos from the selected phone folders are already in the library.",
    "Zmień lub wyczyść filtry, aby zobaczyć więcej zdjęć i filmów.":
        "Change or clear the filters to see more photos and videos.",
    "Zacznij od zaimportowania zdjęć": "Start by importing photos",
    "Podłącz telefon, aparat lub pendrive albo wskaż folder na komputerze. "
    "Pliki zostaną skopiowane — oryginały pozostaną nietknięte.":
        "Connect a phone, camera or USB drive, or choose a folder on your computer. "
        "The files will be copied — the originals stay untouched.",
    "Wszystko posortowane!": "All sorted!",
    "Brak plików w folderze „{folder}”. Możesz przeglądać foldery po prawej stronie albo zaimportować "
    "kolejne zdjęcia.":
        "The “{folder}” folder is empty. You can browse the folders on the right or import more photos.",
    "Biblioteka jest pusta": "The library is empty",
    "Zaimportuj zdjęcia i filmy, aby zacząć.": "Import photos and videos to get started.",
    "Ten folder jest pusty": "This folder is empty",
    "Przeciągnij tu zdjęcia lub filmy z kolejki, aby je posortować.":
        "Drag photos or videos here from the queue to sort them.",
}
