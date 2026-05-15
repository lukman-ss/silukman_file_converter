# Clean Windows Checklist

Run this checklist on a Windows VM that is intended to represent a user machine.

## Machine Requirements

- [ ] Windows VM has no Python installed.
- [ ] Windows VM has no project virtualenv.
- [ ] Windows VM has no source checkout beside the release package.
- [ ] User account is a normal standard user unless the test explicitly requires admin.
- [ ] Release package has been extracted to a writable folder.

## One Command

From the project/release root:

```powershell
powershell -ExecutionPolicy Bypass -File .\qa\clean_windows_runner.ps1
```

Optional explicit paths:

```powershell
powershell -ExecutionPolicy Bypass -File .\qa\clean_windows_runner.ps1 `
  -ExePath .\dist\silukman_file_converter.exe `
  -SamplesPath .\samples `
  -OutputRoot .\output\production_qa
```

## Required Evidence

- [ ] `output\production_qa\clean_windows_validation.json`
- [ ] `output\production_qa\clean_windows_validation.md`
- [ ] `output\production_qa\clean_windows_evidence\python_detection.json`
- [ ] `output\production_qa\clean_windows_evidence\exe_launch.json`
- [ ] `output\production_qa\clean_windows_evidence\dll_loading.json`
- [ ] `output\production_qa\clean_windows_evidence\output_creation.json`

## Pass Rules

- [ ] Python is not detected in PATH.
- [ ] No project virtualenv is detected.
- [ ] EXE artifact exists.
- [ ] EXE launches and stays alive during observation.
- [ ] No immediate missing-DLL crash is observed.
- [ ] A CLI sample operation creates at least one output file.
- [ ] Startup observation passes.

If Python is detected, the clean Windows result must remain `BLOCKED`.
