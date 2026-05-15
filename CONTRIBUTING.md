# Contributing

Thank you for improving Silukman File Converter.

## Development Setup

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Run the app from source:

```powershell
python app\main.py
```

## Quality Rules

- Keep user-facing feature labels honest.
- Do not mark unsupported operations as success.
- Do not expose passwords, local machine paths, test documents, private files, or generated QA artifacts in commits.
- Keep Windows GUI builds console-free.
- Keep subprocess calls hidden on Windows when they are part of normal app behavior.
- Preserve `not_effective`, `not_configured`, `not_validated`, and `success_short_text` semantics.

## Checks Before Pull Request

```powershell
python -m compileall -q app tests tools scripts
python -m pytest -q
python tools\production_qa.py --run-exe-matrix
```

For release work, also run the evidence-based production gate described in `README.md`.

## Commit Hygiene

- Commit source, documentation, tests, and scripts.
- Do not commit `dist/`, `build/`, `output/`, virtual environments, Windows Sandbox files, or generated ZIP/EXE artifacts.
- Remove machine-specific paths from examples before committing.
