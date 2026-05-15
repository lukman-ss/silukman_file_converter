# Final Production Evidence Gate

Command:

```powershell
python tools\production_qa.py --run-exe-matrix --manual-report output\production_qa\manual_qa_filled.json
```

Final decision is evidence-only:

```text
READY_FOR_PRODUCTION
PRODUCTION_CANDIDATE
NOT_READY_FOR_PRODUCTION
```

READY requires:

```text
automated QA pass
EXE matrix pass
OCR validation pass
clean Windows validation pass
installer validation pass
manual QA evidence pass
no blocked checks
no timeouts
no missing evidence
```

Current style of blocker output:

```text
Clean Windows validation: python detected in clean validation machine
Installer validation: installer artifact missing
Installer validation: installer_install evidence missing
```
