# -*- mode: python ; coding: utf-8 -*-
# PyInstaller-leírás a portable (onedir) Windows-buildhez.
# Futtatás: build\build_windows.ps1 (vagy: pyinstaller build\YTDLPStudio.spec)
from pathlib import Path

ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "start.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[(str(ROOT / "assets" / "icon.ico"), "assets"), (str(ROOT / "assets" / "icon.png"), "assets")],
    hiddenimports=["PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSvg", "PySide6.QtNetwork"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PIL", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQuick",
              "PySide6.QtQml", "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization",
              "PySide6.QtPdf", "PySide6.QtBluetooth", "PySide6.QtSql", "PySide6.QtDesigner"],
    noarchive=False,
    optimize=1,
)

# Csak a magyar Qt-fordítások és a szükségtelen szoftveres OpenGL nélkül.
a.datas = [d for d in a.datas
           if not (d[0].replace("\\", "/").find("/translations/") >= 0 and d[0].endswith(".qm") and "_hu" not in d[0])]
a.binaries = [b for b in a.binaries if not b[0].lower().endswith("opengl32sw.dll")]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="YTDLPStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=[str(ROOT / "assets" / "icon.ico")],
    version=str(ROOT / ".build-cache" / "version_info.txt"),
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="YTDLPStudio")
