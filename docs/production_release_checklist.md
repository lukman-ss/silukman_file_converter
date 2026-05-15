# Production Release Checklist

Do not mark a build production-ready until every item is checked.

## Build And Package

- [ ] `VERSION` contains the intended semantic version.
- [ ] `CHANGELOG.md` has a release entry for the version.
- [ ] `RELEASE_MANIFEST.json` matches the version and channel.
- [ ] `dist/silukman_file_converter.exe` exists and is the intended build.
- [ ] `silukman_file_converter.spec` has `console=False`.
- [ ] Release ZIP is built with `build_release_package.ps1`.
- [ ] Package validation passes.

## Installer

- [ ] Inno Setup 6 is installed on the build machine.
- [ ] `build_installer.ps1` creates `dist/silukman_file_converter_setup.exe`.
- [ ] Installer includes `README.md`, `docs/`, and `summary/`.
- [ ] Installer installs into the expected folder.
- [ ] Start Menu shortcut opens the GUI.
- [ ] Desktop shortcut opens the GUI when selected.
- [ ] Uninstall removes the app cleanly.

## Clean Windows

- [ ] Tested on Windows without Python, virtualenv, or development dependencies.
- [ ] App starts without missing DLL errors.
- [ ] No CMD/terminal appears during normal use.
- [ ] Window is not always-on-top.
- [ ] User can choose output folder and write files.

## OCR

- [ ] OCR image works in the EXE.
- [ ] OCR PDF scan works in the EXE.
- [ ] First-run PaddleOCR model setup works with internet.
- [ ] Offline OCR works after model cache exists.
- [ ] Missing model/offline failure shows a user-friendly `ocr_model_not_ready` message.

## Feature Claims

- [ ] Ready features are tested and documented.
- [ ] Basic features are clearly labeled Basic.
- [ ] Coming Soon features are hidden or disabled.
- [ ] Stamp PDF is not described as certificate-backed digital signature.
- [ ] Office-to-PDF production claims are withheld unless layout preservation is validated.

## Final Gate

- [ ] Windows QA runner has been executed:
  `python tools/windows_qa_runner.py --tester "Your Name" --run-defender-scan --run-ocr-online --run-ocr-offline`
- [ ] `output/production_qa/manual_qa_filled.json` exists.
- [ ] `output/production_qa/windows_qa_evidence.md` exists.
- [ ] Evidence logs exist under `output/production_qa/evidence/`.
- [ ] Clean Windows VM evidence has been imported:
  `python tools/import_clean_windows_validation.py path/to/clean_windows_validation.json`
- [ ] VM import report exists:
  `summary/vm_import_result.md`
- [ ] Manual QA evidence validates:
  `python tools/manual_qa_checklist.py validate output/production_qa/manual_qa_filled.json`
- [ ] Final production gate has been executed:
  `python tools/production_qa.py --run-exe-matrix --manual-report output/production_qa/manual_qa_filled.json`
- [ ] EXE matrix per-operation report exists at `output/production_qa/<timestamp>/exe_matrix.json`.
- [ ] EXE matrix Markdown report exists at `output/production_qa/<timestamp>/exe_matrix.md`.
- [ ] EXE matrix logs exist under `output/production_qa/<timestamp>/logs/`.
- [ ] No EXE matrix operation is `blocked` by timeout.
- [ ] Any failed EXE matrix operation can be rerun with `--exe-matrix-op NAME`.
- [ ] Final gate report clearly shows automated QA result.
- [ ] Final gate report clearly shows EXE matrix result.
- [ ] Final gate report clearly shows Windows QA runner/manual evidence result.
- [ ] `output/production_qa/<timestamp>/production_qa_final.md` says `READY_FOR_PRODUCTION`.
- [ ] No check is `blocked`.
- [ ] No check is missing evidence.
