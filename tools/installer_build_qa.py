from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT_DIR / "output" / "production_qa"
EXPECTED_SETUP = ROOT_DIR / "dist" / "silukman_file_converter_setup.exe"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Inno Setup installer and run install/uninstall QA.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--run-installer-test", action="store_true", help="Run silent install/uninstall QA after build.")
    parser.add_argument("--allow-existing-install", action="store_true")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--auto-elevate", action="store_true", help="Relaunch this QA flow in an elevated PowerShell when needed.")
    args = parser.parse_args(argv)

    output_root = Path(args.output).resolve()
    if args.auto_elevate and not running_as_admin():
        result = run_elevated_handoff(
            output_root=output_root,
            run_installer_test=args.run_installer_test,
            allow_existing_install=args.allow_existing_install,
            timeout=args.timeout,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("decision") == "PASS" else 1

    runner = InstallerBuildQa(
        output_root=output_root,
        run_installer_test=args.run_installer_test,
        allow_existing_install=args.allow_existing_install,
        timeout=args.timeout,
    )
    result = runner.run()
    print(f"Installer build QA written: {runner.report_path}")
    print(f"Evidence directory: {runner.evidence_dir}")
    print(f"Decision: {result['decision']}")
    if result["decision"] == "BLOCKED":
        for blocker in result["blockers"]:
            print(f"BLOCKED: {blocker}")
    return 0 if result["decision"] == "PASS" else 1


def run_elevated_handoff(output_root: Path, run_installer_test: bool, allow_existing_install: bool, timeout: int) -> dict[str, Any]:
    evidence_dir = output_root / "evidence" / "installer"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    handoff_path = evidence_dir / "elevation_handoff.json"
    stdout_path = evidence_dir / "elevation_handoff.stdout.log"
    stderr_path = evidence_dir / "elevation_handoff.stderr.log"
    elevated_command = [
        str(Path(sys.executable).resolve()),
        str(ROOT_DIR / "tools" / "installer_build_qa.py"),
        "--output",
        str(output_root),
        "--timeout",
        str(timeout),
    ]
    if run_installer_test:
        elevated_command.append("--run-installer-test")
    if allow_existing_install:
        elevated_command.append("--allow-existing-install")
    inner = (
        f"Set-Location -LiteralPath {ps_quote(str(ROOT_DIR))}; "
        f"& {ps_quote(elevated_command[0])} "
        + " ".join(ps_quote(arg) for arg in elevated_command[1:])
        + "; exit $LASTEXITCODE"
    )
    launcher = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        (
            "$p = Start-Process -FilePath 'powershell' "
            f"-ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-Command',{ps_quote(inner)}) "
            "-Verb RunAs -Wait -PassThru; exit $p.ExitCode"
        ),
    ]
    started = time.perf_counter()
    proc = subprocess.run(launcher, cwd=ROOT_DIR, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout + 120, check=False)
    stdout_path.write_text(proc.stdout or "", encoding="utf-8")
    stderr_path.write_text(proc.stderr or "", encoding="utf-8")
    validation_path = output_root / "installer_validation.json"
    validation = read_json(validation_path) if validation_path.exists() else {}
    decision = str(validation.get("decision", "")).upper()
    result = {
        "schema_version": 1,
        "app": "silukman_file_converter",
        "qa_type": "installer_elevation_handoff",
        "created_at": now_iso(),
        "decision": "PASS" if decision == "PASS" else "BLOCKED",
        "is_admin_before_handoff": False,
        "run_this_if_uac_was_cancelled": "powershell Start-Process powershell -Verb RunAs",
        "continue_command": f"cd {ROOT_DIR}; python tools\\installer_build_qa.py --run-installer-test",
        "elevated_command": elevated_command,
        "launcher": launcher,
        "exit_code": proc.returncode,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "installer_validation": str(validation_path),
        "installer_validation_decision": decision,
        "notes": (
            "Elevated installer validation passed and evidence was written."
            if decision == "PASS"
            else "Elevation was requested, but installer validation has not passed. UAC may have been cancelled or elevated QA was blocked."
        ),
    }
    write_json(handoff_path, result)
    return result


class InstallerBuildQa:
    def __init__(self, output_root: Path, run_installer_test: bool, allow_existing_install: bool, timeout: int) -> None:
        self.output_root = output_root
        self.evidence_dir = output_root / "evidence" / "installer" / "build"
        self.report_path = output_root / "installer_build_qa.json"
        self.markdown_path = output_root / "installer_build_qa.md"
        self.dependency_report_path = output_root / "installer_dependency_report.json"
        self.build_validation_path = output_root / "installer_build_validation.json"
        self.run_installer_test = run_installer_test
        self.allow_existing_install = allow_existing_install
        self.timeout = timeout
        self.checks: list[dict[str, Any]] = []

    def run(self) -> dict[str, Any]:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)

        iscc_check = self.detect_iscc()
        if iscc_check["status"] == "pass":
            self.run_build_installer()
        else:
            self.write_blocked_installer_validation("Inno Setup Compiler is missing; setup EXE cannot be built.")

        self.verify_setup()
        self.run_installer_validation()

        decision = self.decision()
        build_decision = self.build_decision()
        result = {
            "schema_version": 1,
            "app": "silukman_file_converter",
            "qa_type": "installer_build_and_install_uninstall",
            "created_at": now_iso(),
            "decision": decision,
            "expected_setup": str(EXPECTED_SETUP),
            "evidence_dir": str(self.evidence_dir),
            "machine_info": machine_info(),
            "summary": summarize(self.checks),
            "blockers": [check["notes"] for check in self.checks if check["status"] == "blocked"],
            "checks": self.checks,
            "rule": "PASS only when ISCC exists, build_installer.ps1 creates expected setup EXE, and installer_qa_runner.py passes with evidence.",
        }
        build_validation = {
            "schema_version": 1,
            "app": "silukman_file_converter",
            "qa_type": "installer_build_validation",
            "created_at": now_iso(),
            "decision": build_decision,
            "expected_setup": str(EXPECTED_SETUP),
            "evidence_dir": str(self.evidence_dir),
            "summary": summarize([check for check in self.checks if check["id"] in {"iscc_detection", "build_installer", "setup_artifact"}]),
            "blockers": [
                check["notes"]
                for check in self.checks
                if check["id"] in {"iscc_detection", "build_installer", "setup_artifact"} and check["status"] == "blocked"
            ],
            "checks": [check for check in self.checks if check["id"] in {"iscc_detection", "build_installer", "setup_artifact"}],
            "rule": "PASS when ISCC exists, build_installer.ps1 succeeds, and dist\\silukman_file_converter_setup.exe exists with hash evidence.",
        }
        write_json(self.report_path, result)
        write_json(self.build_validation_path, build_validation)
        self.markdown_path.write_text(render_markdown(result), encoding="utf-8")
        return result

    def detect_iscc(self) -> dict[str, Any]:
        path = self.evidence_dir / "iscc_detection.json"
        candidates = iscc_candidates()
        found = next((candidate for candidate in candidates if candidate["exists"]), None)
        evidence = {
            "found": bool(found),
            "searched_paths": [candidate["path"] for candidate in candidates],
            "path_entries_checked": os.environ.get("PATH", ""),
            "candidates": candidates,
            "selected": found["path"] if found else "",
            "recommendation": inno_install_instruction(),
            "install_instruction": inno_install_instruction(),
        }
        write_json(path, evidence)
        write_json(self.dependency_report_path, evidence)
        status = "pass" if found else "blocked"
        notes = "Inno Setup Compiler detected." if found else "Inno Setup Compiler (ISCC.exe) not found. Install Inno Setup 6, then rerun installer build QA."
        return self.record("iscc_detection", "Detect Inno Setup Compiler", status, path, notes, evidence)

    def run_build_installer(self) -> dict[str, Any]:
        path = self.evidence_dir / "build_installer_process.json"
        stdout = self.evidence_dir / "build_installer.stdout.log"
        stderr = self.evidence_dir / "build_installer.stderr.log"
        result = run_process(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT_DIR / "build_installer.ps1"),
            ],
            self.timeout,
            stdout,
            stderr,
        )
        setup_hash = sha256(EXPECTED_SETUP) if EXPECTED_SETUP.exists() else ""
        result["expected_setup"] = str(EXPECTED_SETUP)
        result["setup_exists_after_build"] = EXPECTED_SETUP.exists()
        result["setup_size_bytes_after_build"] = EXPECTED_SETUP.stat().st_size if EXPECTED_SETUP.exists() else 0
        result["setup_sha256_after_build"] = setup_hash
        write_json(path, result)
        status = "pass" if result["exit_code"] == 0 and not result["timed_out"] else "fail"
        notes = "build_installer.ps1 completed." if status == "pass" else "build_installer.ps1 failed or timed out."
        return self.record("build_installer", "Run build_installer.ps1", status, path, notes, result)

    def verify_setup(self) -> dict[str, Any]:
        path = self.evidence_dir / "setup_artifact.json"
        evidence = {
            "expected_setup": str(EXPECTED_SETUP),
            "exists": EXPECTED_SETUP.exists(),
            "size_bytes": EXPECTED_SETUP.stat().st_size if EXPECTED_SETUP.exists() else 0,
            "sha256": sha256(EXPECTED_SETUP) if EXPECTED_SETUP.exists() else "",
            "dist_setup_candidates": [str(candidate) for candidate in sorted((ROOT_DIR / "dist").glob("*setup*.exe"))],
        }
        write_json(path, evidence)
        status = "pass" if evidence["exists"] and evidence["size_bytes"] > 0 else "blocked"
        notes = "Expected installer setup EXE exists." if status == "pass" else "Expected installer setup EXE is missing: dist\\silukman_file_converter_setup.exe"
        return self.record("setup_artifact", "Verify installer setup EXE", status, path, notes, evidence)

    def run_installer_validation(self) -> dict[str, Any]:
        path = self.evidence_dir / "installer_qa_process.json"
        stdout = self.evidence_dir / "installer_qa.stdout.log"
        stderr = self.evidence_dir / "installer_qa.stderr.log"
        command = [
            sys.executable,
            str(ROOT_DIR / "tools" / "installer_qa_runner.py"),
            "--output",
            str(self.output_root),
        ]
        if self.run_installer_test:
            command.append("--run-installer-test")
        if self.allow_existing_install:
            command.append("--allow-existing-install")
        if EXPECTED_SETUP.exists():
            command.extend(["--installer", str(EXPECTED_SETUP)])
        result = run_process(command, self.timeout, stdout, stderr)
        validation_path = self.output_root / "installer_validation.json"
        validation = read_json(validation_path) if validation_path.exists() else {}
        payload = {
            "process": result,
            "installer_validation": str(validation_path),
            "validation_decision": validation.get("decision", ""),
            "validation_summary": validation.get("summary", {}),
        }
        write_json(path, payload)
        decision = str(validation.get("decision", "")).upper()
        if decision == "PASS":
            status = "pass"
            notes = "Installer install/uninstall validation passed."
        elif decision == "BLOCKED":
            status = "blocked"
            notes = "Installer install/uninstall validation is blocked."
        else:
            status = "fail"
            notes = "Installer install/uninstall validation failed or did not produce a decision."
        return self.record("installer_validation", "Run installer install/uninstall QA", status, path, notes, payload)

    def write_blocked_installer_validation(self, reason: str) -> None:
        validation_path = self.output_root / "installer_validation.json"
        evidence_dir = self.output_root / "evidence" / "installer"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "app": "silukman_file_converter",
            "qa_type": "installer_validation",
            "created_at": now_iso(),
            "decision": "BLOCKED",
            "installer": "",
            "install_dir": "",
            "evidence_dir": str(evidence_dir),
            "machine_info": machine_info(),
            "summary": {"pass": 0, "fail": 0, "blocked": 1},
            "checks": [
                {
                    "id": "installer_build_prerequisite",
                    "name": "Installer build prerequisite",
                    "status": "blocked",
                    "evidence": str(self.evidence_dir / "iscc_detection.json"),
                    "timestamp": now_iso(),
                    "notes": reason,
                    "details": {"install_instruction": inno_install_instruction()},
                }
            ],
            "rule": "Installer install/uninstall QA cannot pass until setup EXE exists and is tested.",
        }
        write_json(validation_path, payload)
        (self.output_root / "installer_validation.md").write_text(render_markdown(payload), encoding="utf-8")

    def record(
        self,
        check_id: str,
        name: str,
        status: str,
        evidence_path: Path,
        notes: str,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        check = {
            "id": check_id,
            "name": name,
            "status": status,
            "evidence": str(evidence_path),
            "timestamp": now_iso(),
            "notes": notes,
            "details": details,
        }
        self.checks.append(check)
        return check

    def decision(self) -> str:
        if any(check["status"] == "fail" for check in self.checks):
            return "FAILED"
        if any(check["status"] == "blocked" for check in self.checks):
            return "BLOCKED"
        required = {"iscc_detection", "build_installer", "setup_artifact", "installer_validation"}
        passed = {check["id"] for check in self.checks if check["status"] == "pass"}
        return "PASS" if required.issubset(passed) else "BLOCKED"

    def build_decision(self) -> str:
        build_checks = [check for check in self.checks if check["id"] in {"iscc_detection", "build_installer", "setup_artifact"}]
        if any(check["status"] == "fail" for check in build_checks):
            return "FAILED"
        if any(check["status"] == "blocked" for check in build_checks):
            return "BLOCKED"
        required = {"iscc_detection", "build_installer", "setup_artifact"}
        passed = {check["id"] for check in build_checks if check["status"] == "pass"}
        return "PASS" if required.issubset(passed) else "BLOCKED"


def iscc_candidates() -> list[dict[str, Any]]:
    paths: list[Path] = []
    found = shutil.which("iscc.exe")
    if found:
        paths.append(Path(found))
    paths.extend(
        [
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        ]
    )
    seen: set[str] = set()
    result = []
    for path in paths:
        if not path:
            continue
        resolved = str(path)
        if resolved.lower() in seen:
            continue
        seen.add(resolved.lower())
        result.append({"path": resolved, "exists": path.exists()})
    return result


def inno_install_instruction() -> str:
    return (
        "Install Inno Setup 6 from https://jrsoftware.org/isdl.php, or with winget: "
        "winget install --id JRSoftware.InnoSetup -e. Then open a new PowerShell and rerun: "
        "python tools\\installer_build_qa.py --run-installer-test"
    )


def run_process(command: list[str], timeout: int, stdout_path: Path, stderr_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    timed_out = False
    try:
        proc = subprocess.Popen(command, cwd=ROOT_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError as exc:
        stdout_path.write_text("", encoding="utf-8")
        stderr_path.write_text(str(exc), encoding="utf-8")
        return {
            "command": command,
            "process_id": None,
            "exit_code": None,
            "timed_out": False,
            "elapsed_seconds": 0,
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "start_error": str(exc),
        }
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        kill_process_tree(proc.pid)
        stdout, stderr = proc.communicate(timeout=10)
    stdout_path.write_text(stdout or "", encoding="utf-8")
    stderr_path.write_text(stderr or "", encoding="utf-8")
    return {
        "command": command,
        "process_id": proc.pid,
        "exit_code": None if timed_out else proc.returncode,
        "timed_out": timed_out,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
    }


def kill_process_tree(pid: int) -> None:
    if sys.platform.startswith("win"):
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def sha256(path: Path) -> str:
    digest = __import__("hashlib").sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def summarize(checks: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "pass": sum(1 for check in checks if check["status"] == "pass"),
        "fail": sum(1 for check in checks if check["status"] == "fail"),
        "blocked": sum(1 for check in checks if check["status"] == "blocked"),
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Installer Build And QA",
        "",
        f"Decision: `{result['decision']}`",
        f"Evidence: `{result.get('evidence_dir', '')}`",
        "",
        "## Summary",
        "",
        *[f"- {key}: {value}" for key, value in result["summary"].items()],
        "",
        "## Checks",
        "",
        "| check | status | evidence | notes |",
        "| --- | --- | --- | --- |",
    ]
    for check in result.get("checks", []):
        lines.append(f"| {escape_md(check['name'])} | {escape_md(check['status'])} | {escape_md(check['evidence'])} | {escape_md(check['notes'])} |")
    if result.get("blockers"):
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {escape_md(blocker)}" for blocker in result["blockers"])
    return "\n".join(lines) + "\n"


def machine_info() -> dict[str, Any]:
    return {
        "computer_name": os.environ.get("COMPUTERNAME", ""),
        "user_name": os.environ.get("USERNAME", ""),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version,
    }


def running_as_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def escape_md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())
