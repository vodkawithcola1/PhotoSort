"""Odczyt metadanych zdjęć i filmów.

Źródła (od najlepszego):
  * ExifTool — jeżeli jest dostępny (tools/exiftool.exe obok programu lub w PATH),
  * Pillow / pillow-heif — EXIF zdjęć (JPG, HEIC, TIFF, WEBP, PNG),
  * PyAV (FFmpeg) — metadane kontenerów MOV/MP4/MKV/AVI (data, GPS, model, FPS, długość),
  * nazwa pliku — np. IMG_20230715_123456.jpg, VID-20230715-WA0001.mp4.

Pliki są otwierane wyłącznie do odczytu.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.constants import media_kind

try:
    from PIL import Image
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:  # pragma: no cover
        pass
except Exception:  # pragma: no cover
    Image = None  # type: ignore

try:
    import av  # PyAV
    try:
        import av.logging as _avlog
        _avlog.set_level(_avlog.PANIC)
    except Exception:
        pass
except Exception:  # pragma: no cover
    av = None  # type: ignore


@dataclass
class MediaMeta:
    taken_at: str | None = None        # "YYYY-MM-DD HH:MM:SS" czas lokalny
    taken_source: str | None = None    # exif | video | filename | exiftool
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    fps: float | None = None
    make: str | None = None
    model: str | None = None
    lat: float | None = None
    lon: float | None = None
    orientation: int | None = None
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------- #
# Pomocnicze
# ---------------------------------------------------------------------- #
_EXIF_DT = re.compile(r"(\d{4})[:\-](\d{2})[:\-](\d{2})[ T](\d{2}):(\d{2}):(\d{2})")


def parse_exif_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("ascii", "ignore")
    m = _EXIF_DT.search(str(value).strip())
    if not m:
        return None
    try:
        dt = datetime(*map(int, m.groups()))
    except ValueError:
        return None
    if dt.year < 1980 or dt.year > 2100:
        return None
    return dt


def parse_iso_any(value: str | None, to_local: bool) -> datetime | None:
    """Parsuje daty z kontenerów wideo.

    to_local=True: wartość jest w UTC (np. 'creation_time' MP4) — konwertujemy na czas lokalny.
    to_local=False: wartość zawiera przesunięcie strefy (np. Apple 'creationdate') —
    zachowujemy czas zegarowy z miejsca nagrania.
    """
    if not value:
        return None
    s = str(value).strip().replace("Z", "+00:00")
    s = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", s)
    s = re.sub(r"\.\d+", "", s)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        dt = parse_exif_datetime(value)
        if dt is None:
            return None
    if dt.year < 1980 or dt.year > 2100:
        return None
    if dt.tzinfo is not None:
        if to_local:
            dt = dt.astimezone().replace(tzinfo=None)
        else:
            dt = dt.replace(tzinfo=None)
    elif to_local:
        dt = dt.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    return dt


_FN_PATTERNS = [
    re.compile(r"(?<!\d)(19[89]\d|20\d{2})(\d{2})(\d{2})[_\-\s]?(\d{2})(\d{2})(\d{2})(?!\d)"),
    re.compile(r"(?<!\d)(19[89]\d|20\d{2})-(\d{2})-(\d{2})[ _\-T](\d{2})[.\-:h](\d{2})[.\-:m](\d{2})"),
    re.compile(r"(?<!\d)(19[89]\d|20\d{2})(\d{2})(\d{2})(?!\d)"),            # IMG-20230715-WA0001
    re.compile(r"(?<!\d)(19[89]\d|20\d{2})-(\d{2})-(\d{2})(?!\d)"),
]


def date_from_filename(name: str) -> datetime | None:
    stem = os.path.splitext(name)[0]
    for pat in _FN_PATTERNS:
        m = pat.search(stem)
        if not m:
            continue
        parts = [int(x) for x in m.groups()]
        while len(parts) < 6:
            parts.append(0)
        try:
            return datetime(*parts)
        except ValueError:
            continue
    return None


_ISO6709 = re.compile(r"([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)")


def parse_iso6709(value: str | None) -> tuple[float, float] | None:
    if not value:
        return None
    m = _ISO6709.match(str(value).strip())
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None
    return lat, lon


def _ratio(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError, ZeroDivisionError):
        try:
            return v[0] / v[1]
        except Exception:
            return 0.0


def _gps_to_deg(values, ref) -> float | None:
    try:
        d, m, s = (_ratio(x) for x in values)
        deg = d + m / 60.0 + s / 3600.0
    except Exception:
        return None
    if isinstance(ref, bytes):
        ref = ref.decode("ascii", "ignore")
    if str(ref).upper().startswith(("S", "W")):
        deg = -deg
    return deg


def _clean(s) -> str | None:
    if s is None:
        return None
    if isinstance(s, bytes):
        s = s.decode("utf-8", "ignore")
    s = str(s).replace("\x00", "").strip()
    return s or None


# ---------------------------------------------------------------------- #
# Zdjęcia
# ---------------------------------------------------------------------- #
def read_image_meta(path: Path) -> MediaMeta:
    meta = MediaMeta()
    if Image is None:
        return meta
    with Image.open(path) as im:
        w, h = im.size
        exif = im.getexif()
        orientation = exif.get(0x0112)
        meta.orientation = int(orientation) if orientation else None
        if meta.orientation in (5, 6, 7, 8):
            w, h = h, w
        meta.width, meta.height = w, h
        meta.make = _clean(exif.get(0x010F))
        meta.model = _clean(exif.get(0x0110))
        try:
            exif_ifd = exif.get_ifd(0x8769)
        except Exception:
            exif_ifd = {}
        dt = (parse_exif_datetime(exif_ifd.get(0x9003)) or parse_exif_datetime(exif_ifd.get(0x9004))
              or parse_exif_datetime(exif.get(0x0132)))
        if dt:
            meta.taken_at = dt.strftime("%Y-%m-%d %H:%M:%S")
            meta.taken_source = "exif"
        try:
            gps = exif.get_ifd(0x8825)
        except Exception:
            gps = {}
        if gps and 2 in gps and 4 in gps:
            lat = _gps_to_deg(gps[2], gps.get(1, "N"))
            lon = _gps_to_deg(gps[4], gps.get(3, "E"))
            if lat is not None and lon is not None and not (lat == 0 and lon == 0) \
                    and -90 <= lat <= 90 and -180 <= lon <= 180:
                meta.lat, meta.lon = lat, lon
        if getattr(im, "is_animated", False):
            meta.extra["frames"] = getattr(im, "n_frames", None)
    return meta


# ---------------------------------------------------------------------- #
# Filmy
# ---------------------------------------------------------------------- #
def read_video_meta(path: Path) -> MediaMeta:
    meta = MediaMeta()
    if av is None:
        return meta
    with av.open(str(path)) as container:
        md = {k.lower(): v for k, v in (container.metadata or {}).items()}
        if container.duration:
            meta.duration = container.duration / 1_000_000
        vstreams = container.streams.video
        if vstreams:
            vs = vstreams[0]
            smd = {k.lower(): v for k, v in (vs.metadata or {}).items()}
            for k, v in smd.items():
                md.setdefault(k, v)
            meta.width = vs.codec_context.width or None
            meta.height = vs.codec_context.height or None
            rate = vs.average_rate or vs.guessed_rate or vs.base_rate
            if rate:
                fps = float(rate)
                if 0 < fps < 1000:
                    meta.fps = round(fps, 2)
            if meta.duration is None and vs.duration and vs.time_base:
                meta.duration = float(vs.duration * vs.time_base)
            # Rotacja (np. pionowe filmy z iPhone'a) — z pierwszej klatki.
            rotation = 0
            try:
                rotation = int(md.get("rotate", 0) or 0)
            except ValueError:
                rotation = 0
            if not rotation:
                try:
                    for frame in container.decode(video=0):
                        rotation = int(getattr(frame, "rotation", 0) or 0)
                        break
                except Exception:
                    rotation = 0
            if rotation % 180 == 90 and meta.width and meta.height:
                meta.width, meta.height = meta.height, meta.width
            meta.extra["rotation"] = rotation

        # Data nagrania: Apple (z lokalną strefą) > creation_time (UTC)
        dt = parse_iso_any(md.get("com.apple.quicktime.creationdate"), to_local=False)
        if dt is None:
            dt = parse_iso_any(md.get("creation_time") or md.get("date"), to_local=True)
        if dt is not None and dt.year > 1990:
            meta.taken_at = dt.strftime("%Y-%m-%d %H:%M:%S")
            meta.taken_source = "video"
        loc = parse_iso6709(md.get("com.apple.quicktime.location.iso6709") or md.get("location")
                            or md.get("location-eng"))
        if loc:
            meta.lat, meta.lon = loc
        meta.make = _clean(md.get("com.apple.quicktime.make") or md.get("make")
                           or md.get("com.android.manufacturer"))
        meta.model = _clean(md.get("com.apple.quicktime.model") or md.get("model")
                            or md.get("com.android.model"))
    return meta


# ---------------------------------------------------------------------- #
# ExifTool (opcjonalnie)
# ---------------------------------------------------------------------- #
def find_exiftool() -> str | None:
    candidates = []
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    candidates += [base / "tools" / "exiftool.exe", base / "tools" / "exiftool(-k).exe",
                   Path(sys.executable).parent / "tools" / "exiftool.exe"]
    for c in candidates:
        if c.is_file():
            return str(c)
    return shutil.which("exiftool") or shutil.which("exiftool.exe")


class ExifTool:
    """Proces ExifTool w trybie -stay_open (jeden proces na cały odczyt)."""

    def __init__(self, exe: str):
        self.exe = exe
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()

    def _start(self) -> None:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen(
            [self.exe, "-stay_open", "True", "-@", "-", "-common_args", "-j", "-n", "-charset", "filename=utf8"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=flags)

    def read(self, path: Path) -> dict:
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                self._start()
            assert self.proc and self.proc.stdin and self.proc.stdout
            args = ["-DateTimeOriginal", "-CreateDate", "-CreationDate", "-MediaCreateDate",
                    "-Make", "-Model", "-GPSLatitude", "-GPSLongitude", "-GPSCoordinates",
                    "-ImageWidth", "-ImageHeight", "-Duration", "-VideoFrameRate", "-Orientation",
                    "-Rotation", "-api", "QuickTimeUTC", str(path), "-execute\n"]
            self.proc.stdin.write("\n".join(args).encode("utf-8"))
            self.proc.stdin.flush()
            out = b""
            while not out.rstrip().endswith(b"{ready}"):
                chunk = self.proc.stdout.readline()
                if not chunk:
                    break
                out += chunk
            text = out.decode("utf-8", "ignore").rsplit("{ready}", 1)[0].strip()
            try:
                data = json.loads(text)
                return data[0] if data else {}
            except ValueError:
                return {}

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                assert self.proc.stdin
                self.proc.stdin.write(b"-stay_open\nFalse\n")
                self.proc.stdin.flush()
                self.proc.wait(timeout=3)
            except Exception:
                self.proc.kill()
        self.proc = None


def _merge_exiftool(meta: MediaMeta, d: dict, kind: str) -> None:
    if not d:
        return
    if meta.taken_at is None:
        for key in ("DateTimeOriginal", "CreationDate", "CreateDate", "MediaCreateDate"):
            dt = parse_exif_datetime(d.get(key))
            if dt:
                meta.taken_at = dt.strftime("%Y-%m-%d %H:%M:%S")
                meta.taken_source = "exiftool"
                break
    if meta.lat is None:
        lat, lon = d.get("GPSLatitude"), d.get("GPSLongitude")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and (lat or lon):
            meta.lat, meta.lon = float(lat), float(lon)
        elif d.get("GPSCoordinates"):
            parts = str(d["GPSCoordinates"]).replace(",", " ").split()
            try:
                meta.lat, meta.lon = float(parts[0]), float(parts[1])
            except (ValueError, IndexError):
                pass
    meta.make = meta.make or _clean(d.get("Make"))
    meta.model = meta.model or _clean(d.get("Model"))
    if kind == "video":
        if meta.duration is None and isinstance(d.get("Duration"), (int, float)):
            meta.duration = float(d["Duration"])
        if meta.fps is None and isinstance(d.get("VideoFrameRate"), (int, float)):
            meta.fps = round(float(d["VideoFrameRate"]), 2)
    if meta.width is None and isinstance(d.get("ImageWidth"), int):
        meta.width, meta.height = d.get("ImageWidth"), d.get("ImageHeight")


# ---------------------------------------------------------------------- #
class MetadataReader:
    def __init__(self, use_exiftool: bool = True):
        exe = find_exiftool() if use_exiftool else None
        self.exiftool = ExifTool(exe) if exe else None

    @property
    def has_exiftool(self) -> bool:
        return self.exiftool is not None

    def read(self, path: Path) -> MediaMeta:
        kind = media_kind(path.suffix) or "photo"
        meta = MediaMeta()
        error = None
        try:
            meta = read_video_meta(path) if kind == "video" else read_image_meta(path)
        except Exception as exc:  # uszkodzony plik / nieobsługiwany kodek
            error = exc
        if self.exiftool and (meta.taken_at is None or meta.lat is None or meta.model is None):
            try:
                _merge_exiftool(meta, self.exiftool.read(path), kind)
            except Exception:
                pass
        if meta.taken_at is None:
            dt = date_from_filename(path.name)
            if dt:
                meta.taken_at = dt.strftime("%Y-%m-%d %H:%M:%S")
                meta.taken_source = "filename"
        if error is not None and meta.width is None and meta.taken_at is None:
            meta.extra["error"] = str(error)
        return meta

    def close(self) -> None:
        if self.exiftool:
            self.exiftool.close()
