# Windows Production QA Pipeline

## Purpose

This pipeline prevents broken public releases of `silukman_file_converter`.

It validates:

```text
1. Build/package integrity
2. Frozen EXE behavior
3. OCR runtime readiness
4. Clean Windows compatibility
5. Installer install/uninstall behavior
6. Regression risks around PDF, filenames, permissions, startup, and cleanup
```

## QA Levels

### Level 1 - Automated Dev-Machine QA

Run before every production package:

```powershell
.\run_production_qa.ps1
```

This generates:

```text
output/production_qa/<timestamp>/file.md
output/production_qa/<timestamp>/qa_result.json
output/production_qa/<timestamp>/ocr_bootstrap_status.json
```

Run with the full frozen EXE matrix before release candidate builds:

```powershell
.\run_production_qa.ps1 -RunExeMatrix
```

### Level 2 - Clean Windows QA

Run on a Windows VM or physical machine with:

```text
- No Python installed
- No virtualenv
- No source tree dependencies
- Standard user permissions
- Windows Defender enabled
```

This is mandatory before public production.

### Level 3 - Production Release Gate

Production release is allowed only when:

```text
- Automated QA passes
- Frozen EXE matrix passes
- Clean Windows manual QA passes
- OCR first-run and offline validation pass
- Installer install/uninstall pass
- No release blocker remains
```

## Validation Matrix

| area | automated | manual clean Windows | production gate |
| --- | --- | --- | --- |
| EXE exists | yes | yes | required |
| EXE size budget | yes | no | required |
| Source compile | yes | no | required |
| Unit tests | yes | no | required |
| Release metadata | yes | no | required |
| Frozen EXE sample matrix | optional automated | yes for RC | required |
| OCR bootstrap quick status | yes | yes | required |
| OCR first-run download | no | yes | required |
| Offline OCR after cache | no | yes | required |
| PDF operations | yes via matrix | spot check | required |
| Installer install | no | yes | required |
| Installer uninstall | no | yes | required |
| Startup speed | placeholder | yes | required |
| Memory usage | placeholder | yes | required |
| Temp cleanup | placeholder | yes | required |
| Permission handling | placeholder | yes | required |
| Unicode filenames | matrix/manual | yes | required |
| Long path support | manual | yes | required |
| Defender false positive | no | yes | required |

## Clean Windows Validation Flow

Use a fresh Windows VM snapshot.

### Machine Setup

```text
[ ] Windows 10/11 clean install
[ ] No Python installed
[ ] No Git installed
[ ] No development venv
[ ] Standard user account
[ ] Windows Defender enabled
[ ] Internet available for first-run OCR test
```

### Installer Test

```text
[ ] Run silukman_file_converter_setup.exe
[ ] Install to Program Files
[ ] Create Start Menu shortcut
[ ] Create Desktop shortcut if option exists
[ ] Launch from Start Menu
[ ] Launch from Desktop shortcut
[ ] Confirm no terminal/CMD appears
[ ] Confirm app window is not always-on-top
[ ] Uninstall from Windows Apps/Programs
[ ] Confirm install directory is removed or only expected user data remains
```

### Portable EXE Test

```text
[ ] Run dist/silukman_file_converter.exe or optimized EXE
[ ] Confirm app starts
[ ] Confirm no CMD window appears
[ ] Confirm UI is responsive
[ ] Confirm output folder can be selected
```

## OCR Validation

### First-Run Online

```text
[ ] Start with no PaddleOCR model cache
[ ] Enable internet
[ ] Run OCR image
[ ] Confirm user sees clear setup/status messaging
[ ] Confirm no stack trace is shown
[ ] Confirm OCR output text is created
[ ] Confirm model cache now exists
```

Expected:

```text
status: ocr_ready or success
user message: clear, non-technical
crash: no
```

### Offline After Cache

```text
[ ] Keep model cache from first-run
[ ] Disable internet
[ ] Run OCR image
[ ] Run OCR PDF scan
[ ] Confirm no redownload attempt blocks operation
[ ] Confirm output text is created
```

Expected:

```text
OCR image    : success
OCR PDF scan : success
crash        : no
```

### Offline Before Cache

```text
[ ] Remove or isolate model cache
[ ] Disable internet
[ ] Run OCR image
```

Expected:

```text
status  : ocr_model_not_ready
message : Model OCR belum tersedia. Hubungkan internet lalu jalankan OCR sekali untuk menyiapkan model.
crash   : no
```

### Corrupted Cache

```text
[ ] Create or simulate incomplete OCR model cache
[ ] Disable internet
[ ] Run OCR image
```

Expected:

```text
status  : ocr_health_failed or ocr_model_not_ready
message : clear recovery instruction
crash   : no
```

## PDF Operation Validation

Run the frozen sample matrix:

```powershell
.\run_production_qa.ps1 -RunExeMatrix
```

Required summary:

```text
failed        = 0
partial       = 0
not_configured = 0 for beta-visible features
not_validated  = 0 for beta-visible features
```

Allowed:

```text
not_effective for Compress PDF when compressed size is not smaller
success_short_text for intentionally short dummy text
```

## Startup Speed

Measure both portable EXE and installed shortcut.

Targets:

```text
Cold startup : <= 10 seconds on baseline clean Windows VM
Warm startup : <= 5 seconds on baseline clean Windows VM
```

Record:

```text
- machine specs
- Windows version
- EXE mode: onefile/onedir
- first run vs second run
```

If startup is slow:

```text
- prefer onedir for installed production
- keep onefile for portable builds only when startup and extraction behavior remain acceptable
- avoid importing OCR runtime during app startup
```

## Memory Usage

Record with Task Manager or PowerShell.

Minimum measurements:

```text
[ ] Idle after startup
[ ] PDF to image peak
[ ] OCR image peak
[ ] OCR PDF scan peak
[ ] After operation returns to stable idle
```

Production rule:

```text
Unexpected memory growth after repeated conversions is a blocker.
```

## Temporary File Cleanup

Validate:

```text
[ ] No stale app temp folders after successful conversion
[ ] No unbounded _MEI accumulation after repeated onefile launches
[ ] Failed OCR/conversion does not leave large temporary files
[ ] Output folders contain only expected files
```

## Permission Handling

Test as standard user:

```text
[ ] Output to Documents succeeds
[ ] Output to Desktop succeeds
[ ] Output to Program Files fails gracefully
[ ] Read-only input file is handled
[ ] Missing output permission shows clear error
```

## Filename Compatibility

Test filenames with:

```text
invoice biasa.pdf
tagihan_中文_日本어.pdf
laporan_áéíóú_ñ.pdf
nota panjang dengan spasi dan simbol #1.pdf
very-long-path/<nested folders>/document.pdf
```

Production rule:

```text
Unicode filenames must work.
Long paths must either work or fail with a clear message.
```

## Windows Defender

Before public release:

```text
[ ] Scan EXE
[ ] Scan installer
[ ] Record Defender version and result
[ ] If flagged, stop release and investigate PyInstaller/UPX/signing strategy
```

Recommendation:

```text
For public production, code-sign the EXE and installer.
Consider disabling UPX if false positives appear.
```

## Release Gate Rules

### Internal Beta Entry

Allowed when:

```text
is_frozen            = true
exe_verification     = exe_test_passed
exe_ocr_verification = exe_ocr_passed
failed               = 0
partial              = 0
critical OCR         = success
critical converter   = success
```

### Internal Beta Exit

Allowed when:

```text
[ ] Automated production QA has no fail/blocked checks
[ ] Full EXE matrix passes
[ ] Installer artifact exists
[ ] Clean Windows app launch passes
[ ] OCR first-run and offline validation pass
```

### Production Release

Allowed only when:

```text
[ ] Production candidate criteria pass
[ ] Installer install/uninstall pass
[ ] Startup and memory baselines recorded
[ ] Temp cleanup verified
[ ] Permissions verified
[ ] Unicode/long path validation complete
[ ] Defender scan passes
[ ] Office-to-PDF is either layout-preserving or clearly labeled Basic Text
[ ] README and UI do not claim final production for incomplete features
```

## Regression Prevention

Before every release:

```powershell
.\run_production_qa.ps1 -RunExeMatrix
.\validate_release_package.ps1 -Channel production
```

## Evidence-Based Windows QA Runner

Use the Windows QA runner to collect real evidence before the final gate. The runner only marks a check as `pass` when it has evidence from the current machine. Checks that cannot be proven safely are written as `blocked` with the exact reason.

Recommended command:

```powershell
python tools\windows_qa_runner.py --tester "Your Name" --run-defender-scan --run-ocr-online --run-ocr-offline
```

Runner outputs:

```text
output/production_qa/manual_qa_filled.json
output/production_qa/windows_qa_evidence.md
output/production_qa/evidence/
```

Validate the generated evidence:

```powershell
python tools\manual_qa_checklist.py validate output\production_qa\manual_qa_filled.json
```

Validation exits non-zero until every check is `pass` and every check includes evidence. This is intentional. A blocked clean Windows, Defender, installer, OCR online, or OCR offline check must keep the final decision at `NOT_READY_FOR_PRODUCTION`.

## Clean Windows VM Evidence Import

After running the zero-Python VM package and getting `decision = PASS`, copy `output\production_qa\clean_windows_validation.json` and the adjacent evidence folder back to the development machine. Importing the VM result is production-aware: it validates the schema, rejects malformed evidence, updates `manual_qa_filled.json`, and reruns the final production gate automatically.

```powershell
python tools\import_clean_windows_validation.py path\to\clean_windows_validation.json
```

Import outputs:

```text
summary/vm_import_result.md
output/production_qa/vm_import_result.json
output/production_qa/evidence/clean_windows_import/
```

Use `--skip-production-gate` only for debugging the importer itself:

```powershell
python tools\import_clean_windows_validation.py path\to\clean_windows_validation.json --skip-production-gate
```

## Final Production Gate

Final production gate must include automated QA, the frozen EXE matrix, and Windows QA runner/manual evidence:

```powershell
python tools\windows_qa_runner.py --tester "Your Name" --run-defender-scan --run-ocr-online --run-ocr-offline
python tools\manual_qa_checklist.py validate output\production_qa\manual_qa_filled.json
python tools\production_qa.py --run-exe-matrix --manual-report output\production_qa\manual_qa_filled.json
```

The EXE matrix is executed as per-operation child processes. Each operation has its own timeout, stdout log, stderr log, elapsed time, command, process id, and timeout reason. This prevents one slow conversion from stalling the whole release gate indefinitely.

Useful targeted commands:

```powershell
python tools\production_qa.py --run-exe-matrix --exe-matrix-dry-run
python tools\production_qa.py --run-exe-matrix --exe-matrix-group pdf
python tools\production_qa.py --run-exe-matrix --exe-matrix-group image
python tools\production_qa.py --run-exe-matrix --exe-matrix-group office
python tools\production_qa.py --run-exe-matrix --exe-matrix-group ocr
python tools\production_qa.py --run-exe-matrix --exe-matrix-group security
python tools\production_qa.py --run-exe-matrix --exe-matrix-op pdf_to_png --exe-op-timeout 60
python tools\production_qa.py --run-exe-matrix --exe-matrix-op ocr_txt --exe-matrix-input "02_pdf_scan_no_text_layer/invoice_scan_no_text_layer.pdf" --exe-op-timeout 180
python tools\production_qa.py --resume --run-exe-matrix --exe-matrix-op ocr_txt
```

Per-operation EXE matrix artifacts:

```text
output/production_qa/<timestamp>/exe_matrix.json
output/production_qa/<timestamp>/exe_matrix.md
output/production_qa/<timestamp>/logs/
```

Expected final report files:

```text
output/production_qa/<timestamp>/production_qa_final.json
output/production_qa/<timestamp>/production_qa_final.md
```

Allowed final decisions:

```text
READY_FOR_PRODUCTION
PRODUCTION_CANDIDATE
NOT_READY_FOR_PRODUCTION
```

The final report explicitly separates:

```text
automated QA result
EXE matrix result
Windows QA runner/manual evidence result
final decision
```

Production can be `READY_FOR_PRODUCTION` only when:

```text
automated QA passes
EXE matrix is executed and passes
manual_qa_filled.json exists
every manual/Windows QA check is pass
every manual/Windows QA check has evidence
```

Keep these artifacts:

```text
output/production_qa/<timestamp>/file.md
output/production_qa/<timestamp>/qa_result.json
output/production_qa/<timestamp>/production_qa_final.md
output/production_qa/manual_qa_filled.json
output/production_qa/windows_qa_evidence.md
output/production_qa/evidence/
output/sample_file_matrix or output/<timestamp>/file.md
installer log/screenshot if applicable
Defender scan result
```

Do not ship from a dirty, unvalidated build folder.
