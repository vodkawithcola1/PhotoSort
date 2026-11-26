"""Główne okno: ekran powitalny <-> widok biblioteki."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox, QStackedWidget

from app.constants import APP_NAME
from app.core.library_controller import LibraryController
from app.core.library_manager import Library, LibraryError, is_library
from app.core.session_manager import AppSettings
from app.services.thumbnail_service import ThumbnailService
from app.ui import icons, theme
from app.ui.dialogs import confirm
from app.ui.import_dialog import DeviceDialog, ImportProgressDialog, ImportSourceDialog
from app.ui.library_view import LibraryView
from app.ui.settings_dialog import SettingsDialog
from app.ui.welcome import NewLibraryDialog, WelcomeScreen
from app.utils.formatting import count_pl
from app.utils.paths import desktop_dir


class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings | None = None):
        super().__init__()
        self.settings = settings or AppSettings()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.setMinimumSize(1000, 680)
        self.setAcceptDrops(True)
        self.thumbs = ThumbnailService()
        self.library: Library | None = None
        self.ctrl: LibraryController | None = None
        self.view: LibraryView | None = None
        self._import_dialog: ImportProgressDialog | None = None

        self.stack = QStackedWidget()
        self.stack.setObjectName("Root")
        self.setCentralWidget(self.stack)
        self.welcome = WelcomeScreen()
        self.welcome.new_library.connect(self.new_library)
        self.welcome.open_library.connect(self.open_library_dialog)
        self.welcome.open_path.connect(lambda p: self.open_library(Path(p)))
        self.welcome.remove_recent.connect(self._remove_recent)
        self.welcome.theme_btn.clicked.connect(self.toggle_theme)
        self.stack.addWidget(self.welcome)
        self.welcome.set_recent(self.settings.recent())
        self.welcome.refresh_theme()

        geo = self.settings.get("window")
        if geo:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geo.encode()))
            except Exception:
                self.resize(1400, 900)
        else:
            self.resize(1400, 900)

    # ------------------------------------------------------------------ #
    # Motyw
    # ------------------------------------------------------------------ #
    def set_theme(self, name: str) -> None:
        theme.apply(QApplication.instance(), name)
        icons.clear_cache()
        self.settings.set("theme", name)
        self.welcome.refresh_theme()
        if self.view:
            self.view.refresh_theme()

    def toggle_theme(self) -> None:
        self.set_theme("light" if theme.current()["name"] == "dark" else "dark")

    # ------------------------------------------------------------------ #
    # Biblioteki
    # ------------------------------------------------------------------ #
    def new_library(self) -> None:
        d = NewLibraryDialog(self)
        if d.exec() != NewLibraryDialog.DialogCode.Accepted:
            return
        if d.open_existing:
            self.open_library(d.open_existing)
            return
        target = d.result_path
        try:
            lib = Library.create(target.parent, target.name)
        except FileExistsError:
            QMessageBox.warning(self, APP_NAME, f"Folder „{target.name}” już istnieje. Wybierz inną nazwę.")
            return
        except (LibraryError, OSError) as exc:
            QMessageBox.warning(self, APP_NAME, f"Nie udało się utworzyć biblioteki:\n{exc}")
            return
        lib.close()
        self.open_library(target)

    def open_library_dialog(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Wskaż folder biblioteki PhotoSort", str(desktop_dir()))
        if not d:
            return
        path = Path(d)
        if not is_library(path):
            # może użytkownik wskazał podfolder biblioteki
            for parent in path.parents:
                if is_library(parent):
                    path = parent
                    break
        self.open_library(path)

    def open_library(self, path: Path) -> None:
        if not is_library(path):
            QMessageBox.warning(self, APP_NAME, f"Ten folder nie jest biblioteką PhotoSort:\n{path}\n\n"
                                "Aby uporządkować zdjęcia z tego folderu, utwórz nową bibliotekę i użyj "
                                "„Importuj zdjęcia i filmy”.")
            self.settings.remove_recent(str(path))
            self.welcome.set_recent(self.settings.recent())
            return
        self.close_library()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            lib = Library.open(path)
        except (LibraryError, OSError) as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, APP_NAME, str(exc))
            return
        self.library = lib
        self.ctrl = LibraryController(lib)
        self.view = LibraryView(self.ctrl, self.thumbs)
        self.view.home.connect(self.go_home)
        self.view.import_clicked.connect(self.import_dialog)
        self.view.settings.connect(self.open_settings)
        self.view.theme_toggle.connect(self.toggle_theme)
        self.view.fullscreen_toggle.connect(self.toggle_fullscreen)
        self.stack.addWidget(self.view)
        self.stack.setCurrentWidget(self.view)
        self.ctrl.start()
        self.view.restore_scroll()
        QApplication.restoreOverrideCursor()
        self.settings.add_recent(lib.root)
        self.setWindowTitle(f"{lib.name} — {APP_NAME}")

    def close_library(self) -> None:
        if self.ctrl is None:
            return
        if self.isFullScreen():
            self.toggle_fullscreen()
        self.view.shutdown()
        self.ctrl.shutdown()
        self.thumbs.clear()
        self.stack.removeWidget(self.view)
        self.view.deleteLater()
        self.library.close()
        self.view = None
        self.ctrl = None
        self.library = None
        self.setWindowTitle(APP_NAME)

    def go_home(self) -> None:
        self.close_library()
        self.welcome.set_recent(self.settings.recent())
        self.stack.setCurrentWidget(self.welcome)

    def _remove_recent(self, p: str) -> None:
        self.settings.remove_recent(p)
        self.welcome.set_recent(self.settings.recent())

    # ------------------------------------------------------------------ #
    # Import
    # ------------------------------------------------------------------ #
    def import_dialog(self) -> None:
        if self.library is None:
            return
        d = ImportSourceDialog(self)
        if d.exec() != ImportSourceDialog.DialogCode.Accepted or not d.choice:
            return
        kind, paths = d.choice
        if kind == "device":
            dd = DeviceDialog(self)
            if dd.exec() != DeviceDialog.DialogCode.Accepted or not dd.device:
                return
            if dd.mode == "browse":
                # nic nie jest importowane hurtowo — tylko przeglądanie z telefonu
                self.ctrl.open_device(dd.device, dd.folders, limit=d.limit)
            else:
                self.run_import(device=dd.device, device_folders=dd.folders, limit=d.limit)
        else:
            self.run_import(paths=paths, recursive=d.recursive.isChecked(), limit=d.limit)

    def run_import(self, paths: list[Path] | None = None, recursive: bool = True,
                   device: str | None = None, device_folders: list[str] | None = None,
                   limit: int | None = None) -> None:
        if self.library is None:
            return
        if self._import_dialog is not None and self._import_dialog.worker.isRunning():
            QMessageBox.information(self, APP_NAME, "Trwa już import. Poczekaj na jego zakończenie.")
            return
        dlg = ImportProgressDialog(self.library, self, paths, recursive, device, device_folders, limit)
        dlg.finished_ok.connect(self._import_done)
        self._import_dialog = dlg
        dlg.start()
        dlg.exec()

    def _import_done(self, stats) -> None:
        if self.ctrl is not None:
            self.ctrl.after_import(stats.new_ids)

    # przeciąganie plików z Eksploratora do okna
    def dragEnterEvent(self, e) -> None:
        if self.library is not None and e.mimeData().hasUrls():
            if any(u.isLocalFile() for u in e.mimeData().urls()):
                e.acceptProposedAction()
                return
        e.ignore()

    def dropEvent(self, e) -> None:
        paths = [Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()]
        if not paths or self.library is None:
            return
        e.acceptProposedAction()
        root = str(self.library.root.resolve()).lower()
        paths = [p for p in paths if not str(p.resolve()).lower().startswith(root)]
        if not paths:
            return
        text = (f"Zaimportować {count_pl(len(paths), 'element', 'elementy', 'elementów')} do biblioteki?\n\n"
                "Pliki zostaną skopiowane do folderu „Do posortowania”. Oryginały pozostaną na swoim miejscu.")
        QTimer.singleShot(0, lambda: confirm(self, "Import", text, "Importuj") and self.run_import(paths=paths))

    # ------------------------------------------------------------------ #
    def open_settings(self) -> None:
        d = SettingsDialog(self.ctrl, self)
        d.theme_selected.connect(self.set_theme)
        d.exec()

    def toggle_fullscreen(self) -> None:
        if self.view is None:
            return
        if self.isFullScreen():
            self.view.set_immersive(False)
            if getattr(self, "_was_maximized", False):
                self.showMaximized()
            else:
                self.showNormal()
        else:
            self._was_maximized = self.isMaximized()
            self.view.set_immersive(True)
            self.showFullScreen()

    def closeEvent(self, e) -> None:
        if self._import_dialog is not None and self._import_dialog.worker.isRunning():
            if not confirm(self, APP_NAME, "Trwa import. Przerwać import i zamknąć program?\n"
                           "Skopiowane do tej pory pliki zostaną zachowane.", "Przerwij i zamknij"):
                e.ignore()
                return
            self._import_dialog.worker.cancel()
            self._import_dialog.worker.wait(15000)
        if self.ctrl is not None and self.ctrl._pending_device:
            if not confirm(self, APP_NAME, "Trwa kopiowanie zdjęć z telefonu do folderów.\n"
                           "Zamknąć program teraz? Niedokończone kopie zostaną pominięte "
                           "(zdjęcia zostaną na telefonie).", "Zamknij"):
                e.ignore()
                return
        if self.isFullScreen():
            self.toggle_fullscreen()
        self.settings.data["window"] = bytes(self.saveGeometry().toBase64()).decode()
        self.settings.save()
        self.close_library()
        self.thumbs.shutdown()
        super().closeEvent(e)
