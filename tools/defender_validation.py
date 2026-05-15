from __future__ import annotations

import argparse
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect Windows Defender scan evidence for release artifacts.")
    parser.add_argument("--scan-exe", action="store_true", help="Scan dist EXE artifact.")
    parser.add_argument("--scan-zip", action="store_true", help="Scan latest release ZIP artifact.")
    parser.add_argument("--scan-installer", action="store_true", help="Scan setup installer artifact if present.")
    parser.add_argument("--exe", default="", help="EXE path. Defaults to optimized EXE, then regular EXE.")
    parser.add_argument("--zip", default="", help="Release ZIP path. Defaults to latest dist/*.zip.")
    parser.add_argument("--installer", default="", help="Setup EXE path. Defaults to latest dist/*setup*.exe.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args(argv)

    explicit_flags = args.scan_exe or args.scan_zip or args.scan_installer
    scan_exe = args.scan_exe or not explicit_flags
    scan_zip = args.scan_zip or not explicit_flags
    scan_installer = args.scan_installer or (not explicit_flags and find_installer() is not None)

    runner = DefenderValidation(
        output_root=Path(args.output).resolve(),
        exe=Path(args.exe).resolve() if args.exe else resolve_exe(),
        zip_path=Path(args.zip).resolve() if args.zip else latest_release_zip(),
        installer=Path(args.installer).resolve() if args.installer else find_installer(),
        scan_exe=scan_exe,
        scan_zip=scan_zip,
        scan_installer=scan_installer,
        timeout=args.timeout,
    )
    result = runner.run()
    print(f"Defender validation written: {runner.report_path}")
    print(f"Evidence directory: {runner.evidence_dir}")
    print(f"Decision: {result['decision']}")
    return 0 if result["decision"] == "PASS" else 1


class DefenderValidation:
    def __init__(
        self,
        output_root: Path,
        exe: Path,
        zip_path: Path | None,
        installer: Path | None,
        scan_exe: bool,
        scan_zip: bool,
        scan_installer: bool,
        timeout: int,
    ) -> None:
        self.output_root = output_root
        self.evidence_dir = output_root / "evidence" / "defender"
        self.report_path = output_root / "defender_validation.json"
        self.markdown_path = output_root / "defender_validation.md"
        self.exe = exe
        self.zip_path = zip_path
        self.installer = installer
        self.scan_exe = scan_exe
        self.scan_zip = scan_zip
        self.scan_installer = scan_installer
        self.timeout = timeout
        self.checks: list[dict[str, Any]] = []

    def run(self) -> dict[str, Any]:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)

        availability = self.check_availability()
        if availability["status"] == "pass":
            for artifact in self.selected_artifacts():
                self.scan_artifact(artifact)

        decision = self.decision()
        result = {
            "schema_version": 1,
            "app": APP_NAME,
            "qa_type": "defender_validation",
            "created_at": now_iso(),
            "decision": decision,
            "evidence_dir": str(self.evidence_dir),
            "machine_info": machine_info(),
            "summary": summarize(self.checks),
            "checks": self.checks,
            "rule": "PASS if Defender is available and every selected artifact scan returns clean/no threat evidence. BLOCKED if Defender or requested artifact is unavailable. FAIL if scan reports a threat or scan command fails.",
        }
        write_json(self.report_path, result)
        self.markdown_path.write_text(render_markdown(result), encoding="utf-8")
        return result

    def check_availability(self) -> dict[str, Any]:
        path = self.evidence_dir / "defender_availability.json"
        ps = shutil.which("powershell")
        status_result = run_command(
            [
                ps or "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                (
                    "$ErrorActionPreference='Stop'; "
                    "$cmd=Get-Command Get-MpComputerStatus -ErrorAction SilentlyContinue; "
                    "if (-not $cmd) { throw 'Get-MpComputerStatus unavailable' }; "
                    "Get-MpComputerStatus | Select-Object AMServiceEnabled,AntivirusEnabled,RealTimeProtectionEnabled,"
                    "AntispywareEnabled,NISEnabled,IsTamperProtected,AntivirusSignatureLastUpdated | ConvertTo-Json -Depth 4"
                ),
            ],
            self.timeout,
            self.evidence_dir / "defender_status.stdout.log",
            self.evidence_dir / "defender_status.stderr.log",
        )
        mp_cmd = find_mpcmdrun()
        status_json = parse_json_log(Path(status_result["stdout"]))
        evidence = {
            "powershell": ps or "",
            "mpcmdrun": str(mp_cmd or ""),
            "get_mpcomputerstatus": status_result,
            "status": status_json,
        }
        write_json(path, evidence)

        available = (
            status_result["exit_code"] == 0
            and bool(status_json)
            and bool(status_json.get("AntivirusEnabled", status_json.get("AMServiceEnabled", False)))
        )
        notes = "Windows Defender status was collected." if available else "Windows Defender cmdlets/status are unavailable or antivirus is disabled."
        return self.record("defender_availability", "Defender availability", "pass" if available else "blocked", path, notes, evidence)

    def selected_artifacts(self) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []
        if self.scan_exe:
            artifacts.append({"id": "exe", "name": "EXE artifact", "path": self.exe})
        if self.scan_zip:
            artifacts.append({"id": "zip", "name": "Release ZIP", "path": self.zip_path})
        if self.scan_installer:
            artifacts.append({"id": "installer", "name": "Installer setup", "path": self.installer})
        return artifacts

    def scan_artifact(self, artifact: dict[str, Any]) -> dict[str, Any]:
        artifact_id = artifact["id"]
        artifact_path = artifact.get("path")
        evidence_path = self.evidence_dir / f"scan_{artifact_id}.json"
        if artifact_path is None or not Path(artifact_path).exists():
            evidence = {"artifact": artifact, "exists": False}
            write_json(evidence_path, evidence)
            return self.record(f"scan_{artifact_id}", f"Scan {artifact['name']}", "blocked", evidence_path, "Requested artifact is missing.", evidence)

        target = Path(artifact_path).resolve()
        ps_scan = run_command(
            [
                shutil.which("powershell") or "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                f"$ErrorActionPreference='Stop'; Start-MpScan -ScanType CustomScan -ScanPath '{escape_ps(str(target))}'",
            ],
            self.timeout,
            self.evidence_dir / f"scan_{artifact_id}.powershell.stdout.log",
            self.evidence_dir / f"scan_{artifact_id}.powershell.stderr.log",
        )
        mp_scan = None
        mp_cmd = find_mpcmdrun()
        if mp_cmd:
            mp_scan = run_command(
                [str(mp_cmd), "-Scan", "-ScanType", "3", "-File", str(target), "-DisableRemediation"],
                self.timeout,
                self.evidence_dir / f"scan_{artifact_id}.mpcmdrun.stdout.log",
                self.evidence_dir / f"scan_{artifact_id}.mpcmdrun.stderr.log",
            )

        threat_after = self.threat_detection(artifact_id, target)
        evidence = {
            "artifact": {
                "id": artifact_id,
                "name": artifact["name"],
                "path": str(target),
                "size_bytes": target.stat().st_size,
                "sha256": sha256(target),
            },
            "powershell_scan": ps_scan,
            "mpcmdrun_scan": mp_scan,
            "threat_detection": threat_after,
        }
        write_json(evidence_path, evidence)

        scan_results = [ps_scan] + ([mp_scan] if mp_scan else [])
        command_failed = all(result["exit_code"] not in (0, 2) for result in scan_results if result)
        threat_found = threat_after.get("threat_count", 0) > 0 or any(result["exit_code"] == 2 for result in scan_results if result)
        if threat_found:
            status = "fail"
            notes = "Windows Defender reported a threat for this artifact."
        elif command_failed:
            status = "fail"
            notes = "All available Defender scan commands failed."
        else:
            status = "pass"
            notes = "Defender scan completed with no threat evidence."
        return self.record(f"scan_{artifact_id}", f"Scan {artifact['name']}", status, evidence_path, notes, evidence)

    def threat_detection(self, artifact_id: str, target: Path) -> dict[str, Any]:
        stdout = self.evidence_dir / f"threat_detection_{artifact_id}.stdout.log"
        stderr = self.evidence_dir / f"threat_detection_{artifact_id}.stderr.log"
        command = [
            shutil.which("powershell") or "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                "$items = Get-MpThreatDetection -ErrorAction SilentlyContinue | "
                f"Where-Object {{ $_.Resources -match [regex]::Escape('{escape_ps(str(target))}') }}; "
                "$items | Select-Object ThreatID,ThreatName,Resources,ActionSuccess,InitialDetectionTime | ConvertTo-Json -Depth 6"
            ),
        ]
        result = run_command(command, 120, stdout, stderr)
        parsed = parse_json_log(stdout)
        if isinstance(parsed, list):
            threats = parsed
        elif isinstance(parsed, dict) and parsed:
            threats = [parsed]
        else:
            threats = []
        return {"command": result, "threat_count": len(threats), "threats": threats}

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
        return "PASS" if self.checks and all(check["status"] == "pass" for check in self.checks) else "BLOCKED"


def run_command(command: list[str], timeout: int, stdout_path: Path, stderr_path: Path) -> dict[str, Any]:
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


def find_mpcmdrun() -> Path | None:
    candidates = []
    program_data = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
    platform_root = program_data / "Microsoft" / "Windows Defender" / "Platform"
    if platform_root.exists():
        candidates.extend(sorted(platform_root.glob("*\\MpCmdRun.exe"), reverse=True))
    candidates.extend(
        [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Windows Defender" / "MpCmdRun.exe",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Windows Defender" / "MpCmdRun.exe",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    found = shutil.which("MpCmdRun.exe")
    return Path(found).resolve() if found else None


def resolve_exe() -> Path:
    for candidate in [
        ROOT_DIR / "dist" / "silukman_file_converter_optimized.exe",
        ROOT_DIR / "dist" / "silukman_file_converter.exe",
    ]:
        if candidate.exists():
            return candidate.resolve()
    return (ROOT_DIR / "dist" / "silukman_file_converter_optimized.exe").resolve()


def latest_release_zip() -> Path | None:
    zips = sorted((ROOT_DIR / "dist").glob("*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
    return zips[0].resolve() if zips else None


def find_installer() -> Path | None:
    installers = sorted((ROOT_DIR / "dist").glob("*setup*.exe"), key=lambda path: path.stat().st_mtime, reverse=True)
    return installers[0].resolve() if installers else None


def parse_json_log(path: Path) -> Any:
    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def sha256(path: Path) -> str:
    digest = __import__("hashlib").sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def summarize(checks: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "pass": sum(1 for check in checks if check["status"] == "pass"),
        "fail": sum(1 for check in checks if check["status"] == "fail"),
        "blocked": sum(1 for check in checks if check["status"] == "blocked"),
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Defender Validation",
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
    return "\n".join(lines) + "\n"


def machine_info() -> dict[str, Any]:
    return {
        "computer_name": os.environ.get("COMPUTERNAME", ""),
        "user_name": os.environ.get("USERNAME", ""),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version,
    }


def escape_ps(value: str) -> str:
    return value.replace("'", "''")


def escape_md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())
