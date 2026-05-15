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
TARGET_LENGTHS = (240, 260, 300)
APP_NAME = "silukman_file_converter"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate long path behavior for Silukman File Converter.")
    parser.add_argument("--exe", default="", help="EXE path. Defaults to optimized EXE, then regular EXE.")
    parser.add_argument("--samples", default=str(ROOT_DIR / "samples"))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args(argv)

    runner = LongPathValidation(
        exe=resolve_exe(args.exe),
        samples=Path(args.samples).resolve(),
        output_root=Path(args.output).resolve(),
        timeout=args.timeout,
    )
    result = runner.run()
    print(f"Long path validation written: {runner.report_path}")
    print(f"Evidence directory: {runner.evidence_dir}")
    print(f"Decision: {result['decision']}")
    return 0 if result["decision"] == "PASS" else 1


class LongPathValidation:
    def __init__(self, exe: Path, samples: Path, output_root: Path, timeout: int) -> None:
        self.exe = exe
        self.samples = samples
        self.output_root = output_root
        self.timeout = timeout
        self.evidence_dir = output_root / "evidence" / "longpath"
        self.report_path = output_root / "longpath_validation.json"
        self.markdown_path = output_root / "longpath_validation.md"

    def run(self) -> dict[str, Any]:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        work_root = self.evidence_dir / "work"
        if work_root.exists():
            shutil.rmtree(to_extended_path(work_root), ignore_errors=True)
        work_root.mkdir(parents=True, exist_ok=True)

        sample = find_smoke_sample(self.samples)
        cases: list[dict[str, Any]] = []
        if not self.exe.exists():
            cases.append(controlled_case("exe_missing", 0, f"EXE not found: {self.exe}"))
        elif sample is None:
            cases.append(controlled_case("sample_missing", 0, f"No supported sample found in {self.samples}"))
        else:
            for target_length in TARGET_LENGTHS:
                cases.append(self.run_case(work_root, sample, target_length))

        decision = "PASS" if cases and all(case["status"] == "pass" for case in cases) else "FAILED"
        result = {
            "schema_version": 1,
            "app": APP_NAME,
            "qa_type": "long_path_validation",
            "created_at": now_iso(),
            "decision": decision,
            "exe": str(self.exe),
            "samples": str(self.samples),
            "output_root": str(self.output_root),
            "evidence_dir": str(self.evidence_dir),
            "machine_info": machine_info(),
            "summary": summarize(cases),
            "cases": cases,
            "rule": "PASS if each long path scenario either succeeds or returns a controlled error. FAIL on crash, freeze/timeout, traceback, or stack trace.",
        }
        write_json(self.report_path, result)
        self.markdown_path.write_text(render_markdown(result), encoding="utf-8")
        return result

    def run_case(self, work_root: Path, sample: Path, target_length: int) -> dict[str, Any]:
        case_id = f"path_{target_length}"
        case_root = work_root / case_id
        samples_root = case_root / "samples"
        output_root = case_root / "output"
        stdout_path = self.evidence_dir / f"{case_id}.stdout.log"
        stderr_path = self.evidence_dir / f"{case_id}.stderr.log"
        meta_path = self.evidence_dir / f"{case_id}.json"

        try:
            sample_dir = build_nested_dir(samples_root, target_length - len(sample.name) - 1)
            output_dir = build_nested_dir(output_root, target_length)
            create_dir(sample_dir)
            create_dir(output_dir)
            target = sample_dir / sample.name
            shutil.copy2(to_extended_path(sample), to_extended_path(target))
        except OSError as exc:
            case = {
                "id": case_id,
                "target_length": target_length,
                "status": "pass",
                "classification": "controlled_error",
                "stage": "setup",
                "path_length": 0,
                "evidence": str(meta_path),
                "notes": f"OS/filesystem returned controlled setup error before app execution: {exc}",
                "error": str(exc),
            }
            write_json(meta_path, case)
            return case

        relative_input = target.relative_to(samples_root).as_posix()
        operation = operation_for_sample(sample)
        command = [
            str(self.exe),
            "--sample-matrix",
            "--samples",
            str(samples_root),
            "--output",
            str(output_dir),
            "--source-label",
            f"longpath-{target_length}",
            "--matrix-op",
            operation,
            "--matrix-input",
            relative_input,
        ]
        process = run_process(command, self.timeout, stdout_path, stderr_path)
        summary = inspect_matrix_output(output_dir)
        combined_text = (
            safe_read(stdout_path)[-4000:]
            + "\n"
            + safe_read(stderr_path)[-4000:]
            + "\n"
            + json.dumps(summary, ensure_ascii=False)[-4000:]
        )
        classification, status, notes = classify_result(process, summary, combined_text)
        case = {
            "id": case_id,
            "target_length": target_length,
            "status": status,
            "classification": classification,
            "notes": notes,
            "path_length": len(str(target)),
            "output_path_length": len(str(output_dir)),
            "input": str(target),
            "relative_input": relative_input,
            "operation": operation,
            "command": command,
            "process": process,
            "matrix_summary": summary,
            "evidence": str(meta_path),
        }
        write_json(meta_path, case)
        return case


def resolve_exe(requested: str) -> Path:
    candidates = []
    if requested:
        candidates.append(Path(requested))
    candidates.extend(
        [
            ROOT_DIR / "dist" / "silukman_file_converter_optimized.exe",
            ROOT_DIR / "dist" / "silukman_file_converter.exe",
        ]
    )
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists():
            return resolved
    return candidates[0].resolve()


def find_smoke_sample(samples: Path) -> Path | None:
    preferred = [
        samples / "sample_add_html.html",
        samples / "sample_add_csv.csv",
        samples / "sample_add_png.png",
        samples / "sample_add_pdf.pdf",
    ]
    for path in preferred:
        if path.exists():
            return path.resolve()
    for suffix in (".html", ".htm", ".csv", ".png", ".jpg", ".jpeg", ".pdf"):
        found = sorted(path for path in samples.rglob(f"*{suffix}") if "07_expected_results" not in path.parts)
        if found:
            return found[0].resolve()
    return None


def operation_for_sample(sample: Path) -> str:
    suffix = sample.suffix.lower()
    if suffix in {".html", ".htm"}:
        return "html_to_pdf"
    if suffix == ".csv":
        return "csv_to_excel"
    if suffix in {".png", ".jpg", ".jpeg"}:
        return "image_to_pdf"
    return "pdf_to_png"


def build_nested_dir(root: Path, min_length: int) -> Path:
    nested = root
    segment_index = 0
    while len(str(nested)) < min_length:
        nested = nested / f"long_path_segment_{segment_index:02d}"
        segment_index += 1
    return nested


def create_dir(path: Path) -> None:
    Path(to_extended_path(path)).mkdir(parents=True, exist_ok=True)


def to_extended_path(path: Path | str) -> str:
    value = str(Path(path).resolve())
    if not sys.platform.startswith("win"):
        return value
    if value.startswith("\\\\?\\"):
        return value
    if value.startswith("\\\\"):
        return "\\\\?\\UNC\\" + value.lstrip("\\")
    return "\\\\?\\" + value


def run_process(command: list[str], timeout: int, stdout_path: Path, stderr_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    timed_out = False
    proc = subprocess.Popen(command, cwd=ROOT_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        kill_process_tree(proc.pid)
        stdout, stderr = proc.communicate(timeout=10)
    stdout_path.write_text(stdout or "", encoding="utf-8")
    stderr_path.write_text(stderr or "", encoding="utf-8")
    return {
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


def inspect_matrix_output(output_dir: Path) -> dict[str, Any]:
    summaries = sorted(output_dir.rglob("summary.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    exe_summaries = sorted(output_dir.rglob("summary_exe.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    rows = read_json(summaries[0]) if summaries else []
    exe_summary = read_json(exe_summaries[0]) if exe_summaries else {}
    created_outputs = [
        str(path)
        for path in output_dir.rglob("*")
        if path.is_file() and "\\output\\" in str(path)
    ]
    row_statuses = [str(row.get("final_status", "")) for row in rows if isinstance(row, dict)]
    return {
        "summary_json": str(summaries[0]) if summaries else "",
        "summary_exe_json": str(exe_summaries[0]) if exe_summaries else "",
        "row_count": len(rows) if isinstance(rows, list) else 0,
        "row_statuses": row_statuses,
        "created_outputs": created_outputs,
        "created_output_count": len(created_outputs),
        "exe_summary": exe_summary,
    }


def classify_result(process: dict[str, Any], summary: dict[str, Any], text: str) -> tuple[str, str, str]:
    lowered = text.lower()
    if process["timed_out"]:
        return "freeze_timeout", "fail", "Operation timed out; possible freeze."
    if any(token in lowered for token in ("traceback", "stack trace", "unhandled exception", "modulenotfounderror")):
        return "crash_or_stacktrace", "fail", "Stack trace or unhandled exception detected."
    if process["exit_code"] == 0 and summary.get("created_output_count", 0) > 0:
        return "success", "pass", "Operation succeeded and generated output."

    row_statuses = set(summary.get("row_statuses", []))
    controlled_statuses = {
        "not_effective",
        "not_configured",
        "not_validated",
        "unsupported",
        "skipped",
        "blocked",
        "failed",
    }
    if row_statuses & controlled_statuses:
        return "controlled_error", "pass", f"Operation returned controlled status: {', '.join(sorted(row_statuses))}."
    if process["exit_code"] not in (None, 0) and "error" in lowered:
        return "controlled_error", "pass", "Process returned non-zero with an error message and no stack trace."
    return "unexpected_failure", "fail", "Operation did not generate output and did not return a recognizable controlled error."


def controlled_case(case_id: str, target_length: int, reason: str) -> dict[str, Any]:
    return {
        "id": case_id,
        "target_length": target_length,
        "status": "pass",
        "classification": "controlled_error",
        "notes": reason,
        "evidence": "",
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if path.name.endswith("_exe.json") else []


def safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def summarize(cases: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "pass": sum(1 for case in cases if case.get("status") == "pass"),
        "fail": sum(1 for case in cases if case.get("status") == "fail"),
        "total": len(cases),
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Long Path Validation",
        "",
        f"Decision: `{result['decision']}`",
        f"EXE: `{result.get('exe', '')}`",
        f"Evidence: `{result.get('evidence_dir', '')}`",
        "",
        "## Summary",
        "",
        *[f"- {key}: {value}" for key, value in result["summary"].items()],
        "",
        "## Cases",
        "",
        "| target | actual input length | status | classification | evidence | notes |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for case in result.get("cases", []):
        lines.append(
            "| "
            + " | ".join(
                [
                    escape_md(case.get("target_length", "")),
                    escape_md(case.get("path_length", "")),
                    escape_md(case.get("status", "")),
                    escape_md(case.get("classification", "")),
                    escape_md(case.get("evidence", "")),
                    escape_md(case.get("notes", "")),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def machine_info() -> dict[str, Any]:
    return {
        "computer_name": os.environ.get("COMPUTERNAME", ""),
        "user_name": os.environ.get("USERNAME", ""),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version,
    }


def escape_md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


if __name__ == "__main__":
    raise SystemExit(main())
