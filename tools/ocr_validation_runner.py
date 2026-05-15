from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_EXE = ROOT_DIR / "dist" / "silukman_file_converter_optimized.exe"
DEFAULT_OUTPUT = ROOT_DIR / "output" / "production_qa"
IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
OCR_CACHE_SUFFIXES = {".pdmodel", ".pdiparams", ".yml", ".yaml", ".json", ".nb"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate OCR first-run and cache-based offline behavior.")
    parser.add_argument("--tester", default="")
    parser.add_argument("--exe", default=str(DEFAULT_EXE))
    parser.add_argument("--samples", default=str(ROOT_DIR / "samples"))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--keep-cache", action="store_true", help="Do not clear the controlled OCR validation cache before phase 1.")
    args = parser.parse_args(argv)

    runner = OCRValidationRunner(
        tester=args.tester,
        exe=Path(args.exe).resolve(),
        samples=Path(args.samples).resolve(),
        output_root=Path(args.output).resolve(),
        timeout=args.timeout,
        clear_cache=not args.keep_cache,
    )
    result = runner.run()
    runner.write_outputs(result)
    print(json.dumps({"result": str(runner.result_path), "evidence": str(runner.markdown_path), "decision": result["decision"]}, indent=2))
    return 0 if result["decision"] == "PASS" else 1


class OCRValidationRunner:
    def __init__(self, tester: str, exe: Path, samples: Path, output_root: Path, timeout: int, clear_cache: bool) -> None:
        self.tester = tester
        self.exe = exe
        self.samples = samples
        self.output_root = output_root
        self.timeout = timeout
        self.clear_cache = clear_cache
        self.evidence_dir = output_root / "ocr_evidence"
        self.cache_root = output_root / "ocr_validation_cache"
        self.paddleocr_home = self.cache_root / "paddleocr_home"
        self.paddle_home = self.cache_root / "paddle_home"
        self.result_path = output_root / "ocr_validation.json"
        self.markdown_path = output_root / "ocr_evidence.md"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> dict[str, Any]:
        started = datetime.now().isoformat(timespec="seconds")
        sample = choose_ocr_sample(self.samples)
        checks: list[dict[str, Any]] = []

        if self.clear_cache:
            checks.append(self.clear_controlled_cache())
        else:
            checks.append(self.check("clear_controlled_cache", "blocked", "Controlled cache was preserved because --keep-cache was used.", {"cache_root": str(self.cache_root)}))

        internet = internet_available()
        checks.append(self.check("internet", "pass" if internet else "blocked", "Internet is available." if internet else "Internet is not available.", {"internet_available": internet}))

        if not self.exe.exists():
            checks.append(self.check("exe", "fail", f"EXE not found: {self.exe}", {"exe": str(self.exe)}))
        else:
            checks.append(self.check("exe", "pass", "EXE exists.", {"exe": str(self.exe), "size_bytes": self.exe.stat().st_size}))

        if sample is None:
            checks.append(self.check("sample", "blocked", "No OCR image sample found.", {"samples": str(self.samples)}))
        else:
            checks.append(self.check("sample", "pass", "OCR image sample found.", {"sample": str(sample), "relative": sample.relative_to(self.samples).as_posix()}))

        online_result: dict[str, Any] | None = None
        if self.exe.exists() and sample is not None and internet:
            online_result = self.run_ocr_phase("phase1_online_first_run", sample, allow_download=True)
            checks.append(online_result["check"])
        else:
            checks.append(self.check("phase1_online_first_run", "blocked", "Online OCR phase prerequisites were not met.", {"exe_exists": self.exe.exists(), "sample": str(sample) if sample else "", "internet_available": internet}))

        cache_after_online = collect_cache_snapshot(self.cache_dirs(include_global=True))
        cache_path = self.evidence_dir / "cache_after_online.json"
        write_json(cache_path, cache_after_online)
        controlled_cache_after_online = collect_cache_snapshot(self.cache_dirs(include_global=False))
        checks.append(
            self.check(
                "model_cache_after_online",
                "pass" if cache_after_online["file_count"] > 0 else "blocked",
                (
                    "OCR model/cache files are available after online OCR."
                    if cache_after_online["file_count"] > 0
                    else "No OCR model/cache files were observed; offline cache use cannot be proven."
                ),
                {
                    "cache_snapshot": str(cache_path),
                    "controlled_cache_file_count": controlled_cache_after_online["file_count"],
                    "download_to_controlled_cache_proven": controlled_cache_after_online["file_count"] > 0,
                    "download_note": "If this is false, OCR likely used an existing/global cache on this machine.",
                    **cache_after_online,
                },
            )
        )

        offline_result: dict[str, Any] | None = None
        if self.exe.exists() and sample is not None and cache_after_online["file_count"] > 0:
            offline_result = self.run_ocr_phase("phase2_offline_cache", sample, allow_download=False)
            checks.append(offline_result["check"])
        else:
            checks.append(self.check("phase2_offline_cache", "blocked", "Offline/cache phase prerequisites were not met.", {"cache_file_count": cache_after_online["file_count"]}))

        close_check = self.ensure_no_running_exe()
        checks.append(close_check)

        decision = "PASS" if checks and all(item["status"] == "pass" for item in checks) else "BLOCKED"
        if any(item["status"] == "fail" for item in checks):
            decision = "FAILED"
        return {
            "schema_version": 1,
            "app": "silukman_file_converter",
            "qa_type": "ocr_lifecycle_validation",
            "created_at": started,
            "tester": self.tester,
            "exe": str(self.exe),
            "samples": str(self.samples),
            "sample": str(sample) if sample else "",
            "output_root": str(self.output_root),
            "evidence_dir": str(self.evidence_dir),
            "controlled_cache": {
                "cache_root": str(self.cache_root),
                "paddleocr_home": str(self.paddleocr_home),
                "paddle_home": str(self.paddle_home),
            },
            "offline_simulation": {
                "network_disabled": False,
                "mode": "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True with controlled cache",
                "note": "The runner does not disable the machine network. Use a VM/network adapter disablement for full airgap proof.",
            },
            "phase_results": {
                "online": online_result,
                "offline": offline_result,
            },
            "checks": checks,
            "summary": summarize(checks),
            "decision": decision,
        }

    def clear_controlled_cache(self) -> dict[str, Any]:
        if not is_relative_to(self.cache_root, self.output_root):
            return self.check("clear_controlled_cache", "fail", f"Refusing to clear cache outside output root: {self.cache_root}", {"cache_root": str(self.cache_root)})
        if self.cache_root.exists():
            shutil.rmtree(self.cache_root)
        self.paddleocr_home.mkdir(parents=True, exist_ok=True)
        self.paddle_home.mkdir(parents=True, exist_ok=True)
        return self.check("clear_controlled_cache", "pass", "Controlled OCR validation cache was cleared safely.", {"cache_root": str(self.cache_root)})

    def cache_dirs(self, include_global: bool) -> list[Path]:
        dirs = [self.paddleocr_home, self.paddle_home]
        if include_global:
            dirs.extend(
                [
                    Path.home() / ".paddleocr",
                    Path.home() / ".paddlex",
                    Path.home() / ".paddle",
                    Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SilukmanFileConverter" / "ocr_models",
                ]
            )
        return dirs

    def run_ocr_phase(self, phase: str, sample: Path, allow_download: bool) -> dict[str, Any]:
        phase_dir = self.evidence_dir / phase
        phase_dir.mkdir(parents=True, exist_ok=True)
        matrix_dir = phase_dir / "matrix"
        env = dict(os.environ)
        env["PADDLEOCR_HOME"] = str(self.paddleocr_home)
        env["PADDLE_HOME"] = str(self.paddle_home)
        env["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "False" if allow_download else "True"

        relative = sample.relative_to(self.samples).as_posix()
        command = [
            str(self.exe),
            "--sample-matrix",
            "--samples",
            str(self.samples),
            "--output",
            str(matrix_dir),
            "--source-label",
            phase,
            "--matrix-op",
            "ocr_txt",
            "--matrix-input",
            relative,
        ]
        proc = run_logged(command, phase_dir, phase, timeout=self.timeout, env=env)
        latest = latest_child_dir(matrix_dir)
        rows_path = latest / "summary" / "summary.json" if latest else None
        summary_path = latest / "summary" / "summary_exe.json" if latest else None
        rows = read_json(rows_path) if rows_path and rows_path.exists() else []
        summary = read_json(summary_path) if summary_path and summary_path.exists() else {}
        ocr_outputs = extract_ocr_outputs(rows)
        output_evidence = []
        for output in ocr_outputs:
            output_path = Path(output)
            output_evidence.append(
                {
                    "path": str(output_path),
                    "exists": output_path.exists(),
                    "size_bytes": output_path.stat().st_size if output_path.exists() else 0,
                    "text_preview": output_path.read_text(encoding="utf-8", errors="replace")[:500] if output_path.exists() else "",
                }
            )
        cache_snapshot = collect_cache_snapshot(self.cache_dirs(include_global=True))
        phase_payload = {
            "phase": phase,
            "allow_download": allow_download,
            "command": command,
            "process": proc,
            "matrix_run_dir": str(latest) if latest else "",
            "rows_path": str(rows_path) if rows_path else "",
            "summary_path": str(summary_path) if summary_path else "",
            "rows": rows,
            "summary": summary,
            "ocr_outputs": output_evidence,
            "cache_snapshot": cache_snapshot,
        }
        phase_json = phase_dir / f"{phase}.json"
        write_json(phase_json, phase_payload)

        generated_ocr = any(item["exists"] and item["size_bytes"] > 0 and item["text_preview"].strip() for item in output_evidence)
        row_success = any(row.get("final_status") in {"success", "success_short_text"} for row in rows)
        status = "pass" if proc["returncode"] == 0 and row_success and generated_ocr else "fail"
        notes = "OCR generated text output." if status == "pass" else "OCR phase did not produce generated text output."
        return {
            "phase": phase,
            "json": str(phase_json),
            "check": self.check(
                phase,
                status,
                notes,
                {
                    "phase_json": str(phase_json),
                    "stdout": proc["stdout"],
                    "stderr": proc["stderr"],
                    "summary": str(summary_path) if summary_path else "",
                    "rows": str(rows_path) if rows_path else "",
                    "ocr_outputs": output_evidence,
                    "cache_file_count": cache_snapshot["file_count"],
                    "returncode": proc["returncode"],
                },
            ),
        }

    def ensure_no_running_exe(self) -> dict[str, Any]:
        pids = running_exe_pids(self.exe)
        for pid in pids:
            kill_pid(pid)
        time.sleep(1)
        remaining = running_exe_pids(self.exe)
        return self.check(
            "close_app",
            "pass" if not remaining else "fail",
            "No EXE processes remain." if not remaining else "EXE process remained after validation.",
            {"killed_pids": sorted(pids), "remaining_pids": sorted(remaining)},
        )

    def check(self, check_id: str, status: str, notes: str, details: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": check_id,
            "status": status,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "notes": notes,
            "details": details,
        }

    def write_outputs(self, result: dict[str, Any]) -> None:
        self.output_root.mkdir(parents=True, exist_ok=True)
        write_json(self.result_path, result)
        self.markdown_path.write_text(render_markdown(result), encoding="utf-8")


def choose_ocr_sample(samples: Path) -> Path | None:
    preferred = samples / "03_images_for_ocr" / "invoice_clean.png"
    if preferred.exists():
        return preferred
    for path in sorted(samples.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS and "07_expected_results" not in path.parts:
            return path
    return None


def run_logged(command: list[str], evidence_dir: Path, name: str, timeout: int, env: dict[str, str]) -> dict[str, Any]:
    stdout_path = evidence_dir / f"{name}.stdout.log"
    stderr_path = evidence_dir / f"{name}.stderr.log"
    meta_path = evidence_dir / f"{name}.meta.json"
    started = time.perf_counter()
    proc: subprocess.Popen[str] | None = None
    timed_out = False
    try:
        with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout, stderr_path.open("w", encoding="utf-8", errors="replace") as stderr:
            proc = subprocess.Popen(command, cwd=ROOT_DIR, stdout=stdout, stderr=stderr, text=True, env=env)
            try:
                returncode = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                kill_pid(proc.pid)
                returncode = proc.poll()
                if returncode is None:
                    returncode = -1
    except Exception as exc:
        returncode = -1
        error = str(exc)
    else:
        error = ""
    elapsed = time.perf_counter() - started
    meta = {
        "command": command,
        "pid": proc.pid if proc else None,
        "returncode": returncode,
        "timed_out": timed_out,
        "timeout_seconds": timeout,
        "elapsed_seconds": round(elapsed, 3),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "error": error,
    }
    write_json(meta_path, meta)
    return {**meta, "meta": str(meta_path)}


def collect_cache_snapshot(dirs: list[Path]) -> dict[str, Any]:
    files = []
    for directory in dirs:
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and (path.suffix.lower() in OCR_CACHE_SUFFIXES or "inference" in path.name.lower()):
                files.append({"path": str(path), "size_bytes": path.stat().st_size})
    return {
        "dirs": [str(path) for path in dirs],
        "file_count": len(files),
        "total_bytes": sum(item["size_bytes"] for item in files),
        "files": files[:200],
    }


def extract_ocr_outputs(rows: list[dict[str, Any]]) -> list[str]:
    outputs = []
    for row in rows:
        if row.get("operation") == "ocr_txt":
            outputs.extend(str(item) for item in row.get("outputs", []))
    return outputs


def internet_available(timeout: float = 3.0) -> bool:
    for host, port in (("paddleocr.bj.bcebos.com", 443), ("1.1.1.1", 443)):
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def latest_child_dir(path: Path) -> Path | None:
    if not path.exists():
        return None
    dirs = [item for item in path.iterdir() if item.is_dir()]
    return max(dirs, key=lambda item: item.stat().st_mtime) if dirs else None


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


def summarize(checks: list[dict[str, Any]]) -> dict[str, int]:
    result = {"pass": 0, "fail": 0, "blocked": 0}
    for check in checks:
        result[check["status"]] = result.get(check["status"], 0) + 1
    return result


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# OCR Lifecycle Evidence",
        "",
        f"Decision: `{result['decision']}`",
        f"EXE: `{result['exe']}`",
        f"Sample: `{result['sample']}`",
        f"Evidence: `{result['evidence_dir']}`",
        "",
        "## Summary",
        "",
        *[f"- {key}: {value}" for key, value in result["summary"].items()],
        "",
        "## Checks",
        "",
        "| check | status | notes |",
        "| --- | --- | --- |",
    ]
    for check in result["checks"]:
        lines.append(f"| {escape_md(check['id'])} | {check['status']} | {escape_md(check['notes'])} |")
    lines.extend(
        [
            "",
            "## Offline Note",
            "",
            result["offline_simulation"]["note"],
        ]
    )
    return "\n".join(lines)


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def read_json(path: Path | None) -> Any:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def escape_md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
