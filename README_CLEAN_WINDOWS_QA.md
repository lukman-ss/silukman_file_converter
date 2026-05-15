# Clean Windows QA Package

This package validates Silukman File Converter on a fresh Windows machine without Python.

## Package Contents

```text
dist/
  silukman_file_converter.exe
  silukman_file_converter_optimized.exe
qa/
  clean_windows_runner.ps1
samples/
README_CLEAN_WINDOWS_QA.md
```

No source code, virtualenv, build folders, Python scripts, or git metadata should be present.

## Run On Clean Windows VM

Open PowerShell in this package folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\qa\clean_windows_runner.ps1
```

The runner does not require Python. It checks:

```text
python.exe not found
py launcher not found
pip not found
no local developer artifacts
EXE launches
no immediate missing DLL failure
sample conversion creates output
```

## Evidence Output

The runner writes:

```text
output\production_qa\clean_windows_validation.json
output\production_qa\clean_windows_validation.md
output\production_qa\evidence\clean_windows\
```

Decision rules:

```text
PASS    = no Python/pip/dev artifacts, EXE launches, DLL smoke check passes, output is created
BLOCKED = Python/pip/dev artifacts exist, so this is not a clean Windows proof
FAILED  = no Python/dev artifacts, but EXE/runtime/output check fails
```

## Copy Evidence Back To Dev Machine

After a PASS result, copy the whole package `output\production_qa\` folder back to the dev machine, or at minimum copy:

```text
output\production_qa\clean_windows_validation.json
output\production_qa\clean_windows_validation.md
output\production_qa\evidence\clean_windows\
```

Then import it on the dev machine:

```powershell
python tools\import_clean_windows_validation.py path\to\clean_windows_validation.json
python tools\windows_qa_runner.py --tester "Your Name" --run-defender-scan
python tools\manual_qa_checklist.py validate output\production_qa\manual_qa_filled.json
```

`clean_windows_no_python` may become `pass` only when imported VM evidence has `decision = PASS` and the required evidence files are present:

```text
python_detection.json
developer_artifacts.json
exe_artifact.json
exe_launch.json
dll_loading.json
output_creation.json
clean_windows_decision.json
```
