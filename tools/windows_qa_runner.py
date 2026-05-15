from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT_DIR / "output" / "production_qa"
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
IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
PDF_EXTS = {".pdf"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect evidence for Windows manual QA checks.")
    parser.add_argument("--tester", required=True)
    parser.add_argument("--exe", default=str(ROOT_DIR / "dist" / "silukman_file_converter_optimized.exe"))
    parser.add_argument("--samples", default=str(ROOT_DIR / "samples"))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--run-defender-scan", action="store_true")
    parser.add_argument("--run-installer-test", action="store_true")
    parser.add_argument("--run-ocr-online", action="store_true")
    parser.add_argument("--run-ocr-offline", action="store_true")
    parser.add_argument("--auto-continue", action="store_true", help="Detect environment and continue supported QA automatically when safe.")
    args = parser.parse_args(argv)

    output_root = Path(args.output).resolve()
    evidence_dir = output_root / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    exe = Path(args.exe).resolve()
    samples = Path(args.samples).resolve()
    machine_info = build_machine_info()

    runner = WindowsQARunner(
        tester=args.tester,
        machine_info=machine_info,
        exe=exe,
        samples=samples,
        output_root=output_root,
        evidence_dir=evidence_dir,
        run_defender_scan=args.run_defender_scan,
        run_installer_test=args.run_installer_test,
        run_ocr_online=args.run_ocr_online,
        run_ocr_offline=args.run_ocr_offline,
        auto_continue=args.auto_continue,
    )
    result = runner.run()
    manual_json = output_root / "manual_qa_filled.json"
    evidence_md = output_root / "windows_qa_evidence.md"
    write_json(manual_json, result)
    evidence_md.write_text(render_evidence_markdown(result), encoding="utf-8")
    print(json.dumps({"manual_qa": str(manual_json), "evidence": str(evidence_md)}, indent=2))
    return 0


class WindowsQARunner:
    def __init__(
        self,
        tester: str,
        machine_info: str,
        exe: Path,
        samples: Path,
        output_root: Path,
        evidence_dir: Path,
        run_defender_scan: bool,
        run_installer_test: bool,
        run_ocr_online: bool,
        run_ocr_offline: bool,
        auto_continue: bool,
    ) -> None:
        self.tester = tester
        self.machine_info = machine_info
        self.exe = exe
        self.samples = samples
        self.output_root = output_root
        self.evidence_dir = evidence_dir
        self.run_defender_scan = run_defender_scan
        self.auto_continue = auto_continue
        self.run_installer_test = run_installer_test or (auto_continue and current_user_is_admin())
        self.run_ocr_online = run_ocr_online
        self.run_ocr_offline = run_ocr_offline
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.temp_before = snapshot_temp()

    def run(self) -> dict[str, Any]:
        environment_report = self.environment_detection()
        checks = [
            self.exe_launch(),
            self.package_hash(),
            self.clean_windows_no_python(),
            self.ocr_first_run_online(),
            self.ocr_offline_cache(),
            self.installer_install_uninstall(),
            self.startup_speed(),
            self.memory_usage(),
            self.temporary_file_cleanup(),
            self.permission_standard_user(),
            self.unicode_filename(),
            self.long_path(),
            self.windows_defender_scan(),
        ]
        return {
            "schema_version": 1,
            "app": "silukman_file_converter",
            "qa_type": "manual_production",
            "created_at": self.started_at,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "tester_name": self.tester,
            "machine_info": self.machine_info,
            "runner": {
                "exe": str(self.exe),
                "samples": str(self.samples),
                "output": str(self.output_root),
                "evidence": str(self.evidence_dir),
                "exe_exists": self.exe.exists(),
                "exe_sha256": sha256(self.exe) if self.exe.exists() else "",
                "latest_release_zip": str(latest_release_zip() or ""),
                "latest_release_zip_sha256": sha256(latest_release_zip()) if latest_release_zip() else "",
            },
            "environment_report": environment_report,
            "checks": checks,
        }

    def record(self, check_id: str, name: str, status: str, evidence: str, notes: str) -> dict[str, Any]:
        item = {
            "id": check_id,
            "name": name,
            "status": status,
            "evidence": evidence,
            "machine_info": self.machine_info,
            "tester_name": self.tester,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "notes": notes,
        }
        if status in {"blocked", "fail"}:
            item.update(classify_runner_blocker(check_id, notes))
        return item

    def evidence_path(self, name: str, suffix: str = ".json") -> Path:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return self.evidence_dir / f"{stamp}_{safe_name(name)}{suffix}"

    def clean_windows_no_python(self) -> dict[str, Any]:
        check_id, name = CHECKS[2]
        validation_path = self.output_root / "clean_windows_validation.json"
        if validation_path.exists():
            validation = read_json(validation_path)
            decision = str(validation.get("decision", "")).upper()
            evidence_dir = str(validation.get("evidence_dir", ""))
            if decision == "PASS":
                return self.record(
                    check_id,
                    name,
                    "pass",
                    f"{validation_path}; {evidence_dir}",
                    "Imported clean Windows VM evidence passed: no Python/pip/dev artifacts and EXE runtime checks passed.",
                )
            if decision in {"BLOCKED", "FAILED"}:
                return self.record(
                    check_id,
                    name,
                    "blocked" if decision == "BLOCKED" else "fail",
                    f"{validation_path}; {evidence_dir}",
                    f"Imported clean Windows validation decision is {decision}.",
                )
        evidence = {
            "python_executable_running_runner": sys.executable,
            "python_on_path": shutil.which("python"),
            "py_on_path": shutil.which("py"),
            "venv_exists": (ROOT_DIR / "venv").exists(),
            "dev_markers": [str(path) for path in [ROOT_DIR / "app", ROOT_DIR / "tests", ROOT_DIR / "scripts"] if path.exists()],
        }
        path = self.evidence_path(check_id)
        write_json(path, evidence)
        if evidence["python_on_path"] or evidence["py_on_path"] or evidence["venv_exists"]:
            return self.record(check_id, name, "blocked", str(path), "Python/dev environment detected. Clean Windows no-Python validation must run on a clean machine.")
        launch = launch_and_close(self.exe, self.evidence_dir, "clean_windows_launch")
        status = "pass" if launch["started"] and launch["exit_state"] != "crashed" else "fail"
        notes = "EXE launched and no Python was detected in PATH." if status == "pass" else "EXE did not launch cleanly."
        return self.record(check_id, name, status, f"{path}; {launch['log']}", notes)

    def ocr_first_run_online(self) -> dict[str, Any]:
        check_id, name = CHECKS[3]
        lifecycle = read_ocr_lifecycle()
        if lifecycle_phase_passed(lifecycle, "phase1_online_first_run"):
            return self.record(check_id, name, "pass", str(DEFAULT_OUTPUT / "ocr_validation.json"), "OCR lifecycle validation already proves online OCR output.")
        if not internet_available():
            evidence = self.write_blocked_evidence(check_id, "Internet check failed.")
            return self.record(check_id, name, "blocked", str(evidence), "Internet is unavailable, cannot prove first-run model bootstrap.")
        sample = first_sample(self.samples, IMAGE_EXTS)
        if sample is None:
            evidence = self.write_blocked_evidence(check_id, "No OCR-capable sample found.")
            return self.record(check_id, name, "blocked", str(evidence), "No image sample available.")
        result = run_exe_single_matrix(
            self.exe,
            self.samples,
            self.evidence_dir / "ocr_online_matrix",
            "windows-qa-ocr-online",
            operation="ocr_txt",
            input_file=sample.relative_to(self.samples).as_posix(),
            timeout=240,
        )
        status = "pass" if result["exit_code"] == 0 and result.get("row_status") in {"success", "success_short_text"} else "fail"
        notes = "OCR operation completed with internet available." if status == "pass" else "OCR operation did not complete successfully."
        return self.record(check_id, name, status, result["evidence"], notes)

    def ocr_offline_cache(self) -> dict[str, Any]:
        check_id, name = CHECKS[4]
        lifecycle = read_ocr_lifecycle()
        if lifecycle_phase_passed(lifecycle, "phase2_offline_cache"):
            return self.record(check_id, name, "pass", str(DEFAULT_OUTPUT / "ocr_validation.json"), "OCR lifecycle validation already proves cache-based OCR output.")
        cache = detect_ocr_cache()
        evidence_data = {"cache": cache, "internet_available": internet_available()}
        path = self.evidence_path(check_id)
        write_json(path, evidence_data)
        if not cache["cache_files"]:
            return self.record(check_id, name, "blocked", str(path), "No OCR model cache detected, cannot validate offline OCR.")
        if not self.run_ocr_offline:
            return self.record(check_id, name, "blocked", str(path), "OCR cache exists, but this default runner cannot safely disable internet. Re-run with --run-ocr-offline only in a controlled offline environment.")
        offline_env = dict(os.environ)
        offline_env["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        sample = first_sample(self.samples, IMAGE_EXTS)
        if sample is None:
            return self.record(check_id, name, "blocked", str(path), "No image sample available for offline OCR validation.")
        result = run_exe_single_matrix(
            self.exe,
            self.samples,
            self.evidence_dir / "ocr_offline_matrix",
            "windows-qa-ocr-offline",
            operation="ocr_txt",
            input_file=sample.relative_to(self.samples).as_posix(),
            timeout=240,
            env=offline_env,
        )
        status = "pass" if result["exit_code"] == 0 and result.get("row_status") in {"success", "success_short_text"} else "fail"
        notes = "OCR succeeded with cache-oriented environment. Internet was not forcibly disabled by the runner." if status == "pass" else "Offline-style OCR validation failed."
        return self.record(check_id, name, status, f"{path}; {result['evidence']}", notes)

    def installer_install_uninstall(self) -> dict[str, Any]:
        check_id, name = CHECKS[5]
        validation_path = self.output_root / "installer_validation.json"
        runner_path = ROOT_DIR / "tools" / "installer_qa_runner.py"
        path = self.evidence_path(check_id)

        if self.run_installer_test:
            command = [
                sys.executable,
                str(runner_path),
                "--run-installer-test",
                "--output",
                str(self.output_root),
            ]
            started = time.perf_counter()
            proc = subprocess.run(command, cwd=ROOT_DIR, text=True, capture_output=True, timeout=900)
            evidence = {
                "command": command,
                "exit_code": proc.returncode,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "installer_validation": str(validation_path),
            }
            write_json(path, evidence)

        if validation_path.exists():
            validation = read_json(validation_path)
            decision = str(validation.get("decision", "")).upper()
            status = "pass" if decision == "PASS" else "blocked" if decision == "BLOCKED" else "fail"
            notes = (
                "Installer validation passed with install/uninstall evidence."
                if status == "pass"
                else f"Installer validation decision is {decision or 'missing'}."
            )
            return self.record(check_id, name, status, f"{path}; {validation_path}", notes)

        installers = sorted((ROOT_DIR / "dist").glob("*setup*.exe"))
        evidence = {"installers": [str(item) for item in installers], "run_installer_test": self.run_installer_test}
        write_json(path, evidence)
        if not installers:
            return self.record(check_id, name, "blocked", str(path), "No installer artifact found.")
        return self.record(check_id, name, "blocked", str(path), "Installer artifact exists, but --run-installer-test was not provided.")

    def startup_speed(self) -> dict[str, Any]:
        check_id, name = CHECKS[6]
        cold = launch_and_close(self.exe, self.evidence_dir, "startup_cold", wait_seconds=3)
        warm = launch_and_close(self.exe, self.evidence_dir, "startup_warm", wait_seconds=3)
        evidence = {"cold": cold, "warm": warm, "thresholds": {"cold_seconds": 10, "warm_seconds": 5}}
        path = self.evidence_path(check_id)
        write_json(path, evidence)
        status = "pass" if cold["started"] and warm["started"] and cold["launch_elapsed_seconds"] <= 10 and warm["launch_elapsed_seconds"] <= 5 else "fail"
        notes = f"cold={cold['launch_elapsed_seconds']}s, warm={warm['launch_elapsed_seconds']}s. This measures process launch/survival, not visual UI paint."
        return self.record(check_id, name, status, f"{path}; {cold['log']}; {warm['log']}", notes)

    def memory_usage(self) -> dict[str, Any]:
        check_id, name = CHECKS[7]
        if not self.exe.exists():
            evidence = self.write_blocked_evidence(check_id, "EXE not found.")
            return self.record(check_id, name, "fail", str(evidence), "EXE not found.")
        log_path = self.evidence_path(check_id, ".log")
        started = time.perf_counter()
        proc = subprocess.Popen([str(self.exe)], cwd=ROOT_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(5)
        memory = get_process_memory_bytes(proc.pid)
        exit_state = "running"
        if proc.poll() is not None:
            exit_state = f"exited:{proc.returncode}"
        terminate_process(proc)
        payload = {
            "pid": proc.pid,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "idle_memory_bytes": memory,
            "idle_memory_mib": round(memory / 1024 / 1024, 2) if memory else None,
            "exit_state": exit_state,
            "ocr_peak_memory": "not measured by this runner; OCR UI automation is not safe headlessly",
        }
        log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        status = "pass" if memory and exit_state == "running" else "fail"
        notes = "Idle memory measured; OCR peak not claimed because GUI OCR operation was not safely automated."
        return self.record(check_id, name, status, str(log_path), notes)

    def temporary_file_cleanup(self) -> dict[str, Any]:
        check_id, name = CHECKS[8]
        sample = first_sample(self.samples, PDF_EXTS)
        if sample is None:
            evidence = self.write_blocked_evidence(check_id, "No PDF sample found for graceful CLI temp cleanup probe.")
            return self.record(check_id, name, "blocked", str(evidence), "No PDF sample available.")
        before_probe = snapshot_temp()
        cli_result = run_exe_single_matrix(
            self.exe,
            self.samples,
            self.evidence_dir / "temp_cleanup_matrix",
            "windows-qa-temp-cleanup",
            operation="pdf_to_png",
            input_file=sample.relative_to(self.samples).as_posix(),
            timeout=120,
        )
        cleanup = wait_for_temp_cleanup(before_probe, timeout=15)
        temp_after = cleanup["snapshot"]
        suspicious = cleanup["new_remaining"]
        evidence = {
            "before": sorted(before_probe["_mei_dirs"]),
            "after": sorted(temp_after["_mei_dirs"]),
            "new_remaining_mei_dirs": suspicious,
            "waited_seconds": cleanup["waited_seconds"],
            "cli_result": cli_result,
        }
        path = self.evidence_path(check_id)
        write_json(path, evidence)
        if not suspicious and cli_result["exit_code"] == 0:
            status = "pass"
            notes = "No new _MEI temp directories remained after a graceful EXE CLI operation."
        else:
            status = "fail"
            notes = "Suspicious PyInstaller temp directories remained or the CLI cleanup probe failed."
        return self.record(check_id, name, status, f"{path}; {cli_result['evidence']}", notes)

    def permission_standard_user(self) -> dict[str, Any]:
        check_id, name = CHECKS[9]
        is_admin = current_user_is_admin()
        documents = Path.home() / "Documents"
        doc_probe = documents / f"silukman_permission_probe_{int(time.time())}.txt"
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        denied_probe = program_files / f"silukman_permission_probe_{int(time.time())}.txt"
        doc_write = probe_write_file(doc_probe)
        denied_write = probe_write_file(denied_probe)
        evidence = {
            "is_admin": is_admin,
            "userprofile": os.environ.get("USERPROFILE"),
            "documents": str(documents),
            "documents_probe": doc_write,
            "program_files": str(program_files),
            "program_files_probe": denied_write,
        }
        path = self.evidence_path(check_id)
        write_json(path, evidence)
        if is_admin:
            return self.record(check_id, name, "blocked", str(path), "Current process appears elevated/admin. Standard-user permission handling must be proven as a standard user.")
        status = "pass" if doc_write["success"] and not denied_write["success"] else "fail"
        notes = "Standard user can write Documents and cannot write Program Files probe path." if status == "pass" else "Standard-user permission probe did not behave as expected."
        return self.record(check_id, name, status, str(path), notes)

    def unicode_filename(self) -> dict[str, Any]:
        check_id, name = CHECKS[10]
        sample = first_sample(self.samples, IMAGE_EXTS)
        if sample is None:
            evidence = self.write_blocked_evidence(check_id, "No image sample found.")
            return self.record(check_id, name, "blocked", str(evidence), "No image sample available.")
        with tempfile.TemporaryDirectory(prefix="silukman_unicode_") as temp_dir:
            temp_path = Path(temp_dir)
            unicode_name = "tagihan_Indonesia_中文_日本어_áéíóú.png"
            target = temp_path / unicode_name
            shutil.copy2(sample, target)
            result = run_source_converter(target, "image_to_pdf", temp_path / "output")
            evidence_path = self.evidence_path(check_id)
            write_json(evidence_path, {"sample": str(sample), "unicode_input": str(target), "result": result})
            status = "pass" if result.get("success") and result.get("outputs") else "fail"
            notes = "Unicode filename conversion succeeded." if status == "pass" else "Unicode filename conversion failed."
            return self.record(check_id, name, status, str(evidence_path), notes)

    def long_path(self) -> dict[str, Any]:
        check_id, name = CHECKS[11]
        validation_path = self.output_root / "longpath_validation.json"
        runner_path = ROOT_DIR / "tools" / "longpath_validation.py"
        evidence_path = self.evidence_path(check_id)
        command = [
            sys.executable,
            str(runner_path),
            "--exe",
            str(self.exe),
            "--samples",
            str(self.samples),
            "--output",
            str(self.output_root),
        ]
        started = time.perf_counter()
        proc = subprocess.run(command, cwd=ROOT_DIR, text=True, capture_output=True, timeout=420)
        evidence = {
            "command": command,
            "exit_code": proc.returncode,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "longpath_validation": str(validation_path),
        }
        write_json(evidence_path, evidence)
        if not validation_path.exists():
            return self.record(check_id, name, "fail", str(evidence_path), "Long path validation report was not generated.")
        validation = read_json(validation_path)
        decision = str(validation.get("decision", "")).upper()
        status = "pass" if decision == "PASS" else "fail"
        notes = (
            "Long path validation passed: every case succeeded or returned controlled error."
            if status == "pass"
            else f"Long path validation decision is {decision or 'missing'}."
        )
        return self.record(check_id, name, status, f"{evidence_path}; {validation_path}", notes)

    def windows_defender_scan(self) -> dict[str, Any]:
        check_id, name = CHECKS[12]
        if not self.run_defender_scan:
            validation_path = self.output_root / "defender_validation.json"
            if validation_path.exists():
                validation = read_json(validation_path)
                decision = str(validation.get("decision", "")).upper()
                status = "pass" if decision == "PASS" else "blocked" if decision == "BLOCKED" else "fail"
                notes = (
                    "Defender validation already passed with evidence."
                    if status == "pass"
                    else f"Defender validation decision is {decision or 'missing'}."
                )
                return self.record(check_id, name, status, str(validation_path), notes)
            evidence = self.write_blocked_evidence(check_id, "Flag --run-defender-scan was not provided.")
            return self.record(check_id, name, "blocked", str(evidence), "Defender scan is opt-in.")

        validation_path = self.output_root / "defender_validation.json"
        runner_path = ROOT_DIR / "tools" / "defender_validation.py"
        evidence_path = self.evidence_path(check_id)
        command = [
            sys.executable,
            str(runner_path),
            "--scan-exe",
            "--scan-zip",
            "--output",
            str(self.output_root),
        ]
        if sorted((ROOT_DIR / "dist").glob("*setup*.exe")):
            command.append("--scan-installer")
        started = time.perf_counter()
        proc = subprocess.run(command, cwd=ROOT_DIR, text=True, capture_output=True, timeout=2400)
        evidence = {
            "command": command,
            "exit_code": proc.returncode,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "defender_validation": str(validation_path),
        }
        write_json(evidence_path, evidence)

        if not validation_path.exists():
            return self.record(check_id, name, "fail", str(evidence_path), "Defender validation report was not generated.")
        validation = read_json(validation_path)
        decision = str(validation.get("decision", "")).upper()
        status = "pass" if decision == "PASS" else "blocked" if decision == "BLOCKED" else "fail"
        notes = (
            "Defender scan passed for selected artifacts."
            if status == "pass"
            else f"Defender validation decision is {decision or 'missing'}."
        )
        return self.record(check_id, name, status, f"{evidence_path}; {validation_path}", notes)

    def exe_launch(self) -> dict[str, Any]:
        check_id, name = CHECKS[0]
        launch = launch_and_close(self.exe, self.evidence_dir, "exe_launch", wait_seconds=3)
        status = "pass" if launch.get("started") and launch.get("exit_state") == "running" else "fail"
        notes = "EXE launched and stayed alive during observation window." if status == "pass" else "EXE did not launch or exited during observation."
        return self.record(check_id, name, status, launch["log"], notes)

    def package_hash(self) -> dict[str, Any]:
        check_id, name = CHECKS[1]
        zip_path = latest_release_zip()
        payload = {
            "exe": str(self.exe),
            "exe_exists": self.exe.exists(),
            "exe_size_bytes": self.exe.stat().st_size if self.exe.exists() else 0,
            "exe_sha256": sha256(self.exe) if self.exe.exists() else "",
            "release_zip": str(zip_path or ""),
            "release_zip_exists": bool(zip_path and zip_path.exists()),
            "release_zip_size_bytes": zip_path.stat().st_size if zip_path and zip_path.exists() else 0,
            "release_zip_sha256": sha256(zip_path) if zip_path and zip_path.exists() else "",
        }
        path = self.evidence_path(check_id)
        write_json(path, payload)
        status = "pass" if payload["exe_sha256"] and payload["release_zip_sha256"] else "blocked"
        notes = "EXE and latest release ZIP hashes recorded." if status == "pass" else "EXE or release ZIP hash could not be recorded."
        return self.record(check_id, name, status, str(path), notes)

    def write_blocked_evidence(self, check_id: str, reason: str) -> Path:
        path = self.evidence_path(check_id)
        write_json(path, {"status": "blocked", "reason": reason})
        return path

    def environment_detection(self) -> dict[str, Any]:
        runner = ROOT_DIR / "tools" / "environment_detector.py"
        report_path = self.output_root / "environment_report.json"
        command = [sys.executable, str(runner), "--output", str(self.output_root)]
        started = time.perf_counter()
        proc = subprocess.run(command, cwd=ROOT_DIR, text=True, capture_output=True, timeout=120)
        evidence = {
            "command": command,
            "exit_code": proc.returncode,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "report": str(report_path),
            "auto_continue": self.auto_continue,
            "run_installer_test": self.run_installer_test,
        }
        path = self.evidence_path("environment_detection")
        write_json(path, evidence)
        data = read_json(report_path) if report_path.exists() else {}
        return {
            "status": "pass" if proc.returncode == 0 and data else "fail",
            "evidence": f"{path}; {report_path}",
            "summary": data.get("summary", {}) if isinstance(data, dict) else {},
            "actions": data.get("actions", []) if isinstance(data, dict) else [],
        }


def classify_runner_blocker(check_id: str, notes: str) -> dict[str, str]:
    lower = f"{check_id} {notes}".lower()
    if check_id == "installer_install_uninstall" or "installer" in lower:
        setup_exists = any((ROOT_DIR / "dist").glob("*setup*.exe"))
        blocker_type = "missing_admin" if setup_exists or "administrator" in lower or "program files" in lower else "artifact_missing"
        cause = "Installer install/uninstall validation has not passed."
        why = "Production requires install, shortcut, launch, uninstall, and cleanup evidence."
        auto_fix = "no" if blocker_type == "missing_admin" else "partial"
        command = (
            f"Auto: python tools\\installer_build_qa.py --run-installer-test --auto-elevate; "
            f"Manual UAC: powershell Start-Process powershell -Verb RunAs, then run: cd {ROOT_DIR}; python tools\\installer_build_qa.py --run-installer-test"
        )
        estimate = "5-10 minutes after an elevated PowerShell is available."
    elif check_id == "clean_windows_no_python":
        blocker_type = "external_vm_required"
        cause = "Clean Windows no-Python validation has not passed."
        why = "This can pass only on a clean Windows VM/machine without Python, pip, venv, source code, or build tools."
        auto_fix = "no"
        command = "Run in clean VM: powershell -ExecutionPolicy Bypass -File .\\qa\\clean_windows_runner.ps1; then import: python tools\\import_clean_windows_validation.py path\\to\\clean_windows_validation.json"
        estimate = "10-20 minutes plus VM startup time."
    elif "not provided" in lower or "not found" in lower or "missing" in lower:
        blocker_type = "evidence_missing"
        cause = "Required evidence or artifact is missing."
        why = "The Windows QA runner cannot mark pass without concrete evidence."
        auto_fix = "partial"
        command = "python tools\\windows_qa_runner.py --tester \"Your Name\" --run-defender-scan"
        estimate = "5-15 minutes."
    else:
        blocker_type = "runtime_failure"
        cause = "Runtime QA check did not pass."
        why = "Production requires every automated and evidence-backed manual check to pass."
        auto_fix = "partial"
        command = "Inspect the evidence path shown for this check, fix the cause, and rerun the relevant QA runner."
        estimate = "Depends on the failure; usually 5-30 minutes."
    return {
        "blocker_type": blocker_type,
        "exact_cause": cause,
        "why_blocked": why,
        "auto_fix_possible": auto_fix,
        "next_command": command,
        "estimated_remaining_work": estimate,
    }


def run_source_converter(input_path: Path, operation: str, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    code = (
        "import json, sys; "
        "from app.core.converter import Converter; "
        "result=Converter().convert(sys.argv[1], sys.argv[2], sys.argv[3]); "
        "print(json.dumps({**result, 'outputs':[str(p) for p in result.get('outputs', [])]}, default=str))"
    )
    command = [str(project_python()), "-c", code, str(input_path), operation, str(output_dir)]
    proc = subprocess.run(command, cwd=ROOT_DIR, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {}
    payload.update({"returncode": proc.returncode, "stderr": proc.stderr[-2000:], "stdout": proc.stdout[-2000:]})
    return payload


def run_exe_matrix(exe: Path, samples: Path, output: Path, label: str, timeout: int, env: dict[str, str] | None = None) -> dict[str, Any]:
    command = [str(exe), "--sample-matrix", "--samples", str(samples), "--output", str(output), "--source-label", label]
    result = run_logged(command, output.parent, label, timeout=timeout, env=env)
    latest = latest_child_dir(output)
    summary_path = latest / "summary" / "summary_exe.json" if latest else None
    summary_json = read_json(summary_path) if summary_path and summary_path.exists() else {}
    return {
        "exit_code": result["returncode"],
        "evidence": f"{result['log']}; {summary_path}" if summary_path else result["log"],
        "summary_json": summary_json,
    }


def run_exe_single_matrix(
    exe: Path,
    samples: Path,
    output: Path,
    label: str,
    operation: str,
    input_file: str,
    timeout: int,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    command = [
        str(exe),
        "--sample-matrix",
        "--samples",
        str(samples),
        "--output",
        str(output),
        "--source-label",
        label,
        "--matrix-op",
        operation,
        "--matrix-input",
        input_file,
    ]
    result = run_logged(command, output.parent, label, timeout=timeout, env=env)
    latest = latest_child_dir(output)
    summary_path = latest / "summary" / "summary_exe.json" if latest else None
    rows_path = latest / "summary" / "summary.json" if latest else None
    summary_json = read_json(summary_path) if summary_path and summary_path.exists() else {}
    rows = read_json(rows_path) if rows_path and rows_path.exists() else []
    row_status = rows[0].get("final_status") if rows else ""
    return {
        "exit_code": result["returncode"],
        "evidence": f"{result['log']}; {summary_path}; {rows_path}" if summary_path else result["log"],
        "summary_json": summary_json,
        "row_status": row_status,
        "rows": rows,
    }


def matrix_has_ocr_success(summary: dict[str, Any] | None) -> bool:
    if not summary:
        return False
    return summary.get("exe_ocr_verification") == "exe_ocr_passed" and summary.get("summary", {}).get("failed", 1) == 0


def launch_and_close(exe: Path, evidence_dir: Path, name: str, wait_seconds: float = 3) -> dict[str, Any]:
    log_path = evidence_dir / f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_name(name)}.json"
    if not exe.exists():
        payload = {"started": False, "error": f"EXE not found: {exe}", "log": str(log_path)}
        write_json(log_path, payload)
        return payload
    before_pids = running_exe_pids(exe)
    started = time.perf_counter()
    proc = subprocess.Popen([str(exe)], cwd=ROOT_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    launch_elapsed = time.perf_counter() - started
    time.sleep(wait_seconds)
    after_pids = running_exe_pids(exe)
    new_pids = sorted(after_pids - before_pids)
    exit_state = "running"
    if proc.poll() is not None:
        exit_state = "crashed" if proc.returncode else "exited"
    terminate_process(proc)
    for pid in new_pids:
        kill_pid(pid)
    payload = {
        "started": True,
        "pid": proc.pid,
        "new_child_pids": new_pids,
        "launch_elapsed_seconds": round(launch_elapsed, 3),
        "observed_seconds": wait_seconds,
        "exit_state": exit_state,
        "log": str(log_path),
    }
    write_json(log_path, payload)
    return payload


def terminate_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)
        try:
            proc.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            pass
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def running_exe_pids(exe: Path) -> set[int]:
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"Get-Process | Where-Object {{$_.Path -eq '{str(exe)}'}} | Select-Object -ExpandProperty Id",
    ]
    proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30, check=False)
    pids = set()
    for line in proc.stdout.splitlines():
        try:
            pids.add(int(line.strip()))
        except ValueError:
            continue
    return pids


def kill_pid(pid: int) -> None:
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)


def run_logged(command: list[str], evidence_dir: Path, name: str, timeout: int, env: dict[str, str] | None = None) -> dict[str, Any]:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    base = evidence_dir / f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_name(name)}"
    stdout_path = base.with_suffix(".stdout.log")
    stderr_path = base.with_suffix(".stderr.log")
    meta_path = base.with_suffix(".meta.json")
    started = time.perf_counter()
    try:
        proc = subprocess.run(command, cwd=ROOT_DIR, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, env=env, check=False)
        elapsed = time.perf_counter() - started
        stdout_path.write_text(proc.stdout, encoding="utf-8", errors="replace")
        stderr_path.write_text(proc.stderr, encoding="utf-8", errors="replace")
        meta = {"command": command, "returncode": proc.returncode, "elapsed_seconds": round(elapsed, 3), "stdout": str(stdout_path), "stderr": str(stderr_path)}
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - started
        stdout_path.write_text(str(exc.stdout or ""), encoding="utf-8", errors="replace")
        stderr_path.write_text(str(exc.stderr or ""), encoding="utf-8", errors="replace")
        meta = {"command": command, "returncode": -999, "elapsed_seconds": round(elapsed, 3), "timeout": timeout, "stdout": str(stdout_path), "stderr": str(stderr_path)}
    write_json(meta_path, meta)
    return {"returncode": meta["returncode"], "log": str(meta_path), "stdout": str(stdout_path), "stderr": str(stderr_path)}


def first_sample(samples: Path, extensions: set[str]) -> Path | None:
    if not samples.exists():
        return None
    skip_names = {"README_TEST_INPUTS.md", "SOURCE_URLS.txt", "expected_keywords.json"}
    for path in sorted(samples.rglob("*")):
        if not path.is_file() or path.name in skip_names:
            continue
        if "07_expected_results" in path.parts:
            continue
        if path.suffix.lower() in extensions:
            return path
    return None


def detect_ocr_cache() -> dict[str, Any]:
    candidates = [
        Path(os.environ["PADDLEOCR_HOME"]) if os.environ.get("PADDLEOCR_HOME") else None,
        Path(os.environ["PADDLE_HOME"]) if os.environ.get("PADDLE_HOME") else None,
        Path.home() / ".paddleocr",
        Path.home() / ".paddlex",
        Path.home() / ".paddle",
        Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SilukmanFileConverter" / "ocr_models",
    ]
    files: list[str] = []
    for directory in [path for path in candidates if path is not None]:
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and (path.suffix.lower() in {".pdmodel", ".pdiparams", ".yml", ".yaml", ".json", ".nb"} or "inference" in path.name.lower()):
                files.append(str(path))
    return {"cache_dirs": [str(path) for path in candidates if path is not None], "cache_files": files, "cache_file_count": len(files)}


def internet_available(timeout: float = 3.0) -> bool:
    for host, port in (("paddleocr.bj.bcebos.com", 443), ("1.1.1.1", 443)):
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def snapshot_temp() -> dict[str, set[str]]:
    temp_root = Path(tempfile.gettempdir())
    mei_dirs = set()
    app_dirs = set()
    for path in temp_root.glob("*"):
        name = path.name.lower()
        if path.is_dir() and name.startswith("_mei"):
            mei_dirs.add(str(path))
        if path.is_dir() and "silukman" in name:
            app_dirs.add(str(path))
    return {"_mei_dirs": mei_dirs, "app_dirs": app_dirs}


def wait_for_temp_cleanup(before: dict[str, set[str]], timeout: float = 15.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    latest = snapshot_temp()
    while time.time() < deadline:
        latest = snapshot_temp()
        new_mei = sorted(latest["_mei_dirs"] - before["_mei_dirs"])
        if not [path for path in new_mei if Path(path).exists()]:
            return {"snapshot": latest, "new_remaining": [], "waited_seconds": round(timeout - (deadline - time.time()), 2)}
        time.sleep(1)
    latest = snapshot_temp()
    new_mei = sorted(latest["_mei_dirs"] - before["_mei_dirs"])
    return {"snapshot": latest, "new_remaining": [path for path in new_mei if Path(path).exists()], "waited_seconds": timeout}


def get_process_memory_bytes(pid: int) -> int:
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).WorkingSet64",
    ]
    proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
    try:
        return int(proc.stdout.strip())
    except ValueError:
        return 0


def current_user_is_admin() -> bool:
    command = ["powershell", "-NoProfile", "-Command", "([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)"]
    proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
    return proc.stdout.strip().lower() == "true"


def probe_write_file(path: Path) -> dict[str, Any]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("silukman permission probe\n", encoding="utf-8")
        path.unlink(missing_ok=True)
        return {"path": str(path), "success": True, "error": ""}
    except Exception as exc:
        return {"path": str(path), "success": False, "error": f"{type(exc).__name__}: {exc}"}


def defender_scan_command(path: Path) -> list[str] | None:
    powershell = shutil.which("powershell")
    if powershell:
        return [powershell, "-NoProfile", "-Command", f"Start-MpScan -ScanType CustomScan -ScanPath '{str(path)}'"]
    return None


def build_machine_info() -> str:
    return f"{platform.platform()} | {platform.machine()} | {platform.processor()}".strip()


def project_python() -> Path:
    candidate = ROOT_DIR / "venv" / "Scripts" / "python.exe"
    return candidate if candidate.exists() else Path(sys.executable)


def latest_release_zip() -> Path | None:
    dist = ROOT_DIR / "dist"
    if not dist.exists():
        return None
    candidates = sorted(dist.glob("silukman_file_converter_*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def read_ocr_lifecycle() -> dict[str, Any]:
    path = DEFAULT_OUTPUT / "ocr_validation.json"
    if not path.exists():
        return {}
    try:
        return read_json(path)
    except Exception:
        return {}


def lifecycle_phase_passed(data: dict[str, Any], phase_id: str) -> bool:
    if not data or data.get("decision") not in {"PASS", "BLOCKED", "FAILED"}:
        return False
    for check in data.get("checks", []):
        if check.get("id") == phase_id and check.get("status") == "pass":
            outputs = check.get("details", {}).get("ocr_outputs", [])
            return any(item.get("exists") and item.get("size_bytes", 0) > 0 for item in outputs)
    return False


def render_evidence_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# Windows QA Evidence",
        "",
        f"App: `{data['app']}`",
        f"Tester: `{data['tester_name']}`",
        f"Machine: `{data['machine_info']}`",
        f"Created: `{data['created_at']}`",
        f"Evidence: `{data['runner']['evidence']}`",
        "",
        "## Checks",
        "",
        "| check | status | evidence | notes |",
        "| --- | --- | --- | --- |",
    ]
    for check in data["checks"]:
        lines.append(f"| {escape_md(check['name'])} | {check['status']} | {escape_md(check['evidence'])} | {escape_md(check['notes'])} |")
    return "\n".join(lines)


def latest_child_dir(path: Path) -> Path | None:
    if not path.exists():
        return None
    dirs = [item for item in path.iterdir() if item.is_dir()]
    return max(dirs, key=lambda item: item.stat().st_mtime) if dirs else None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value).strip("_").lower()


def escape_md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
