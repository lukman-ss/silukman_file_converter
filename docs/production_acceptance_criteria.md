# Production Acceptance Criteria

## Decision Labels

Use only these labels in release notes and QA reports:

```text
READY FOR PRODUCTION CANDIDATE
READY FOR PRODUCTION
NOT READY
```

## Ready For Production Candidate

Required:

```text
[ ] run_production_qa.ps1 automated checks pass
[ ] Full frozen EXE matrix passes
[ ] Installer artifact is generated
[ ] OCR bootstrap manager reports runtime available
[ ] Clean Windows test plan is scheduled and assigned
```

## Ready For Production

Required:

```text
[ ] Production candidate criteria pass
[ ] Clean Windows no-Python app launch passes
[ ] Inno Setup install/uninstall passes
[ ] Start Menu shortcut passes
[ ] Desktop shortcut passes if enabled
[ ] No terminal/CMD appears
[ ] Window is not always-on-top
[ ] OCR first-run online passes
[ ] OCR offline after cache passes
[ ] Offline before cache shows ocr_model_not_ready, not crash
[ ] Corrupted cache has a recovery path
[ ] PDF core operations pass
[ ] Startup speed baseline recorded
[ ] Memory usage baseline recorded
[ ] Temporary file cleanup verified
[ ] Standard-user permission handling verified
[ ] Unicode filename validation passes
[ ] Long path validation passes or fails clearly
[ ] Windows Defender scan passes
[ ] Release package contains VERSION, LICENSE, CHANGELOG, README, docs, installer metadata
```

## Automatic Blockers

Any of these means `NOT READY`:

```text
failed > 0
partial > 0
exe_verification != exe_test_passed
exe_ocr_verification != exe_ocr_passed
Clean Windows launch fails
OCR crashes on first run
OCR offline after cache fails
Installer cannot install or uninstall
Missing DLL on clean Windows
Raw stack trace shown to non-technical user
Feature labeled production-ready while still Basic/Coming Soon
Windows Defender blocks EXE or setup
```

## Manual Sign-Off

Before public release, record:

```text
QA owner:
Machine / VM:
Windows version:
Installer file:
EXE hash:
QA report path:
Sample matrix report path:
Defender scan result:
Decision:
```
