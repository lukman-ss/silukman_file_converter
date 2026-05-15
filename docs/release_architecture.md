# Release Architecture

## Standard Production Package Layout

Production release ZIPs use this layout:

```text
silukman_file_converter/
|-- app/
|-- dist/
|   `-- silukman_file_converter.exe
|-- docs/
|-- installer/
|   `-- silukman_file_converter.iss
|-- release/
|   |-- internal-beta.json
|   `-- production.json
|-- summary/
|   |-- summary_exe.json
|   |-- summary.md
|   `-- file.md
|-- tests/
|-- tools/
|-- scripts/
|-- CHANGELOG.md
|-- LICENSE
|-- README.md
|-- RELEASE_MANIFEST.json
|-- VERSION
|-- build.ps1
|-- build_installer.ps1
|-- build_release_package.ps1
|-- requirements.txt
`-- silukman_file_converter.spec
```

Generated folders such as `dist/`, `build/`, `output/`, Windows Sandbox files, virtual environments, and historical test ZIPs are not committed to source control.

## Release Channels

- `production`: public release channel. Requires clean Windows, installer, OCR first-run/offline, full EXE matrix, and final evidence gate validation.
- `internal-beta`: optional pre-release channel for internal testers.

## Versioning

Use semantic versioning:

```text
1.0.0
1.0.1
1.1.0
2.0.0
```

Pre-release builds may use suffixes:

```text
1.1.0-rc.1
1.1.0-internal-beta.1
```

Rules:

- Increment `MAJOR` for incompatible behavior or distribution changes.
- Increment `MINOR` for new user-facing features and production-readiness milestones.
- Increment `PATCH` for fixes, validation, packaging, documentation, and security hardening.
- Use `rc.N` for release candidates and `internal-beta.N` only for private testing packages.

## Deterministic ZIP Output

Create production packages with:

```powershell
.\build_release_package.ps1 -Channel production -Version 1.0.0
```

This uses `scripts/build_release_package.py`, which:

- stages files into a clean release directory;
- excludes caches, virtual environments, local QA evidence, historical ZIPs, and build intermediates;
- sorts ZIP entries;
- writes fixed ZIP timestamps;
- validates required files before writing the archive.
