"""Stałe używane w całej aplikacji PhotoSort."""
from __future__ import annotations

APP_NAME = "PhotoSort"
APP_VERSION = "1.0.0"

# Nazwy folderów wewnątrz biblioteki
UNSORTED_FOLDER = "Do posortowania"
DATA_DIR = ".photosort"
DB_FILE = "library.db"
THUMBS_DIR = "thumbnails"
STAGING_DIR = "staging"
SETTINGS_FILE = "settings.json"
PARTIAL_SUFFIX = ".photosort-partial"

# Zakres "wszystkie multimedia" (wirtualny widok całej biblioteki)
SCOPE_ALL = "__all__"
# Zakres „telefon” — przeglądanie i sortowanie prosto z podłączonego urządzenia
SCOPE_DEVICE = "__device__"

PHOTO_EXTENSIONS = {
    ".jpg", ".jpeg", ".jpe", ".png", ".heic", ".heif", ".webp",
    ".tif", ".tiff", ".bmp", ".gif",
}
VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".m4v", ".wmv", ".3gp", ".3g2",
    ".mts", ".m2ts", ".mpg", ".mpeg", ".webm", ".flv", ".asf",
}
MEDIA_EXTENSIONS = PHOTO_EXTENSIONS | VIDEO_EXTENSIONS

# Znaki niedozwolone w nazwach folderów Windows
INVALID_NAME_CHARS = set('<>:"/\\|?*')
RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

THUMB_SIZE = 320
# Minimalny zapas wolnego miejsca zostawiany na dysku podczas importu
DISK_SPACE_MARGIN = 200 * 1024 * 1024

MIME_MEDIA_IDS = "application/x-photosort-media-ids"


def media_kind(ext: str) -> str | None:
    ext = ext.lower()
    if ext in PHOTO_EXTENSIONS:
        return "photo"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return None
