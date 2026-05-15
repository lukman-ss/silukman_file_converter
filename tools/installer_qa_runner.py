from __future__ import annotations

import argparse
import ctypes
import hashlib
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
APP_NAME = "silukman_file_converter"
EXE_NAME = "silukman_file_converter.exe"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Inno Setup installer install/uninstall behavior.")
    parser.add_argument("--run-installer-test", action="store_true", help="Actually run silent install/uninstall.")
    parser.add_argument("--installer", default="", help="Path to setup EXE. Defaults to newest dist/*setup*.exe.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Production QA output directory.")
    parser.add_argument("--install-dir", default="", help="Override install directory. Production pass requires Program Files.")
    parser.add_argument("--allow-existing-install", action="store_true", help="Allow testing when an existing app install is detected.")
    parser.add_argument("--timeout", type=int, default=300, help="Install/uninstall timeout in seconds.")
    args = parser.parse_args(argv)

    runner = InstallerQaRunner(
        output=Path(args.output).resolve(),
        installer=Path(args.installer).resolve() if args.installer else None,
        run_installer_test=args.run_installer_test,
        install_dir=Path(args.install_dir).resolve() if args.install_dir else default_install_dir(),
        allow_existing_install=args.allow_existing_install,
        timeout=args.timeout,
    )
    result = runner.run()
    manual_path = runner.update_manual_qa(result)
    print(f"Installer validation written: {runner.report_path}")
    print(f"Evidence directory: {runner.evidence_dir}")
    if manual_path:
        print(f"Manual QA updated: {manual_path}")
    print(f"Decision: {result['decision']}")
    return 0 if result["decision"] == "PASS" else 1


class InstallerQaRunner:
    def __init__(
        self,
        output: Path,
        installer: Path | None,
        run_installer_test: bool,
        install_dir: Path,
        allow_existing_install: bool,
        timeout: int,
    ) -> None:
        self.output = output
        self.evidence_dir = output / "evidence" / "installer"
        self.report_path = output / "installer_validation.json"
        self.markdown_path = output / "installer_validation.md"
        self.installer = installer or find_installer()
        self.run_installer_test = run_installer_test
        self.install_dir = install_dir
        self.allow_existing_install = allow_existing_install
        self.timeout = timeout
        self.checks: list[dict[str, Any]] = []

    def run(self) -> dict[str, Any]:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.output.mkdir(parents=True, exist_ok=True)

        installer_check = self.check_installer_artifact()
        preflight_check = self.check_preflight()

        if installer_check["status"] == "pass" and preflight_check["status"] == "pass":
            self.run_install_uninstall_flow()

        decision = self.decision()
        result = {
            "schema_version": 1,
            "app": APP_NAME,
            "qa_type": "installer_validation",
            "created_at": now_iso(),
            "decision": decision,
            "installer": str(self.installer) if self.installer else "",
            "install_dir": str(self.install_dir),
            "evidence_dir": str(self.evidence_dir),
            "machine_info": machine_info(),
            "summary": summarize(self.checks),
            "checks": self.checks,
            "rule": "PASS only when installer exists, --run-installer-test is used, Program Files install succeeds, shortcuts exist, EXE launches, uninstall succeeds, and leftovers are gone.",
        }
        write_json(self.report_path, result)
        self.markdown_path.write_text(render_markdown(result), encoding="utf-8")
        return result

    def update_manual_qa(self, result: dict[str, Any]) -> Path | None:
        manual_path = self.output / "manual_qa_filled.json"
        if not manual_path.exists():
            return None
        try:
            manual = read_json(manual_path)
        except Exception:
            return None
        checks = manual.get("checks")
        if not isinstance(checks, list):
            return None
        decision = str(result.get("decision", "")).upper()
        status = "pass" if decision == "PASS" else "blocked" if decision == "BLOCKED" else "fail"
        notes = (
            "Installer install/uninstall validation passed with evidence."
            if status == "pass"
            else f"Installer validation decision is {decision or 'missing'}."
        )
        evidence = f"{self.report_path}; {self.evidence_dir}"
        machine = manual.get("machine_info") or json.dumps(machine_info(), ensure_ascii=False)
        tester = str(manual.get("tester_name") or "")
        timestamp = now_iso()
        updated = False
        for check in checks:
            if isinstance(check, dict) and check.get("id") == "installer_install_uninstall":
                check.update(
                    {
                        "status": status,
                        "evidence": evidence,
                        "machine_info": check.get("machine_info") or machine,
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
                    "id": "installer_install_uninstall",
                    "name": "Installer install/uninstall",
                    "status": status,
                    "evidence": evidence,
                    "machine_info": machine,
                    "tester_name": tester,
                    "timestamp": timestamp,
                    "notes": notes,
                }
            )
        manual["updated_at"] = timestamp
        write_json(manual_path, manual)
        return manual_path

    def check_installer_artifact(self) -> dict[str, Any]:
        path = self.evidence_dir / "installer_artifact.json"
        evidence = {
            "installer": str(self.installer) if self.installer else "",
            "exists": bool(self.installer and self.installer.exists()),
            "size_bytes": self.installer.stat().st_size if self.installer and self.installer.exists() else 0,
            "sha256": sha256(self.installer) if self.installer and self.installer.exists() else "",
            "candidates": [str(item) for item in sorted((ROOT_DIR / "dist").glob("*setup*.exe"))],
        }
        write_json(path, evidence)
        status = "pass" if evidence["exists"] else "blocked"
        notes = (
            "Installer setup EXE found and hashed."
            if status == "pass"
            else "No setup EXE found. Install Inno Setup 6, run .\\build_installer.ps1, then rerun installer QA."
        )
        return self.record("installer_artifact", "Installer artifact", status, path, notes, evidence)

    def check_preflight(self) -> dict[str, Any]:
        path = self.evidence_dir / "preflight.json"
        is_admin = running_as_admin()
        program_files_root = Path(os.environ.get("ProgramFiles", r"C:\Program Files")).resolve()
        install_in_program_files = is_relative_to(self.install_dir, program_files_root)
        existing = existing_install_evidence(self.install_dir)
        evidence = {
            "run_installer_test": self.run_installer_test,
            "is_admin": is_admin,
            "program_files_root": str(program_files_root),
            "install_dir": str(self.install_dir),
            "install_in_program_files": install_in_program_files,
            "allow_existing_install": self.allow_existing_install,
            "existing_install": existing,
        }
        write_json(path, evidence)

        blockers: list[str] = []
        if not self.run_installer_test:
            blockers.append("--run-installer-test was not provided; installer mutation is intentionally blocked by default.")
        if not install_in_program_files:
            blockers.append("Install directory is not under Program Files; production installer validation requires Program Files evidence.")
        if install_in_program_files and not is_admin:
            blockers.append("Program Files install validation requires an elevated shell.")
        if existing["exists"] and not self.allow_existing_install:
            blockers.append("Existing installation detected; rerun in a clean VM or pass --allow-existing-install intentionally.")

        status = "pass" if not blockers else "blocked"
        notes = "Preflight passed; silent installer test may run." if status == "pass" else " ".join(blockers)
        return self.record("installer_preflight", "Installer preflight", status, path, notes, evidence)

    def run_install_uninstall_flow(self) -> None:
        before = self.snapshot("before")
        install = self.run_install()
        after_install = self.snapshot("after_install")
        launch = self.launch_installed_exe()
        uninstall = self.run_uninstall(after_install)
        cleanup_wait = self.wait_for_uninstall_cleanup()
        after_uninstall = self.snapshot("after_uninstall")

        self.verify_install(install, before, after_install, launch)
        self.verify_uninstall(uninstall, after_install, after_uninstall, cleanup_wait)

    def run_install(self) -> dict[str, Any]:
        assert self.installer is not None
        log_path = self.evidence_dir / "install.inno.log"
        stdout_path = self.evidence_dir / "install.stdout.log"
        stderr_path = self.evidence_dir / "install.stderr.log"
        args = [
            str(self.installer),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/SP-",
            f"/DIR={self.install_dir}",
            "/TASKS=desktopicon",
            f"/LOG={log_path}",
        ]
        result = run_process(args, self.timeout, stdout_path, stderr_path)
        result["inno_log"] = str(log_path)
        write_json(self.evidence_dir / "install_process.json", result)
        return result

    def run_uninstall(self, after_install: dict[str, Any]) -> dict[str, Any]:
        uninstallers = [Path(path) for path in after_install.get("uninstallers", [])]
        if not uninstallers:
            result = {"status": "blocked", "reason": "No uninstaller found after install.", "uninstallers": []}
            write_json(self.evidence_dir / "uninstall_process.json", result)
            return result

        uninstaller = uninstallers[0]
        log_path = self.evidence_dir / "uninstall.inno.log"
        stdout_path = self.evidence_dir / "uninstall.stdout.log"
        stderr_path = self.evidence_dir / "uninstall.stderr.log"
        result = run_process(
            [
                str(uninstaller),
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                f"/LOG={log_path}",
            ],
            self.timeout,
            stdout_path,
            stderr_path,
        )
        result["uninstaller"] = str(uninstaller)
        result["inno_log"] = str(log_path)
        write_json(self.evidence_dir / "uninstall_process.json", result)
        return result

    def wait_for_uninstall_cleanup(self) -> dict[str, Any]:
        path = self.evidence_dir / "uninstall_cleanup_wait.json"
        started = time.perf_counter()
        observations: list[dict[str, Any]] = []
        deadline = started + 20
        stable_empty_count = 0

        while time.perf_counter() <= deadline:
            files = list_files(self.install_dir)
            uninstallers = [str(item) for item in sorted(self.install_dir.glob("unins*.exe"))] if self.install_dir.exists() else []
            observation = {
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "install_dir_exists": self.install_dir.exists(),
                "install_files": files,
                "uninstallers": uninstallers,
            }
            observations.append(observation)
            if not files:
                stable_empty_count += 1
                if stable_empty_count >= 2:
                    break
            else:
                stable_empty_count = 0
            time.sleep(0.5)

        result = {
            "waited_seconds": round(time.perf_counter() - started, 3),
            "install_dir": str(self.install_dir),
            "cleanup_complete": not list_files(self.install_dir),
            "observations": observations,
            "notes": "Waited for Inno Setup second-phase uninstaller self-cleanup before taking final snapshot.",
        }
        write_json(path, result)
        return result

    def launch_installed_exe(self) -> dict[str, Any]:
        exe = self.install_dir / EXE_NAME
        log_path = self.evidence_dir / "installed_exe_launch.json"
        if not exe.exists():
            result = {"started": False, "reason": "Installed EXE not found.", "exe": str(exe)}
            write_json(log_path, result)
            return result

        started = time.perf_counter()
        proc = subprocess.Popen([str(exe)], cwd=self.install_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(5)
        running = proc.poll() is None
        exit_code = proc.returncode
        terminate_process(proc)
        result = {
            "exe": str(exe),
            "pid": proc.pid,
            "started": True,
            "running_after_observation": running,
            "exit_code": exit_code,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }
        write_json(log_path, result)
        return result

    def snapshot(self, label: str) -> dict[str, Any]:
        data = {
            "label": label,
            "timestamp": now_iso(),
            "install_dir": str(self.install_dir),
            "install_dir_exists": self.install_dir.exists(),
            "installed_exe_exists": (self.install_dir / EXE_NAME).exists(),
            "install_files": list_files(self.install_dir),
            "uninstallers": [str(path) for path in sorted(self.install_dir.glob("unins*.exe"))] if self.install_dir.exists() else [],
            "desktop_shortcuts": find_shortcuts("desktop"),
            "start_menu_shortcuts": find_shortcuts("start_menu"),
        }
        write_json(self.evidence_dir / f"snapshot_{label}.json", data)
        return data

    def verify_install(
        self,
        install: dict[str, Any],
        before: dict[str, Any],
        after_install: dict[str, Any],
        launch: dict[str, Any],
    ) -> None:
        path = self.evidence_dir / "install_verification.json"
        new_desktop = added_paths(before["desktop_shortcuts"], after_install["desktop_shortcuts"])
        new_start = added_paths(before["start_menu_shortcuts"], after_install["start_menu_shortcuts"])
        evidence = {
            "install_process": install,
            "after_install": after_install,
            "new_desktop_shortcuts": new_desktop,
            "new_start_menu_shortcuts": new_start,
            "launch": launch,
        }
        write_json(path, evidence)
        checks = {
            "install_exit_code_zero": install.get("exit_code") == 0,
            "install_not_timed_out": not install.get("timed_out"),
            "install_dir_exists": after_install["install_dir_exists"],
            "installed_exe_exists": after_install["installed_exe_exists"],
            "desktop_shortcut_created": bool(new_desktop or matching_shortcuts(after_install["desktop_shortcuts"])),
            "start_menu_shortcut_created": bool(new_start or matching_shortcuts(after_install["start_menu_shortcuts"])),
            "installed_exe_launches": bool(launch.get("started") and launch.get("running_after_observation")),
        }
        status = "pass" if all(checks.values()) else "fail"
        notes = "Installer installed app, shortcuts, and launched installed EXE." if status == "pass" else failed_notes(checks)
        self.record("installer_install", "Installer silent install", status, path, notes, {**evidence, "checks": checks})

    def verify_uninstall(
        self,
        uninstall: dict[str, Any],
        after_install: dict[str, Any],
        after_uninstall: dict[str, Any],
        cleanup_wait: dict[str, Any],
    ) -> None:
        path = self.evidence_dir / "uninstall_verification.json"
        installed_desktop = matching_shortcuts(after_install["desktop_shortcuts"])
        installed_start = matching_shortcuts(after_install["start_menu_shortcuts"])
        remaining_desktop = matching_shortcuts(after_uninstall["desktop_shortcuts"])
        remaining_start = matching_shortcuts(after_uninstall["start_menu_shortcuts"])
        evidence = {
            "uninstall_process": uninstall,
            "after_install": after_install,
            "after_uninstall": after_uninstall,
            "cleanup_wait": cleanup_wait,
            "installed_desktop_shortcuts": installed_desktop,
            "installed_start_menu_shortcuts": installed_start,
            "remaining_desktop_shortcuts": remaining_desktop,
            "remaining_start_menu_shortcuts": remaining_start,
        }
        write_json(path, evidence)
        checks = {
            "uninstall_exit_code_zero": uninstall.get("exit_code") == 0,
            "uninstall_not_timed_out": not uninstall.get("timed_out"),
            "installed_exe_removed": not after_uninstall["installed_exe_exists"],
            "install_dir_removed_or_empty": not after_uninstall["install_files"],
            "desktop_shortcuts_removed": not remaining_desktop,
            "start_menu_shortcuts_removed": not remaining_start,
        }
        status = "pass" if all(checks.values()) else "fail"
        notes = "Uninstaller removed installed EXE, shortcuts, and install files." if status == "pass" else failed_notes(checks)
        self.record("installer_uninstall", "Installer silent uninstall", status, path, notes, {**evidence, "checks": checks})

    def record(
        self,
        check_id: str,
        name: str,
        status: str,
        evidence_path: Path,
        notes: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        check = {
            "id": check_id,
            "name": name,
            "status": status,
            "evidence": str(evidence_path),
            "timestamp": now_iso(),
            "notes": notes,
            "details": details or {},
        }
        self.checks.append(check)
        return check

    def decision(self) -> str:
        if any(check["status"] == "fail" for check in self.checks):
            return "FAILED"
        if any(check["status"] == "blocked" for check in self.checks):
            return "BLOCKED"
        required = {"installer_artifact", "installer_preflight", "installer_install", "installer_uninstall"}
        passed = {check["id"] for check in self.checks if check["status"] == "pass"}
        return "PASS" if required.issubset(passed) else "BLOCKED"


def find_installer() -> Path | None:
    candidates = sorted((ROOT_DIR / "dist").glob("*setup*.exe"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def default_install_dir() -> Path:
    return Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / APP_NAME


def running_as_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def existing_install_evidence(install_dir: Path) -> dict[str, Any]:
    return {
        "exists": install_dir.exists(),
        "installed_exe_exists": (install_dir / EXE_NAME).exists(),
        "uninstallers": [str(path) for path in sorted(install_dir.glob("unins*.exe"))] if install_dir.exists() else [],
    }


def run_process(args: list[str], timeout: int, stdout_path: Path, stderr_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    proc = subprocess.Popen(args, cwd=ROOT_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        terminate_process(proc)
        stdout, stderr = proc.communicate(timeout=10)
    stdout_path.write_text(stdout or "", encoding="utf-8")
    stderr_path.write_text(stderr or "", encoding="utf-8")
    return {
        "command": args,
        "process_id": proc.pid,
        "exit_code": None if timed_out else proc.returncode,
        "timed_out": timed_out,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
    }


def terminate_process(proc: subprocess.Popen[Any]) -> None:
    if proc.poll() is not None:
        return
    if sys.platform.startswith("win"):
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def find_shortcuts(kind: str) -> list[str]:
    candidates: list[Path] = []
    if kind == "desktop":
        candidates.extend(
            [
                Path(os.environ.get("USERPROFILE", "")) / "Desktop",
                Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop",
                Path(os.environ.get("OneDrive", "")) / "Desktop",
            ]
        )
    elif kind == "start_menu":
        candidates.extend(
            [
                Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
                Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
            ]
        )
    shortcuts: set[str] = set()
    for root in candidates:
        if not root or not root.exists():
            continue
        for path in root.rglob("*.lnk"):
            if APP_NAME.lower() in path.name.lower() or "silukman" in str(path).lower():
                shortcuts.add(str(path))
    return sorted(shortcuts)


def matching_shortcuts(paths: list[str]) -> list[str]:
    return sorted(path for path in paths if APP_NAME.lower() in Path(path).name.lower() or "silukman" in path.lower())


def added_paths(before: list[str], after: list[str]) -> list[str]:
    before_set = {str(path).lower() for path in before}
    return sorted(path for path in after if path.lower() not in before_set)


def list_files(path: Path) -> list[str]:
    if not path.exists():
        return []
    return sorted(str(item) for item in path.rglob("*") if item.is_file())


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def machine_info() -> dict[str, Any]:
    return {
        "computer_name": os.environ.get("COMPUTERNAME", ""),
        "user_name": os.environ.get("USERNAME", ""),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version,
        "is_admin": running_as_admin(),
    }


def summarize(checks: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "pass": sum(1 for check in checks if check["status"] == "pass"),
        "fail": sum(1 for check in checks if check["status"] == "fail"),
        "blocked": sum(1 for check in checks if check["status"] == "blocked"),
    }


def failed_notes(checks: dict[str, bool]) -> str:
    failed = [name for name, ok in checks.items() if not ok]
    return "Failed checks: " + ", ".join(failed)


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Installer Validation",
        "",
        f"Decision: `{result['decision']}`",
        f"Installer: `{result.get('installer', '')}`",
        f"Install dir: `{result.get('install_dir', '')}`",
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
        lines.append(
            f"| {escape_md(check['name'])} | {escape_md(check['status'])} | {escape_md(check['evidence'])} | {escape_md(check['notes'])} |"
        )
    return "\n".join(lines) + "\n"


def escape_md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
