# VM Validation Guide

Use this guide to prove clean Windows compatibility without relying on assumptions from the development machine.

## Prepare VM

1. Install a fresh Windows VM.
2. Do not install Python.
3. Do not install project dependencies.
4. Copy the release package ZIP to the VM.
5. Extract the ZIP to a normal user-writable folder such as:

```text
C:\Users\<user>\Downloads\silukman_file_converter
```

## Run Validation

Open PowerShell in the extracted release root and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\qa\clean_windows_runner.ps1
```

The script writes:

```text
output\production_qa\clean_windows_validation.json
output\production_qa\clean_windows_validation.md
output\production_qa\clean_windows_evidence\
```

## Interpret Result

`PASS` means:

- Python was not detected in PATH.
- EXE launched.
- DLL loading smoke check did not crash immediately.
- Startup observation passed.
- Output creation was proven through a sample CLI operation.

`BLOCKED` means the VM is not clean enough or required proof could not be collected.

`FAILED` means a real runtime validation failed and the build must not be promoted.

## Attach Evidence

Copy these files back into the release evidence folder:

```text
clean_windows_validation.json
clean_windows_validation.md
clean_windows_evidence\
```

Do not mark production ready without this evidence.
