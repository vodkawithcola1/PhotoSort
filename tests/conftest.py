import os
import sys
from fractions import Fraction
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def make_jpeg(path: Path, color=(200, 80, 40), size=(640, 480), date: str | None = "2026:12:24 18:30:00",
              gps: tuple[float, float] | None = None, model: str | None = "iPhone 15",
              orientation: int | None = None) -> Path:
    from PIL import Image
    im = Image.new("RGB", size, color)
    exif = Image.Exif()
    if model:
        exif[0x010F] = "Apple"
        exif[0x0110] = model
    if orientation:
        exif[0x0112] = orientation
    if date:
        exif.get_ifd(0x8769)[0x9003] = date
    if gps:
        lat, lon = gps

        def dms(v):
            v = abs(v)
            d = int(v)
            m = int((v - d) * 60)
            s = round(((v - d) * 60 - m) * 60 * 100)
            return (Fraction(d, 1), Fraction(m, 1), Fraction(s, 100))
        g = exif.get_ifd(0x8825)
        g[1] = "N" if lat >= 0 else "S"
        g[2] = dms(lat)
        g[3] = "E" if lon >= 0 else "W"
        g[4] = dms(lon)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "JPEG", exif=exif, quality=85)
    return path


def make_heic(path: Path, color=(30, 120, 200)) -> Path:
    import pillow_heif
    from PIL import Image
    pillow_heif.register_heif_opener()
    im = Image.new("RGB", (400, 300), color)
    exif = Image.Exif()
    exif.get_ifd(0x8769)[0x9003] = "2025:07:15 10:00:00"
    im.save(path, "HEIF", exif=exif)
    return path


def make_mp4(path: Path, seconds: float = 2.0, fps: int = 25, size=(320, 240),
             creation_time: str | None = "2025-08-01T10:15:00.000000Z",
             location: str | None = "+54.2486+015.9628/", rotation: int = 0) -> Path:
    import av
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(path), "w", format="mov" if path.suffix.lower() == ".mov" else "mp4") as out:
        if creation_time:
            out.metadata["creation_time"] = creation_time
        if location:
            out.metadata["location"] = location
            out.metadata["com.apple.quicktime.location.ISO6709"] = location
        st = out.add_stream("mpeg4", rate=fps)
        st.width, st.height = size
        st.pix_fmt = "yuv420p"
        if rotation:
            st.set_display_rotation(rotation)
        n = int(seconds * fps)
        for i in range(n):
            frame = av.VideoFrame.from_image(Image.new("RGB", size, ((i * 9) % 255, 100, 150)))
            for pkt in st.encode(frame.reformat(format="yuv420p")):
                out.mux(pkt)
        for pkt in st.encode():
            out.mux(pkt)
    return path


@pytest.fixture
def source_dir(tmp_path):
    src = tmp_path / "telefon" / "DCIM" / "100APPLE"
    make_jpeg(src / "IMG_0001.JPG", color=(255, 0, 0), gps=(52.2297, 21.0122))
    make_jpeg(src / "IMG_0002.JPG", color=(0, 255, 0), date="2026:01:05 08:00:00")
    make_jpeg(src / "IMG_0003.JPG", color=(0, 0, 255), date=None, model=None)
    make_mp4(src / "IMG_0004.MOV")
    return tmp_path / "telefon"


@pytest.fixture
def library(tmp_path):
    from app.core.library_manager import Library
    desk = tmp_path / "Pulpit"
    desk.mkdir()
    lib = Library.create(desk, "Zdjęcia mamy")
    yield lib
    lib.close()
