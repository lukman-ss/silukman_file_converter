# Windows QA Runner Example

Command:

```powershell
python tools\windows_qa_runner.py --tester "Your Name" --run-defender-scan --run-ocr-online --run-ocr-offline
```

Expected output files:

```text
output\production_qa\manual_qa_filled.json
output\production_qa\windows_qa_evidence.md
output\production_qa\evidence\
```

Example decision on a development machine:

```text
pass    : startup_speed, memory_usage, unicode_filename
blocked : clean_windows_no_python, installer_install_uninstall, permission_standard_user
blocked : ocr_first_run_online or ocr_offline_cache if not executed/proven
blocked : windows_defender_scan if Defender scan is not executed or unavailable
```

Production rule:

```text
No blocked check can be treated as pass.
Every pass must include evidence path or measured result.
The generated manual_qa_filled.json must still be validated by manual_qa_checklist.py.
```
