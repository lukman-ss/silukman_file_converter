# Changelog

All notable changes to Silukman File Converter are documented here.

This project follows semantic versioning:

- `MAJOR`: incompatible workflow, file format, or distribution changes.
- `MINOR`: new user-visible features or production-readiness milestones.
- `PATCH`: bug fixes, packaging fixes, documentation, and validation updates.
- Pre-release suffixes use labels such as `-rc.N` or `-internal-beta.N` when needed.

## [1.0.0] - 2026-05-15

### Added

- First production release of Silukman File Converter for Windows.
- Evidence-based production QA gate with automated checks, EXE matrix validation, OCR lifecycle validation, installer validation, clean Windows validation import, and strict manual evidence validation.
- Windows Sandbox clean-machine QA flow for proving no-Python execution.
- Inno Setup installer build and install/uninstall QA automation.
- Public project metadata: MIT license, security policy, contribution guide, release manifest, version file, and production release documentation.
- Lossless DOCX -> PDF -> DOCX round-trip for PDFs created by this application.

### Changed

- Updated application and documentation from internal beta status to production release status.
- Kept advanced or incomplete features honestly labeled as Basic or Coming Soon instead of presenting them as fully production-grade engines.
- Standardized release package metadata around version `1.0.0` and the `production` channel.
- Word to PDF now uses LibreOffice automatically when available, with Basic Text fallback when it is not installed.

### Validation

- Final production gate reached `READY_FOR_PRODUCTION`.
- EXE matrix completed with no failed or blocked operations.
- OCR first-run and offline cache validation passed with evidence.
- Installer build and install/uninstall validation passed with evidence.
- Clean Windows no-Python validation passed with evidence.

### Known Limitations

- Office-to-PDF remains Basic Text conversion unless a layout-preserving engine such as LibreOffice is configured and validated.
- DOCX round-trip recovery requires the PDF to have been created by this application.
- Stamp PDF is a visible stamp workflow, not certificate-backed digital signing.
- Translate PDF, AI Summarizer, PDF/A validation, and real digital signatures remain Coming Soon.
