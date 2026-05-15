from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT_DIR / "output" / "production_qa"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import clean Windows VM validation evidence into production QA output.")
    parser.add_argument("source", help="Path to clean_windows_validation.json copied from the VM package output.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--manual-report", default="", help="Manual QA JSON to update. Defaults to output/manual_qa_filled.json.")
    parser.add_argument("--skip-production-gate", action="store_true", help="Import evidence without rerunning the final production gate.")
    parser.add_argument("--production-gate-timeout", type=int, default=3600, help="Timeout in seconds for the production gate rerun.")
    args = parser.parse_args(argv)

    source = Path(args.source).resolve()
    output = Path(args.output).resolve()
    manual_report = Path(args.manual_report).resolve() if args.manual_report else output / "manual_qa_filled.json"
    evidence_dir = output / "evidence" / "clean_windows_import"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    result = import_validation(
        source,
        output,
        evidence_dir,
        manual_report,
        rerun_production_gate=not args.skip_production_gate,
        production_gate_timeout=args.production_gate_timeout,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["imported"] and result["decision"] == "PASS" and result.get("production_gate", {}).get("ran", False) else 1


def import_validation(
    source: Path,
    output: Path,
    evidence_dir: Path,
    manual_report: Path,
    *,
    rerun_production_gate: bool,
    production_gate_timeout: int,
) -> dict[str, Any]:
    if not source.exists():
        result = {"imported": False, "decision": "", "reason": f"Source not found: {source}"}
        write_json(evidence_dir / "clean_windows_import.json", result)
        write_import_markdown(result)
        return result

    try:
        data = json.loads(source.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        result = {"imported": False, "decision": "", "reason": f"Malformed JSON: {exc}"}
        write_json(evidence_dir / "clean_windows_import.json", result)
        write_import_markdown(result)
        return result
    if not isinstance(data, dict):
        result = {"imported": False, "decision": "", "reason": "Malformed evidence: top-level JSON must be an object."}
        write_json(evidence_dir / "clean_windows_import.json", result)
        write_import_markdown(result)
        return result

    decision = str(data.get("decision", "")).upper()
    source_evidence = resolve_evidence_dir(source, data)
    validation = validate_clean_windows_data(data, source_evidence)
    schema_validation = validation.get("schema", {})
    if not schema_validation.get("valid", False):
        result = {
            "imported": False,
            "decision": decision,
            "reason": "Clean Windows VM evidence schema is invalid.",
            "validation": validation,
            "source": str(source),
            "imported_at": datetime.now().isoformat(timespec="seconds"),
        }
        write_json(evidence_dir / "clean_windows_import.json", result)
        write_import_markdown(result)
        return result

    target = output / "clean_windows_validation.json"
    if not same_path(source, target):
        shutil.copy2(source, target)

    source_root = source.parent
    copied_files: list[str] = [str(target)]
    for name in ["clean_windows_validation.md"]:
        candidate = source_root / name
        if candidate.exists():
            destination = output / name
            if not same_path(candidate, destination):
                shutil.copy2(candidate, destination)
            copied_files.append(str(destination))

    if source_evidence and source_evidence.exists():
        destination_evidence = output / "evidence" / "clean_windows"
        if same_path(source_evidence, destination_evidence):
            copied_files.append(str(destination_evidence))
        else:
            if destination_evidence.exists():
                shutil.rmtree(destination_evidence)
            shutil.copytree(source_evidence, destination_evidence)
            copied_files.append(str(destination_evidence))

    manual_update = update_manual_report(manual_report, target, output / "evidence" / "clean_windows", data, validation)
    production_gate = (
        rerun_final_production_gate(output, manual_report, evidence_dir, production_gate_timeout)
        if rerun_production_gate
        else {"ran": False, "reason": "Skipped by --skip-production-gate."}
    )
    result = {
        "imported": True,
        "decision": decision,
        "validation": validation,
        "source": str(source),
        "target": str(target),
        "copied_files": copied_files,
        "manual_report": str(manual_report),
        "manual_update": manual_update,
        "production_gate": production_gate,
        "imported_at": datetime.now().isoformat(timespec="seconds"),
        "next_step": "Review summary\\vm_import_result.md and the latest production QA final report.",
    }
    write_json(evidence_dir / "clean_windows_import.json", result)
    write_json(output / "vm_import_result.json", result)
    write_import_markdown(result)
    return result


def validate_clean_windows_data(data: dict[str, Any], source_evidence: Path | None) -> dict[str, Any]:
    checks = data.get("checks") if isinstance(data.get("checks"), list) else []
    by_id = {str(check.get("id")): check for check in checks if isinstance(check, dict)}
    decision = str(data.get("decision", "")).upper()
    required_pass = [
        "python_path_detection",
        "developer_artifacts",
        "exe_artifact",
        "exe_launch",
        "dll_loading",
        "output_creation",
        "clean_windows_no_python",
    ]
    schema_errors = validate_schema(data, by_id)
    statuses = {check_id: str(by_id.get(check_id, {}).get("status", "")).lower() for check_id in required_pass}
    missing = [check_id for check_id in required_pass if check_id not in by_id]
    non_pass = [check_id for check_id, status in statuses.items() if status != "pass"]
    python_check = by_id.get("python_path_detection", {})
    python_details = python_check.get("details", {}) if isinstance(python_check.get("details"), dict) else {}
    python_commands = ["python", "py", "python3", "pip", "pip3"]
    detected_python_tools = [name for name in python_commands if str(python_details.get(name, "")).strip()]
    has_python = str(python_check.get("status", "")).lower() != "pass" or bool(detected_python_tools)
    output_check = by_id.get("output_creation", {})
    output_details = output_check.get("details", {}) if isinstance(output_check.get("details"), dict) else {}
    created_outputs = output_details.get("created_outputs", [])
    output_generated = isinstance(created_outputs, list) and bool(created_outputs)
    exe_launch_pass = str(by_id.get("exe_launch", {}).get("status", "")).lower() == "pass"
    expected_evidence_files = [
        "python_detection.json",
        "developer_artifacts.json",
        "exe_artifact.json",
        "exe_launch.json",
        "dll_loading.json",
        "output_creation.json",
        "clean_windows_decision.json",
    ]
    missing_evidence_files: list[str] = []
    if not source_evidence or not source_evidence.exists():
        missing_evidence_files = expected_evidence_files
    else:
        missing_evidence_files = [
            name for name in expected_evidence_files if not (source_evidence / name).exists()
        ]
    missing_check_evidence = []
    for check_id in required_pass:
        evidence = str(by_id.get(check_id, {}).get("evidence", "")).strip()
        expected_name = expected_evidence_file_for_check(check_id)
        if not evidence:
            missing_check_evidence.append(f"{check_id}: evidence field is empty")
        elif source_evidence and expected_name and not (source_evidence / expected_name).exists():
            missing_check_evidence.append(f"{check_id}: {expected_name} not found")

    is_valid_pass = (
        decision == "PASS"
        and not schema_errors
        and not missing
        and not non_pass
        and not missing_evidence_files
        and not missing_check_evidence
        and not has_python
        and exe_launch_pass
        and output_generated
    )
    return {
        "schema": {"valid": not schema_errors, "errors": schema_errors},
        "decision": decision,
        "is_valid_pass": is_valid_pass,
        "missing_checks": missing,
        "non_pass_checks": non_pass,
        "source_evidence": str(source_evidence) if source_evidence else "",
        "missing_evidence_files": missing_evidence_files,
        "missing_check_evidence": missing_check_evidence,
        "python_detected_or_unproven": has_python,
        "detected_python_tools": detected_python_tools,
        "exe_launch_pass": exe_launch_pass,
        "output_generated": output_generated,
    }


def validate_schema(data: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1.")
    if data.get("app") != "silukman_file_converter":
        errors.append("app must be silukman_file_converter.")
    if data.get("qa_type") != "clean_windows_validation":
        errors.append("qa_type must be clean_windows_validation.")
    if str(data.get("decision", "")).upper() not in {"PASS", "BLOCKED", "FAILED"}:
        errors.append("decision must be PASS, BLOCKED, or FAILED.")
    if not isinstance(data.get("machine_info"), dict):
        errors.append("machine_info must be an object.")
    if not isinstance(data.get("summary"), dict):
        errors.append("summary must be an object.")
    checks = data.get("checks")
    if not isinstance(checks, list):
        errors.append("checks must be a list.")
        return errors
    for check_id, check in by_id.items():
        if not isinstance(check.get("status"), str):
            errors.append(f"{check_id}: status must be a string.")
        if not str(check.get("evidence", "")).strip():
            errors.append(f"{check_id}: evidence must be non-empty.")
        if not isinstance(check.get("details", {}), dict):
            errors.append(f"{check_id}: details must be an object.")
    return errors


def expected_evidence_file_for_check(check_id: str) -> str:
    return {
        "python_path_detection": "python_detection.json",
        "developer_artifacts": "developer_artifacts.json",
        "exe_artifact": "exe_artifact.json",
        "exe_launch": "exe_launch.json",
        "dll_loading": "dll_loading.json",
        "output_creation": "output_creation.json",
        "clean_windows_no_python": "clean_windows_decision.json",
    }.get(check_id, "")


def resolve_evidence_dir(source: Path, data: dict[str, Any]) -> Path | None:
    raw = str(data.get("evidence_dir", "")).strip()
    candidates = []
    if raw:
        candidates.append(Path(raw))
    candidates.append(source.parent / "evidence" / "clean_windows")
    candidates.append(source.parent / "clean_windows_evidence")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def update_manual_report(
    manual_report: Path,
    validation_target: Path,
    evidence_target: Path,
    data: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any]:
    if not manual_report.exists():
        return {"updated": False, "reason": f"Manual QA report not found: {manual_report}"}
    manual = json.loads(manual_report.read_text(encoding="utf-8-sig"))
    checks = manual.get("checks")
    if not isinstance(checks, list):
        return {"updated": False, "reason": "manual_qa_filled.json has no checks list."}

    decision = validation["decision"]
    if validation["is_valid_pass"]:
        status = "pass"
        notes = "Imported clean Windows VM evidence passed: no Python/pip/dev artifacts and EXE runtime checks passed."
    elif decision == "FAILED":
        status = "fail"
        notes = "Imported clean Windows VM evidence failed runtime checks."
    else:
        status = "blocked"
        blockers = []
        if validation.get("missing_checks"):
            blockers.append("missing checks: " + ", ".join(validation["missing_checks"]))
        if validation.get("non_pass_checks"):
            blockers.append("non-pass checks: " + ", ".join(validation["non_pass_checks"]))
        if validation.get("missing_evidence_files"):
            blockers.append("missing evidence files: " + ", ".join(validation["missing_evidence_files"]))
        if validation.get("missing_check_evidence"):
            blockers.append("missing check evidence: " + ", ".join(validation["missing_check_evidence"]))
        if validation.get("python_detected_or_unproven"):
            detected = ", ".join(validation.get("detected_python_tools") or [])
            blockers.append("Python/pip absence is not proven" + (f" ({detected})" if detected else ""))
        if not validation.get("exe_launch_pass"):
            blockers.append("EXE launch pass is not proven")
        if not validation.get("output_generated"):
            blockers.append("sample output generation is not proven")
        if not validation.get("schema", {}).get("valid", False):
            blockers.append("schema errors: " + ", ".join(validation.get("schema", {}).get("errors", [])))
        details = "; ".join(blockers) if blockers else "decision is not PASS"
        notes = f"Imported clean Windows evidence is not a valid PASS: {details}."

    evidence = f"{validation_target}; {evidence_target}"
    machine = machine_info_string(data.get("machine_info"))
    tester = str(manual.get("tester_name") or "")
    timestamp = datetime.now().isoformat(timespec="seconds")
    updated = False
    for check in checks:
        if isinstance(check, dict) and check.get("id") == "clean_windows_no_python":
            check.update(
                {
                    "status": status,
                    "evidence": evidence,
                    "machine_info": machine or check.get("machine_info", ""),
                    "tester_name": check.get("tester_name") or tester,
                    "timestamp": timestamp,
                    "notes": notes,
                }
            )
            updated = True
            break
    if not updated:
        checks.append(
            {
                "id": "clean_windows_no_python",
                "name": "Clean Windows no-Python validation",
                "status": status,
                "evidence": evidence,
                "machine_info": machine,
                "tester_name": tester,
                "timestamp": timestamp,
                "notes": notes,
            }
        )
    manual["updated_at"] = timestamp
    write_json(manual_report, manual)
    return {"updated": True, "status": status, "notes": notes}


def rerun_final_production_gate(output: Path, manual_report: Path, evidence_dir: Path, timeout: int) -> dict[str, Any]:
    stdout_path = evidence_dir / "production_gate.stdout.log"
    stderr_path = evidence_dir / "production_gate.stderr.log"
    command = [
        sys.executable,
        str(ROOT_DIR / "tools" / "production_qa.py"),
        "--run-exe-matrix",
        "--manual-report",
        str(manual_report),
    ]
    started = datetime.now()
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT_DIR,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        final_report = newest_file(output, "production_qa_final.json")
        final_data = json.loads(final_report.read_text(encoding="utf-8-sig")) if final_report else {}
        return {
            "ran": True,
            "command": " ".join(command),
            "exit_code": completed.returncode,
            "elapsed_seconds": round((datetime.now() - started).total_seconds(), 3),
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "final_report": str(final_report) if final_report else "",
            "final_decision": final_data.get("decision", ""),
            "blockers": final_data.get("blockers", []),
        }
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        return {
            "ran": True,
            "command": " ".join(command),
            "exit_code": None,
            "timed_out": True,
            "timeout_seconds": timeout,
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "final_decision": "",
            "blockers": [f"Production gate timed out after {timeout} seconds."],
        }


def newest_file(root: Path, name: str) -> Path | None:
    candidates = [path for path in root.glob(f"*/{name}") if path.is_file()]
    if not candidates:
        direct = root / name
        return direct if direct.exists() else None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def write_import_markdown(result: dict[str, Any]) -> None:
    summary_dir = ROOT_DIR / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    validation = result.get("validation", {}) if isinstance(result.get("validation"), dict) else {}
    gate = result.get("production_gate", {}) if isinstance(result.get("production_gate"), dict) else {}
    lines = [
        "# VM Import Result",
        "",
        f"Imported: `{result.get('imported', False)}`",
        f"Decision: `{result.get('decision', '')}`",
        f"Source: `{result.get('source', '')}`",
        f"Imported at: `{result.get('imported_at', '')}`",
        "",
        "## Evidence Validation",
        "",
        f"- Schema valid: `{validation.get('schema', {}).get('valid', False)}`",
        f"- Valid clean Windows pass: `{validation.get('is_valid_pass', False)}`",
        f"- Python detected/unproven: `{validation.get('python_detected_or_unproven', '')}`",
        f"- EXE launch pass: `{validation.get('exe_launch_pass', '')}`",
        f"- Output generated: `{validation.get('output_generated', '')}`",
        f"- Missing checks: `{', '.join(validation.get('missing_checks', []) or [])}`",
        f"- Non-pass checks: `{', '.join(validation.get('non_pass_checks', []) or [])}`",
        f"- Missing evidence files: `{', '.join(validation.get('missing_evidence_files', []) or [])}`",
        "",
        "## Production Gate",
        "",
        f"- Ran: `{gate.get('ran', False)}`",
        f"- Exit code: `{gate.get('exit_code', '')}`",
        f"- Final decision: `{gate.get('final_decision', '')}`",
        f"- Final report: `{gate.get('final_report', '')}`",
        "",
        "## Blockers",
        "",
    ]
    blockers = gate.get("blockers") or validation_blockers(validation) or [result.get("reason", "")]
    blockers = [str(item) for item in blockers if str(item).strip()]
    if blockers:
        lines.extend(f"- {item}" for item in blockers)
    else:
        lines.append("- None.")
    (summary_dir / "vm_import_result.md").write_text("\n".join(lines), encoding="utf-8")


def validation_blockers(validation: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    schema = validation.get("schema", {}) if isinstance(validation.get("schema"), dict) else {}
    for error in schema.get("errors", []) or []:
        blockers.append(f"schema: {error}")
    for check_id in validation.get("missing_checks", []) or []:
        blockers.append(f"missing check: {check_id}")
    for check_id in validation.get("non_pass_checks", []) or []:
        blockers.append(f"non-pass check: {check_id}")
    for item in validation.get("missing_evidence_files", []) or []:
        blockers.append(f"missing evidence file: {item}")
    for item in validation.get("missing_check_evidence", []) or []:
        blockers.append(f"missing check evidence: {item}")
    if validation.get("python_detected_or_unproven"):
        detected = ", ".join(validation.get("detected_python_tools") or [])
        blockers.append("Python/pip absence is not proven" + (f": {detected}" if detected else "."))
    if validation and not validation.get("exe_launch_pass"):
        blockers.append("EXE launch pass is not proven.")
    if validation and not validation.get("output_generated"):
        blockers.append("sample output generation is not proven.")
    return blockers


def machine_info_string(value: Any) -> str:
    if isinstance(value, dict):
        parts = [str(value.get(key, "")) for key in ("os", "os_version", "architecture", "computer_name")]
        return " | ".join(part for part in parts if part)
    return str(value or "")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
