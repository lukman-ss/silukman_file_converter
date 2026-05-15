# Production Blocked Example

```text
Decision: NOT_READY_FOR_PRODUCTION
```

Example exact blockers:

```text
Manual QA: clean_windows_no_python: status is blocked, production sign-off requires pass.
Manual QA: installer_install_uninstall: status is blocked, production sign-off requires pass.
Clean Windows validation: python detected in clean validation machine
Clean Windows validation: clean Windows no-Python decision is not pass
Installer validation: installer artifact missing
Installer validation: Program Files install validation requires an elevated shell.
Installer validation: installer_install evidence missing
Installer validation: installer_uninstall evidence missing
```

This is intentional. The gate must not say production is ready until VM clean Windows evidence and installer install/uninstall evidence both pass.
