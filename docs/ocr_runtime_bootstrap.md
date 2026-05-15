# OCR Runtime Bootstrap

## Goal

OCR must be safe for non-technical users:

```text
1. Detect runtime availability before OCR starts.
2. Detect missing model cache before offline OCR fails.
3. Allow first-run model preparation when internet is available.
4. Reuse local cache for offline OCR after setup.
5. Return clear statuses instead of raw stack traces.
```

## Runtime Architecture

The desktop EXE keeps PaddleOCR outside the main GUI bundle to keep the app small.

Current runtime lookup order:

```text
1. <project>/.venv_ocr/Scripts/python.exe
2. <cwd>/.venv_ocr/Scripts/python.exe
3. <exe_parent_parent>/.venv_ocr/Scripts/python.exe
4. <exe_parent>/runtime/ocr/python.exe
5. In-process paddleocr import fallback
```

Worker lookup order:

```text
1. <project>/app/core/paddle_ocr_worker.py
2. <cwd>/app/core/paddle_ocr_worker.py
3. <PyInstaller _MEIPASS>/app/core/paddle_ocr_worker.py
4. <exe_parent>/app/core/paddle_ocr_worker.py
```

Production installer recommendation:

```text
Program Files/Silukman File Converter/
  silukman_file_converter.exe
  app/core/paddle_ocr_worker.py
  runtime/ocr/python.exe
  runtime/ocr/Lib/site-packages/...
```

## Bootstrap Flow

Before an OCR operation runs:

```text
1. Check PaddleOCR runtime.
2. Check known model cache folders.
3. Check internet availability.
4. Run a small OCR health-check image through PaddleOCR.
5. If the health check succeeds, continue OCR.
6. If the health check fails because model/cache/download is unavailable, return ocr_model_not_ready.
7. If the runtime is missing, return ocr_runtime_missing.
8. If the cache looks corrupted or OCR cannot initialize, return ocr_health_failed.
```

User-facing first-run message:

```text
Model OCR belum tersedia. Hubungkan internet lalu jalankan OCR sekali untuk menyiapkan model.
```

## Cache Strategy

The bootstrap manager checks these cache folders:

```text
%PADDLEOCR_HOME%
%PADDLE_HOME%
%USERPROFILE%/.paddleocr
%USERPROFILE%/.paddlex
%USERPROFILE%/.paddle
%LOCALAPPDATA%/SilukmanFileConverter/ocr_models
```

Cache is considered present when model-like files are found:

```text
.pdmodel
.pdiparams
.yml
.yaml
.json
.txt
.nb
files containing "inference" in the filename
```

This is a lightweight pre-check. The authoritative validation is the OCR health check.

## Health Check

The health checker creates a small probe image:

```text
SILUKMAN OCR HEALTH 123
```

Then it runs OCR through the same runtime used by real OCR jobs.

Success means:

```text
status  : ocr_ready
message : OCR runtime is ready.
```

Failure statuses:

```text
ocr_runtime_missing : PaddleOCR runtime is not installed or not packaged.
ocr_model_not_ready : model cache is missing and first-run setup cannot complete.
ocr_health_failed   : runtime exists, but OCR initialization/health check failed.
```

## Offline Validation

For production sign-off, run this manual validation:

```text
1. Clean Windows machine, no Python.
2. Install the app.
3. Turn internet on.
4. Run OCR once.
5. Confirm health check and OCR pass.
6. Close app.
7. Turn internet off.
8. Run OCR image and OCR PDF scan again.
9. Confirm no redownload, no crash, and output text is created.
```

Expected offline result after first setup:

```text
ocr_ready
OCR image success
OCR PDF scan success
```

Expected offline result before first setup:

```text
ocr_model_not_ready
Model OCR belum tersedia. Hubungkan internet lalu jalankan OCR sekali untuk menyiapkan model.
```

## Recovery Handling

If the cache is missing:

```text
Show ocr_model_not_ready and ask user to connect internet for first OCR setup.
```

If the cache is corrupted:

```text
Show ocr_health_failed with diagnostics.
Ask user to rerun OCR with internet or clear the OCR model cache.
```

If runtime is missing:

```text
Show ocr_runtime_missing.
Ask user to reinstall the application or install the OCR runtime package.
```

## Files

Implementation:

```text
app/core/ocr_bootstrap.py
app/core/ocr_engine.py
app/core/paddle_ocr_worker.py
app/ui/main_window.py
```

Tests:

```text
tests/test_ocr_model_status.py
```

## Production Notes

The bootstrap manager improves first-run safety, but final production still needs real clean-machine validation:

```text
1. No-Python Windows install test.
2. First-run internet model bootstrap.
3. Offline OCR after cache exists.
4. Corrupted-cache recovery test.
5. Installer packaging of runtime/ocr.
```
