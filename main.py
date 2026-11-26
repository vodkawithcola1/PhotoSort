"""PhotoSort — porządkowanie zdjęć i filmów metodą „przeciągnij i upuść”.

Uruchomienie:  python main.py
"""
from __future__ import annotations

import faulthandler
import logging
import os
import sys
import traceback
from pathlib import Path

# Qt Multimedia: backend FFmpeg (obsługuje MOV/HEVC/MKV itd.)
os.environ.setdefault("QT_MEDIA_BACKEND", "ffmpeg")
os.environ.setdefault("QT_FFMPEG_DECODING_HW_DEVICE_TYPES", "d3d11va,dxva2")


def _setup_logging() -> Path:
    from app.utils.paths import app_data_dir
    log = app_data_dir() / "photosort.log"
    logging.basicConfig(filename=str(log), level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        faulthandler.enable(open(app_data_dir() / "crash.log", "a", encoding="utf-8"))
    except OSError:
        pass
    return log


def main() -> int:
    if "--selftest" in sys.argv:
        from app.selftest import run
        i = sys.argv.index("--selftest")
        out = Path(sys.argv[i + 1]) if len(sys.argv) > i + 1 else None
        return run(out)
    log_path = _setup_logging()
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PhotoSort.App")
        except Exception:
            pass

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication, QMessageBox

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("PhotoSort")
    app.setOrganizationName("PhotoSort")

    from app import i18n
    from app.core.session_manager import AppSettings

    settings = AppSettings()
    # Interface language: saved in settings; on first run — the system language.
    # Must be set before the UI modules are imported.
    i18n.set_language(settings.get("language") or i18n.system_language())

    from app.ui import icons, theme
    from app.ui.main_window import MainWindow

    theme.apply(app, settings.get("theme", "light"))
    app.setWindowIcon(icons.app_icon())

    def excepthook(etype, value, tb):
        text = "".join(traceback.format_exception(etype, value, tb))
        logging.error("Nieobsłużony wyjątek:\n%s", text)
        try:
            QMessageBox.critical(None, "PhotoSort",
                                 i18n.tr("Wystąpił nieoczekiwany błąd. Twoje pliki są bezpieczne.\n\n"
                                         "{error}\n\nSzczegóły zapisano w:\n{log}", error=value, log=log_path))
        except Exception:
            pass

    sys.excepthook = excepthook

    win = MainWindow(settings)
    win.show()
    # argument wiersza poleceń: ścieżka biblioteki do otwarcia
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_dir():
        win.open_library(Path(sys.argv[1]))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
