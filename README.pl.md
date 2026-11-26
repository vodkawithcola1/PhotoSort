<p align="center"><img src="docs/logo.png" alt="PhotoSort" width="128" height="128"></p>

# PhotoSort

<a href="README.md">English</a> · Polski

Desktopowa aplikacja na Windows 10/11 do **ręcznego** porządkowania dużych kolekcji rodzinnych zdjęć i filmów
metodą **przeciągnij i upuść**. Interfejs po polsku i po angielsku (Ustawienia → Język). Bez AI, bez chmury, bez internetu — wszystko zostaje na Twoim komputerze.

> Otwierasz program → widzisz zdjęcie lub film → przeciągasz go na folder po prawej → plik zostaje
> fizycznie przeniesiony na dysku → pojawia się następny. Po zamknięciu programu nic nie ginie —
> przy następnym uruchomieniu wracasz dokładnie do tego samego miejsca.

---

## Szybki start

### Wersja .exe (dla użytkownika)

1. Zbuduj program raz (patrz „Budowanie .exe”) albo otrzymaj gotowy folder `PhotoSort`.
2. Uruchom `PhotoSort\PhotoSort.exe` (można zrobić skrót na Pulpicie).
3. **Utwórz nową bibliotekę** → wpisz np. „Zdjęcia mamy” → powstaje folder na Pulpicie.
4. **Importuj zdjęcia i filmy** → telefon / folder / pendrive. Pliki są **kopiowane** do „Do posortowania”.
5. Przeciągaj zdjęcia na foldery po prawej. **Ctrl+Z** cofa ostatnie przeniesienie.

### Uruchomienie ze źródeł (dla programisty)

Wymagany Python 3.12 lub nowszy (testowane na 3.13).

```bat
cd PhotoOrganizer
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

albo po prostu dwuklik na `run.bat` (za pierwszym razem zainstaluje biblioteki).

### Budowanie .exe

```bat
build.bat
```

Skrypt tworzy środowisko `.venv`, instaluje zależności, generuje ikonę i uruchamia PyInstaller
(`PhotoSort.spec`). Wynik: **`dist\PhotoSort\PhotoSort.exe`** (folder ok. 250 MB — zawiera Qt, FFmpeg
i bibliotekę HEIC, nic nie trzeba doinstalowywać). Na koniec skrypt uruchamia autotest zbudowanej
wersji (`PhotoSort.exe --selftest wynik.txt`), który sprawdza JPEG, HEIC, wideo, miniatury, metadane,
geolokalizację, przenoszenie/cofanie i odtwarzacz.

Ręcznie:

```bat
pip install -r requirements-dev.txt
python tools\make_icon.py
pyinstaller PhotoSort.spec --noconfirm
```

Cały folder `dist\PhotoSort` można skopiować na inny komputer z Windows 10/11 (64-bit).

---

## Co potrafi

| Obszar | Funkcje |
|---|---|
| **Biblioteki** | ekran powitalny; nowa biblioteka (domyślnie na Pulpicie, także przekierowanym do OneDrive); otwieranie istniejącej i ostatniej; nigdy nie nadpisuje istniejącego folderu — proponuje otwarcie lub inną nazwę |
| **Import** | iPhone / Android / Windows Phone / aparat przez USB (MTP/PTP), folder, pendrive, karta SD, wybrane pliki, przeciągnięcie plików z Eksploratora do okna; pasek postępu, liczniki, lista błędów, przerwanie; **wykrywanie duplikatów po zawartości (SHA-256)**; **tryb próbny „Importuj tylko N najnowszych plików”** (pliki zaimportowane wcześniej nie liczą się do limitu, więc kolejny import bierze następne); ponowny import z tego samego telefonu pomija już skopiowane pliki bez kopiowania |
| **Formaty** | zdjęcia: JPG, PNG, HEIC/HEIF, WEBP, TIFF, BMP, GIF; filmy: MP4, MOV, AVI, MKV, M4V, WMV, 3GP, MTS, WEBM i inne obsługiwane przez FFmpeg |
| **Podgląd** | duże zdjęcie dopasowane do okna; powiększanie (kółko myszy, +/−), przesuwanie, 100% (dwuklik), obrót podglądu (R), pełny ekran (F11), poprzedni/następny (←/→), orientacja z EXIF |
| **Filmy** | wbudowany odtwarzacz: odtwarzanie/pauza (spacja lub klik), pasek przewijania, czas bieżący i całkowity, głośność, wyciszenie (M), pełny ekran; **brak autostartu**; czytelny komunikat zamiast zawieszenia przy nieobsługiwanym kodeku (z przyciskiem „Otwórz w odtwarzaczu Windows”) |
| **Metadane** | nazwa, data i godzina wykonania (EXIF / metadane filmu / nazwa pliku — źródło jest podane), data utworzenia i modyfikacji pliku (Windows), data importu (PhotoSort), GPS, **miasto i kraj offline**, „Pokaż na mapie” (OpenStreetMap), model telefonu/aparatu, rozdzielczość, rozmiar, format, długość i kl/s filmu; „Brak danych”, gdy informacji brak |
| **Kolejka** | poziomy pasek miniatur, rozwijany do dużej siatki; ikonka odtwarzania i długość na filmach; wyraźna ramka bieżącego pliku; zaznaczanie wielu (Ctrl/Shift); przeciąganie z kolejki; wirtualizacja i cache miniatur (sprawdzone na 50 000 plików) |
| **Foldery** | panel z ikoną, nazwą i licznikiem; tworzenie, zmiana nazwy, wyszukiwanie, usuwanie **tylko pustych**; **wejście do folderu i przeglądanie go dokładnie jak kolejki**; nawigacja „Zdjęcia mamy › Wakacje Sarbinowo”; przenoszenie między folderami; widok „Wszystkie multimedia” |
| **Przeciąganie** | główne zdjęcie/film, miniatury, wiele plików naraz (licznik na podglądzie przeciągania), między folderami; podświetlenie folderu docelowego; upuszczenie na „Nowy folder” tworzy folder i przenosi |
| **Cofanie** | przycisk „Cofnij”, Ctrl+Z oraz „Cofnij” w powiadomieniu; działa także po ponownym uruchomieniu i po zmianie nazwy folderu |
| **Postęp** | automatyczny zapis po każdej operacji: folder, bieżący plik, pozycja (osobno dla każdego folderu), sortowanie, filtry, stan siatki, przewinięcie, ostatni folder, historia przeniesień; **zakładki** (Ctrl+D) w panelu po prawej |
| **Filtry** | nazwa pliku, zdjęcia/filmy, rok, miesiąc, zakres dat, rozmiar, lokalizacja (z GPS / bez / miejscowość), status posortowane/nieposortowane i folder (w widoku „Wszystkie”), „Ten sam dzień”; sortowanie wg daty wykonania, nazwy, daty importu, rozmiaru — rosnąco/malejąco |
| **Statystyki** | wskaźnik postępu w pasku górnym (klik → szczegóły: wszystkie, zdjęcia, filmy, posortowane, pozostałe, %, liczba folderów) |
| **Wygląd** | jasny i ciemny motyw, polski interfejs, zaokrąglone panele, subtelne animacje |

Celowo **nie ma** trybu szybkiego sortowania cyframi 1–9 ani przypisywania folderów do klawiszy.

---

## Bezpieczeństwo plików

* **Oryginały są tylko czytane.** Import otwiera pliki źródłowe wyłącznie do odczytu i tworzy kopie.
  Na telefonie używane jest tylko kopiowanie (`CopyHere`) — nigdy przenoszenie ani usuwanie.
  Program nie ingeruje w Apple Photos/Google Photos, nie tworzy albumów na iPhonie, nie wymaga iCloud.
* **Kopia jest weryfikowana**: najpierw zapis do pliku tymczasowego `*.photosort-partial`, `fsync`,
  porównanie rozmiaru, dopiero potem nadanie docelowej nazwy. Zachowane są daty modyfikacji i utworzenia.
* **Nic nie jest nadpisywane** — przy kolizji nazw powstaje `IMG_001 (1).JPG`.
* **Przenoszenie z dziennikiem**: przed operacją na dysku zapisywany jest wpis „w toku”; po awarii
  program przy następnym otwarciu sprawdza stan dysku i domyka lub wycofuje wpis. Przeniesienie w obrębie
  dysku jest atomowe (`rename`); gdy się nie powiedzie, plik źródłowy zostaje na miejscu.
* **Brak miejsca na dysku**: przed każdym plikiem sprawdzane jest wolne miejsce (z zapasem 200 MB);
  import zatrzymuje się z czytelnym komunikatem, niedokończone kopie są usuwane (tylko nasze kopie).
* **Przerwany import / zamknięcie programu** — pozostałości tymczasowe są sprzątane przy otwarciu.
* Obrót w podglądzie **nie zmienia pliku**. Program nigdy nie modyfikuje zawartości ani jakości mediów.
* Pliki dodane lub usunięte ręcznie w Eksploratorze są wykrywane przy otwarciu biblioteki
  (i przyciskiem „Odśwież” w ustawieniach).

## Struktura biblioteki na dysku

```
Pulpit/
└── Zdjęcia mamy/
    ├── Do posortowania/          ← tu trafia import
    ├── Święta 2026/
    ├── Wakacje Sarbinowo/
    └── .photosort/               (ukryty)
        ├── library.db            ← SQLite: indeks, historia, zakładki, postęp
        ├── thumbnails/           ← miniatury JPEG
        ├── staging/              ← kopie tymczasowe podczas importu z telefonu
        └── settings.json
```

Foldery to zwykłe foldery Windows — można je otwierać w Eksploratorze, a nawet usunąć program;
zdjęcia zostaną tam, gdzie są.

## Sortowanie prosto z telefonu (bez kopiowania wszystkiego)

Jeśli nie chcesz, żeby na komputer trafiły tysiące zdjęć przed posortowaniem:
**Importuj zdjęcia i filmy → Telefon lub aparat (USB) → „Sortuj prosto z telefonu”.**

* W panelu folderów pojawia się pozycja **„Telefon: …”** — przeglądasz zdjęcia z telefonu jak zwykłą kolejkę
  (domyślnie tylko te, których jeszcze nie ma w bibliotece, od najnowszych).
* Miniatury pochodzą z telefonu (ten sam mechanizm co w Eksploratorze) — nic nie jest kopiowane.
* Do dużego podglądu kopiowany jest tylko oglądany plik (i 2 kolejne zdjęcia z wyprzedzeniem) do tymczasowej
  pamięci podręcznej `.photosort\staging\device-cache` — maks. 40 plików, czyszczona po zakończeniu.
* **Przeciągnięcie na folder kopiuje zdjęcie z telefonu prosto do tego folderu** (z pominięciem
  „Do posortowania”). Zdjęć, których nie przeciągniesz, nie ma na komputerze.
* **Ctrl+Z / „Cofnij”** usuwa świeżo zrobioną kopię z komputera — zdjęcie wraca na listę telefonu
  (oryginał na telefonie jest zawsze nietknięty).
* Zakończenie: prawy przycisk na „Telefon: …” → „Zakończ przeglądanie telefonu” (albo zamknięcie programu).

## Import z iPhone'a / Androida

iPhone i większość telefonów **nie są** widoczne jako dysk z literą — Windows pokazuje je jako
„urządzenia przenośne”. PhotoSort korzysta z mechanizmu powłoki Windows, aby z nich kopiować.

* **iPhone**: podłącz kablem, **odblokuj**, stuknij „Ufaj temu komputerowi”. Jeśli iPhone się nie
  pojawia, zainstaluj „Urządzenia Apple” (Apple Devices) lub iTunes z Microsoft Store (sterownik).
  Aby skopiować oryginalne HEIC/MOV: Ustawienia → Zdjęcia → „Przenieś na Mac lub PC” → „Zachowaj oryginały”.
* **Android**: po podłączeniu wybierz na telefonie „Przesyłanie plików (MTP)”.
* **Gdy bezpośredni import nie działa**: skopiuj zdjęcia aplikacją „Zdjęcia” systemu Windows lub
  Eksploratorem, a potem w PhotoSort wybierz „Folder na komputerze”.

Te instrukcje są też pokazywane w programie w oknie importu z urządzenia.

## Technologie

* **Python 3.12+**, **PySide6 (Qt 6)** — interfejs; Qt Multimedia z backendem FFmpeg — odtwarzanie filmów
* **Pillow + pillow-heif** — zdjęcia, HEIC/HEIF, EXIF, miniatury
* **PyAV (FFmpeg)** — metadane i klatki filmów (data, GPS z MOV/MP4, model, FPS, długość, obrót)
* **SQLite (WAL)** — stan biblioteki, dziennik przeniesień, zakładki, postęp
* **pywin32** — import z urządzeń przenośnych (MTP/PTP) przez powłokę Windows
* **GeoNames cities1000** (CC BY 4.0, wbudowane, 2 MB) — miasto i kraj offline
* **ExifTool — opcjonalnie**: jeśli `exiftool.exe` jest w `PATH` albo w folderze `tools\` obok programu
  (przy budowaniu: `tools\exiftool.exe` w źródłach), jest używany do uzupełniania brakujących metadanych.
  Nie jest wymagany — wbudowany odczyt obsługuje JPEG/HEIC/MOV/MP4. Zastosowano PyAV zamiast
  obowiązkowego ExifTool, żeby program działał bez instalowania zewnętrznych narzędzi.
* **PyInstaller** — budowa `.exe`

Operacje długotrwałe (import, skan dysku, metadane, miniatury, wczytywanie dużych zdjęć) działają
w wątkach tła — interfejs się nie blokuje.

## Struktura projektu

```
main.py                      punkt startowy (także --selftest)
app/
  constants.py               rozszerzenia, nazwy folderów
  core/
    library_manager.py       tworzenie/otwieranie/skan biblioteki, foldery, odzyskiwanie po awarii
    media_manager.py         zapytania i filtry, bezpieczne przenoszenie, cofanie, zakładki
    import_manager.py        import z kopiowaniem, weryfikacją i duplikatami
    session_manager.py       zapis postępu (SQLite) i ustawienia programu
    library_controller.py    kontroler otwartej biblioteki (kolejka, bieżący plik, autozapis)
    workers.py               wątki tła: skan, metadane, import
  services/
    metadata_service.py      EXIF / metadane wideo / ExifTool / data z nazwy pliku
    thumbnail_service.py     miniatury (cache na dysku i w pamięci), wczytywanie podglądu
    geocode_service.py       miasto i kraj offline
    device_service.py        telefony i aparaty (MTP/PTP)
  database/database.py       schemat SQLite
  ui/                        ekran powitalny, okno główne, podgląd, kolejka, foldery, metadane,
                             filtry, import, ustawienia, motywy i ikony
  resources/                 places.tsv.gz (GeoNames), photosort.ico
tests/                       testy automatyczne (pytest)
tools/                       build_places.py, make_icon.py
PhotoSort.spec, build.bat, run.bat
```

## Testy

```bat
pip install -r requirements-dev.txt
set QT_QPA_PLATFORM=offscreen
pytest -q
```

Testy obejmują m.in.: tworzenie biblioteki i brak nadpisywania, import (oryginały bit w bit
nietknięte, zachowane daty), duplikaty, kolizje nazw, brak miejsca, przerwanie importu,
przenoszenie i cofanie (także wielu plików i po zmianie nazwy folderu), nieudane przeniesienie
(źródło zostaje), odzyskiwanie po awarii w trakcie przenoszenia, wykrywanie zmian z Eksploratora,
filtry i statystyki, zapis postępu i zakładek po ponownym otwarciu, pełny przepływ w interfejsie
(upuszczenie na folder → plik przeniesiony na dysku → następny plik → cofnij → wejście do folderu →
przeniesienie między folderami → zamknięcie i ponowne otwarcie w tym samym miejscu), odtwarzanie
filmu (brak autostartu, odtwarzanie, pauza), komunikat dla uszkodzonego filmu, import „z urządzenia”
przez powłokę Windows oraz wydajność kolejki z 50 000 pozycji.

## Znane ograniczenia

* Import bezpośrednio z telefonu (MTP) został przetestowany na mechanizmie powłoki Windows
  z podstawionym folderem — **nie na fizycznym iPhonie ani Androidzie**. Zależy też od sterowników
  urządzenia w Windows. W razie problemów działa obejście opisane wyżej (import z folderu).
* Odtwarzanie filmów zależy od dekoderów FFmpeg dołączonych do Qt; bardzo nietypowe kodeki mogą być
  nieobsługiwane — program pokaże wtedy komunikat i pozwoli otworzyć film w odtwarzaczu Windows.
* Geolokalizacja offline wskazuje najbliższą miejscowość powyżej 1000 mieszkańców (dla mniejszych
  wsi pokazuje „okolice: …”).
* Przeciąganie odbywa się wewnątrz okna PhotoSort (celowo nie można przeciągnąć pliku do Eksploratora,
  aby nie rozsynchronizować biblioteki).

Dziennik błędów: `%APPDATA%\PhotoSort\photosort.log`.
