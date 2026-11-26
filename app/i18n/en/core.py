"""English translations (Polish text -> English text)."""

MESSAGES: dict[str, str] = {
    # plural forms used with count_pl
    "plik": "file",
    "plików": "files",
    "pliku": "file",
    "kopię": "copy",
    "kopii": "copies",
    "plik był": "file was",
    "plików było": "files were",

    # app/core/library_controller.py
    "Ten plik nie jest już dostępny w bibliotece.": "This file is no longer available in the library.",
    "Przeniesiono {files} do „{folder}”": "Moved {files} to “{folder}”",
    "Nie udało się przenieść niektórych plików. Pliki źródłowe pozostały na swoim miejscu.":
        "Some files couldn't be moved. The source files were left where they were.",
    "Poczekaj, aż skończy się kopiowanie z telefonu": "Wait until copying from the phone has finished",
    "Cofnięto przeniesienie ({files})": "Move undone ({files})",
    "Nie udało się cofnąć wszystkich plików:": "Not all files could be restored:",
    "Cofnij skopiowanie {files} z telefonu do „{folder}” (Ctrl+Z) — zdjęcia zostają na telefonie":
        "Undo copying {files} from the phone to “{folder}” (Ctrl+Z) — the photos stay on the phone",
    "Cofnij przeniesienie {files} do „{folder}” (Ctrl+Z)": "Undo moving {files} to “{folder}” (Ctrl+Z)",
    "Brak operacji do cofnięcia": "Nothing to undo",
    "Telefon został odłączony albo zablokowany. Zdjęcia, które zdążyłeś przeciągnąć do folderów, "
    "są już na komputerze. Podłącz i odblokuj telefon, a potem otwórz go ponownie: "
    "Importuj zdjęcia i filmy → Telefon lub aparat.":
        "The phone was disconnected or locked. The photos you already dragged into folders are safe on "
        "the computer. Connect and unlock the phone, then open it again: "
        "Import photos and videos → Phone or camera.",
    "Folder „{folder}” nie istnieje.": "The folder “{folder}” doesn't exist.",
    "Nie udało się skopiować pliku z telefonu. Plik pozostał na liście telefonu.":
        "Couldn't copy the file from the phone. The file is still in the phone list.",
    "Skopiowano z telefonu {files} do „{folder}”": "Copied {files} from the phone to “{folder}”",
    "{files} już w bibliotece — pominięto": "{files} already in the library — skipped",
    "{name}: plik został zmieniony — nie usunięto": "{name}: the file has been changed — not deleted",
    "Cofnięto: usunięto z komputera {copies} — zdjęcia są nadal na telefonie":
        "Undone: removed {copies} from the computer — the photos are still on the phone",
    "Nie wszystko udało się cofnąć:": "Not everything could be undone:",
    "Zakładki działają dla zdjęć w bibliotece — najpierw przeciągnij zdjęcie do folderu":
        "Bookmarks work for photos in the library — drag the photo into a folder first",
    "Usunięto zakładkę": "Bookmark removed",
    "Dodano zakładkę — znajdziesz ją w panelu po prawej": "Bookmark added — you'll find it in the panel on the right",

    # app/core/library_manager.py
    "Lokalizacja nie istnieje: {path}": "Location doesn't exist: {path}",
    "Folder biblioteki nie istnieje:\n{path}": "The library folder doesn't exist:\n{path}",
    "Wybrany folder nie jest biblioteką PhotoSort.": "The selected folder is not a PhotoSort library.",
    "Folder „{folder}” już istnieje.": "The folder “{folder}” already exists.",
    "Folderu „Do posortowania” nie można zmienić.": "The “To sort” folder can't be renamed.",
    "Nie udało się zmienić nazwy folderu:\n{error}": "Couldn't rename the folder:\n{error}",
    "Folderu „Do posortowania” nie można usunąć.": "The “To sort” folder can't be deleted.",
    "Folder nie istnieje.": "The folder doesn't exist.",
    "Można usunąć tylko pusty folder. Najpierw przenieś z niego zdjęcia i filmy.":
        "Only an empty folder can be deleted. Move its photos and videos out first.",
    "Nie udało się usunąć folderu:\n{error}": "Couldn't delete the folder:\n{error}",

    # app/core/media_manager.py
    "plik nie istnieje na dysku (mógł zostać usunięty poza programem)":
        "the file doesn't exist on disk (it may have been deleted outside the app)",
    "nie udało się nadać unikalnej nazwy": "couldn't assign a unique name",
    "weryfikacja kopii nie powiodła się": "copy verification failed",
    "brak miejsca na dysku": "not enough disk space",
    "plik jest używany przez inny program lub brak uprawnień":
        "the file is in use by another program or access is denied",

    # app/core/import_manager.py
    "Import przerwany przez użytkownika.": "Import cancelled by the user.",
    "nieobsługiwany format": "unsupported format",
    "Brak miejsca na dysku — import został zatrzymany. Zwolnij miejsce i uruchom import ponownie.":
        "Not enough disk space — the import was stopped. Free up some space and run the import again.",
    "rozmiar kopii nie zgadza się z oryginałem": "the copy's size doesn't match the original",
    "Brak miejsca na dysku — import został zatrzymany.": "Not enough disk space — the import was stopped.",
    "nie udało się nadać unikalnej nazwy pliku": "couldn't assign a unique file name",
    "brak dostępu do pliku (może być używany przez inny program)":
        "can't access the file (it may be in use by another program)",
    "plik nie istnieje lub urządzenie zostało odłączone": "the file doesn't exist or the device was disconnected",

    # app/core/workers.py
    "Nieoczekiwany błąd importu: {error}": "Unexpected import error: {error}",

    # app/utils/paths.py
    "Nazwa nie może być pusta.": "The name can't be empty.",
    'Nazwa nie może zawierać znaków: < > : " / \\ | ? *': 'The name can\'t contain these characters: < > : " / \\ | ? *',
    "Nazwa nie może kończyć się kropką.": "The name can't end with a period.",
    "Nazwa nie może zaczynać się od kropki.": "The name can't start with a period.",
    "Ta nazwa jest zarezerwowana przez system Windows.": "This name is reserved by Windows.",
    "Nazwa jest zbyt długa.": "The name is too long.",
    "Nazwa zawiera niedozwolone znaki.": "The name contains invalid characters.",
}
