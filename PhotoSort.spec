# -*- mode: python ; coding: utf-8 -*-
# Budowanie:  pyinstaller PhotoSort.spec --noconfirm
# Wynik:      dist\PhotoSort\PhotoSort.exe  (wersja folderowa — szybki start)
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

datas = [("app/resources/places.tsv.gz", "app/resources")]
datas += collect_data_files("pillow_heif")
binaries = collect_dynamic_libs("pillow_heif") + collect_dynamic_libs("av")
hiddenimports = collect_submodules("av") + ["pillow_heif", "win32com.client", "pythoncom", "pywintypes",
                                            "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
                                            "PySide6.QtSvg"]
# opcjonalnie: ExifTool w folderze tools/ zostanie dołączony, jeśli istnieje
import os
if os.path.isfile("tools/exiftool.exe"):
    binaries.append(("tools/exiftool.exe", "tools"))
    if os.path.isdir("tools/exiftool_files"):
        datas.append(("tools/exiftool_files", "tools/exiftool_files"))

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick3D", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf",
              "PySide6.QtDesigner", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PhotoSort",
    icon="app/resources/photosort.ico",
    console=False,
    disable_windowed_traceback=False,
    upx=False,
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="PhotoSort")
