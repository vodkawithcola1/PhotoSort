"""English translations (Polish text -> English text).

Covers app/ui/filter_bar.py, app/ui/folder_panel.py and app/ui/import_dialog.py.
"""

MESSAGES: dict[str, str] = {
    # ---- filter_bar.py -------------------------------------------------
    # SORT_OPTIONS (translated at use site)
    "Data wykonania": "Date taken",
    "Nazwa pliku": "File name",
    "Data importu": "Date imported",
    "Rozmiar pliku": "File size",
    # filters popup
    "Filtry": "Filters",
    "Filtry ({n})": "Filters ({n})",
    "Rok": "Year",
    "Miesiąc": "Month",
    "Dowolny": "Any",
    "Dowolna": "Any",
    "Zakres dat": "Date range",
    "do": "to",
    "Rozmiar od (MB)": "Size from (MB)",
    "do (MB)": "to (MB)",
    "Lokalizacja": "Location",
    "Tylko z lokalizacją GPS": "Only with GPS location",
    "Bez lokalizacji": "No location",
    "Miejscowość…": "Place…",
    "np. Kraków": "e.g. London",
    "Status": "Status",
    "Wszystkie": "All",
    "Posortowane": "Sorted",
    "Nieposortowane": "Unsorted",
    "Folder": "Folder",
    "Wyczyść filtry": "Clear filters",
    "Zastosuj": "Apply",
    # queue header
    "Szukaj po nazwie pliku": "Search by file name",
    "Wszystko": "All",
    "Zdjęcia": "Photos",
    "Filmy": "Videos",
    "Sortowanie": "Sort by",
    "Ten sam dzień": "Same day",
    "Pokaż wszystkie zdjęcia i filmy z dnia, w którym wykonano bieżący plik":
        "Show all photos and videos from the day the current file was taken",
    "Rozwiń / zwiń siatkę miniatur": "Expand / collapse the thumbnail grid",
    "Rosnąco (od najstarszych)": "Ascending (oldest first)",
    "Malejąco (od najnowszych)": "Descending (newest first)",
    "Telefon": "Phone",
    "Wszystkie multimedia": "All media",
    "Zdjęcia z telefonu są ułożone od najnowszych": "Phone photos are listed newest first",
    " na telefonie": " on the phone",
    " · wczytywanie {found}/{limit}…": " · loading {found}/{limit}…",
    " · wczytywanie…": " · loading…",
    " (są kolejne)": " (more available)",
    "wczytywanie…": "loading…",
    "brak nowych plików": "no new files",
    "brak plików": "no files",
    "{pos} z {files}{suffix}": "{pos} of {files}{suffix}",
    # filter summary chips
    "z dnia {date}": "from {date}",
    "rok {year}": "year {year}",
    "{month} (każdy rok)": "{month} (any year)",
    "rozmiar {low}–{high} MB": "size {low}–{high} MB",
    "z lokalizacją GPS": "with GPS location",
    "bez lokalizacji": "no location",
    "miejsce: {place}": "place: {place}",
    "posortowane": "sorted",
    "nieposortowane": "unsorted",
    "folder: {folder}": "folder: {folder}",
    "tylko zdjęcia": "photos only",
    "tylko filmy": "videos only",
    "nazwa zawiera „{text}”": "name contains “{text}”",

    # ---- folder_panel.py -----------------------------------------------
    "Nowy folder": "New folder",
    "Upuść, aby utworzyć nowy folder": "Drop to create a new folder",
    "Foldery": "Folders",
    "Utwórz nowy folder": "Create a new folder",
    "Szukaj folderu": "Search folders",
    "ZAKŁADKI": "BOOKMARKS",
    "ZAKŁADKI ({count})": "BOOKMARKS ({count})",
    "Pokaż / ukryj zakładki": "Show / hide bookmarks",
    "Kliknij ikonę zakładki na górze, aby oznaczyć zdjęcie, do którego chcesz wrócić.":
        "Click the bookmark icon at the top to mark a photo you want to come back to.",
    "Telefon: {name}": "Phone: {name}",
    "Zdjęcia na telefonie, których jeszcze nie ma w bibliotece. Przeciągnij zdjęcie "
    "na folder, aby skopiować je prosto do tego folderu.":
        "Photos on the phone that are not in the library yet. Drag a photo onto a folder "
        "to copy it straight into that folder.",
    "Wczytywanie listy…": "Loading the list…",
    "Do przejrzenia: {count}": "To review: {count}",
    "FOLDERY TEMATYCZNE": "YOUR FOLDERS",
    "Utwórz pierwszy folder, np. „Święta 2026”": "Create your first folder, e.g. “Christmas 2026”",
    "{photos} · {videos} · {folders}": "{photos} · {videos} · {folders}",
    "zdjęcie": "photo",
    "zdjęć": "photos",
    "film": "video",
    "filmów": "videos",
    "Utwórz folder i przenieś do niego {files}.": "Create a folder and move {files} into it.",
    "Utwórz i przenieś": "Create and move",
    "Podaj nazwę folderu, np. „Wakacje Sarbinowo”.": "Enter a folder name, e.g. “Summer holiday”.",
    "Utwórz": "Create",
    "Pokaż zdjęcia z telefonu": "Show photos from the phone",
    "Zakończ przeglądanie telefonu": "Stop browsing the phone",
    "Otwórz": "Open",
    "Zmień nazwę…": "Rename…",
    "Usuń pusty folder": "Delete empty folder",
    "Pokaż w Eksploratorze": "Show in Explorer",
    "Zmień nazwę folderu": "Rename folder",
    "Nowa nazwa dla „{name}”:": "New name for “{name}”:",
    "Zmień nazwę": "Rename",
    "Usuń folder": "Delete folder",
    "Usunąć pusty folder „{name}”?": "Delete the empty folder “{name}”?",
    "Usuń": "Delete",
    "{filename}\nFolder: {folder}\nKliknij, aby przejść do tego pliku.":
        "{filename}\nFolder: {folder}\nClick to go to this file.",
    "Przejdź do pliku": "Go to file",
    "Usuń zakładkę": "Remove bookmark",

    # ---- import_dialog.py ----------------------------------------------
    # DEVICE_HELP (translated at use site)
    """<b>Jak podłączyć telefon lub aparat</b>
<ol style="margin-left:-20px">
<li><b>iPhone:</b> podłącz kablem USB i <b>odblokuj</b> telefon. Na ekranie iPhone'a stuknij
<b>„Ufaj temu komputerowi”</b> (lub „Zezwól”) i wpisz kod.</li>
<li>Jeśli iPhone się nie pojawia, zainstaluj ze sklepu Microsoft Store aplikację
<b>„Urządzenia Apple”</b> (Apple Devices) lub iTunes — zawiera sterownik — a potem odłącz i podłącz telefon ponownie.</li>
<li><b>Android:</b> po podłączeniu rozwiń pasek powiadomień na telefonie i wybierz
<b>„Przesyłanie plików”</b> (MTP).</li>
<li><b>Aparat / karta SD / pendrive</b> z literą dysku (np. E:) — wybierz w poprzednim kroku
„Folder na komputerze lub pendrive”.</li>
</ol>
<p>PhotoSort wyłącznie <b>kopiuje</b> pliki — niczego nie usuwa ani nie zmienia na telefonie.</p>
<p style="color:gray">Wskazówka dla iPhone'a: w Ustawienia → Zdjęcia → „Przenieś na Mac lub PC” wybierz
„Zachowaj oryginały”, aby skopiować oryginalne pliki HEIC/MOV. Gdy import z telefonu nie działa,
możesz też skopiować zdjęcia aplikacją „Zdjęcia” systemu Windows, a następnie wskazać folder z kopiami.</p>""":
    """<b>How to connect a phone or camera</b>
<ol style="margin-left:-20px">
<li><b>iPhone:</b> connect it with a USB cable and <b>unlock</b> the phone. On the iPhone screen tap
<b>“Trust This Computer”</b> (or “Allow”) and enter your passcode.</li>
<li>If the iPhone does not appear, install the <b>“Apple Devices”</b> app or iTunes from the
Microsoft Store — it includes the driver — then disconnect and reconnect the phone.</li>
<li><b>Android:</b> after connecting, pull down the notification shade on the phone and choose
<b>“File transfer”</b> (MTP).</li>
<li><b>Camera / SD card / USB drive</b> with a drive letter (e.g. E:) — choose
“Folder on this computer or USB drive” in the previous step.</li>
</ol>
<p>PhotoSort only <b>copies</b> files — it never deletes or changes anything on the phone.</p>
<p style="color:gray">iPhone tip: in Settings → Photos → “Transfer to Mac or PC” choose
“Keep Originals” to copy the original HEIC/MOV files. If importing from the phone does not work,
you can also copy the photos with the Windows Photos app and then select the folder with the copies.</p>""",
    "Importuj zdjęcia i filmy": "Import photos and videos",
    "Pliki zostaną <b>skopiowane</b> do folderu „{folder}”. Oryginały pozostaną "
    "nietknięte, a duplikaty zostaną pominięte.":
        "Files will be <b>copied</b> to the “{folder}” folder. The originals stay "
        "untouched, and duplicates are skipped.",
    "Telefon lub aparat (USB)": "Phone or camera (USB)",
    "Sortuj prosto z telefonu albo zaimportuj — iPhone, Android, aparat":
        "Sort straight from the phone or import — iPhone, Android, camera",
    "Folder na komputerze lub pendrive": "Folder on this computer or USB drive",
    "Folder, karta SD, dysk zewnętrzny": "Folder, SD card, external drive",
    "Wybrane pliki": "Selected files",
    "Zaznacz pojedyncze zdjęcia lub filmy": "Pick individual photos or videos",
    "Uwzględnij podfoldery": "Include subfolders",
    "Tylko": "Only",
    "Tryb próbny — np. aby sprawdzić import z telefonu bez kopiowania wszystkich zdjęć":
        "Trial mode — e.g. to test importing from the phone without copying all the photos",
    "Wpisz liczbę lub zmień kółkiem myszy": "Type a number or use the mouse wheel",
    "najnowszych zdjęć i filmów (np. na próbę)": "newest photos and videos (e.g. as a trial)",
    "Dotyczy importu i trybu „Sortuj prosto z telefonu”. Zdjęcia, które już są "
    "w bibliotece, nie liczą się do limitu — następnym razem dostaniesz kolejne.":
        "Applies to importing and to “Sort straight from the phone”. Photos already "
        "in the library don’t count towards the limit — next time you’ll get the next ones.",
    "Możesz też po prostu przeciągnąć pliki lub foldery z Eksploratora do okna PhotoSort.":
        "You can also simply drag files or folders from File Explorer into the PhotoSort window.",
    "Anuluj": "Cancel",
    "Wybierz folder ze zdjęciami i filmami": "Choose a folder with photos and videos",
    "Wybierz zdjęcia i filmy": "Choose photos and videos",
    "Zdjęcia i filmy ({exts});;Wszystkie pliki (*.*)": "Photos and videos ({exts});;All files (*.*)",
    "Import z telefonu lub aparatu": "Import from a phone or camera",
    "Jak podłączyć telefon?": "How do I connect a phone?",
    "Ukryj instrukcję": "Hide instructions",
    "Podłączone urządzenia": "Connected devices",
    "Odśwież": "Refresh",
    "Foldery do zaimportowania": "Folders to import",
    "Importuj do „{folder}”": "Import to “{folder}”",
    "Skopiuj zdjęcia z telefonu na komputer (wszystkie lub N najnowszych), "
    "a potem sortuj je na komputerze":
        "Copy photos from the phone to the computer (all or the N newest), "
        "then sort them on the computer",
    "Sortuj prosto z telefonu": "Sort straight from the phone",
    "Przeglądaj zdjęcia z telefonu w PhotoSort. Na komputer trafią tylko te, które "
    "przeciągniesz do folderu — od razu do właściwego folderu.":
        "Browse the phone’s photos in PhotoSort. Only the ones you drag to a folder are "
        "copied to the computer — straight into the right folder.",
    "<b>Sortuj prosto z telefonu</b> — przeglądasz zdjęcia z telefonu, a na komputer "
    "kopiowane są tylko te, które przeciągniesz do folderu. Pozostałe nie trafiają na dysk.":
        "<b>Sort straight from the phone</b> — you browse the phone’s photos, and only the ones "
        "you drag to a folder are copied to the computer. The rest never touch the disk.",
    "Obsługa urządzeń przenośnych jest niedostępna w tym systemie. "
    "Skopiuj zdjęcia do folderu i wybierz „Folder na komputerze”.":
        "Portable device support is not available on this system. "
        "Copy the photos to a folder and choose “Folder on this computer”.",
    "Wyszukiwanie urządzeń…": "Looking for devices…",
    "Nie udało się odczytać listy urządzeń: {error}": "Could not read the list of devices: {error}",
    "Wybierz urządzenie z listy.": "Choose a device from the list.",
    "Nie znaleziono telefonu ani aparatu. Sprawdź kabel, odblokuj telefon i "
    "potwierdź dostęp na jego ekranie, a następnie kliknij „Odśwież”.":
        "No phone or camera found. Check the cable, unlock the phone and "
        "allow access on its screen, then click “Refresh”.",
    "Brak dostępu do urządzenia: {error}": "Cannot access the device: {error}",
    "Urządzenie nie udostępnia plików. Odblokuj telefon i zezwól na dostęp "
    "(iPhone: „Ufaj temu komputerowi”; Android: „Przesyłanie plików”), "
    "potem „Odśwież”.":
        "The device is not sharing its files. Unlock the phone and allow access "
        "(iPhone: “Trust This Computer”; Android: “File transfer”), "
        "then click “Refresh”.",
    "Zaznaczono foldery, w których telefony zwykle przechowują zdjęcia "
    "(DCIM, Pictures…).":
        "Folders where phones usually keep photos are selected "
        "(DCIM, Pictures…).",
    "Import": "Import",
    "Importowanie…": "Importing…",
    "Przygotowywanie listy plików…": "Preparing the file list…",
    "Przerwij": "Stop",
    "Gotowe": "Done",
    "Przerywanie…": "Stopping…",
    "Wyszukiwanie zdjęć i filmów na urządzeniu… znaleziono {count}":
        "Looking for photos and videos on the device… found {count}",
    "Wyszukiwanie zdjęć i filmów… znaleziono {count}": "Looking for photos and videos… found {count}",
    "Tryb próbny: kopiowanie {copied} z {limit} najnowszych nowych plików "
    "(przejrzano {done} z {total})":
        "Trial mode: copying {copied} of the {limit} newest new files "
        "(checked {done} of {total})",
    "Kopiowanie {done} z {total}": "Copying {done} of {total}",
    "Skopiowano: <b>{copied}</b>   ·   Pominięte duplikaty: <b>{duplicates}</b>"
    "   ·   Błędy: <b>{errors}</b>":
        "Copied: <b>{copied}</b>   ·   Duplicates skipped: <b>{duplicates}</b>"
        "   ·   Errors: <b>{errors}</b>",
    "Import zatrzymany": "Import stopped",
    "Nie znaleziono plików": "No files found",
    "We wskazanym miejscu nie ma obsługiwanych zdjęć ani filmów.":
        "There are no supported photos or videos in the selected location.",
    "Import zakończony": "Import complete",
    "Dodano {files} ({size}) do folderu „{folder}”.": "Added {files} ({size}) to the “{folder}” folder.",
    "nowy plik": "new file",
    "nowych plików": "new files",
    " Osiągnięto limit próbny ({limit}) — pozostałe pliki nie zostały "
    "skopiowane. Uruchom import ponownie, aby dodać kolejne.":
        " Trial limit reached ({limit}) — the remaining files were not "
        "copied. Run the import again to add more.",
}
