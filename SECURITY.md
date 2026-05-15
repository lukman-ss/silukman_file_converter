# Security Policy

## Supported Versions

Security fixes are handled for the latest production release.

| Version | Supported |
| --- | --- |
| 1.0.x | Yes |

## Reporting a Vulnerability

Please report suspected security issues through GitHub Security Advisories when available. If private reporting is not available, open a GitHub issue with a minimal description and avoid posting exploit details, credentials, private files, or sensitive logs.

Include:

- affected version
- operating system
- steps to reproduce
- expected behavior
- actual behavior
- relevant logs with secrets removed

The project will avoid requesting or storing private documents. Do not upload confidential PDFs, images, office files, or OCR results unless you have removed sensitive content.

## Dependency and Build Security

Release readiness is evidence-based. A production release requires:

- clean Windows no-Python validation
- installer install/uninstall validation
- OCR first-run and offline validation
- Windows Defender scan when available
- deterministic release package validation

Generated folders such as `dist/`, `build/`, `output/`, virtual environments, and local sandbox artifacts are intentionally excluded from source control.
