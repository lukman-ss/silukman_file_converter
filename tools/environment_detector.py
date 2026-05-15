from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT_DIR / "output" / "production_qa"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect Windows QA execution environment.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)

    output = Path(args.output).resolve()
    report = build_environment_report(output)
    report_path = output / "environment_report.json"
    write_json(report_path, report)
    print(json.dumps({"report": str(report_path), "summary": report["summary"]}, indent=2))
    return 0


def build_environment_report(output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    commands = detect_commands()
    artifacts = detect_developer_artifacts()
    virtualization = detect_virtualization()
    is_admin = running_as_admin()
    python_detected = bool(commands["python"] or commands["python3"] or commands["py"])
    pip_detected = bool(commands["pip"] or commands["pip3"])
    venv_detected = bool(artifacts["venv_paths"])
    vm_detected = virtualization["detected"]
    installer_setup = ROOT_DIR / "dist" / "silukman_file_converter_setup.exe"
    clean_package = ROOT_DIR / "clean_windows_validation_package.zip"

    actions: list[dict[str, str]] = []
    if not is_admin:
        actions.append(
            {
                "type": "missing_admin",
                "condition": "Current shell is not elevated.",
                "next_command": "powershell Start-Process powershell -Verb RunAs",
                "continue_command": "python tools\\installer_build_qa.py --run-installer-test --auto-elevate",
                "auto_continue_possible": "no",
                "notes": "Use --auto-elevate to request UAC automatically, or open an elevated PowerShell and run without --auto-elevate.",
            }
        )
    else:
        actions.append(
            {
                "type": "admin_available",
                "condition": "Current shell is elevated.",
                "next_command": "python tools\\installer_build_qa.py --run-installer-test",
                "continue_command": "python tools\\installer_build_qa.py --run-installer-test",
                "auto_continue_possible": "yes",
                "notes": "Installer install/uninstall QA can run in this shell.",
            }
        )

    if vm_detected:
        actions.append(
            {
                "type": "vm_detected",
                "condition": virtualization["provider"] or "Virtual machine indicators detected.",
                "next_command": "powershell -ExecutionPolicy Bypass -File .\\qa\\clean_windows_runner.ps1",
                "continue_command": "python tools\\import_clean_windows_validation.py path\\to\\clean_windows_validation.json",
                "auto_continue_possible": "yes",
                "notes": "If this is the clean validation package and Python is absent, run the clean Windows runner.",
            }
        )
    else:
        actions.append(
            {
                "type": "external_vm_required",
                "condition": "No VM or Windows Sandbox indicator detected.",
                "next_command": "Copy clean_windows_validation_package.zip to a clean Windows VM, then run: powershell -ExecutionPolicy Bypass -File .\\qa\\clean_windows_runner.ps1",
                "continue_command": "python tools\\import_clean_windows_validation.py path\\to\\clean_windows_validation.json",
                "auto_continue_possible": "no",
                "notes": "Clean Windows no-Python evidence must come from a separate clean VM or machine.",
            }
        )

    clean_candidate = vm_detected and not python_detected and not pip_detected and not venv_detected
    summary = {
        "admin": is_admin,
        "python_detected": python_detected,
        "pip_detected": pip_detected,
        "venv_detected": venv_detected,
        "vm_detected": vm_detected,
        "vm_provider": virtualization["provider"],
        "clean_windows_candidate": clean_candidate,
        "installer_setup_exists": installer_setup.exists(),
        "clean_windows_package_exists": clean_package.exists(),
    }
    return {
        "schema_version": 1,
        "app": "silukman_file_converter",
        "qa_type": "environment_detection",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(ROOT_DIR),
        "output": str(output),
        "machine_info": machine_info(),
        "summary": summary,
        "commands": commands,
        "developer_artifacts": artifacts,
        "virtualization": virtualization,
        "actions": actions,
        "rules": {
            "installer_auto_continue": "Allowed only when current shell is elevated.",
            "clean_windows_auto_continue": "Suggested only when VM/Sandbox is detected; pass still requires no Python/pip/venv and EXE evidence.",
        },
    }


def detect_commands() -> dict[str, str]:
    return {
        "python": shutil.which("python") or "",
        "python3": shutil.which("python3") or "",
        "py": shutil.which("py") or "",
        "pip": shutil.which("pip") or "",
        "pip3": shutil.which("pip3") or "",
    }


def detect_developer_artifacts() -> dict[str, Any]:
    venv_names = ["venv", ".venv", ".venv_ocr"]
    dev_names = ["app", "tests", "scripts", "build", ".git", ".pytest_cache", "__pycache__"]
    venv_paths = [str(ROOT_DIR / name) for name in venv_names if (ROOT_DIR / name).exists()]
    dev_paths = [str(ROOT_DIR / name) for name in dev_names if (ROOT_DIR / name).exists()]
    return {
        "venv_paths": venv_paths,
        "developer_paths": dev_paths,
    }


def detect_virtualization() -> dict[str, Any]:
    indicators: list[str] = []
    provider = ""
    system = wmi_query("Win32_ComputerSystem", ["Manufacturer", "Model"])
    bios = wmi_query("Win32_BIOS", ["Manufacturer", "SerialNumber", "Version"])
    baseboard = wmi_query("Win32_BaseBoard", ["Manufacturer", "Product"])
    text = " ".join(
        str(value)
        for item in [*system, *bios, *baseboard]
        for value in item.values()
        if value
    ).lower()

    provider_patterns = [
        ("Windows Sandbox", ["windows sandbox"]),
        ("Hyper-V", ["microsoft corporation virtual machine", "hyper-v", "virtual machine"]),
        ("VirtualBox", ["virtualbox", "oracle"]),
        ("VMware", ["vmware"]),
    ]
    for name, patterns in provider_patterns:
        if any(pattern in text for pattern in patterns):
            provider = name
            indicators.append(f"{name} indicator found in WMI hardware strings.")
            break

    sandbox_markers = [
        Path(os.environ.get("USERPROFILE", "")) / "Desktop" / "Windows Sandbox.wsb",
        Path(r"C:\Users\WDAGUtilityAccount"),
    ]
    for marker in sandbox_markers:
        if marker.exists():
            provider = provider or "Windows Sandbox"
            indicators.append(f"Windows Sandbox marker exists: {marker}")

    return {
        "detected": bool(provider or indicators),
        "provider": provider,
        "indicators": indicators,
        "computer_system": system,
        "bios": bios,
        "baseboard": baseboard,
    }


def wmi_query(class_name: str, properties: list[str]) -> list[dict[str, str]]:
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"Get-CimInstance {class_name} | Select-Object {','.join(properties)} | ConvertTo-Json -Compress",
    ]
    try:
        proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20, check=False)
    except Exception:
        return []
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    rows = []
    for item in data:
        if isinstance(item, dict):
            rows.append({key: str(item.get(key, "")) for key in properties})
    return rows


def running_as_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def machine_info() -> dict[str, Any]:
    return {
        "computer_name": os.environ.get("COMPUTERNAME", ""),
        "user_name": os.environ.get("USERNAME", ""),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version,
        "is_admin": running_as_admin(),
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
