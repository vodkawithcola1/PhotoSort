"""Miniatury z powłoki Windows (IShellItemImageFactory) — także dla telefonów (MTP).

Eksplorator Windows pokazuje miniatury zdjęć z iPhone'a/Androida bez kopiowania całych
plików: telefon sam udostępnia małe podglądy. Korzystamy z tego samego mechanizmu, żeby
pasek miniatur w trybie „Sortuj z telefonu” nie musiał ściągać każdego zdjęcia.

Wywołanie przez ctypes (pywin32 nie udostępnia IShellItemImageFactory). Musi działać
w wątku z zainicjalizowanym COM.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtGui import QImage

_ok = sys.platform == "win32"


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, s: str) -> "GUID":
        import uuid
        u = uuid.UUID(s)
        g = cls()
        g.Data1, g.Data2, g.Data3 = u.fields[0], u.fields[1], u.fields[2]
        for i, b in enumerate(u.bytes[8:]):
            g.Data4[i] = b
        return g


class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class BITMAP(ctypes.Structure):
    _fields_ = [("bmType", ctypes.c_long), ("bmWidth", ctypes.c_long), ("bmHeight", ctypes.c_long),
                ("bmWidthBytes", ctypes.c_long), ("bmPlanes", wintypes.WORD),
                ("bmBitsPixel", wintypes.WORD), ("bmBits", ctypes.c_void_p)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


IID_IShellItemImageFactory = GUID.parse("{bcc18b79-ba16-442f-80c4-8a59c30c463b}")
SIIGBF_BIGGERSIZEOK = 0x1
SIIGBF_THUMBNAILONLY = 0x8   # nie zwracaj ikony typu pliku, gdy brak miniatury


def shell_thumbnail(parsing_name: str, size: int = 256) -> QImage | None:
    """Zwraca miniaturę elementu powłoki (ścieżka lub nazwa parsowania urządzenia WPD)."""
    if not _ok:
        return None
    shell32 = ctypes.windll.shell32
    gdi32 = ctypes.windll.gdi32
    factory = ctypes.c_void_p()
    hr = shell32.SHCreateItemFromParsingName(ctypes.c_wchar_p(parsing_name), None,
                                             ctypes.byref(IID_IShellItemImageFactory), ctypes.byref(factory))
    if hr != 0 or not factory.value:
        return None
    try:
        vtbl = ctypes.cast(ctypes.cast(factory, ctypes.POINTER(ctypes.c_void_p))[0],
                           ctypes.POINTER(ctypes.c_void_p))
        # IUnknown (3 metody) + GetImage
        get_image = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, SIZE, ctypes.c_int,
                                       ctypes.POINTER(wintypes.HBITMAP))(vtbl[3])
        hbmp = wintypes.HBITMAP()
        hr = get_image(factory, SIZE(size, size), SIIGBF_BIGGERSIZEOK | SIIGBF_THUMBNAILONLY, ctypes.byref(hbmp))
        if hr != 0 or not hbmp:
            return None
        try:
            return _hbitmap_to_qimage(hbmp, gdi32)
        finally:
            gdi32.DeleteObject(hbmp)
    except Exception:
        return None
    finally:
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(
            ctypes.cast(ctypes.cast(factory, ctypes.POINTER(ctypes.c_void_p))[0],
                        ctypes.POINTER(ctypes.c_void_p))[2])
        release(factory)


def _hbitmap_to_qimage(hbmp, gdi32) -> QImage | None:
    bm = BITMAP()
    if not gdi32.GetObjectW(hbmp, ctypes.sizeof(BITMAP), ctypes.byref(bm)):
        return None
    w, h = bm.bmWidth, abs(bm.bmHeight)
    if w <= 0 or h <= 0:
        return None
    bih = BITMAPINFOHEADER()
    bih.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bih.biWidth, bih.biHeight = w, -h  # od góry do dołu
    bih.biPlanes, bih.biBitCount = 1, 32
    buf = ctypes.create_string_buffer(w * h * 4)
    hdc = ctypes.windll.user32.GetDC(None)
    try:
        lines = gdi32.GetDIBits(hdc, hbmp, 0, h, buf, ctypes.byref(bih), 0)
    finally:
        ctypes.windll.user32.ReleaseDC(None, hdc)
    if lines != h:
        return None
    img = QImage(buf.raw, w, h, w * 4, QImage.Format.Format_ARGB32).copy()
    # część miniatur ma pusty kanał alfa — wtedy traktuj obraz jako nieprzezroczysty
    if img.pixelColor(w // 2, h // 2).alpha() == 0:
        img = img.convertToFormat(QImage.Format.Format_RGB32)
    return img
