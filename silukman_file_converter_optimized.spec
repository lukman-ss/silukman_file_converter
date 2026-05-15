# -*- mode: python ; coding: utf-8 -*-

from pathlib import PureWindowsPath


EXCLUDES = [
    "cv2",
    "numpy",
    "numpy.libs",
    "pandas",
    "scipy",
    "matplotlib",
    "sklearn",
    "torch",
    "tensorflow",
    "paddle",
    "paddleocr",
    "paddlex",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtConcurrent",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNetwork",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtPrintSupport",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtUiTools",
    "PySide6.QtVirtualKeyboard",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "PySide6.QtXml",
]

UNUSED_BINARY_NAMES = {
    "opengl32sw.dll",
    "qt6quick.dll",
    "qt6qml.dll",
    "qt6qmlmodels.dll",
    "qt6qmlworkerscript.dll",
    "qt6pdf.dll",
    "qt6pdfwidgets.dll",
    "qt6virtualkeyboard.dll",
    "qt6webenginecore.dll",
    "qt6webenginewidgets.dll",
    "qt6multimedia.dll",
    "qt6network.dll",
    "qt6opengl.dll",
    "qt6openglwidgets.dll",
    "libcrypto-3-x64.dll",
    "libssl-3-x64.dll",
}

UNUSED_PATH_PARTS = (
    "pyside6\\qml\\",
    "pyside6\\translations\\",
    "pyside6\\plugins\\virtualkeyboard\\",
    "pyside6\\plugins\\qmltooling\\",
    "pyside6\\plugins\\multimedia\\",
    "pyside6\\plugins\\networkinformation\\",
    "pyside6\\plugins\\sqldrivers\\",
    "pyside6\\plugins\\tls\\",
    "pyside6\\plugins\\platforms\\qdirect2d.dll",
    "pyside6\\plugins\\imageformats\\qgif.dll",
    "pyside6\\plugins\\imageformats\\qicns.dll",
    "pyside6\\plugins\\imageformats\\qtga.dll",
    "pyside6\\plugins\\imageformats\\qtiff.dll",
    "pyside6\\plugins\\imageformats\\qwbmp.dll",
    "pyside6\\plugins\\imageformats\\qwebp.dll",
    "pil\\_avif",
    "pil\\_webp",
    "pil\\avifimageplugin.py",
    "pil\\webpimageplugin.py",
    "\\phpwebstudy-data\\app\\php-",
)


def normalized(value):
    return str(value).replace("/", "\\").lower()


def should_keep_toc_entry(entry):
    dest_name = normalized(entry[0])
    source_name = normalized(entry[1]) if len(entry) > 1 else ""
    base_name = PureWindowsPath(dest_name).name.lower()
    if base_name in UNUSED_BINARY_NAMES:
        return False
    combined = f"{dest_name}\\{source_name}"
    return not any(part in combined for part in UNUSED_PATH_PARTS)


def filter_toc(toc):
    return type(toc)(entry for entry in toc if should_keep_toc_entry(entry))


a = Analysis(
    ["app\\main.py"],
    pathex=[],
    binaries=[],
    datas=[("app/core/paddle_ocr_worker.py", "app/core")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=1,
)

a.binaries = filter_toc(a.binaries)
a.datas = filter_toc(a.datas)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="silukman_file_converter_optimized",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
