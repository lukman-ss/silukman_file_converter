from __future__ import annotations

import argparse
import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT_DIR / "output" / "production_qa" / "manual_qa_template.json"
CHECKS = [
    ("exe_launch", "EXE launch"),
    ("package_hash", "Package hash"),
    ("clean_windows_no_python", "Clean Windows no-Python validation"),
    ("ocr_first_run_online", "OCR first-run model bootstrap with internet"),
    ("ocr_offline_cache", "OCR offline cache validation"),
    ("installer_install_uninstall", "Installer install/uninstall"),
    ("startup_speed", "Startup speed cold/warm"),
    ("memory_usage", "Memory usage idle/OCR peak"),
    ("temporary_file_cleanup", "Temporary file cleanup"),
    ("permission_standard_user", "Permission handling as standard user"),
    ("unicode_filename", "Unicode filename validation"),
    ("long_path", "Long path validation"),
    ("windows_defender_scan", "Windows Defender scan"),
]
ALLOWED_STATUSES = {"pass", "fail", "blocked"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate, validate, and report manual production QA evidence.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Generate a blank manual QA template.")
    generate.add_argument("--output", default=str(DEFAULT_TEMPLATE))
    generate.add_argument("--tester", default="")
    generate.add_argument("--machine", default="")

    validate = subparsers.add_parser("validate", help="Validate a filled manual QA JSON file.")
    validate.add_argument("input")
    validate.add_argument("--report", default="")

    report = subparsers.add_parser("report", help="Generate Markdown report from a filled manual QA JSON file.")
    report.add_argument("input")
    report.add_argument("--output", default="")

    args = parser.parse_args(argv)
    if args.command == "generate":
        path = Path(args.output).resolve()
        data = build_template(tester=args.tester, machine=args.machine)
        write_json(path, data)
        markdown_path = path.with_suffix(".md")
        markdown_path.write_text(render_markdown(data, validate_data(data)), encoding="utf-8")
        print(json.dumps({"template": str(path), "report": str(markdown_path)}, indent=2))
        return 0

    if args.command == "validate":
        path = Path(args.input).resolve()
        data = read_json(path)
        result = validate_data(data)
        report_path = Path(args.report).resolve() if args.report else path.with_suffix(".md")
        report_path.write_text(render_markdown(data, result), encoding="utf-8")
        print(json.dumps({"input": str(path), "report": str(report_path), "result": result}, indent=2))
        return 0 if result["production_signoff_allowed"] else 1

    if args.command == "report":
        path = Path(args.input).resolve()
        data = read_json(path)
        result = validate_data(data)
        report_path = Path(args.output).resolve() if args.output else path.with_suffix(".md")
        report_path.write_text(render_markdown(data, result), encoding="utf-8")
        print(json.dumps({"input": str(path), "report": str(report_path), "result": result}, indent=2))
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")


def build_template(tester: str = "", machine: str = "") -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "schema_version": 1,
        "app": "silukman_file_converter",
        "qa_type": "manual_production",
        "created_at": now,
        "updated_at": "",
        "tester_name": tester,
        "machine_info": machine or default_machine_info(),
        "instructions": {
            "status": "Each check must be pass, fail, or blocked.",
            "evidence": "Required. Use file paths, screenshots, logs, hashes, scan results, or concise observed measurements.",
            "production_rule": "Production sign-off is rejected if any check is missing, not pass, or has empty evidence.",
        },
        "checks": [
            {
                "id": check_id,
                "name": name,
                "status": "",
                "evidence": "",
                "machine_info": machine or default_machine_info(),
                "tester_name": tester,
                "timestamp": "",
                "notes": "",
            }
            for check_id, name in CHECKS
        ],
    }


def validate_data(data: dict[str, Any]) -> dict[str, Any]:
    problems: list[str] = []
    checks = data.get("checks")
    if not isinstance(checks, list):
        return {
            "production_signoff_allowed": False,
            "missing_checks": [check_id for check_id, _ in CHECKS],
            "problems": ["checks must be a list"],
            "summary": {"pass": 0, "fail": 0, "blocked": 0, "invalid": len(CHECKS)},
        }

    by_id = {str(check.get("id")): check for check in checks if isinstance(check, dict)}
    missing = [check_id for check_id, _ in CHECKS if check_id not in by_id]
    if missing:
        problems.append(f"Missing required checks: {', '.join(missing)}")

    summary = {"pass": 0, "fail": 0, "blocked": 0, "invalid": 0}
    for check_id, name in CHECKS:
        check = by_id.get(check_id)
        if not check:
            summary["invalid"] += 1
            continue
        status = str(check.get("status", "")).strip().lower()
        if status not in ALLOWED_STATUSES:
            summary["invalid"] += 1
            problems.append(f"{check_id}: status must be pass/fail/blocked.")
            continue
        summary[status] += 1
        for field in ("evidence", "machine_info", "tester_name", "timestamp"):
            if not str(check.get(field, "")).strip():
                problems.append(f"{check_id}: {field} is required.")
        if status != "pass":
            problems.append(f"{check_id}: status is {status}, production sign-off requires pass.")
        if not str(check.get("evidence", "")).strip():
            problems.append(f"{check_id}: evidence is empty.")

    production_signoff_allowed = not problems and summary["pass"] == len(CHECKS)
    return {
        "production_signoff_allowed": production_signoff_allowed,
        "missing_checks": missing,
        "problems": problems,
        "actionable_blockers": [classify_manual_problem(problem) for problem in problems],
        "summary": summary,
    }


def classify_manual_problem(problem: str) -> dict[str, str]:
    lower = problem.lower()
    if "installer_install_uninstall" in lower:
        blocker_type = "missing_admin"
        cause = "Installer install/uninstall evidence is not passing."
        why = "Production requires proof that the setup installs to Program Files, creates shortcuts, launches, uninstalls, and cleans up."
        auto_fix = "no"
        command = (
            f"Auto: python tools\\installer_build_qa.py --run-installer-test --auto-elevate; "
            f"Manual UAC: powershell Start-Process powershell -Verb RunAs, then run: cd {ROOT_DIR}; python tools\\installer_build_qa.py --run-installer-test"
        )
        estimate = "5-10 minutes after an elevated PowerShell is available."
    elif "clean_windows_no_python" in lower:
        blocker_type = "external_vm_required"
        cause = "Clean Windows no-Python evidence is missing, blocked, or failed."
        why = "This can pass only from a clean Windows VM/machine where Python, pip, venv, source code, and build tools are absent."
        auto_fix = "no"
        command = "Run in clean VM: powershell -ExecutionPolicy Bypass -File .\\qa\\clean_windows_runner.ps1; then import: python tools\\import_clean_windows_validation.py path\\to\\clean_windows_validation.json"
        estimate = "10-20 minutes plus VM startup time."
    elif "evidence" in lower:
        blocker_type = "evidence_missing"
        cause = "Required evidence is empty or missing."
        why = "Production sign-off requires file paths, logs, screenshots, hashes, or measurements."
        auto_fix = "partial"
        command = "python tools\\windows_qa_runner.py --tester \"Your Name\" --run-defender-scan"
        estimate = "5-15 minutes depending on the check."
    elif "missing required checks" in lower:
        blocker_type = "evidence_missing"
        cause = "Manual QA report is missing required check entries."
        why = "The final gate requires a complete manual evidence schema."
        auto_fix = "yes"
        command = "python tools\\manual_qa_checklist.py generate --tester \"Your Name\" --output output\\production_qa\\manual_qa_template.json"
        estimate = "1-3 minutes to regenerate the template."
    else:
        blocker_type = "runtime_failure"
        cause = "Manual QA check is not passing."
        why = "Every manual QA check must pass before production sign-off."
        auto_fix = "partial"
        command = "Inspect the check evidence path, fix the cause, then rerun: python tools\\manual_qa_checklist.py validate output\\production_qa\\manual_qa_filled.json"
        estimate = "Depends on the failed check; usually 5-30 minutes."
    return {
        "problem": problem,
        "type": blocker_type,
        "exact_cause": cause,
        "why_blocked": why,
        "auto_fix_possible": auto_fix,
        "next_command": command,
        "estimated_remaining_work": estimate,
    }


def render_markdown(data: dict[str, Any], result: dict[str, Any]) -> str:
    lines = [
        "# Manual Production QA Checklist",
        "",
        f"App: `{data.get('app', 'silukman_file_converter')}`",
        f"Tester: `{data.get('tester_name', '')}`",
        f"Machine: `{data.get('machine_info', '')}`",
        f"Decision: `{'READY FOR PRODUCTION SIGN-OFF' if result['production_signoff_allowed'] else 'BLOCKED'}`",
        "",
        "## Summary",
        "",
        *[f"- {key}: {value}" for key, value in result["summary"].items()],
        "",
        "## Checks",
        "",
        "| check | status | evidence | machine_info | tester | timestamp | notes |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for check in data.get("checks", []):
        lines.append(
            "| "
            + " | ".join(
                [
                    escape_md(check.get("name", check.get("id", ""))),
                    escape_md(check.get("status", "")),
                    escape_md(check.get("evidence", "")),
                    escape_md(check.get("machine_info", "")),
                    escape_md(check.get("tester_name", "")),
                    escape_md(check.get("timestamp", "")),
                    escape_md(check.get("notes", "")),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Blocking Problems", ""])
    if result["problems"]:
        lines.extend(f"- {escape_md(problem)}" for problem in result["problems"])
    else:
        lines.append("- None.")
    actionable = result.get("actionable_blockers", [])
    if actionable:
        lines.extend(
            [
                "",
                "## Next Actions",
                "",
                "| type | exact cause | why blocked | auto-fix | next command | estimate |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for blocker in actionable:
            lines.append(
                "| "
                + " | ".join(
                    [
                        escape_md(blocker.get("type", "")),
                        escape_md(blocker.get("exact_cause", "")),
                        escape_md(blocker.get("why_blocked", "")),
                        escape_md(blocker.get("auto_fix_possible", "")),
                        escape_md(blocker.get("next_command", "")),
                        escape_md(blocker.get("estimated_remaining_work", "")),
                    ]
                )
                + " |"
            )
    lines.extend(
        [
            "",
            "## Production Rule",
            "",
            "Production sign-off is rejected if any required check is missing, any status is not pass, or any evidence field is empty.",
        ]
    )
    return "\n".join(lines)


def default_machine_info() -> str:
    return f"{platform.platform()} | {platform.machine()} | {platform.processor()}".strip()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def escape_md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
