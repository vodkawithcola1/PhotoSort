"""Generuje app/resources/photosort.ico z logo SVG (używane przez PyInstaller)."""
import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

app = QGuiApplication([])
from app.ui.icons import logo_pixmap  # noqa: E402

pm = logo_pixmap(256, 1.0)
buf = QBuffer()
buf.open(QIODevice.OpenModeFlag.WriteOnly)
pm.save(buf, "PNG")
img = Image.open(io.BytesIO(bytes(buf.data())))
out = ROOT / "app" / "resources" / "photosort.ico"
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("zapisano", out)
