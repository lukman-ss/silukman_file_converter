from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
from datetime import datetime
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT_DIR / "dist" / "silukman_file_converter_optimized.exe"
MATRIX_SKIP_TEST_FILES = {
    "README_TEST_INPUTS.md",
    "SOURCE_URLS.txt",
    "expected_keywords.json",
}
MATRIX_SKIP_TEST_FOLDERS = {"07_expected_results"}
MATRIX_DISABLED_BETA_OPERATIONS = {"ai_summarizer", "translate_pdf", "pdf_to_pdfa"}
MATRIX_OPERATIONS = [
    {"label": "Merge PDF", "operation": "merge_pdf", "extensions": {".pdf"}, "batch": True, "min_files": 2},
    {"label": "Compare PDF", "operation": "compare_pdf", "extensions": {".pdf"}, "batch": True, "min_files": 2, "max_files": 2},
    {"label": "Split PDF", "operation": "split_pdf", "extensions": {".pdf"}},
    {"label": "Compress PDF", "operation": "compress_pdf", "extensions": {".pdf"}},
    {"label": "PDF to Word (Basic Text)", "operation": "pdf_to_word", "extensions": {".pdf"}},
    {"label": "PDF to PowerPoint (Basic)", "operation": "pdf_to_powerpoint", "extensions": {".pdf"}},
    {"label": "PDF to Excel (Basic Text)", "operation": "pdf_to_excel", "extensions": {".pdf"}},
    {"label": "Edit PDF (Basic)", "operation": "edit_pdf", "extensions": {".pdf"}},
    {"label": "PDF to JPG", "operation": "pdf_to_jpg", "extensions": {".pdf"}},
    {"label": "PDF to PNG", "operation": "pdf_to_png", "extensions": {".pdf"}},
    {"label": "Stamp PDF", "operation": "sign_pdf", "extensions": {".pdf"}},
    {"label": "Watermark (Basic)", "operation": "watermark", "extensions": {".pdf"}},
    {"label": "Rotate PDF (Basic)", "operation": "rotate_pdf", "extensions": {".pdf"}},
    {"label": "Unlock PDF", "operation": "unlock_pdf", "extensions": {".pdf"}},
    {"label": "Protect PDF", "operation": "protect_pdf", "extensions": {".pdf"}},
    {"label": "Organize PDF", "operation": "organize_pdf", "extensions": {".pdf"}},
    {"label": "PDF to PDF/A", "operation": "pdf_to_pdfa", "extensions": {".pdf"}},
    {"label": "Repair PDF", "operation": "repair_pdf", "extensions": {".pdf"}},
    {"label": "Page numbers", "operation": "page_numbers", "extensions": {".pdf"}},
    {"label": "OCR PDF/Image", "operation": "ocr_txt", "extensions": {".pdf", ".png", ".jpg", ".jpeg"}},
    {"label": "Redact PDF (Basic)", "operation": "redact_pdf", "extensions": {".pdf"}},
    {"label": "Crop PDF (Basic)", "operation": "crop_pdf", "extensions": {".pdf"}},
    {"label": "PDF Forms", "operation": "pdf_forms", "extensions": {".pdf"}},
    {"label": "Translate PDF", "operation": "translate_pdf", "extensions": {".pdf"}},
    {"label": "JPG/PNG to PDF", "operation": "image_to_pdf", "extensions": {".png", ".jpg", ".jpeg"}},
    {"label": "Scan to PDF", "operation": "scan_to_pdf", "extensions": {".png", ".jpg", ".jpeg"}},
    {"label": "Word to PDF (Basic Text)", "operation": "word_to_pdf", "extensions": {".doc", ".docx"}},
    {"label": "AI Summarizer", "operation": "ai_summarizer", "extensions": {".pdf", ".doc", ".docx", ".txt"}},
    {"label": "PowerPoint to PDF (Basic Text)", "operation": "powerpoint_to_pdf", "extensions": {".ppt", ".pptx"}},
    {"label": "Excel to PDF (Basic Text)", "operation": "excel_to_pdf", "extensions": {".xls", ".xlsx"}},
    {"label": "Excel to CSV", "operation": "excel_to_csv", "extensions": {".xls", ".xlsx"}},
    {"label": "Excel to JSON", "operation": "excel_to_json", "extensions": {".xls", ".xlsx"}},
    {"label": "HTML to PDF", "operation": "html_to_pdf", "extensions": {".html", ".htm"}},
    {"label": "CSV to Excel", "operation": "csv_to_excel", "extensions": {".csv"}},
    {"label": "JSON to Excel", "operation": "json_to_excel", "extensions": {".json"}},
]
OPERATION_GROUPS = {
    "pdf": {
        "merge_pdf",
        "compare_pdf",
        "split_pdf",
        "compress_pdf",
        "pdf_to_word",
        "pdf_to_powerpoint",
        "pdf_to_excel",
        "edit_pdf",
        "pdf_to_jpg",
        "pdf_to_png",
        "sign_pdf",
        "watermark",
        "rotate_pdf",
        "organize_pdf",
        "repair_pdf",
        "page_numbers",
        "redact_pdf",
        "crop_pdf",
        "pdf_forms",
    },
    "image": {"image_to_pdf", "scan_to_pdf"},
    "office": {"word_to_pdf", "powerpoint_to_pdf", "excel_to_pdf", "excel_to_csv", "excel_to_json", "html_to_pdf", "csv_to_excel", "json_to_excel"},
    "ocr": {"ocr_txt"},
    "security": {"protect_pdf", "unlock_pdf"},
}
SAMPLE_TYPES = {
    "PDF": {".pdf"},
    "image": {".png", ".jpg", ".jpeg"},
    "DOCX": {".docx"},
    "XLSX": {".xlsx"},
    "TXT": {".txt"},
    "CSV": {".csv"},
}
MATRIX_PASS_STATUSES = {"success", "success_short_text", "not_effective"}
BLOCKER_TYPES = {
    "missing_admin",
    "external_vm_required",
    "dependency_missing",
    "artifact_missing",
    "evidence_missing",
    "runtime_failure",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run production QA checks for Silukman File Converter.")
    parser.add_argument("--exe", default=str(DEFAULT_EXE), help="EXE to validate.")
    parser.add_argument("--output-root", default=str(ROOT_DIR / "output" / "production_qa"), help="QA report root.")
    parser.add_argument("--run-exe-matrix", action="store_true", help="Run the full frozen EXE sample matrix.")
    parser.add_argument("--exe-matrix-group", action="append", choices=sorted(OPERATION_GROUPS), default=[], help="Run only one EXE matrix group. May be provided multiple times.")
    parser.add_argument("--exe-matrix-op", action="append", default=[], help="Run only one operation name, for example ocr_txt or pdf_to_png. May be provided multiple times.")
    parser.add_argument("--exe-matrix-input", action="append", default=[], help="Run only one sample input path relative to samples/. May be provided multiple times.")
    parser.add_argument("--exe-op-timeout", type=int, default=180, help="Timeout in seconds for each EXE matrix operation.")
    parser.add_argument("--exe-matrix-timeout", type=int, default=2400, help="Global timeout in seconds for the whole EXE matrix.")
    parser.add_argument("--exe-matrix-dry-run", action="store_true", help="Write the EXE matrix plan without executing operations.")
    parser.add_argument("--resume", action="store_true", help="Resume the latest production QA run directory when possible.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip Python test suite.")
    parser.add_argument("--auto-continue", action="store_true", help="Detect environment and continue installer QA automatically when safe.")
    parser.add_argument("--channel", default="production", choices=["internal-beta", "production"])
    parser.add_argument("--manual-qa", default="", help="Filled manual QA JSON to validate for production sign-off.")
    parser.add_argument("--manual-report", default="", help="Alias for --manual-qa. Filled manual QA JSON evidence report.")
    args = parser.parse_args(argv)

    output_root = Path(args.output_root).resolve()
    run_dir = latest_run_dir(output_root) if args.resume else unique_run_dir(output_root)
    run_dir.mkdir(parents=True, exist_ok=True)

    checks: list[dict[str, Any]] = []
    context = build_context(Path(args.exe))

    checks.append(check_file_exists("EXE artifact exists", Path(args.exe)))
    checks.append(check_exe_size(Path(args.exe)))
    checks.append(check_file_exists("README exists", ROOT_DIR / "README.md"))
    checks.append(check_file_exists("VERSION exists", ROOT_DIR / "VERSION"))
    checks.append(check_file_exists("Release manifest exists", ROOT_DIR / "RELEASE_MANIFEST.json"))
    checks.append(run_command_check("Release package metadata validation", python_command(["scripts/build_release_package.py", "--channel", args.channel, "--validate-only"])))
    checks.append(run_command_check("Python compile check", python_command(["-m", "compileall", "-q", "app", "tests"])))

    if not args.skip_tests:
        checks.append(run_command_check("Unit tests", python_command(["-m", "pytest", "tests", "-q"]), timeout=1800))

    checks.append(run_ocr_bootstrap_check(run_dir))
    environment_report = run_environment_detection()
    if args.auto_continue:
        auto_continue_result = run_auto_continue(environment_report)
        checks.append(auto_continue_result)

    if args.run_exe_matrix:
        checks.append(
            run_exe_matrix_check(
                Path(args.exe),
                run_dir,
                groups=set(args.exe_matrix_group),
                operations=set(args.exe_matrix_op),
                inputs=set(args.exe_matrix_input),
                per_operation_timeout=args.exe_op_timeout,
                global_timeout=args.exe_matrix_timeout,
                dry_run=args.exe_matrix_dry_run,
                resume=args.resume,
            )
        )
    else:
        checks.append(
            {
                "name": "Frozen EXE sample matrix",
                "status": "manual_required",
                "notes": "Skipped. Re-run with --run-exe-matrix before production sign-off.",
            }
        )

    manual_report = args.manual_report or args.manual_qa
    checks.append(run_manual_qa_check(Path(manual_report).resolve() if manual_report else None, run_dir))
    result = summarize(context, checks)
    final_gate = build_final_gate(
        context,
        checks,
        result,
        run_exe_matrix=args.run_exe_matrix,
        manual_report=manual_report,
        environment_report=environment_report,
    )
    write_outputs(run_dir, context, checks, result, final_gate)
    print(json.dumps({"run_dir": str(run_dir), "summary": result, "final_decision": final_gate["decision"]}, indent=2))
    if final_gate["decision"] == "READY_FOR_PRODUCTION":
        print("PRODUCTION SIGN-OFF: READY_FOR_PRODUCTION")
        return 0
    return 1


def build_context(exe: Path) -> dict[str, Any]:
    return {
        "app": "silukman_file_converter",
        "qa_type": "windows_production",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "root_dir": str(ROOT_DIR),
        "exe": str(exe.resolve()),
        "python": sys.executable,
        "platform": platform.platform(),
        "windows_version": platform.version(),
        "cwd": str(Path.cwd()),
    }


def unique_run_dir(output_root: Path) -> Path:
    base = output_root / datetime.now().strftime("%Y%m%d%H%M%S")
    if not base.exists():
        return base
    index = 2
    while True:
        candidate = output_root / f"{base.name}_{index:02d}"
        if not candidate.exists():
            return candidate
        index += 1


def latest_run_dir(output_root: Path) -> Path:
    if not output_root.exists():
        return unique_run_dir(output_root)
    candidates = [path for path in output_root.iterdir() if path.is_dir() and path.name[:8].isdigit()]
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else unique_run_dir(output_root)


def python_command(args: list[str]) -> list[str]:
    python = ROOT_DIR / "venv" / "Scripts" / "python.exe"
    return [str(python if python.exists() else sys.executable), *args]


def check_file_exists(name: str, path: Path) -> dict[str, Any]:
    exists = path.exists()
    return {
        "name": name,
        "status": "pass" if exists else "fail",
        "notes": str(path),
        "details": {"exists": exists, "path": str(path)},
    }


def check_exe_size(exe: Path) -> dict[str, Any]:
    if not exe.exists():
        return {"name": "EXE size", "status": "fail", "notes": f"Missing EXE: {exe}"}
    size_mib = exe.stat().st_size / 1024 / 1024
    status = "pass" if size_mib <= 150 else "blocked"
    return {
        "name": "EXE size budget",
        "status": status,
        "notes": f"{size_mib:.2f} MiB; budget <= 150 MiB for the production portable EXE.",
        "details": {"size_bytes": exe.stat().st_size, "size_mib": round(size_mib, 2)},
    }


def run_command_check(name: str, command: list[str], timeout: int = 600) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            command,
            cwd=ROOT_DIR,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        elapsed = time.perf_counter() - started
        return {
            "name": name,
            "status": "pass" if proc.returncode == 0 else "fail",
            "notes": f"exit={proc.returncode}, elapsed={elapsed:.2f}s",
            "details": {
                "command": command,
                "elapsed_seconds": round(elapsed, 2),
                "stdout_tail": tail(proc.stdout),
                "stderr_tail": tail(proc.stderr),
            },
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": name,
            "status": "fail",
            "notes": f"Timed out after {timeout}s",
            "details": {"command": command, "stdout_tail": tail(exc.stdout or ""), "stderr_tail": tail(exc.stderr or "")},
        }


def run_ocr_bootstrap_check(run_dir: Path) -> dict[str, Any]:
    command = python_command(
        [
            "-c",
            "from app.core.ocr_bootstrap import OCRBootstrapManager; "
            "import json; "
            "print(json.dumps(OCRBootstrapManager().quick_status().to_dict()))",
        ]
    )
    proc = subprocess.run(command, cwd=ROOT_DIR, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False)
    try:
        quick_data = json.loads(proc.stdout) if proc.returncode == 0 else {}
        output = run_dir / "ocr_bootstrap_status.json"
        output.write_text(json.dumps(quick_data, indent=2), encoding="utf-8")
        return {
            "name": "OCR bootstrap quick status",
            "status": "pass" if proc.returncode == 0 and quick_data.get("success") else "fail",
            "notes": f"{quick_data.get('status', 'unknown')}; runtime={quick_data.get('runtime_mode', 'unknown')}; cache_files={quick_data.get('cache_files', 0)}",
            "details": quick_data or {"stdout_tail": tail(proc.stdout), "stderr_tail": tail(proc.stderr)},
        }
    except Exception as exc:
        return {"name": "OCR bootstrap quick status", "status": "fail", "notes": str(exc), "details": {"stdout_tail": tail(proc.stdout), "stderr_tail": tail(proc.stderr)}}


def run_environment_detection() -> dict[str, Any]:
    command = python_command(["tools/environment_detector.py"])
    proc = subprocess.run(command, cwd=ROOT_DIR, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False)
    report_path = ROOT_DIR / "output" / "production_qa" / "environment_report.json"
    data = read_json_safe(report_path)
    status = "pass" if proc.returncode == 0 and data else "fail"
    return {
        "name": "Environment detection",
        "status": status,
        "notes": environment_notes(data) if data else f"exit={proc.returncode}",
        "details": data or {"stdout_tail": tail(proc.stdout), "stderr_tail": tail(proc.stderr)},
    }


def environment_notes(report: dict[str, Any]) -> str:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    return (
        f"admin={summary.get('admin')}; "
        f"python={summary.get('python_detected')}; "
        f"pip={summary.get('pip_detected')}; "
        f"venv={summary.get('venv_detected')}; "
        f"vm={summary.get('vm_detected')} ({summary.get('vm_provider') or 'none'})"
    )


def run_auto_continue(environment_report: dict[str, Any]) -> dict[str, Any]:
    details = environment_report.get("details", {}) if isinstance(environment_report.get("details"), dict) else {}
    summary = details.get("summary", {}) if isinstance(details.get("summary"), dict) else {}
    actions = details.get("actions", []) if isinstance(details.get("actions"), list) else []
    output = ROOT_DIR / "output" / "production_qa" / "auto_continue_installer_qa.json"
    if summary.get("admin") is True:
        command = python_command(["tools/installer_build_qa.py", "--run-installer-test"])
        started = time.perf_counter()
        proc = subprocess.run(command, cwd=ROOT_DIR, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1200, check=False)
        payload = {
            "mode": "installer_admin_auto_continue",
            "command": command,
            "exit_code": proc.returncode,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "stdout_tail": tail(proc.stdout),
            "stderr_tail": tail(proc.stderr),
            "installer_validation": str(ROOT_DIR / "output" / "production_qa" / "installer_validation.json"),
        }
        output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return {
            "name": "Environment auto-continue",
            "status": "pass" if proc.returncode == 0 else "blocked",
            "notes": "Installer QA auto-continued from elevated shell." if proc.returncode == 0 else "Installer QA auto-continue did not pass; see evidence.",
            "details": payload,
        }
    payload = {
        "mode": "no_elevated_shell",
        "status": "blocked",
        "reason": "Current shell is not elevated; installer QA cannot auto-continue into Program Files validation.",
        "run_this": "powershell Start-Process powershell -Verb RunAs",
        "continue_command": "python tools\\installer_build_qa.py --run-installer-test",
        "environment_actions": actions,
    }
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {
        "name": "Environment auto-continue",
        "status": "blocked",
        "notes": "Current shell is not elevated. Run: powershell Start-Process powershell -Verb RunAs",
        "details": payload,
    }


def run_exe_matrix_check(
    exe: Path,
    run_dir: Path,
    groups: set[str],
    operations: set[str],
    inputs: set[str],
    per_operation_timeout: int,
    global_timeout: int,
    dry_run: bool,
    resume: bool,
) -> dict[str, Any]:
    if not exe.exists():
        return {"name": "Frozen EXE sample matrix", "status": "fail", "notes": f"Missing EXE: {exe}"}
    matrix_json = run_dir / "exe_matrix.json"
    matrix_md = run_dir / "exe_matrix.md"
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    plan = build_exe_matrix_plan(ROOT_DIR / "samples", groups=groups, operations=operations, inputs=inputs)
    full_plan_count = len(build_exe_matrix_plan(ROOT_DIR / "samples", groups=set(), operations=set(), inputs=set()))
    if dry_run:
        report = build_matrix_execution_report(
            plan=plan,
            results=[],
            samples_dir=ROOT_DIR / "samples",
            started_at=datetime.now().isoformat(timespec="seconds"),
            elapsed_seconds=0,
            dry_run=True,
            global_timeout=global_timeout,
            per_operation_timeout=per_operation_timeout,
        )
        write_matrix_execution_report(matrix_json, matrix_md, report)
        return {
            "name": "Frozen EXE sample matrix",
            "status": "manual_required",
            "notes": f"Dry run only; planned_operations={len(plan)}; report={matrix_json}",
            "details": {"matrix_report": str(matrix_json), "planned_operations": len(plan), "full_plan_operations": full_plan_count},
        }

    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    started_at = datetime.now().isoformat(timespec="seconds")
    for item in plan:
        elapsed_global = time.perf_counter() - started
        if elapsed_global >= global_timeout:
            results.append(blocked_matrix_item(item, "matrix_global_timeout", f"Global timeout reached after {elapsed_global:.2f}s."))
            continue
        result_path = logs_dir / f"{item['id']}.json"
        if resume and result_path.exists():
            results.append(json.loads(result_path.read_text(encoding="utf-8")))
            continue
        remaining_timeout = max(1, min(per_operation_timeout, int(global_timeout - elapsed_global)))
        result = run_one_exe_matrix_item(
            exe=exe,
            samples_dir=ROOT_DIR / "samples",
            run_dir=run_dir,
            logs_dir=logs_dir,
            item=item,
            timeout=remaining_timeout,
        )
        results.append(result)
        result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    elapsed = time.perf_counter() - started
    report = build_matrix_execution_report(
        plan=plan,
        results=results,
        samples_dir=ROOT_DIR / "samples",
        started_at=started_at,
        elapsed_seconds=elapsed,
        dry_run=False,
        global_timeout=global_timeout,
        per_operation_timeout=per_operation_timeout,
    )
    write_matrix_execution_report(matrix_json, matrix_md, report)
    failed = [row for row in results if row["status"] == "fail"]
    blocked = [row for row in results if row["status"] == "blocked"]
    passed = bool(plan) and not failed and not blocked and all(row["status"] in {"pass", "skipped"} for row in results)
    return {
        "name": "Frozen EXE sample matrix",
        "status": "pass" if passed else "fail",
        "notes": f"elapsed={elapsed:.2f}s, pass={report['summary']['pass']}, fail={report['summary']['fail']}, blocked={report['summary']['blocked']}, skipped={report['summary']['skipped']}, report={matrix_json}",
        "details": {
            "matrix_report": str(matrix_json),
            "matrix_markdown": str(matrix_md),
            "summary": report["summary"],
            "planned_operations": len(plan),
            "full_plan_operations": full_plan_count,
            "is_full_matrix": len(plan) == full_plan_count and not groups and not operations and not inputs,
        },
    }


def build_exe_matrix_plan(samples_dir: Path, groups: set[str], operations: set[str], inputs: set[str]) -> list[dict[str, Any]]:
    selected_operations = set(operations)
    for group in groups:
        selected_operations.update(OPERATION_GROUPS.get(group, set()))
    sample_files = sorted(path for path in samples_dir.rglob("*") if path.is_file() and not should_skip_matrix_sample(samples_dir, path))
    plan: list[dict[str, Any]] = []
    for sample in sample_files:
        relative = sample.relative_to(samples_dir).as_posix()
        if inputs and relative not in {Path(item).as_posix() for item in inputs}:
            continue
        for operation in MATRIX_OPERATIONS:
            operation_name = operation["operation"]
            if operation_name in MATRIX_DISABLED_BETA_OPERATIONS or operation.get("batch"):
                continue
            if selected_operations and operation_name not in selected_operations:
                continue
            if sample.suffix.lower() not in operation["extensions"]:
                continue
            plan.append(
                {
                    "id": stable_matrix_id(relative, operation_name),
                    "operation": operation_name,
                    "operation_label": operation["label"],
                    "group": group_for_operation(operation_name),
                    "input_file": relative,
                    "batch": False,
                }
            )

    if not inputs:
        pdf_count = sum(1 for path in sample_files if path.suffix.lower() == ".pdf")
        for operation in MATRIX_OPERATIONS:
            operation_name = operation["operation"]
            if operation_name in MATRIX_DISABLED_BETA_OPERATIONS or not operation.get("batch"):
                continue
            if selected_operations and operation_name not in selected_operations:
                continue
            if pdf_count < int(operation.get("min_files", 1)):
                continue
            plan.append(
                {
                    "id": stable_matrix_id("__batch__", operation_name),
                    "operation": operation_name,
                    "operation_label": operation["label"],
                    "group": group_for_operation(operation_name),
                    "input_file": "__batch__",
                    "batch": True,
                }
            )
    return plan


def should_skip_matrix_sample(samples_path: Path, path: Path) -> bool:
    relative = path.relative_to(samples_path)
    if path.name in MATRIX_SKIP_TEST_FILES:
        return True
    if path.suffix.lower() in {".md", ".json"}:
        return True
    return any(part in MATRIX_SKIP_TEST_FOLDERS for part in relative.parts)


def stable_matrix_id(input_file: str, operation: str) -> str:
    digest = hashlib.sha1(f"{operation}:{input_file}".encode("utf-8")).hexdigest()[:10]
    stem = Path(input_file).stem if input_file != "__batch__" else "batch"
    safe_stem = "".join(char if char.isalnum() else "_" for char in stem)[:32].strip("_")
    return f"{operation}_{safe_stem}_{digest}".strip("_")


def group_for_operation(operation: str) -> str:
    for group, operation_names in OPERATION_GROUPS.items():
        if operation in operation_names:
            return group
    return "other"


def short_matrix_run_id(item: dict[str, Any]) -> str:
    digest = hashlib.sha1(str(item["id"]).encode("utf-8")).hexdigest()[:10]
    operation = sanitize_filename(str(item["operation"]))[:18].strip("_")
    return f"{operation}_{digest}" if operation else digest


def sanitize_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")


def run_one_exe_matrix_item(
    exe: Path,
    samples_dir: Path,
    run_dir: Path,
    logs_dir: Path,
    item: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    item_output = run_dir / "m" / short_matrix_run_id(item)
    command = [
        str(exe),
        "--sample-matrix",
        "--samples",
        str(samples_dir),
        "--output",
        str(item_output),
        "--source-label",
        "production-qa-exe",
        "--matrix-op",
        item["operation"],
    ]
    if not item.get("batch"):
        command.extend(["--matrix-input", item["input_file"]])

    stdout_path = logs_dir / f"{item['id']}.stdout.log"
    stderr_path = logs_dir / f"{item['id']}.stderr.log"
    started = time.perf_counter()
    proc: subprocess.Popen[str] | None = None
    timed_out = False
    timeout_reason = ""
    try:
        with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout, stderr_path.open("w", encoding="utf-8", errors="replace") as stderr:
            proc = subprocess.Popen(
                command,
                cwd=ROOT_DIR,
                stdout=stdout,
                stderr=stderr,
                text=True,
            )
            try:
                exit_code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                timeout_reason = f"Operation exceeded timeout of {timeout}s."
                kill_process_tree(proc.pid)
                exit_code = proc.poll()
                if exit_code is None:
                    exit_code = -1
    except Exception as exc:
        return {
            **item,
            "status": "blocked",
            "exit_code": -1,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "command": command,
            "process_id": proc.pid if proc else None,
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "timeout": timed_out,
            "timeout_reason": timeout_reason,
            "error_message": str(exc),
        }

    elapsed = time.perf_counter() - started
    latest = latest_child_dir(item_output)
    rows_path = latest / "summary" / "summary.json" if latest else None
    summary_path = latest / "summary" / "summary_exe.json" if latest else None
    rows = json.loads(rows_path.read_text(encoding="utf-8")) if rows_path and rows_path.exists() else []
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path and summary_path.exists() else {}
    normalized_rows = [normalize_matrix_row(row, exit_code=exit_code) for row in rows]
    if timed_out:
        status = "blocked"
        error_message = timeout_reason
    elif exit_code != 0:
        status = "fail"
        error_message = f"EXE exited with code {exit_code}."
    elif not normalized_rows:
        status = "blocked"
        error_message = "No matrix row was produced by the EXE."
    elif any(row["status"] in {"fail", "blocked"} for row in normalized_rows):
        status = "fail"
        error_message = "; ".join(row.get("error_message", "") for row in normalized_rows if row["status"] in {"fail", "blocked"})
    else:
        status = "pass"
        error_message = ""

    return {
        **item,
        "status": status,
        "exit_code": exit_code,
        "elapsed_seconds": round(elapsed, 3),
        "command": command,
        "process_id": proc.pid if proc else None,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "timeout": timed_out,
        "timeout_reason": timeout_reason,
        "error_message": error_message,
        "matrix_run_dir": str(latest) if latest else "",
        "rows": normalized_rows,
        "summary": summary,
    }


def kill_process_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def blocked_matrix_item(item: dict[str, Any], reason: str, message: str) -> dict[str, Any]:
    return {
        **item,
        "status": "blocked",
        "exit_code": None,
        "elapsed_seconds": 0,
        "command": [],
        "process_id": None,
        "stdout": "",
        "stderr": "",
        "timeout": True,
        "timeout_reason": reason,
        "error_message": message,
        "rows": [],
        "summary": {},
    }


def build_matrix_execution_report(
    plan: list[dict[str, Any]],
    results: list[dict[str, Any]],
    samples_dir: Path,
    started_at: str,
    elapsed_seconds: float,
    dry_run: bool,
    global_timeout: int,
    per_operation_timeout: int,
) -> dict[str, Any]:
    counts = {"pass": 0, "fail": 0, "blocked": 0, "skipped": 0, "planned": len(plan)}
    for row in results:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "schema_version": 1,
        "started_at": started_at,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "samples_dir": str(samples_dir),
        "dry_run": dry_run,
        "global_timeout_seconds": global_timeout,
        "per_operation_timeout_seconds": per_operation_timeout,
        "summary": counts,
        "plan": plan,
        "results": results,
    }


def write_matrix_execution_report(json_path: Path, markdown_path: Path, report: dict[str, Any]) -> None:
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# EXE Matrix Execution Report",
        "",
        f"Samples: `{report['samples_dir']}`",
        f"Dry run: `{report['dry_run']}`",
        f"Elapsed: `{report['elapsed_seconds']}s`",
        f"Global timeout: `{report['global_timeout_seconds']}s`",
        f"Per-operation timeout: `{report['per_operation_timeout_seconds']}s`",
        "",
        "## Summary",
        "",
        *[f"- {key}: {value}" for key, value in report["summary"].items()],
        "",
        "## Operations",
        "",
        "| id | group | operation | input | status | exit_code | elapsed | pid | timeout | reason | stdout | stderr |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- | --- | --- | --- |",
    ]
    rows = report["results"] if not report["dry_run"] else report["plan"]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    escape_md(row.get("id", "")),
                    escape_md(row.get("group", "")),
                    escape_md(row.get("operation", "")),
                    escape_md(row.get("input_file", "")),
                    escape_md(row.get("status", "planned")),
                    "" if row.get("exit_code") is None else str(row.get("exit_code", "")),
                    "" if row.get("elapsed_seconds") is None else str(row.get("elapsed_seconds", "")),
                    "" if row.get("process_id") is None else str(row.get("process_id", "")),
                    str(row.get("timeout", "")),
                    escape_md(row.get("timeout_reason") or row.get("error_message", "")),
                    escape_md(row.get("stdout", "")),
                    escape_md(row.get("stderr", "")),
                ]
            )
            + " |"
        )
    markdown_path.write_text("\n".join(lines), encoding="utf-8")


def run_manual_qa_check(manual_qa_path: Path | None, run_dir: Path) -> dict[str, Any]:
    if manual_qa_path is None:
        template_path = ROOT_DIR / "output" / "production_qa" / "manual_qa_template.json"
        return {
            "name": "Manual QA evidence checklist",
            "status": "manual_required",
            "notes": f"Provide --manual-qa with a filled checklist. Template: {template_path}",
        }
    if not manual_qa_path.exists():
        return {
            "name": "Manual QA evidence checklist",
            "status": "fail",
            "notes": f"Manual QA file not found: {manual_qa_path}",
        }
    report_path = run_dir / "manual_qa_report.md"
    command = python_command(["tools/manual_qa_checklist.py", "validate", str(manual_qa_path), "--report", str(report_path)])
    proc = subprocess.run(command, cwd=ROOT_DIR, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False)
    try:
        payload = json.loads(proc.stdout)
        result = payload.get("result", {})
    except json.JSONDecodeError:
        result = {}
    return {
        "name": "Manual QA evidence checklist",
        "status": "pass" if proc.returncode == 0 and result.get("production_signoff_allowed") else "fail",
        "notes": f"exit={proc.returncode}, report={report_path}",
        "details": result or {"stdout_tail": tail(proc.stdout), "stderr_tail": tail(proc.stderr)},
    }


def build_exe_matrix_report(
    samples_dir: Path,
    matrix_root: Path,
    matrix_run_dir: Path | None,
    rows: list[dict[str, Any]],
    exit_code: int,
    total_elapsed_seconds: float,
) -> dict[str, Any]:
    detected = detect_sample_types(samples_dir)
    report_rows = [
        normalize_matrix_row(row, exit_code=exit_code)
        for row in rows
    ]
    for sample_type, files in detected.items():
        if files:
            continue
        report_rows.append(
            {
                "operation_name": f"{sample_type} sample availability",
                "input_file": "",
                "output_file": "",
                "exit_code": exit_code,
                "elapsed_seconds": 0,
                "status": "skipped",
                "error_message": f"No {sample_type} sample found in samples/.",
                "final_status": "skipped",
            }
        )

    counts = {"pass": 0, "fail": 0, "blocked": 0, "skipped": 0}
    for row in report_rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    return {
        "samples_dir": str(samples_dir),
        "matrix_root": str(matrix_root),
        "matrix_run_dir": str(matrix_run_dir) if matrix_run_dir else None,
        "exit_code": exit_code,
        "total_elapsed_seconds": round(total_elapsed_seconds, 3),
        "detected_sample_types": {key: [str(path.relative_to(samples_dir)) for path in value] for key, value in detected.items()},
        "summary": counts,
        "rows": report_rows,
    }


def normalize_matrix_row(row: dict[str, Any], exit_code: int) -> dict[str, Any]:
    final_status = str(row.get("final_status") or "failed")
    operation = str(row.get("operation_label") or row.get("operation") or "unknown")
    outputs = row.get("outputs") or []
    output_file = str(outputs[0]) if outputs else ""
    notes = str(row.get("notes") or "")
    if final_status in MATRIX_PASS_STATUSES:
        status = "pass"
    elif row.get("operation") == "no_supported_operation" or final_status in {"not_configured", "not_validated"}:
        status = "skipped"
    elif exit_code != 0:
        status = "blocked"
    else:
        status = "fail"
    return {
        "operation_name": operation,
        "operation": row.get("operation"),
        "input_file": row.get("input_file", ""),
        "output_file": output_file,
        "output_files": outputs,
        "exit_code": exit_code,
        "elapsed_seconds": row.get("elapsed_seconds"),
        "status": status,
        "error_message": notes,
        "final_status": final_status,
    }


def detect_sample_types(samples_dir: Path) -> dict[str, list[Path]]:
    files = [path for path in samples_dir.rglob("*") if path.is_file()]
    detected: dict[str, list[Path]] = {key: [] for key in SAMPLE_TYPES}
    for path in files:
        if any(part == "07_expected_results" for part in path.relative_to(samples_dir).parts):
            continue
        suffix = path.suffix.lower()
        for sample_type, extensions in SAMPLE_TYPES.items():
            if suffix in extensions:
                detected[sample_type].append(path)
    return detected


def write_exe_matrix_report(matrix_root: Path, report: dict[str, Any]) -> None:
    matrix_root.mkdir(parents=True, exist_ok=True)
    (matrix_root / "exe_matrix_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# EXE Sample Matrix Report",
        "",
        f"Samples: `{report['samples_dir']}`",
        f"Matrix run: `{report['matrix_run_dir']}`",
        f"Exit code: `{report['exit_code']}`",
        f"Elapsed: `{report['total_elapsed_seconds']}s`",
        "",
        "## Summary",
        "",
        *[f"- {key}: {value}" for key, value in report["summary"].items()],
        "",
        "## Detected Sample Types",
        "",
    ]
    for sample_type, files in report["detected_sample_types"].items():
        lines.append(f"- {sample_type}: {len(files)}")
    lines.extend(
        [
            "",
            "## Operations",
            "",
            "| operation | input_file | output_file | exit_code | elapsed_seconds | status | error_message |",
            "| --- | --- | --- | ---: | ---: | --- | --- |",
        ]
    )
    for row in report["rows"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    escape_md(row.get("operation_name", "")),
                    escape_md(row.get("input_file", "")),
                    escape_md(row.get("output_file", "")),
                    str(row.get("exit_code", "")),
                    "" if row.get("elapsed_seconds") is None else str(row.get("elapsed_seconds")),
                    row.get("status", ""),
                    escape_md(row.get("error_message", "")),
                ]
            )
            + " |"
        )
    (matrix_root / "exe_matrix_report.md").write_text("\n".join(lines), encoding="utf-8")


def latest_child_dir(path: Path) -> Path | None:
    if not path.exists():
        return None
    dirs = [item for item in path.iterdir() if item.is_dir()]
    return max(dirs, key=lambda item: item.stat().st_mtime) if dirs else None


def manual_gate_placeholders() -> list[dict[str, Any]]:
    return [
        manual("Clean Windows no-Python validation", "Install and run on a clean Windows VM without Python, venv, or dev dependencies."),
        manual("OCR first-run model bootstrap", "With internet enabled, run OCR once and confirm model preparation completes without crash."),
        manual("OCR offline cache validation", "After first setup, disable internet and confirm OCR image/PDF scan still works."),
        manual("Installer install/uninstall", "Install from Inno Setup artifact, launch shortcuts, then uninstall cleanly."),
        manual("Startup speed", "Measure cold and warm startup. Target: cold <= 10s, warm <= 5s on baseline VM."),
        manual("Memory usage", "Measure idle and OCR peak memory. Record baseline and investigate large regressions."),
        manual("Temporary file cleanup", "After conversions and app exit, confirm temp folders do not accumulate stale _MEI or OCR temp files."),
        manual("Permission handling", "Run as standard user; validate Program Files install, Documents output, denied folders, and read-only inputs."),
        manual("Unicode and long path filenames", "Validate Indonesian/Unicode names, spaces, and paths near Windows MAX_PATH/long-path policy."),
        manual("Windows Defender false positive risk", "Scan EXE/setup with Defender and record result before public release."),
        manual("Manual QA evidence sign-off", "Fill output/production_qa/manual_qa_template.json and pass it with --manual-qa."),
    ]


def manual(name: str, notes: str) -> dict[str, Any]:
    return {"name": name, "status": "manual_required", "notes": notes}


def build_final_gate(
    context: dict[str, Any],
    checks: list[dict[str, Any]],
    summary: dict[str, Any],
    run_exe_matrix: bool,
    manual_report: str,
    environment_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del summary
    blockers: list[str] = []
    check_by_name = {check["name"]: check for check in checks}
    automated_checks = [
        check
        for check in checks
        if check["name"] not in {"Frozen EXE sample matrix", "Manual QA evidence checklist", "Environment auto-continue"}
    ]

    for check in checks:
        if check["name"] == "Environment auto-continue":
            continue
        if check["name"] == "Manual QA evidence checklist" and check["status"] != "pass":
            continue
        if check["status"] != "pass":
            blockers.append(f"{check['name']} did not pass: {check.get('notes', '')}")

    matrix_check = check_by_name.get("Frozen EXE sample matrix")
    if not run_exe_matrix:
        blockers.append("EXE matrix was not executed. Run with --run-exe-matrix.")
    elif not matrix_check or matrix_check.get("status") != "pass":
        blockers.append("EXE matrix did not pass.")
    elif not matrix_check.get("details", {}).get("is_full_matrix", False):
        blockers.append("EXE matrix was targeted, not full. Production sign-off requires the full sample matrix.")

    manual_check = check_by_name.get("Manual QA evidence checklist")
    if not manual_report:
        blockers.append("Manual QA report was not provided. Use --manual-report path/to/manual_qa.json.")
    elif not Path(manual_report).exists():
        blockers.append(f"Manual QA report does not exist: {manual_report}")
    elif not manual_check or manual_check.get("status") != "pass":
        details = manual_check.get("details", {}) if manual_check else {}
        problems = details.get("problems", []) if isinstance(details, dict) else []
        if problems:
            blockers.extend(f"Manual QA: {problem}" for problem in problems)
        else:
            blockers.append("Manual QA report did not pass validation.")

    ocr_gate = evaluate_ocr_validation(ROOT_DIR / "output" / "production_qa" / "ocr_validation.json")
    clean_windows_gate = evaluate_clean_windows_validation(ROOT_DIR / "output" / "production_qa" / "clean_windows_validation.json")
    installer_gate = evaluate_installer_validation(ROOT_DIR / "output" / "production_qa" / "installer_validation.json")
    timeout_gate = evaluate_exe_matrix_timeouts(matrix_check)
    environment_gate = evaluate_environment_report(environment_report)

    for blocker in ocr_gate["blockers"]:
        blockers.append(f"OCR validation: {blocker}")
    for blocker in clean_windows_gate["blockers"]:
        blockers.append(f"Clean Windows validation: {blocker}")
    for blocker in installer_gate["blockers"]:
        blockers.append(f"Installer validation: {blocker}")
    for blocker in timeout_gate["blockers"]:
        blockers.append(f"EXE matrix timeout: {blocker}")
    gate_results = {
        "automated_qa": {
            "status": "pass" if all(check["status"] == "pass" for check in automated_checks) else "blocker",
            "passed": sum(1 for check in automated_checks if check["status"] == "pass"),
            "total": len(automated_checks),
            "blockers": [
                f"{check['name']}: {check.get('notes', '')}"
                for check in automated_checks
                if check["status"] != "pass"
            ],
        },
        "exe_matrix": {
            "status": "pass" if run_exe_matrix and matrix_check and matrix_check.get("status") == "pass" else "blocker",
            "executed": run_exe_matrix,
            "notes": matrix_check.get("notes", "") if matrix_check else "Frozen EXE sample matrix check not found.",
        },
        "windows_qa_manual_evidence": {
            "status": "pass" if manual_report and manual_check and manual_check.get("status") == "pass" else "blocker",
            "manual_report": str(Path(manual_report).resolve()) if manual_report else "",
            "notes": manual_check.get("notes", "") if manual_check else "Manual QA evidence checklist check not found.",
            "summary": (
                manual_check.get("details", {}).get("summary", {})
                if manual_check and isinstance(manual_check.get("details"), dict)
                else {}
            ),
        },
        "ocr_validation": ocr_gate,
        "clean_windows_validation": clean_windows_gate,
        "installer_validation": installer_gate,
        "timeout_validation": timeout_gate,
        "environment_detection": environment_gate,
    }

    unique_blockers = []
    for blocker in blockers:
        if blocker not in unique_blockers:
            unique_blockers.append(blocker)
    actionable_blockers = [classify_blocker(blocker) for blocker in unique_blockers]
    next_actions = build_next_actions(actionable_blockers)
    decision = determine_production_decision(
        unique_blockers=unique_blockers,
        actionable_blockers=actionable_blockers,
        gate_results=gate_results,
        run_exe_matrix=run_exe_matrix,
    )

    return {
        "app": context["app"],
        "exe": context["exe"],
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "decision": decision,
        "production_candidate": decision == "PRODUCTION_CANDIDATE",
        "blockers": unique_blockers,
        "actionable_blockers": actionable_blockers,
        "next_actions": next_actions,
        "gate_results": gate_results,
        "checks": checks,
        "manual_report": str(Path(manual_report).resolve()) if manual_report else "",
        "exe_matrix_executed": run_exe_matrix,
    }


def evaluate_environment_report(environment_check: dict[str, Any] | None) -> dict[str, Any]:
    if not environment_check or environment_check.get("status") != "pass":
        return {
            "status": "blocker",
            "path": str(ROOT_DIR / "output" / "production_qa" / "environment_report.json"),
            "summary": {},
            "actions": [],
            "blockers": ["environment detection did not pass"],
        }
    report = environment_check.get("details", {}) if isinstance(environment_check.get("details"), dict) else {}
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    actions = report.get("actions", []) if isinstance(report.get("actions"), list) else []
    blockers: list[str] = []
    if summary.get("admin") is not True:
        blockers.append("shell is not elevated; installer QA cannot auto-continue")
    if summary.get("clean_windows_candidate") is not True:
        blockers.append("current environment is not a clean Windows no-Python candidate")
    return {
        "status": "pass" if not blockers else "advisory",
        "path": str(ROOT_DIR / "output" / "production_qa" / "environment_report.json"),
        "summary": summary,
        "actions": actions,
        "blockers": blockers,
    }


def classify_blocker(message: str) -> dict[str, str]:
    lower = message.lower()
    if "clean_windows_no_python" in lower or "clean windows" in lower or "python detected" in lower or "developer_artifacts" in lower or "no-python" in lower:
        blocker_type = "external_vm_required"
        cause = "Clean Windows evidence was collected on a developer machine or has not been imported from a clean VM."
        why = "This check can pass only on Windows without Python, pip, venv, source tree, or build artifacts."
        auto_fix = "no"
        command = (
            "Copy clean_windows_validation_package.zip to a clean Windows VM, run: "
            "powershell -ExecutionPolicy Bypass -File .\\qa\\clean_windows_runner.ps1; "
            "then import on dev machine: python tools\\import_clean_windows_validation.py path\\to\\clean_windows_validation.json"
        )
        estimate = "10-20 minutes plus VM startup time."
    elif (
        "installer_install_uninstall" in lower
        or "installer_install evidence" in lower
        or "installer_uninstall evidence" in lower
        or "administrator" in lower
        or "elevated" in lower
        or "program files install validation" in lower
        or "installer validation is blocked" in lower
        or "installer validation hash" in lower
    ):
        blocker_type = "missing_admin"
        cause = "Installer install/uninstall evidence must be regenerated for the current setup artifact."
        why = "Production installer QA must prove the current setup installs to Program Files, launches, uninstalls, cleans up, and matches the current artifact hash."
        auto_fix = "no"
        command = (
            f"Auto: python tools\\installer_build_qa.py --run-installer-test --auto-elevate; "
            f"Manual UAC: powershell Start-Process powershell -Verb RunAs, then run: cd {ROOT_DIR}; python tools\\installer_build_qa.py --run-installer-test"
        )
        estimate = "5-10 minutes after an elevated PowerShell is available."
    elif "inno" in lower or "iscc" in lower or "dependency" in lower:
        blocker_type = "dependency_missing"
        cause = "Required installer dependency is missing."
        why = "Inno Setup Compiler is needed to build the setup artifact."
        auto_fix = "yes"
        command = "winget install --id JRSoftware.InnoSetup -e"
        estimate = "2-5 minutes."
    elif "artifact missing" in lower or "setup exe is missing" in lower or "missing exe" in lower:
        blocker_type = "artifact_missing"
        cause = "A required release artifact is missing."
        why = "Production sign-off requires concrete artifacts such as the setup EXE and release package."
        auto_fix = "yes"
        command = "python tools\\installer_build_qa.py --run-installer-test"
        estimate = "5-10 minutes if dependencies and permissions are ready."
    elif "evidence missing" in lower or "manual qa report" in lower or "report was not provided" in lower or "not executed" in lower:
        blocker_type = "evidence_missing"
        cause = "Required QA evidence has not been generated or imported."
        why = "The release gate is evidence-only and cannot infer pass from assumptions."
        auto_fix = "partial"
        command = "python tools\\windows_qa_runner.py --tester \"Your Name\" --run-defender-scan"
        estimate = "5-15 minutes depending on the missing evidence."
    else:
        blocker_type = "runtime_failure"
        cause = "A runtime validation failed or timed out."
        why = "Production sign-off requires every supported automated operation to pass without timeout or uncontrolled failure."
        auto_fix = "partial"
        command = "Inspect the referenced report/log, then rerun the failed operation with: python tools\\production_qa.py --run-exe-matrix --exe-matrix-op OPERATION --manual-report output\\production_qa\\manual_qa_filled.json"
        estimate = "Depends on the failing operation; usually 5-30 minutes."
    return {
        "message": message,
        "type": blocker_type,
        "exact_cause": cause,
        "why_blocked": why,
        "auto_fix_possible": auto_fix,
        "next_command": command,
        "estimated_remaining_work": estimate,
    }


def build_next_actions(actionable_blockers: list[dict[str, str]]) -> list[dict[str, str]]:
    ordered_types = [
        "dependency_missing",
        "artifact_missing",
        "missing_admin",
        "external_vm_required",
        "evidence_missing",
        "runtime_failure",
    ]
    actions: list[dict[str, str]] = []
    seen: set[str] = set()
    for blocker_type in ordered_types:
        for blocker in actionable_blockers:
            if blocker["type"] != blocker_type or blocker["next_command"] in seen:
                continue
            seen.add(blocker["next_command"])
            actions.append(
                {
                    "step": str(len(actions) + 1),
                    "type": blocker["type"],
                    "action": blocker["next_command"],
                    "why": blocker["why_blocked"],
                    "estimated_remaining_work": blocker["estimated_remaining_work"],
                }
            )
            break
    return actions


def determine_production_decision(
    unique_blockers: list[str],
    actionable_blockers: list[dict[str, str]],
    gate_results: dict[str, Any],
    run_exe_matrix: bool,
) -> str:
    if not unique_blockers:
        return "READY_FOR_PRODUCTION"
    if is_production_candidate(actionable_blockers, gate_results, run_exe_matrix):
        return "PRODUCTION_CANDIDATE"
    return "NOT_READY_FOR_PRODUCTION"


def is_production_candidate(
    actionable_blockers: list[dict[str, str]],
    gate_results: dict[str, Any],
    run_exe_matrix: bool,
) -> bool:
    if not run_exe_matrix:
        return False
    automated = gate_results.get("automated_qa", {})
    exe_matrix = gate_results.get("exe_matrix", {})
    ocr = gate_results.get("ocr_validation", {})
    timeouts = gate_results.get("timeout_validation", {})
    if automated.get("status") != "pass":
        return False
    if exe_matrix.get("status") != "pass":
        return False
    if ocr.get("status") != "pass":
        return False
    if timeouts.get("status") != "pass":
        return False
    allowed_external = {"missing_admin", "external_vm_required", "evidence_missing"}
    blocker_types = {blocker.get("type", "") for blocker in actionable_blockers}
    if not blocker_types:
        return False
    if not blocker_types.issubset(allowed_external):
        return False
    return any(blocker_type in blocker_types for blocker_type in {"missing_admin", "external_vm_required"})


def evaluate_ocr_validation(path: Path) -> dict[str, Any]:
    data = read_json_safe(path)
    if not data:
        return {
            "status": "blocker",
            "path": str(path),
            "decision": "",
            "summary": {},
            "blockers": [f"OCR validation report is missing or unreadable: {path}"],
        }
    blockers = evidence_report_blockers(data, expected_decision="PASS", report_name="OCR validation")
    required_checks = {"phase1_online_first_run", "phase2_offline_cache", "model_cache_after_online", "close_app"}
    checks = {str(item.get("id")): item for item in data.get("checks", []) if isinstance(item, dict)}
    for check_id in sorted(required_checks - set(checks)):
        blockers.append(f"required check is missing: {check_id}")
    for phase_id in ("phase1_online_first_run", "phase2_offline_cache"):
        check = checks.get(phase_id, {})
        outputs = check.get("details", {}).get("ocr_outputs", []) if isinstance(check.get("details"), dict) else []
        if not any(item.get("exists") and item.get("size_bytes", 0) > 0 for item in outputs if isinstance(item, dict)):
            blockers.append(f"{phase_id} has no generated OCR output evidence.")
    return {
        "status": "pass" if not blockers else "blocker",
        "path": str(path),
        "decision": data.get("decision", ""),
        "summary": data.get("summary", {}),
        "blockers": blockers,
    }


def evaluate_clean_windows_validation(path: Path) -> dict[str, Any]:
    data = read_json_safe(path)
    if not data:
        return {
            "status": "blocker",
            "path": str(path),
            "decision": "",
            "summary": {},
            "blockers": [f"Clean Windows validation report is missing or unreadable: {path}"],
        }
    blockers = evidence_report_blockers(data, expected_decision="PASS", report_name="Clean Windows validation")
    required_checks = {"python_path_detection", "exe_launch", "dll_loading", "output_creation", "clean_windows_no_python"}
    checks = {str(item.get("id")): item for item in data.get("checks", []) if isinstance(item, dict)}
    for check_id in sorted(required_checks - set(checks)):
        blockers.append(f"required check is missing: {check_id}")
    return {
        "status": "pass" if not blockers else "blocker",
        "path": str(path),
        "decision": data.get("decision", ""),
        "summary": data.get("summary", {}),
        "blockers": blockers,
    }


def evaluate_installer_validation(path: Path) -> dict[str, Any]:
    data = read_json_safe(path)
    if not data:
        return {
            "status": "blocker",
            "path": str(path),
            "decision": "",
            "summary": {},
            "blockers": [f"installer validation report is missing or unreadable: {path}"],
        }
    blockers = evidence_report_blockers(data, expected_decision="PASS", report_name="Installer validation")
    required_checks = {"installer_artifact", "installer_preflight", "installer_install", "installer_uninstall"}
    checks = {str(item.get("id")): item for item in data.get("checks", []) if isinstance(item, dict)}
    for check_id in sorted(required_checks - set(checks)):
        if check_id == "installer_artifact":
            blockers.append("installer artifact missing")
        elif check_id in {"installer_install", "installer_uninstall"}:
            blockers.append(f"{check_id} evidence missing")
        else:
            blockers.append(f"required check is missing: {check_id}")
    artifact = checks.get("installer_artifact", {})
    details = artifact.get("details", {}) if isinstance(artifact.get("details"), dict) else {}
    if artifact and not details.get("exists", False):
        blockers.append("installer artifact missing")
    installer_path = Path(str(data.get("installer", "")))
    if installer_path.exists() and details.get("sha256"):
        current_hash = file_sha256(installer_path)
        if str(details.get("sha256", "")).lower() != current_hash.lower():
            blockers.append("installer validation hash does not match current setup artifact")
    return {
        "status": "pass" if not blockers else "blocker",
        "path": str(path),
        "decision": data.get("decision", ""),
        "summary": data.get("summary", {}),
        "blockers": unique_list(blockers),
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evidence_report_blockers(data: dict[str, Any], expected_decision: str, report_name: str) -> list[str]:
    blockers: list[str] = []
    if data.get("decision") != expected_decision:
        blockers.append(describe_decision_blocker(report_name, data))
    checks = data.get("checks")
    if not isinstance(checks, list):
        return [*blockers, "checks list is missing."]
    for check in checks:
        if not isinstance(check, dict):
            blockers.append("check entry is not an object.")
            continue
        check_id = str(check.get("id", "unknown"))
        status = str(check.get("status", ""))
        if status != "pass":
            blockers.append(describe_check_blocker(report_name, check_id, status, check))
        evidence = check.get("evidence") or check.get("details")
        if not evidence:
            blockers.append(f"{check_id}: evidence/details missing.")
    if any("timeout" in str(check).lower() and "'timed_out': True" in repr(check) for check in checks):
        blockers.append(f"{report_name} contains a timeout.")
    return blockers


def describe_decision_blocker(report_name: str, data: dict[str, Any]) -> str:
    decision = str(data.get("decision", ""))
    if report_name == "Clean Windows validation" and decision == "BLOCKED":
        return "clean Windows evidence is blocked"
    if report_name == "Installer validation" and decision == "BLOCKED":
        return "installer validation is blocked"
    return f"decision is {decision!r}; expected 'PASS'."


def describe_check_blocker(report_name: str, check_id: str, status: str, check: dict[str, Any]) -> str:
    notes = str(check.get("notes", ""))
    details = check.get("details", {}) if isinstance(check.get("details"), dict) else {}
    if report_name == "Clean Windows validation":
        if check_id == "python_path_detection":
            return "python detected in clean validation machine"
        if check_id == "clean_windows_no_python":
            return "clean Windows no-Python decision is not pass"
        if check_id == "output_creation":
            return "clean Windows sample output was not generated"
        if check_id == "dll_loading":
            return "clean Windows DLL smoke check did not pass"
    if report_name == "Installer validation":
        if check_id == "installer_artifact" and not details.get("exists", False):
            return "installer artifact missing"
        if check_id == "installer_preflight":
            return notes or "installer preflight did not pass"
        if check_id == "installer_install":
            return "installer install evidence failed"
        if check_id == "installer_uninstall":
            return "installer uninstall evidence failed"
    if "timeout" in notes.lower():
        return f"{check_id} timed out"
    return f"{check_id}: status is {status}; production requires pass."


def evaluate_exe_matrix_timeouts(matrix_check: dict[str, Any] | None) -> dict[str, Any]:
    report_path = ""
    if matrix_check and isinstance(matrix_check.get("details"), dict):
        report_path = str(matrix_check["details"].get("matrix_report") or "")
    data = read_json_safe(Path(report_path)) if report_path else {}
    blockers: list[str] = []
    if not report_path:
        blockers.append("matrix report path is missing.")
    elif not data:
        blockers.append(f"matrix report is missing or unreadable: {report_path}")
    else:
        for row in data.get("results", []):
            if not isinstance(row, dict):
                continue
            if row.get("timeout") is True or row.get("timed_out") is True:
                blockers.append(f"{row.get('operation')} on {row.get('input_file')} timed out: {row.get('timeout_reason') or row.get('error_message')}")
            if row.get("status") == "blocked":
                blockers.append(f"{row.get('operation')} on {row.get('input_file')} is blocked: {row.get('timeout_reason') or row.get('error_message')}")
    return {
        "status": "pass" if not blockers else "blocker",
        "path": report_path,
        "blockers": blockers,
    }


def summarize(context: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    del context
    counts = {"pass": 0, "fail": 0, "blocked": 0, "manual_required": 0}
    for check in checks:
        counts[check["status"]] = counts.get(check["status"], 0) + 1
    production_ready = counts["fail"] == 0 and counts["blocked"] == 0 and counts["manual_required"] == 0
    internal_beta_exit_ready = counts["fail"] == 0 and counts["blocked"] == 0
    return {
        **counts,
        "automated_failed": counts["fail"],
        "production_ready": production_ready,
        "internal_beta_exit_ready": internal_beta_exit_ready,
        "decision": "READY_FOR_PRODUCTION" if production_ready else "NOT_READY_FOR_PRODUCTION",
    }


def write_outputs(run_dir: Path, context: dict[str, Any], checks: list[dict[str, Any]], result: dict[str, Any], final_gate: dict[str, Any]) -> None:
    (run_dir / "qa_result.json").write_text(
        json.dumps({"context": context, "summary": result, "checks": checks}, indent=2),
        encoding="utf-8",
    )
    (run_dir / "production_qa_final.json").write_text(json.dumps(final_gate, indent=2), encoding="utf-8")
    lines = [
        "# Windows Production QA Report",
        "",
        f"App: `{context['app']}`",
        f"EXE: `{context['exe']}`",
        f"Run: `{run_dir}`",
        f"Decision: `{final_gate['decision']}`",
        "",
        "## Summary",
        "",
        *[f"- {key}: {value}" for key, value in result.items()],
        "",
        "## Checks",
        "",
        "| check | status | notes |",
        "| --- | --- | --- |",
    ]
    for check in checks:
        lines.append(f"| {escape_md(check['name'])} | {check['status']} | {escape_md(check.get('notes', ''))} |")
    lines.extend(
        [
            "",
            "## Release Rule",
            "",
            "Production release is blocked until every automated check passes and every manual_required item is completed on a clean Windows machine.",
        ]
    )
    (run_dir / "file.md").write_text("\n".join(lines), encoding="utf-8")
    (run_dir / "production_qa_final.md").write_text(render_final_markdown(run_dir, final_gate), encoding="utf-8")
    write_next_actions_summary(final_gate)
    write_production_candidate_summary(final_gate)


def render_final_markdown(run_dir: Path, final_gate: dict[str, Any]) -> str:
    lines = [
        "# Final Production QA Gate",
        "",
        f"App: `{final_gate['app']}`",
        f"EXE: `{final_gate['exe']}`",
        f"Run: `{run_dir}`",
        f"Decision: `{final_gate['decision']}`",
        f"EXE matrix executed: `{final_gate['exe_matrix_executed']}`",
        f"Manual report: `{final_gate['manual_report']}`",
        "",
        "## Gate Results",
        "",
        "| gate | status | details |",
        "| --- | --- | --- |",
    ]
    gate_results = final_gate.get("gate_results", {})
    automated = gate_results.get("automated_qa", {})
    exe_matrix = gate_results.get("exe_matrix", {})
    manual = gate_results.get("windows_qa_manual_evidence", {})
    ocr = gate_results.get("ocr_validation", {})
    clean = gate_results.get("clean_windows_validation", {})
    installer = gate_results.get("installer_validation", {})
    timeouts = gate_results.get("timeout_validation", {})
    environment = gate_results.get("environment_detection", {})
    lines.extend(
        [
            f"| Automated QA | {automated.get('status', 'blocker')} | {automated.get('passed', 0)}/{automated.get('total', 0)} checks passed |",
            f"| EXE matrix | {exe_matrix.get('status', 'blocker')} | executed={exe_matrix.get('executed', False)}; {escape_md(exe_matrix.get('notes', ''))} |",
            f"| OCR validation | {ocr.get('status', 'blocker')} | decision={escape_md(ocr.get('decision', ''))}; summary={escape_md(json.dumps(ocr.get('summary', {}), sort_keys=True))}; path={escape_md(ocr.get('path', ''))} |",
            f"| Clean Windows validation | {clean.get('status', 'blocker')} | decision={escape_md(clean.get('decision', ''))}; summary={escape_md(json.dumps(clean.get('summary', {}), sort_keys=True))}; path={escape_md(clean.get('path', ''))} |",
            f"| Installer validation | {installer.get('status', 'blocker')} | decision={escape_md(installer.get('decision', ''))}; summary={escape_md(json.dumps(installer.get('summary', {}), sort_keys=True))}; path={escape_md(installer.get('path', ''))} |",
            f"| Timeout validation | {timeouts.get('status', 'blocker')} | path={escape_md(timeouts.get('path', ''))} |",
            f"| Environment detection | {environment.get('status', 'advisory')} | summary={escape_md(json.dumps(environment.get('summary', {}), sort_keys=True))}; path={escape_md(environment.get('path', ''))} |",
            f"| Windows QA runner/manual evidence | {manual.get('status', 'blocker')} | report={escape_md(manual.get('manual_report', ''))}; summary={escape_md(json.dumps(manual.get('summary', {}), sort_keys=True))} |",
            "",
        ]
    )
    lines.extend(
        [
        "## Blockers",
        "",
        ]
    )
    if final_gate["blockers"]:
        lines.extend(f"- {escape_md(blocker)}" for blocker in final_gate["blockers"])
    else:
        lines.append("- None.")
        lines.extend(["", "## Production Sign-Off", "", "READY_FOR_PRODUCTION"])

    if final_gate.get("decision") == "PRODUCTION_CANDIDATE":
        lines.extend(
            [
                "",
                "## Production Candidate",
                "",
                "Code/package/EXE/OCR automation gates have passed. Production sign-off is waiting only for external environment evidence.",
            ]
        )

    lines.extend(["", "## Next Actions", ""])
    next_actions = final_gate.get("next_actions", [])
    if next_actions:
        for action in next_actions:
            lines.extend(
                [
                    f"### Step {escape_md(action.get('step', ''))}",
                    "",
                    f"- Type: `{escape_md(action.get('type', ''))}`",
                    f"- Why: {escape_md(action.get('why', ''))}",
                    f"- Command: `{escape_md(action.get('action', ''))}`",
                    f"- Estimated remaining work: {escape_md(action.get('estimated_remaining_work', ''))}",
                    "",
                ]
            )
    else:
        lines.append("- None.")

    actionable = unique_actionable_blockers(final_gate.get("actionable_blockers", []))
    if actionable:
        lines.extend(
            [
                "",
                "## Actionable Blockers",
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
            "## Checks",
            "",
            "| check | status | notes |",
            "| --- | --- | --- |",
        ]
    )
    for check in final_gate["checks"]:
        status = check["status"] if check["status"] == "pass" else "blocker"
        lines.append(f"| {escape_md(check['name'])} | {status} | {escape_md(check.get('notes', ''))} |")
    return "\n".join(lines)


def write_next_actions_summary(final_gate: dict[str, Any]) -> None:
    summary_dir = ROOT_DIR / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    path = summary_dir / "next_actions.md"
    lines = [
        "# Production QA Next Actions",
        "",
        f"Decision: `{final_gate.get('decision', '')}`",
        f"Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        "",
    ]
    actions = final_gate.get("next_actions", [])
    if actions:
        lines.append("## Next Actions")
        lines.append("")
        for action in actions:
            lines.extend(
                [
                    f"### Step {escape_md(action.get('step', ''))}",
                    "",
                    f"- Type: `{escape_md(action.get('type', ''))}`",
                    f"- Why: {escape_md(action.get('why', ''))}",
                    f"- Command: `{escape_md(action.get('action', ''))}`",
                    f"- Estimated remaining work: {escape_md(action.get('estimated_remaining_work', ''))}",
                    "",
                ]
            )
    else:
        lines.extend(["## Next Actions", "", "- None. Production gate has no blockers.", ""])
    blockers = unique_actionable_blockers(final_gate.get("actionable_blockers", []))
    if blockers:
        lines.extend(
            [
                "## Blocker Details",
                "",
                "| type | exact cause | why blocked | auto-fix | next command | estimate |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for blocker in blockers:
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
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_production_candidate_summary(final_gate: dict[str, Any]) -> None:
    summary_dir = ROOT_DIR / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    path = summary_dir / "production_candidate.md"
    decision = final_gate.get("decision", "")
    lines = [
        "# Production Candidate Status",
        "",
        f"Status: `{decision}`",
        f"Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        "",
    ]
    if decision == "PRODUCTION_CANDIDATE":
        lines.extend(
            [
                "The project has passed code/package/EXE/OCR automation gates and is waiting only for external environment evidence.",
                "",
                "## Remaining Evidence",
                "",
            ]
        )
        actions = final_gate.get("next_actions", [])
        if actions:
            for action in actions:
                lines.extend(
                    [
                        f"{action.get('step', '')}. `{action.get('type', '')}`",
                        f"   Command: `{action.get('action', '')}`",
                        f"   Estimate: {action.get('estimated_remaining_work', '')}",
                        "",
                    ]
                )
        else:
            lines.append("- None.")
    elif decision == "READY_FOR_PRODUCTION":
        lines.extend(["All gates passed. Production sign-off is allowed.", ""])
    else:
        lines.extend(
            [
                "The project is not yet a production candidate because at least one blocker is not external-evidence-only.",
                "",
                "## Current Actions",
                "",
            ]
        )
        for action in final_gate.get("next_actions", []):
            lines.append(f"- `{action.get('type', '')}`: {action.get('action', '')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def unique_actionable_blockers(blockers: list[dict[str, str]]) -> list[dict[str, str]]:
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for blocker in blockers:
        key = (
            blocker.get("type", ""),
            blocker.get("exact_cause", ""),
            blocker.get("next_command", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(blocker)
    return unique


def tail(value: str | bytes, limit: int = 4000) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value[-limit:]


def read_json_safe(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def escape_md(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def unique_list(items: list[str]) -> list[str]:
    unique: list[str] = []
    for item in items:
        if item not in unique:
            unique.append(item)
    return unique


if __name__ == "__main__":
    raise SystemExit(main())
