"""Operacje na ścieżkach i plikach specyficzne dla Windows."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.constants import INVALID_NAME_CHARS, RESERVED_NAMES


def desktop_dir() -> Path:
    """Zwraca rzeczywisty Pulpit użytkownika (również gdy jest przekierowany do OneDrive)."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                            ("Data3", wintypes.WORD), ("Data4", wintypes.BYTE * 8)]

            # FOLDERID_Desktop {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
            guid = GUID(0xB4BFCC3A, 0xDB2C, 0x424C,
                        (wintypes.BYTE * 8)(0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41))
            ptr = ctypes.c_wchar_p()
            res = ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(ptr))
            if res == 0 and ptr.value:
                path = Path(ptr.value)
                ctypes.windll.ole32.CoTaskMemFree(ptr)
                return path
        except Exception:
            pass
    home = Path.home()
    for cand in (home / "Desktop", home / "Pulpit"):
        if cand.is_dir():
            return cand
    return home


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA")
    path = Path(base) / "PhotoSort" if base else Path.home() / ".photosort-app"
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_folder_name(name: str) -> str | None:
    """Zwraca komunikat błędu albo None, gdy nazwa jest poprawna."""
    stripped = name.strip()
    if not stripped:
        return "Nazwa nie może być pusta."
    if any(ch in INVALID_NAME_CHARS for ch in stripped):
        return 'Nazwa nie może zawierać znaków: < > : " / \\ | ? *'
    if stripped.endswith("."):
        return "Nazwa nie może kończyć się kropką."
    if stripped.startswith("."):
        return "Nazwa nie może zaczynać się od kropki."
    if stripped.split(".")[0].upper() in RESERVED_NAMES:
        return "Ta nazwa jest zarezerwowana przez system Windows."
    if len(stripped) > 120:
        return "Nazwa jest zbyt długa."
    if any(ord(ch) < 32 for ch in stripped):
        return "Nazwa zawiera niedozwolone znaki."
    return None


def unique_path(directory: Path, filename: str) -> Path:
    """Zwraca ścieżkę, która nie istnieje — nigdy nie nadpisujemy plików.

    IMG_001.JPG -> IMG_001 (1).JPG -> IMG_001 (2).JPG ...
    """
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem, suffix = os.path.splitext(filename)
    i = 1
    while True:
        candidate = directory / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def set_hidden(path: Path) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        FILE_ATTRIBUTE_HIDDEN = 0x02
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attrs != -1:
            ctypes.windll.kernel32.SetFileAttributesW(str(path), attrs | FILE_ATTRIBUTE_HIDDEN)
    except Exception:
        pass


def copy_creation_time(src: Path, dst: Path) -> None:
    """Kopiuje datę utworzenia (Windows) z oryginału na kopię. Oryginał jest tylko czytany."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000
        FILE_WRITE_ATTRIBUTES = 0x100
        OPEN_EXISTING = 3
        SHARE = 0x1 | 0x2 | 0x4
        FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
        kernel32.CreateFileW.restype = wintypes.HANDLE
        INVALID = wintypes.HANDLE(-1).value

        hs = kernel32.CreateFileW(str(src), GENERIC_READ, SHARE, None, OPEN_EXISTING,
                                  FILE_FLAG_BACKUP_SEMANTICS, None)
        if hs in (None, INVALID):
            return
        try:
            ctime = wintypes.FILETIME()
            if not kernel32.GetFileTime(wintypes.HANDLE(hs), ctypes.byref(ctime), None, None):
                return
        finally:
            kernel32.CloseHandle(wintypes.HANDLE(hs))
        hd = kernel32.CreateFileW(str(dst), FILE_WRITE_ATTRIBUTES, SHARE, None, OPEN_EXISTING,
                                  FILE_FLAG_BACKUP_SEMANTICS, None)
        if hd in (None, INVALID):
            return
        try:
            kernel32.SetFileTime(wintypes.HANDLE(hd), ctypes.byref(ctime), None, None)
        finally:
            kernel32.CloseHandle(wintypes.HANDLE(hd))
    except Exception:
        pass


def file_creation_time(st: os.stat_result) -> float:
    """Data utworzenia pliku na Windows (st_birthtime w nowszych Pythonach)."""
    return getattr(st, "st_birthtime", None) or st.st_ctime


def reveal_in_explorer(path: Path) -> None:
    if sys.platform == "win32":
        if path.is_file():
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            os.startfile(str(path))  # type: ignore[attr-defined]


def is_hidden_name(name: str) -> bool:
    return name.startswith(".") or name.startswith("~$") or name.lower() in {"thumbs.db", "desktop.ini"}
