"""Autotest składników (uruchamiany: PhotoSort.exe --selftest).

Sprawdza w zbudowanej wersji .exe, czy dostępne są wszystkie biblioteki:
JPEG/HEIC, miniatury, metadane, geolokalizacja offline, odtwarzacz wideo,
tworzenie biblioteki, import i przenoszenie. Wynik zapisuje do pliku i
zwraca kod 0 (OK) lub 1 (błąd).
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path


def run(out_file: Path | None = None) -> int:
    lines: list[str] = []
    ok = True

    def check(name, fn):
        nonlocal ok
        try:
            res = fn()
            lines.append(f"OK    {name}: {res}")
        except Exception as exc:
            ok = False
            lines.append(f"BŁĄD  {name}: {exc}\n{traceback.format_exc()}")

    tmp = Path(tempfile.mkdtemp(prefix="photosort-selftest-"))
    try:
        from PIL import Image
        src = tmp / "src"
        src.mkdir()

        def jpeg():
            im = Image.new("RGB", (800, 600), (200, 100, 50))
            exif = Image.Exif()
            exif.get_ifd(0x8769)[0x9003] = "2024:05:01 12:00:00"
            im.save(src / "a.jpg", exif=exif)
            return "zapisano"

        def heic():
            import pillow_heif
            pillow_heif.register_heif_opener()
            Image.new("RGB", (400, 300), (10, 120, 200)).save(src / "b.heic", "HEIF")
            with Image.open(src / "b.heic") as im:
                return f"{im.format} {im.size}"

        def video():
            import av
            with av.open(str(src / "c.mp4"), "w") as out:
                st = out.add_stream("mpeg4", rate=25)
                st.width, st.height, st.pix_fmt = 320, 240, "yuv420p"
                for i in range(30):
                    fr = av.VideoFrame.from_image(Image.new("RGB", (320, 240), (i * 8, 50, 90)))
                    for p in st.encode(fr):
                        out.mux(p)
                for p in st.encode():
                    out.mux(p)
            return f"PyAV {av.__version__}"

        check("JPEG", jpeg)
        check("HEIC (pillow-heif)", heic)
        check("Wideo (PyAV/FFmpeg)", video)

        from app.core.import_manager import Importer, collect_media_files
        from app.core.library_manager import Library
        from app.core.media_manager import Filters, MediaManager

        holder = {}

        def library():
            lib = Library.create(tmp, "Test")
            holder["lib"] = lib
            st = Importer(lib, lib.db).import_paths(collect_media_files([src]))
            return f"zaimportowano {st.copied}, błędy {len(st.errors)}"

        check("Biblioteka i import", library)

        def meta():
            from app.services.metadata_service import MetadataReader
            r = MetadataReader()
            lib = holder["lib"]
            m1 = r.read(lib.unsorted_dir / "a.jpg")
            m2 = r.read(lib.unsorted_dir / "c.mp4")
            r.close()
            return f"jpg data={m1.taken_at}; mp4 {m2.width}x{m2.height} {m2.duration:.1f}s {m2.fps} kl/s"

        def thumbs():
            from app.services.thumbnail_service import make_thumbnail
            lib = holder["lib"]
            res = []
            for name, kind in (("a.jpg", "photo"), ("b.heic", "photo"), ("c.mp4", "video")):
                res.append(make_thumbnail(lib.unsorted_dir / name, kind, tmp / f"t_{name}.jpg"))
            if not all(res):
                raise RuntimeError(res)
            return "3/3"

        def geo():
            from app.services.geocode_service import Geocoder
            g = Geocoder.shared()
            return g.lookup(52.2297, 21.0122)

        def move():
            lib = holder["lib"]
            mm = MediaManager(lib)
            lib.create_folder("Cel")
            ids = mm.query_ids(lib.unsorted, Filters())
            r = mm.move(ids[:1], "Cel")
            u = mm.undo_last()
            return f"przeniesiono {len(r.moved)}, cofnięto {len(u.moved)}"

        def player():
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QMediaPlayer
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance() or QApplication(sys.argv[:1])
            p = QMediaPlayer()
            p.setSource(QUrl.fromLocalFile(str(holder["lib"].unsorted_dir / "c.mp4")))
            end = time.time() + 10
            while time.time() < end and p.mediaStatus() not in (QMediaPlayer.MediaStatus.LoadedMedia,
                                                                QMediaPlayer.MediaStatus.InvalidMedia):
                app.processEvents()
                time.sleep(0.02)
            if p.mediaStatus() != QMediaPlayer.MediaStatus.LoadedMedia:
                raise RuntimeError(f"status {p.mediaStatus()} {p.errorString()}")
            return f"długość {p.duration()} ms"

        check("Metadane", meta)
        check("Miniatury JPG/HEIC/MP4", thumbs)
        check("Geolokalizacja offline", geo)
        check("Przenoszenie i cofanie", move)
        check("Odtwarzacz Qt Multimedia", player)
        if "lib" in holder:
            holder["lib"].close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    lines.append("WYNIK: " + ("OK" if ok else "BŁĘDY"))
    text = "\n".join(lines)
    if out_file:
        out_file.write_text(text, "utf-8")
    try:
        print(text)
    except Exception:
        pass
    return 0 if ok else 1
