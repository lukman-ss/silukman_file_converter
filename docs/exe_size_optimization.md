# EXE Size Optimization

## Current Result

The optimized Windows GUI build is available at:

```text
dist/silukman_file_converter_optimized.exe
```

Measured size:

```text
Original EXE   : 123.73 MiB
Optimized EXE  : 51.26 MiB
Reduction      : 72.47 MiB / 58.6%
```

The optimized EXE passed the frozen EXE sample matrix:

```text
Run file.md          : output/20260514105959/file.md
is_frozen            : true
exe_verification     : exe_test_passed
exe_ocr_verification : exe_ocr_passed
success              : 198
success_short_text   : 1
failed               : 0
partial              : 0
not_effective        : 2
production readiness : READY_FOR_PRODUCTION when the final production gate passes
final production     : READY when the full production gate passes
```

## Root Cause Analysis

The original onefile EXE bundled about 303 MiB of referenced binaries before PyInstaller compression. The largest entries were:

```text
cv2/cv2.pyd                                      71.35 MiB
cv2/opencv_videoio_ffmpeg4130_64.dll            27.25 MiB
pymupdf/mupdfcpp64.dll                          24.46 MiB
PySide6/opengl32sw.dll                          19.68 MiB
numpy.libs/libscipy_openblas64_*.dll            19.47 MiB
pymupdf/_mupdf.pyd                              11.73 MiB
PySide6/Qt6Core.dll                             10.00 MiB
PySide6/Qt6Gui.dll                               9.10 MiB
PIL/_avif*.pyd                                   7.53 MiB
PySide6/Qt6Quick.dll                             6.28 MiB
PySide6/Qt6Qml.dll                               5.12 MiB
```

Main causes:

```text
1. OpenCV was imported at module import time even though OCR runs through an external worker.
2. NumPy/OpenBLAS came along with OpenCV.
3. PyInstaller collected unused Qt modules/plugins such as QML, Quick, Pdf, OpenGL software renderer, translations, and extra image plugins.
4. Pillow AVIF/WebP support was bundled although the app only needs common PNG/JPEG paths for current workflows.
5. Duplicate OpenSSL/PHP-path DLLs could be collected from the local PATH if not filtered carefully.
```

## Implemented Changes

### 1. Optional OpenCV Preprocessing

`app/core/image_service.py` no longer imports `cv2` and `numpy` at module import time.

The OCR preprocessing path now:

```text
1. Uses OpenCV if available.
2. Falls back to Pillow-only preprocessing if OpenCV is unavailable or disabled.
3. Supports SILUKMAN_DISABLE_CV2_PREPROCESS=1 for optimized builds/tests.
```

This allows the main EXE to exclude OpenCV while preserving OCR through the existing external PaddleOCR worker.

### 2. Lazy OCR Engine Construction

`app/core/converter.py` now creates `OCREngine` only when an OCR operation is executed.

Benefit:

```text
- Faster non-OCR startup path
- Cleaner dependency graph
- Less accidental import pressure during PyInstaller analysis
```

### 3. Optimized PyInstaller Spec

Added:

```text
silukman_file_converter_optimized.spec
build_optimized.ps1
```

The optimized spec excludes:

```text
cv2
numpy / numpy.libs
paddle / paddleocr / paddlex from the main EXE
pandas / scipy / matplotlib / sklearn / torch / tensorflow
unused PySide6 modules: QtQml, QtQuick, QtPdf, QtOpenGL, QtVirtualKeyboard, WebEngine, Multimedia, etc.
unused Qt plugins/translations
Pillow AVIF/WebP binaries
duplicate PHP-path OpenSSL DLLs
```

Build command:

```powershell
.\build_optimized.ps1
```

## Verification

Source-level focused tests:

```text
venv\Scripts\python.exe -m py_compile app\core\image_service.py app\core\converter.py
venv\Scripts\python.exe -m pytest tests\test_ocr_model_status.py tests\test_currency.py -q
$env:SILUKMAN_DISABLE_CV2_PREPROCESS='1'; venv\Scripts\python.exe tests\test_operations.py
```

Results:

```text
currency/model tests : 7 passed
operation test       : 39 success, 0 failed, 0 partial
```

Frozen optimized EXE matrix:

```powershell
$p = Start-Process -FilePath (Resolve-Path 'dist\silukman_file_converter_optimized.exe') `
  -ArgumentList @('--sample-matrix','--samples',(Resolve-Path 'samples').Path,'--output',(Resolve-Path 'output').Path,'--source-label','exe-optimized-windowed') `
  -WorkingDirectory (Resolve-Path '.').Path -PassThru
Wait-Process -Id $p.Id -Timeout 2400
```

Result file:

```text
output/20260514105959/file.md
```

## Onefile vs Onedir

Recommended production strategy:

```text
Internal beta portable artifact : onefile, optimized
Installed production artifact   : onedir wrapped by Inno Setup
```

Tradeoffs:

```text
onefile
- Easier to share
- Smaller single artifact
- Slower startup because it extracts to a temp directory

onedir
- Faster startup
- Easier to inspect and patch runtime files
- Better for separating OCR runtime/models
- Needs installer or folder packaging to avoid user confusion
```

For public production, prefer:

```text
Inno Setup installer -> onedir app payload -> external OCR runtime/model cache
```

## OCR Packaging Strategy

Current optimized EXE keeps PaddleOCR out of the main executable.

Recommended production architecture:

```text
app/
runtime/
  ocr/
    python.exe or embedded OCR runtime
    paddleocr dependencies
models/
  paddleocr/
cache/
logs/
```

This keeps the GUI/converter EXE small while allowing:

```text
- first-run OCR model bootstrap
- offline OCR after cache exists
- independent OCR runtime updates
- smaller GUI-only updates
```

## Production Gate Requirements

The optimized build is production-valid only after the final evidence gate passes. Required evidence includes:

```text
1. Clean Windows no-Python test
2. PaddleOCR first-run model download validation
3. Offline OCR cache validation
4. Inno Setup installer generation
5. Office-to-PDF is either layout-preserving or clearly labeled Basic Text
6. Optional onedir installer build for faster startup
```

Do not label a rebuilt artifact production-ready until these checks pass for that artifact.
