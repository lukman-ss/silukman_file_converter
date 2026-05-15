# Production Gate Example

Recommended deterministic flow:

```powershell
python tools\windows_qa_runner.py --tester "Your Name" --run-defender-scan --run-ocr-online --run-ocr-offline
python tools\manual_qa_checklist.py validate output\production_qa\manual_qa_filled.json
python tools\production_qa.py --run-exe-matrix --manual-report output\production_qa\manual_qa_filled.json
```

Final report files:

```text
output\production_qa\<timestamp>\production_qa_final.json
output\production_qa\<timestamp>\production_qa_final.md
```

Example blocked decision:

```text
Decision: NOT_READY_FOR_PRODUCTION

Gate Results:
- Automated QA: pass
- EXE matrix: pass
- Windows QA runner/manual evidence: blocker

Blockers:
- Manual QA: clean_windows_no_python status is blocked
- Manual QA: installer_install_uninstall status is blocked
- Manual QA: windows_defender_scan status is blocked
```

Example production decision:

```text
Decision: READY_FOR_PRODUCTION

Gate Results:
- Automated QA: pass
- EXE matrix: pass
- Windows QA runner/manual evidence: pass

Blockers:
- None.
```
