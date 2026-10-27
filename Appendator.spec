# -*- mode: python ; coding: utf-8 -*-
# pyinstaller --noconfirm Appendator.spec
#   Windows -> dist/Appendator.exe (un único archivo)
#   macOS   -> dist/Appendator.app (Apple Silicon)
#   Linux   -> dist/Appendator (un único archivo)
import sys

VERSION = "1.2.0"
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("assets/icon.ico", "assets"), ("assets/icon.png", "assets")],
    hiddenimports=["appendator.selftest"] + (["windnd"] if IS_WIN else []),
    excludes=["numpy", "matplotlib", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if IS_MAC:
    # En macOS el formato adecuado es un .app (carpeta), no un ejecutable onefile.
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="Appendator",
        console=False,
        upx=False,
        strip=False,
        debug=False,
        target_arch="arm64",
    )
    coll = COLLECT(exe, a.binaries, a.datas, name="Appendator", upx=False, strip=False)
    app = BUNDLE(
        coll,
        name="Appendator.app",
        icon="assets/icon.icns",
        bundle_identifier="app.appendator.desktop",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "Appendator",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": "13.0",
            "LSApplicationCategoryType": "public.app-category.productivity",
            "NSHighResolutionCapable": True,
            # La interfaz usa colores claros fijos: se evita el modo oscuro.
            "NSRequiresAquaSystemAppearance": True,
            "NSDownloadsFolderUsageDescription":
                "Appendator guarda el PDF combinado en la carpeta Descargas.",
            "NSDesktopFolderUsageDescription":
                "Appendator necesita leer los PDF y Markdown que elijas.",
            "NSDocumentsFolderUsageDescription":
                "Appendator necesita leer los PDF y Markdown que elijas.",
            "NSRemovableVolumesUsageDescription":
                "Appendator necesita leer los PDF y Markdown que elijas.",
            "NSNetworkVolumesUsageDescription":
                "Appendator necesita leer los PDF y Markdown que elijas.",
        },
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="Appendator",
        icon="assets/icon.ico" if IS_WIN else None,
        console=False,
        upx=False,
        strip=False,
        debug=False,
        version="version_info.txt" if IS_WIN else None,
    )
