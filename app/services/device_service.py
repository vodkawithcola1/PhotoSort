"""Import z telefonów i aparatów podłączonych przez USB (MTP/PTP — „urządzenia przenośne”).

iPhone, telefony z Androidem, Windows Phone i wiele aparatów NIE są widoczne jako
zwykły dysk z literą. Windows udostępnia je w „Ten komputer” jako urządzenia
przenośne (WPD). Korzystamy z interfejsu powłoki Windows (Shell.Application),
który potrafi z nich KOPIOWAĆ pliki.

Bezpieczeństwo: używamy wyłącznie operacji odczytu/kopiowania (CopyHere do
lokalnego folderu tymczasowego). Nigdy nie wywołujemy MoveHere ani usuwania
na urządzeniu.
"""
from __future__ import annotations

import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.constants import DISK_SPACE_MARGIN, media_kind
from app.i18n import tr

SSF_DRIVES = 17  # „Ten komputer”
# FOF_SILENT | FOF_NOCONFIRMATION | FOF_NOCONFIRMMKDIR | FOF_NOERRORUI
COPY_FLAGS = 4 | 16 | 512 | 1024

MEDIA_FOLDER_HINTS = ("dcim", "camera", "pictures", "picture", "photos", "movies", "videos",
                      "whatsapp", "screenshots", "zdjęcia", "obrazy", "aparat")  # i18n: ignore


def available() -> bool:
    try:
        import win32com.client  # noqa: F401
        import pythoncom  # noqa: F401
        return True
    except Exception:
        return False


@dataclass
class DeviceFile:
    item: object
    rel: str
    name: str
    size: int
    modified: str


class _Com:
    def __enter__(self):
        import pythoncom
        pythoncom.CoInitialize()
        return self

    def __exit__(self, *exc):
        import pythoncom
        pythoncom.CoUninitialize()


def _shell():
    import win32com.client
    return win32com.client.Dispatch("Shell.Application")


def _items(folder):
    items = folder.Items()
    for i in range(items.Count):
        yield items.Item(i)


def _prop(item, name, default=None):
    try:
        v = item.ExtendedProperty(name)
        return default if v is None else v
    except Exception:
        return default


def list_devices() -> list[str]:
    """Nazwy urządzeń przenośnych widocznych w „Ten komputer” (np. „Apple iPhone”)."""
    if not available():
        return []
    names = []
    with _Com():
        pc = _shell().NameSpace(SSF_DRIVES)
        for item in _items(pc):
            try:
                if item.IsFolder and not item.IsFileSystem:
                    path = str(item.Path)
                    # urządzenia WPD mają ścieżkę w przestrzeni nazw powłoki (::{...}\\?\usb#...)
                    if "usb" in path.lower() or "wpdbusenum" in path.lower() or "\\\\?\\" in path:
                        names.append(str(item.Name))
            except Exception:
                continue
    return names


def _find_device(shell, name: str):
    pc = shell.NameSpace(SSF_DRIVES)
    for item in _items(pc):
        if str(item.Name) == name and item.IsFolder:
            return item.GetFolder
    return None


def _navigate(shell, device: str, rel: str):
    folder = _find_device(shell, device)
    if folder is None:
        return None
    for part in [p for p in rel.split("/") if p]:
        nxt = None
        for item in _items(folder):
            if item.IsFolder and str(item.Name) == part:
                nxt = item.GetFolder
                break
        if nxt is None:
            return None
        folder = nxt
    return folder


def list_device_folders(device: str) -> list[tuple[str, bool]]:
    """Foldery urządzenia do dwóch poziomów w głąb: [(ścieżka, czy_zalecany)].

    iPhone: 'Internal Storage/DCIM'; Android: 'Pamięć wewnętrzna/DCIM', '.../Pictures'.
    """
    result: list[tuple[str, bool]] = []
    if not available():
        return result
    with _Com():
        shell = _shell()
        root = _find_device(shell, device)
        if root is None:
            return result
        for storage in _items(root):
            if not storage.IsFolder:
                continue
            sname = str(storage.Name)
            sub_found = False
            for sub in _items(storage.GetFolder):
                if sub.IsFolder:
                    sub_found = True
                    n = str(sub.Name)
                    rec = any(h in n.lower() for h in MEDIA_FOLDER_HINTS)
                    result.append((f"{sname}/{n}", rec))
            if not sub_found:
                result.append((sname, True))
    return result


def _walk(folder, rel: str, out: list[DeviceFile], cancelled: Callable[[], bool],
          found_cb: Callable[[int], None], depth: int = 0) -> None:
    if depth > 12 or cancelled():
        return
    for item in _items(folder):
        if cancelled():
            return
        try:
            name = str(_prop(item, "System.FileName") or item.Name)
            if name.startswith("."):
                continue   # .thumbnails, .trashed-… — pliki systemowe, nie zdjęcia użytkownika
            if item.IsFolder:
                _walk(item.GetFolder, f"{rel}/{name}", out, cancelled, found_cb, depth + 1)
                continue
            ext = os.path.splitext(name)[1]
            if ext and not media_kind(ext):
                continue
            try:
                size = int(_prop(item, "System.Size") or item.Size or 0)
            except Exception:
                size = 0
            modified = str(_prop(item, "System.DateModified", "") or "")
            out.append(DeviceFile(item, f"{rel}/{name}", name, size, modified))
            found_cb(len(out))
        except Exception:
            continue


_NUM = re.compile(r"(\d+)")


def natural_key(name: str):
    """IMG_9 < IMG_10 < IMG_100; 100APPLE < 101APPLE."""
    return [int(t) if t.isdigit() else t.lower() for t in _NUM.split(name)]


def _parse_ts(value) -> float:
    """Data z właściwości powłoki (np. '2026-11-03 14:22:10+00:00') -> timestamp; 0 gdy brak."""
    if not value:
        return 0.0
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(value).strip()).timestamp()
    except (ValueError, OSError, OverflowError):
        return 0.0


def _is_hidden_device_name(name: str) -> bool:
    # .thumbnails, .trashed-…, .pending-… (Android), .Trash itp. — nie są zdjęciami użytkownika
    return name.startswith(".")


SHCONTF_FOLDERS = 0x20
SHCONTF_NONFOLDERS = 0x40


class _ItemList:
    """Lista elementów folderu: FolderItems powłoki (bez kopiowania nazw) albo lista Pythona."""

    def __init__(self, items=None, py: list | None = None):
        self.items = items
        self.py = py

    def __len__(self) -> int:
        return len(self.py) if self.py is not None else int(self.items.Count)

    def __getitem__(self, i: int):
        return self.py[i] if self.py is not None else self.items.Item(i)


def _split_folder(folder, want_subs: bool = True) -> tuple[_ItemList, _ItemList]:
    """(podfoldery, pliki) folderu. Filtr powłoki pozwala NIE odpytywać telefonu o każdy plik.

    want_subs=False: folder na pewno nie ma podfolderów (np. 202611_a, 105APPLE na iPhonie) —
    oszczędza drugie wyliczanie zawartości (na iPhonie ~0,1 s na każdy plik)."""
    try:
        if want_subs:
            subs = folder.Items()
            subs.Filter(SHCONTF_FOLDERS, "*")
            subs = _ItemList(subs)
        else:
            subs = _ItemList(py=[])
        files = folder.Items()
        files.Filter(SHCONTF_NONFOLDERS, "*")
        return subs, _ItemList(files)
    except Exception:
        # zapasowo: pełna lista z podziałem (wolniejsze — każdy element odpytywany osobno)
        s, f = [], []
        for item in _items(folder):
            try:
                (s if item.IsFolder else f).append(item)
            except Exception:
                continue
        return _ItemList(py=s), _ItemList(py=f)


_INF = float("inf")

# iPhone: „Internal Storage/202611_a”, „DCIM/105APPLE” — foldery-liście bez podfolderów
_LEAF_RE = re.compile(r"^(\d{6}_[a-z]+|\d{3}APPLE)$", re.IGNORECASE)
# nazwa zaczynająca się od roku i miesiąca: 202611_a, 2026-11, 2026_11 …
_YM_RE = re.compile(r"^((?:19|20)\d\d)[-_ ]?(0[1-9]|1[0-2])(?!\d)")


def _folder_date_bound(name: str) -> float | None:
    """Górne oszacowanie dat plików w folderze nazwanym rokiem i miesiącem (202611_a → do
    1 grudnia 2026, z zapasem doby na strefy czasowe). None — nazwa nie zawiera daty."""
    m = _YM_RE.match(name)
    if not m:
        return None
    from datetime import datetime
    y, mo = int(m.group(1)), int(m.group(2))
    y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
    try:
        return datetime(y, mo, 1).timestamp() + 86400
    except (ValueError, OverflowError, OSError):
        return None


def iter_newest(shell, device: str, folders: list[str], cancelled: Callable[[], bool],
                examined_cb: Callable[[int], None] | None = None,
                status_cb: Callable[[str], None] | None = None):
    """Leniwie zwraca pliki multimedialne od NAJNOWSZYCH — otwiera tylko potrzebne foldery.

    Jedna kolejka priorytetowa zawiera:
      * pliki z już otwartych folderów — z RZECZYWISTĄ datą z telefonu,
      * NIEOTWARTE foldery — z datą modyfikacji folderu jako górnym oszacowaniem dat plików
        w środku (folder zmienia datę, gdy coś do niego dochodzi).
    Folder jest otwierany dopiero wtedy, gdy może zawierać coś nowszego niż najlepszy znany
    plik. Gdy telefon nie podaje dat folderów, kolejność ustala numeracja nazw
    (105APPLE przed 104APPLE): otwierany jest najpierw „najwyższy”, kolejne dopiero, gdy
    zabraknie plików. Pliki w folderze czytamy od końca listy (telefon podaje je w kolejności
    dodawania, więc koniec = najnowsze) — bez odczytywania nazw wszystkich plików.
    Ukryte foldery i pliki (.thumbnails, .trashed-…) są pomijane.
    """
    import heapq
    import logging
    log = logging.getLogger("photosort.device")
    counters = {"files": 0, "folders": 0}
    seq = [0]

    def report():
        if examined_cb:
            examined_cb(counters["files"])

    def status(text: str) -> None:
        log.info(text)
        if status_cb:
            status_cb(text)

    streams: list[tuple[str, _ItemList]] = []
    heap: list = []   # (-klucz, seq, rodzaj, dane)

    def push(key: float, kind: str, data) -> None:
        seq[0] += 1
        heapq.heappush(heap, (-key, seq[0], kind, data))

    def read_dates(rel: str, files: _ItemList) -> list:
        """Pliki multimedialne folderu posortowane od NAJNOWSZEGO wg daty z telefonu.

        Nie zakładamy kolejności listy — iPhone nie podaje plików chronologicznie (zdjęcia,
        zrzuty ekranu i pliki zapisane z aplikacji są przemieszane). Daty są już w danych
        wyliczonych przez powłokę, więc ich odczyt jest szybki w porównaniu z otwarciem folderu."""
        t0 = time.time()
        out = []
        n = len(files)
        for pos in range(n):
            if cancelled():
                break
            if pos and pos % 50 == 0:
                status(tr("Czytam daty plików: {folder}  ({done} z {total})", folder=rel, done=pos, total=n))
            try:
                item = files[pos]
                fname = str(_prop(item, "System.FileName") or item.Name)
                ext = os.path.splitext(fname)[1]
                if not ext or not media_kind(ext) or _is_hidden_device_name(fname):
                    continue   # np. .AAE (edycje iPhone'a) albo pliki nie-multimedialne
                modified = str(_prop(item, "System.DateModified", "") or "")
                out.append((_parse_ts(modified), pos, item, fname, modified))
            except Exception as exc:
                log.debug("element %s[%d]: %s", rel, pos, exc)
        out.sort(key=lambda t: (t[0], t[1]), reverse=True)
        if out:
            log.info("daty w %s: %d plików w %.1fs, najnowszy %s (%s), najstarszy %s (%s)", rel, len(out),
                     time.time() - t0, out[0][3], out[0][4], out[-1][3], out[-1][4])
        return out

    def head(si: int, k: int):
        """k-ty od najnowszego plik strumienia si (albo None)."""
        files = streams[si][1]
        if k >= len(files):
            return None
        counters["files"] += 1
        if counters["files"] % 3 == 0:
            report()
        return files[k]

    def open_folder(folder, rel: str, depth: int, leaf: bool = False) -> None:
        t0 = time.time()
        counters["folders"] += 1
        status(tr("Otwieram folder telefonu: {folder}  (otwarte foldery: {count})", folder=rel,
                   count=counters["folders"]))
        subs, files = _split_folder(folder, want_subs=not leaf)
        n = len(files)
        log.info("folder %s: %d plików, %d podfolderów (%.1fs)", rel, n, len(subs), time.time() - t0)
        if n:
            streams.append((rel, read_dates(rel, files)))
            h = head(len(streams) - 1, 0)
            if h:
                ts, _pos, item, fname, modified = h
                push(ts, "F", (len(streams) - 1, 0, item, fname, modified))
        if depth >= 8:
            return
        # podfoldery: na razie NIE otwieramy — tylko szacujemy, jak nowe mogą być
        entries = []
        for i in range(len(subs)):
            if cancelled():
                return
            try:
                it = subs[i]
                name = str(it.Name)
                if _is_hidden_device_name(name):
                    continue
                fname = str(_prop(it, "System.FileName") or name)
                if _is_hidden_device_name(fname):
                    continue
                ts = _parse_ts(_prop(it, "System.DateModified", ""))
                entries.append((natural_key(fname), ts, (lambda it=it: it.GetFolder), f"{rel}/{fname}", fname))
            except Exception as exc:
                log.warning("podfolder w %s: %s", rel, exc)
        schedule(entries, depth + 1, top=depth == 0)

    def schedule(entries, depth: int, top: bool) -> None:
        """Wstawia NIEOTWARTE foldery do kolejki z oszacowaniem, jak nowe pliki mogą zawierać."""
        dated, numbered, named = [], [], []
        for e in entries:
            bound = _folder_date_bound(e[4])
            if bound is not None:
                dated.append((bound, e))
            elif e[4][:1].isdigit():
                numbered.append(e)
            else:
                named.append(e)
        # foldery z rokiem i miesiącem w nazwie (iPhone: 202611_a, 202611_b): otwierane dopiero,
        # gdy mogą zawierać coś nowszego niż najlepszy znany plik — reszta telefonu czeka
        for bound, (_k, _ts, opener, r, nm) in dated:
            push(bound, "D", (opener, r, depth, bool(_LEAF_RE.match(nm))))
        # foldery numerowane (iPhone: 100APPLE…): kolejność wg numeru — od razu tylko
        # najwyższy, kolejne dopiero gdy zabraknie nowszych plików
        numbered.sort(key=lambda u: u[0], reverse=True)
        for rank, (_k, _ts, opener, r, nm) in enumerate(numbered):
            push(_INF if rank == 0 else -1e12 - rank, "D", (opener, r, depth, bool(_LEAF_RE.match(nm))))
        # foldery nazwane (Camera, Screenshots…): wg daty folderu — o ile daty coś mówią
        dates = {u[1] for u in named if u[1] > 0}
        if top:
            # bezpośrednio pod wybranym folderem (DCIM/Camera, DCIM/Screenshots…) — zwykle kilka;
            # otwieramy wszystkie, żeby o kolejności decydowały prawdziwe daty ZDJĘĆ
            for _k, ts, opener, r, _nm in named:
                push(_INF, "D", (opener, r, depth, False))
        elif len(named) > 1 and len(dates) > 1:
            for _k, ts, opener, r, _nm in named:
                push(ts if ts > 0 else -1e12, "D", (opener, r, depth, False))
        else:
            named.sort(key=lambda u: u[0], reverse=True)
            for rank, (_k, ts, opener, r, _nm) in enumerate(named):
                push(_INF if rank == 0 else -1e12 - 1000 - rank, "D", (opener, r, depth, False))

    def navigator(rel: str):
        def go():
            folder = _navigate(shell, device, rel)
            if folder is None:
                raise LookupError(f"nie znaleziono folderu {rel} na {device}")
            return folder
        return go

    # wybrane foldery też otwieramy leniwie: przy iPhonie użytkownik często zaznacza wszystkie
    # 202503_a … 202611_b, a otwarcie dużego folderu trwa nawet 1–2 minuty
    selected = []
    for rel in dict.fromkeys(folders):
        name = rel.rstrip("/").rsplit("/", 1)[-1]
        selected.append((natural_key(name), 0.0, navigator(rel), rel, name))
    schedule(selected, 0, top=True)

    while heap and not cancelled():
        _neg, _s, kind, data = heapq.heappop(heap)
        if kind == "D":
            opener, rel, depth, leaf = data
            try:
                open_folder(opener(), rel, depth, leaf)
            except Exception as exc:
                log.warning("nie udało się otworzyć %s: %s", rel, exc)
            continue
        si, pos, item, fname, modified = data
        rel = streams[si][0]
        try:
            size = int(_prop(item, "System.Size") or item.Size or 0)
        except Exception:
            size = 0
        yield DeviceFile(item, f"{rel}/{fname}", fname, size, modified)
        h = head(si, pos + 1)
        if h:
            nts, _np, nitem, nf, nm = h
            push(nts, "F", (si, pos + 1, nitem, nf, nm))
    report()


def _pump() -> None:
    """Wątek COM (STA) musi obsługiwać komunikaty — inaczej asynchroniczne CopyHere powłoki
    potrafi utknąć po pierwszym pliku."""
    try:
        import pythoncom
        pythoncom.PumpWaitingMessages()
    except Exception:
        pass


def _wait_for_copy(target_dir: Path, expected: int, cancelled: Callable[[], bool],
                   progress: Callable[[int], None] | None = None) -> Path | None:
    """CopyHere działa asynchronicznie — czekamy, aż plik pojawi się i będzie kompletny."""
    start = time.time()
    last_size = -1
    stable = 0
    timeout_empty = 45.0
    while True:
        if cancelled():
            return None
        _pump()
        files = [p for p in target_dir.iterdir() if p.is_file()]
        if files:
            f = files[0]
            try:
                size = f.stat().st_size
            except OSError:
                size = -1
            if size == last_size and size > 0:
                stable += 1
                # iPhone („Automatycznie”) zamienia HEIC→JPG i HEVC→H.264 — rozmiar kopii może się
                # różnić od podanego przez telefon; mniejszy plik akceptujemy po dłuższej ciszy
                need = 3 if (expected <= 0 or size >= expected * 0.5) else 12
                if stable >= need:
                    # plik zamknięty przez kopiującego? (zmiana nazwy nie uda się, gdy jest otwarty)
                    probe = f.with_name(f.name + ".chk")
                    try:
                        os.rename(f, probe)
                        os.rename(probe, f)
                        return f
                    except OSError:
                        stable = 0
            else:
                stable = 0
                last_size = size
                start = time.time()  # trwa kopiowanie — wydłuż limit
                if progress and expected > 0 and size > 0:
                    progress(min(99, int(size * 100 / expected)))
        elif time.time() - start > timeout_empty:
            return None
        if time.time() - start > max(120.0, expected / (1024 * 1024)):
            return None
        time.sleep(0.25)


class DeviceCopyError(OSError):
    pass


_stream_unsupported = False      # ustawiane, gdy telefon nie daje strumienia, a CopyHere działa


def reset_copy_mode() -> None:
    global _stream_unsupported
    _stream_unsupported = False


_HEIF_EXT = {".heic", ".heif"}


def _fix_extension(path: Path) -> Path:
    """iPhone w trybie „Automatycznie” podaje plik IMG_1234.HEIC, a wysyła JPEG.
    Nadajemy rozszerzenie zgodne z zawartością, żeby podgląd i metadane działały."""
    if path.suffix.lower() not in _HEIF_EXT:
        return path
    try:
        with open(path, "rb") as fh:
            head = fh.read(4)
    except OSError:
        return path
    if head[:3] == b"\xff\xd8\xff":
        target = path.with_suffix(".JPG")
        try:
            os.replace(path, target)
            return target
        except OSError:
            return path
    return path


def _stream_copy(item, dest: Path, expected: int, cancelled: Callable[[], bool],
                 progress: Callable[[int], None] | None) -> Path | None:
    """Kopiuje plik z telefonu, czytając go jak strumień (IShellItem → IStream).

    Synchronicznie i bez mechanizmu kopiowania Eksploratora: wiadomo dokładnie, ile już
    przeczytano (postęp w %), a błąd telefonu (np. zablokowany ekran) daje wyjątek z opisem."""
    import pythoncom
    from win32com.shell import shell as sh
    si = sh.SHCreateItemFromParsingName(str(item.Path), None, sh.IID_IShellItem)
    stream = si.BindToHandler(None, sh.BHID_Stream, pythoncom.IID_IStream)
    if expected <= 0:
        try:
            expected = int(stream.Stat()[2])
        except Exception:
            expected = 0
    part = dest.with_name(dest.name + ".photosort-partial")
    done = 0
    last_pct = -1
    try:
        with open(part, "wb") as out:
            while True:
                if cancelled():
                    raise InterruptedError
                chunk = stream.Read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress and expected > 0:
                    pct = min(99, int(done * 100 / expected))
                    if pct != last_pct:
                        last_pct = pct
                        progress(pct)
            out.flush()
            os.fsync(out.fileno())
        if done == 0:
            raise DeviceCopyError(tr("telefon zwrócił pusty plik"))
        os.replace(part, dest)
    except InterruptedError:
        part.unlink(missing_ok=True)
        return None
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return _fix_extension(dest)


def copy_item(shell, item, name: str, expected: int, slot: Path, cancelled: Callable[[], bool],
              progress: Callable[[int], None] | None = None) -> Path | None:
    """Kopiuje JEDEN plik z urządzenia do pustego folderu `slot` (tylko odczyt z telefonu).

    Najpierw odczyt strumieniowy (szybki, z postępem), a gdy telefon/sterownik go nie obsługuje —
    CopyHere powłoki. Zwraca ścieżkę kopii; None = przerwane. Błąd → DeviceCopyError z opisem."""
    import logging
    log = logging.getLogger("photosort.device")
    slot.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or "plik"
    t0 = time.time()
    first_error = None
    global _stream_unsupported
    for attempt in (() if _stream_unsupported else (1, 2)):
        try:
            path = _stream_copy(item, slot / safe, expected, cancelled, progress)
            if path is not None:
                log.info("skopiowano %s (%d B) strumieniem w %.1fs", name, path.stat().st_size, time.time() - t0)
            return path
        except Exception as exc:
            first_error = first_error or exc
            log.warning("odczyt strumieniowy %s (próba %d): %s", name, attempt, exc)
        if cancelled():
            return None
        time.sleep(0.5)
    # zapasowo: mechanizm kopiowania Eksploratora
    for p in slot.iterdir():
        if p.is_file():
            p.unlink(missing_ok=True)
    try:
        shell.NameSpace(str(slot)).CopyHere(item, COPY_FLAGS)
        path = _wait_for_copy(slot, expected, cancelled, progress)
    except Exception as exc:
        log.warning("CopyHere %s: %s", name, exc)
        path = None
    if path is not None:
        log.info("skopiowano %s (%d B) przez CopyHere w %.1fs", name, path.stat().st_size, time.time() - t0)
        if first_error is not None and not _stream_unsupported:
            # telefon nie udostępnia pliku jako strumienia (iPhone: E_INVALIDARG) — dalej tylko CopyHere
            log.info("odczyt strumieniowy wyłączony dla tego urządzenia")
            _stream_unsupported = True
        return _fix_extension(path)
    if cancelled():
        return None
    log.error("nie udało się skopiować %s z telefonu: %s", name, first_error)
    raise DeviceCopyError(tr("{name}: nie udało się skopiować z telefonu (telefon zablokowany lub odłączony?)",
                             name=name)
                          + (f" — {_describe(first_error)}" if first_error else ""))


def _describe(exc: BaseException) -> str:
    """Krótki opis błędu COM/Windows (bez długich krotek pywin32)."""
    args = getattr(exc, "args", ())
    if len(args) >= 2 and isinstance(args[1], str):
        return args[1].strip()
    return str(exc).strip()[:200]


def _newest_key(df: DeviceFile):
    """Klucz „od najnowszych”: data modyfikacji z urządzenia, a gdy jej brak — ścieżka
    (telefony numerują foldery i pliki rosnąco: 100APPLE/IMG_0001 … 105APPLE/IMG_5321)."""
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(df.modified.strip()) if df.modified else None
        ts = dt.timestamp() if dt else 0.0
    except (ValueError, OSError, OverflowError):
        ts = 0.0
    return (ts, df.rel.lower())


def _copy_one(shell, df: DeviceFile, key: str, importer, staging: Path, slot_no: int,
              cancelled: Callable[[], bool]) -> None:
    """Kopiuje jeden plik z urządzenia do stagingu i importuje go (wyjątki przekazuje dalej)."""
    stats = importer.stats
    if shutil.disk_usage(staging).free < df.size + DISK_SPACE_MARGIN:
        from app.core.import_manager import DiskFullError
        raise DiskFullError(tr("Brak miejsca na dysku — import został zatrzymany."))
    slot = staging / f"{slot_no:06d}"
    slot.mkdir(parents=True, exist_ok=True)
    try:
        try:
            staged = copy_item(shell, df.item, df.name, df.size, slot, cancelled)
        except DeviceCopyError as exc:
            stats.errors.append(str(exc))
            return
        if staged is None:
            pass
        elif media_kind(staged.suffix):
            importer.import_file(staged, source_key=key, consume=True)
        else:
            stats.errors.append(tr("{name}: nieobsługiwany format", name=staged.name))
    finally:
        shutil.rmtree(slot, ignore_errors=True)  # tylko nasza kopia tymczasowa


def _import_newest(shell, device, folders, importer, staging, progress, cancelled, limit) -> None:
    from app.core.import_manager import DiskFullError
    stats = importer.stats
    staging.mkdir(parents=True, exist_ok=True)
    stats.total = 0
    progress("copy", 0, 0)
    for n, df in enumerate(iter_newest(shell, device, folders, cancelled,
                                       lambda k: progress("scan", k, 0) if stats.copied == 0 else None)):
        if cancelled():
            stats.aborted_reason = tr("Import przerwany przez użytkownika.")
            break
        stats.total = n + 1
        key = f"wpd:{device}/{df.rel}|{df.size}|{df.modified}"
        if importer.is_known_source(key):
            stats.skipped_known += 1
        else:
            try:
                _copy_one(shell, df, key, importer, staging, n, cancelled)
            except DiskFullError as exc:
                stats.aborted_reason = str(exc)
                break
            except Exception as exc:
                stats.errors.append(f"{df.name}: {exc}")
        stats.processed += 1
        progress("copy", stats.processed, stats.total)
        if stats.copied >= limit:
            stats.limit_reached = True   # mamy N nowych — dalej telefonu nie przeglądamy
            break


def import_from_device(device: str, folders: list[str], importer, staging: Path,
                       progress: Callable[[str, int, int], None],
                       cancelled: Callable[[], bool], limit: int | None = None) -> None:
    """Skanuje wskazane foldery urządzenia i importuje pliki przez kopię tymczasową.

    progress(etap, wykonane, wszystkie)
    """
    from app.core.import_manager import DiskFullError

    stats = importer.stats
    reset_copy_mode()
    with _Com():
        shell = _shell()
        if limit:
            # tryb próbny: nie skanuj całego telefonu — bierz od najnowszych, aż będzie N nowych
            stats.limit = limit
            _import_newest(shell, device, folders, importer, staging, progress, cancelled, limit)
            return
        files: list[DeviceFile] = []
        for rel in folders:
            folder = _navigate(shell, device, rel)
            if folder is None:
                stats.errors.append(tr("Nie znaleziono folderu na urządzeniu: {folder} "
                                       "(odblokuj telefon i sprawdź połączenie).", folder=rel))
                continue
            _walk(folder, rel, files, cancelled, lambda n: progress("scan", n, 0))
        if limit:
            stats.limit = limit
            files.sort(key=_newest_key, reverse=True)
        stats.total = len(files)
        progress("copy", 0, len(files))
        staging.mkdir(parents=True, exist_ok=True)
        for i, df in enumerate(files):
            if stats.limit and stats.copied >= stats.limit:
                stats.limit_reached = True
                break
            if cancelled():
                stats.aborted_reason = tr("Import przerwany przez użytkownika.")
                break
            key = f"wpd:{device}/{df.rel}|{df.size}|{df.modified}"
            if importer.is_known_source(key):
                stats.skipped_known += 1
                stats.processed += 1
                progress("copy", i + 1, len(files))
                continue
            free = shutil.disk_usage(staging).free
            if free < df.size + DISK_SPACE_MARGIN:
                stats.aborted_reason = tr("Brak miejsca na dysku — import został zatrzymany.")
                break
            slot = staging / f"{i:06d}"
            slot.mkdir(exist_ok=True)
            try:
                staged = copy_item(shell, df.item, df.name, df.size, slot, cancelled)
                if staged is None:
                    pass
                else:
                    if media_kind(staged.suffix):
                        importer.import_file(staged, source_key=key, consume=True)
                    else:
                        stats.errors.append(tr("{name}: nieobsługiwany format", name=staged.name))
            except DiskFullError as exc:
                stats.aborted_reason = str(exc)
                break
            except DeviceCopyError as exc:
                stats.errors.append(str(exc))
            except Exception as exc:
                stats.errors.append(f"{df.name}: {exc}")
            finally:
                shutil.rmtree(slot, ignore_errors=True)  # tylko nasza kopia tymczasowa
            stats.processed += 1
            progress("copy", i + 1, len(files))
