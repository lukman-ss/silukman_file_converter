from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import hashlib
import json
import shutil
import sys
import time
import traceback

import fitz

from app.core.converter import Converter
from app.core.quality_validator import QualityResult, sanitize_operation_name, validate_output_quality


SKIP_TEST_FILES = {
    "README_TEST_INPUTS.md",
    "SOURCE_URLS.txt",
    "expected_keywords.json",
}
SKIP_TEST_FOLDERS = {"07_expected_results"}
CRITICAL_CHECKS = [
    ("03_images_for_ocr/invoice_clean.png", "ocr_txt"),
    ("03_images_for_ocr/nota_blur.jpg", "ocr_txt"),
    ("03_images_for_ocr/surat_jalan_rotated.png", "ocr_txt"),
    ("03_images_for_ocr/table_lowres.jpg", "ocr_txt"),
    ("02_pdf_scan_no_text_layer/invoice_scan_no_text_layer.pdf", "ocr_txt"),
    ("02_pdf_scan_no_text_layer/nota_scan_no_text_layer.pdf", "ocr_txt"),
    ("02_pdf_scan_no_text_layer/multipage_scan_no_text_layer.pdf", "ocr_txt"),
    ("04_images_for_converter/sample_add_png.png", "image_to_pdf"),
    ("04_images_for_converter/sample_add_jpg.jpg", "image_to_pdf"),
    ("01_pdf_text_layer/pdfobject_sample_text_layer.pdf", "pdf_to_png"),
    ("01_pdf_text_layer/generated_invoice_text_layer.pdf", "ocr_txt"),
]
DISABLED_BETA_OPERATIONS = {
    "ai_summarizer",
    "translate_pdf",
    "pdf_to_pdfa",
}
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
    "office": {
        "word_to_pdf",
        "powerpoint_to_pdf",
        "excel_to_pdf",
        "excel_to_csv",
        "excel_to_json",
        "html_to_pdf",
        "csv_to_excel",
        "json_to_excel",
    },
    "ocr": {"ocr_txt"},
    "security": {"protect_pdf", "unlock_pdf"},
}


@dataclass(frozen=True)
class MatrixOperation:
    label: str
    operation: str
    expected_format: str | None
    extensions: set[str]
    batch: bool = False
    min_files: int = 1
    max_files: int | None = None


OPERATIONS = [
    MatrixOperation("Merge PDF", "merge_pdf", "pdf", {".pdf"}, batch=True, min_files=2),
    MatrixOperation("Compare PDF", "compare_pdf", "txt", {".pdf"}, batch=True, min_files=2, max_files=2),
    MatrixOperation("Split PDF", "split_pdf", "pdf", {".pdf"}),
    MatrixOperation("Compress PDF", "compress_pdf", "pdf", {".pdf"}),
    MatrixOperation("PDF to Word (Basic Text)", "pdf_to_word", "docx", {".pdf"}),
    MatrixOperation("PDF to PowerPoint (Basic)", "pdf_to_powerpoint", "pptx", {".pdf"}),
    MatrixOperation("PDF to Excel (Basic Text)", "pdf_to_excel", "xlsx", {".pdf"}),
    MatrixOperation("Edit PDF (Basic)", "edit_pdf", "pdf", {".pdf"}),
    MatrixOperation("PDF to JPG", "pdf_to_jpg", "jpg", {".pdf"}),
    MatrixOperation("PDF to PNG", "pdf_to_png", "png", {".pdf"}),
    MatrixOperation("Stamp PDF", "sign_pdf", "pdf", {".pdf"}),
    MatrixOperation("Watermark (Basic)", "watermark", "pdf", {".pdf"}),
    MatrixOperation("Rotate PDF (Basic)", "rotate_pdf", "pdf", {".pdf"}),
    MatrixOperation("Unlock PDF", "unlock_pdf", "pdf", {".pdf"}),
    MatrixOperation("Protect PDF", "protect_pdf", "pdf", {".pdf"}),
    MatrixOperation("Organize PDF", "organize_pdf", "pdf", {".pdf"}),
    MatrixOperation("PDF to PDF/A", "pdf_to_pdfa", "pdf", {".pdf"}),
    MatrixOperation("Repair PDF", "repair_pdf", "pdf", {".pdf"}),
    MatrixOperation("Page numbers", "page_numbers", "pdf", {".pdf"}),
    MatrixOperation("OCR PDF/Image", "ocr_txt", "txt", {".pdf", ".png", ".jpg", ".jpeg"}),
    MatrixOperation("Redact PDF (Basic)", "redact_pdf", "pdf", {".pdf"}),
    MatrixOperation("Crop PDF (Basic)", "crop_pdf", "pdf", {".pdf"}),
    MatrixOperation("PDF Forms", "pdf_forms", "pdf", {".pdf"}),
    MatrixOperation("Translate PDF", "translate_pdf", "txt", {".pdf"}),
    MatrixOperation("JPG/PNG to PDF", "image_to_pdf", "pdf", {".png", ".jpg", ".jpeg"}),
    MatrixOperation("Scan to PDF", "scan_to_pdf", "pdf", {".png", ".jpg", ".jpeg"}),
    MatrixOperation("Word to PDF (Basic Text)", "word_to_pdf", "pdf", {".doc", ".docx"}),
    MatrixOperation("AI Summarizer", "ai_summarizer", "txt", {".pdf", ".doc", ".docx", ".txt"}),
    MatrixOperation("PowerPoint to PDF (Basic Text)", "powerpoint_to_pdf", "pdf", {".ppt", ".pptx"}),
    MatrixOperation("Excel to PDF (Basic Text)", "excel_to_pdf", "pdf", {".xls", ".xlsx"}),
    MatrixOperation("Excel to CSV", "excel_to_csv", "csv", {".xls", ".xlsx"}),
    MatrixOperation("Excel to JSON", "excel_to_json", "json", {".xls", ".xlsx"}),
    MatrixOperation("HTML to PDF", "html_to_pdf", "pdf", {".html", ".htm"}),
    MatrixOperation("CSV to Excel", "csv_to_excel", "xlsx", {".csv"}),
    MatrixOperation("JSON to Excel", "json_to_excel", "xlsx", {".json"}),
]


def run_sample_matrix(
    samples_dir: str | Path,
    output_root: str | Path,
    source_label: str = "source",
    operation_filters: set[str] | None = None,
    input_filters: set[str] | None = None,
) -> dict:
    samples_path = Path(samples_dir).resolve()
    output_base = Path(output_root).resolve()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    run_dir = output_base / timestamp
    input_dir = run_dir / "input"
    output_dir = run_dir / "output"
    summary_dir = run_dir / "summary"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)

    sample_files = sorted(path for path in samples_path.rglob("*") if path.is_file() and not should_skip_sample(samples_path, path))
    copied_inputs = copy_inputs(samples_path, input_dir, sample_files)
    expected_keywords = load_expected_keywords(samples_path)
    converter = Converter()
    rows = []

    for sample in sample_files:
        relative = sample.relative_to(samples_path).as_posix()
        if input_filters and relative not in input_filters:
            continue

        applicable = [
            operation
            for operation in OPERATIONS
            if operation.operation not in DISABLED_BETA_OPERATIONS
            and not operation.batch
            and sample.suffix.lower() in operation.extensions
            and (operation_filters is None or operation.operation in operation_filters)
        ]
        if not applicable:
            continue

        for operation in applicable:
            operation_output_dir = output_dir / safe_relative_stem(relative) / sanitize_operation_name(operation.operation)
            operation_output_dir.mkdir(parents=True, exist_ok=True)
            rows.append(run_single_operation(converter, operation, sample, relative, operation_output_dir, expected_keywords))

    if not input_filters:
        rows.extend(run_batch_operations(converter, sample_files, output_dir, expected_keywords, operation_filters))
    summary = summarize(rows)
    exe = Path(sys.executable).resolve()
    exe_info = {
        "source_label": source_label,
        "test_type": "exe" if bool(getattr(sys, "frozen", False)) else "source",
        "runner": str(exe),
        "python_or_exe": str(exe),
        "is_frozen": bool(getattr(sys, "frozen", False)),
        "samples_dir": str(samples_path),
        "run_dir": str(run_dir),
        "input_file_count": len(sample_files),
        "operation_row_count": len(rows),
        "summary": summary,
    }
    exe_info["exe_verification"] = exe_verification_status(exe_info["is_frozen"], summary)
    exe_info["source_verification"] = source_verification_status(exe_info["is_frozen"], summary)
    exe_info["exe_ocr_verification"] = exe_ocr_verification_status(exe_info["is_frozen"], rows)
    exe_info["production_readiness"] = production_readiness_status(exe_info["is_frozen"], rows, summary)
    exe_info["production_gate"] = production_gate_status(exe_info, rows, summary)
    exe_info["final_production_readiness"] = final_production_readiness_status(exe_info["production_gate"])

    (summary_dir / "input_manifest.json").write_text(json.dumps(copied_inputs, indent=2), encoding="utf-8")
    (summary_dir / "summary.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (summary_dir / "exe_verification.json").write_text(json.dumps(exe_info, indent=2), encoding="utf-8")
    summary_name = "summary_exe.json" if exe_info["test_type"] == "exe" else "summary_source.json"
    (summary_dir / summary_name).write_text(json.dumps(exe_info, indent=2), encoding="utf-8")
    write_summary_markdown(summary_dir / "summary.md", rows, summary, exe_info)
    write_production_gate_markdown(run_dir / "file.md", rows, summary, exe_info)
    write_production_gate_markdown(summary_dir / "file.md", rows, summary, exe_info)
    return exe_info


def should_skip_sample(samples_path: Path, path: Path) -> bool:
    relative = path.relative_to(samples_path)
    if path.name in SKIP_TEST_FILES:
        return True
    if path.suffix.lower() in {".md", ".json"}:
        return True
    return any(part in SKIP_TEST_FOLDERS for part in relative.parts)


def copy_inputs(samples_path: Path, input_dir: Path, sample_files: list[Path]) -> list[dict]:
    manifest = []
    for source in sample_files:
        relative = source.relative_to(samples_path)
        destination = input_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        manifest.append(
            {
                "relative_path": relative.as_posix(),
                "source": str(source),
                "copied_to": str(destination),
                "size": source.stat().st_size,
            }
        )
    return manifest


def load_expected_keywords(samples_path: Path) -> dict[str, list[str]]:
    manifest = samples_path / "07_expected_results" / "expected_keywords.json"
    if not manifest.exists():
        return {}
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return data.get("expected_keywords", {})


def run_single_operation(
    converter: Converter,
    operation: MatrixOperation,
    sample: Path,
    relative: str,
    output_dir: Path,
    expected_keywords: dict[str, list[str]],
) -> dict:
    started = time.perf_counter()
    try:
        result = converter.convert(
            str(sample),
            operation.operation,
            str(output_dir),
            operation_options=operation_options_for(operation.operation),
        )
        outputs = [Path(path) for path in result.get("outputs", [])]
        quality = [
            validate_output_quality(
                operation.operation,
                sample,
                output,
                operation.expected_format,
                converter_status=result.get("status", "success"),
                notes=result.get("error"),
                expected_pages=expected_pdf_pages(operation, sample),
                expected_ocr_pages=expected_ocr_pages(operation, sample),
                expected_keywords=keywords_for(relative, operation, expected_keywords),
                ocr_metadata=result.get("ocr"),
            )
            for output in outputs
        ]
        if not quality:
            quality = [
                validate_output_quality(
                    operation.operation,
                    sample,
                    None,
                    operation.expected_format,
                    converter_status=result.get("status", "failed"),
                    notes=result.get("error"),
                    expected_ocr_pages=expected_ocr_pages(operation, sample),
                    expected_keywords=keywords_for(relative, operation, expected_keywords),
                    ocr_metadata=result.get("ocr"),
                )
            ]
        row = row_from_quality(relative, operation.label, operation.operation, outputs, result.get("error"), quality)
        row["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        return row
    except Exception as exc:
        quality = [QualityResult(operation.operation, str(sample), None, False, 0, False, False, str(exc), "failed").to_dict()]
        return {
            "input_file": relative,
            "operation_label": operation.label,
            "operation": operation.operation,
            "outputs": [],
            "final_status": "failed",
            "notes": str(exc),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "traceback": traceback.format_exc(),
            "quality": quality,
        }


def run_batch_operations(
    converter: Converter,
    sample_files: list[Path],
    output_dir: Path,
    expected_keywords: dict[str, list[str]],
    operation_filters: set[str] | None = None,
) -> list[dict]:
    del expected_keywords
    pdfs = [path for path in sample_files if path.suffix.lower() == ".pdf"]
    rows = []
    for operation in [
        item
        for item in OPERATIONS
        if item.batch
        and item.operation not in DISABLED_BETA_OPERATIONS
        and (operation_filters is None or item.operation in operation_filters)
    ]:
        if len(pdfs) < operation.min_files:
            continue
        inputs = pdfs[: operation.max_files] if operation.max_files else pdfs
        target_dir = output_dir / "_batch" / sanitize_operation_name(operation.operation)
        target_dir.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        try:
            result = converter.convert_batch([str(path) for path in inputs], operation.operation, str(target_dir))
            outputs = [Path(path) for path in result.get("outputs", [])]
            quality = [
                validate_output_quality(
                    operation.operation,
                    inputs[0],
                    output,
                    operation.expected_format,
                    converter_status=result.get("status", "success"),
                    notes=result.get("error"),
                    expected_pages=expected_batch_pages(operation, inputs),
                )
                for output in outputs
            ]
            row = row_from_quality(";".join(str(path.name) for path in inputs), operation.label, operation.operation, outputs, result.get("error"), quality)
            row["elapsed_seconds"] = round(time.perf_counter() - started, 3)
            rows.append(row)
        except Exception as exc:
            rows.append(
                {
                    "input_file": ";".join(str(path.name) for path in inputs),
                    "operation_label": operation.label,
                    "operation": operation.operation,
                    "outputs": [],
                    "final_status": "failed",
                    "notes": str(exc),
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "traceback": traceback.format_exc(),
                    "quality": [],
                }
            )
    return rows


def row_from_quality(
    relative: str,
    label: str,
    operation: str,
    outputs: list[Path],
    notes: str | None,
    quality: list[QualityResult],
) -> dict:
    quality_dicts = [item.to_dict() if hasattr(item, "to_dict") else item for item in quality]
    statuses = {item["final_status"] for item in quality_dicts}
    if "failed" in statuses:
        final_status = "failed"
    elif "partial" in statuses:
        final_status = "partial"
    elif "not_effective" in statuses:
        final_status = "not_effective"
    elif "not_validated" in statuses:
        final_status = "not_validated"
    elif "not_configured" in statuses:
        final_status = "not_configured"
    elif statuses == {"success_short_text"}:
        final_status = "success_short_text"
    else:
        final_status = "success"
    return {
        "input_file": relative,
        "operation_label": label,
        "operation": operation,
        "outputs": [str(path) for path in outputs],
        "final_status": final_status,
        "notes": notes,
        "elapsed_seconds": None,
        "quality": quality_dicts,
    }


def no_operation_row(relative: str, sample: Path) -> dict:
    return {
        "input_file": relative,
        "operation_label": "No supported operation",
        "operation": "no_supported_operation",
        "outputs": [],
        "final_status": "not_configured",
        "notes": f"No supported operation for extension {sample.suffix or '(none)'}",
        "elapsed_seconds": 0,
        "quality": [
            QualityResult(
                "no_supported_operation",
                str(sample),
                None,
                False,
                0,
                False,
                False,
                "No supported operation for this input extension",
                "not_configured",
                f"Extension: {sample.suffix or '(none)'}",
            ).to_dict()
        ],
    }


def expected_pdf_pages(operation: MatrixOperation, sample: Path) -> int | None:
    if operation.expected_format != "pdf":
        return None
    if operation.operation in {"image_to_pdf", "scan_to_pdf", "word_to_pdf", "powerpoint_to_pdf", "excel_to_pdf", "html_to_pdf", "protect_pdf"}:
        return None
    if operation.operation == "split_pdf":
        return 1
    try:
        with fitz.open(sample) as document:
            if operation.operation == "pdf_forms":
                return document.page_count + 1
            return document.page_count
    except Exception:
        return None


def expected_ocr_pages(operation: MatrixOperation, sample: Path) -> int | None:
    if operation.operation != "ocr_txt" or sample.suffix.lower() != ".pdf":
        return None
    try:
        with fitz.open(sample) as document:
            return document.page_count
    except Exception:
        return None


def expected_batch_pages(operation: MatrixOperation, inputs: list[Path]) -> int | None:
    if operation.operation != "merge_pdf":
        return None
    total = 0
    for item in inputs:
        with fitz.open(item) as document:
            total += document.page_count
    return total


def keywords_for(relative: str, operation: MatrixOperation, expected_keywords: dict[str, list[str]]) -> list[str] | None:
    if operation.operation != "ocr_txt":
        return None
    return expected_keywords.get(relative)


def operation_options_for(operation: str) -> dict:
    if operation == "protect_pdf":
        return {"password": "sample-matrix-test"}
    return {}


def operations_for_groups(groups: set[str]) -> set[str]:
    selected: set[str] = set()
    for group in groups:
        selected.update(OPERATION_GROUPS.get(group, set()))
    return selected


def safe_relative_stem(relative: str) -> str:
    path = Path(relative)
    digest = hashlib.sha1(relative.encode("utf-8")).hexdigest()[:10]
    stem = sanitize_operation_name(path.stem).replace(" ", "_")[:32].strip("_")
    return f"{stem}_{digest}" if stem else digest


def summarize(rows: list[dict]) -> dict[str, int]:
    statuses = ["success", "success_short_text", "failed", "partial", "not_effective", "not_configured", "not_validated"]
    counts = {status: 0 for status in statuses}
    for row in rows:
        counts[row["final_status"]] = counts.get(row["final_status"], 0) + 1
    return counts


def write_summary_markdown(path: Path, rows: list[dict], summary: dict, exe_info: dict) -> None:
    lines = [
        "# Sample File Matrix",
        "",
        f"Runner: `{exe_info['python_or_exe']}`",
        f"Frozen EXE: `{exe_info['is_frozen']}`",
        f"Test type: `{exe_info['test_type']}`",
        f"EXE verification: `{exe_info['exe_verification']}`",
        f"Source verification: `{exe_info['source_verification']}`",
        f"EXE OCR verification: `{exe_info['exe_ocr_verification']}`",
        f"Production readiness: `{exe_info['production_readiness']}`",
        f"Final production readiness: `{exe_info.get('final_production_readiness', 'NOT READY')}`",
        f"Samples: `{exe_info['samples_dir']}`",
        f"Run: `{exe_info['run_dir']}`",
        "",
        "## Summary",
        "",
        *[f"- {key}: {value}" for key, value in summary.items()],
        "",
        "## Input Output Summary",
        "",
        "| input | operation | output_count | final_status | notes |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    escape_md(row["input_file"]),
                    escape_md(row["operation_label"]),
                    str(len(row.get("outputs", []))),
                    row["final_status"],
                    escape_md(str(row.get("notes") or "")),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_production_gate_markdown(path: Path, rows: list[dict], summary: dict, exe_info: dict) -> None:
    del rows
    gate = exe_info.get("production_gate", {})
    checks = gate.get("checks", [])
    blockers = gate.get("blockers", [])
    manual_required = gate.get("manual_required", [])
    lines = [
        "# Production Readiness Gate",
        "",
        f"Runner: `{exe_info['python_or_exe']}`",
        f"Frozen EXE: `{exe_info['is_frozen']}`",
        f"EXE verification: `{exe_info['exe_verification']}`",
        f"EXE OCR verification: `{exe_info['exe_ocr_verification']}`",
        f"Internal beta readiness: `{exe_info['production_readiness']}`",
        f"Final production readiness: `{exe_info.get('final_production_readiness', 'NOT READY')}`",
        f"Run: `{exe_info['run_dir']}`",
        "",
        "## Summary",
        "",
        *[f"- {key}: {value}" for key, value in summary.items()],
        "",
        "## Automated Gate Checks",
        "",
        "| check | status | notes |",
        "| --- | --- | --- |",
    ]
    for check in checks:
        lines.append(
            "| "
            + " | ".join(
                [
                    escape_md(str(check.get("name", ""))),
                    escape_md(str(check.get("status", ""))),
                    escape_md(str(check.get("notes", ""))),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Production Blockers", ""])
    if blockers:
        lines.extend(f"- {item}" for item in blockers)
    else:
        lines.append("- None from automated checks.")

    lines.extend(["", "## Manual Checks Still Required", ""])
    if manual_required:
        lines.extend(f"- {item}" for item in manual_required)
    else:
        lines.append("- None.")

    lines.extend(
        [
            "",
            "## Production Decision",
            "",
            "This matrix validates frozen EXE behavior for the available sample files.",
            "Final production status is decided by tools/production_qa.py after automated, installer, OCR, and clean Windows evidence gates pass.",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def exe_verification_status(is_frozen: bool, summary: dict[str, int]) -> str:
    if not is_frozen:
        return "exe_not_tested"
    if summary.get("failed", 0) == 0:
        return "exe_test_passed"
    return "exe_test_failed"


def source_verification_status(is_frozen: bool, summary: dict[str, int]) -> str:
    if is_frozen:
        return "not_applicable"
    if summary.get("failed", 0) == 0:
        return "source_test_passed"
    return "source_test_failed"


def exe_ocr_verification_status(is_frozen: bool, rows: list[dict]) -> str:
    if not is_frozen:
        return "exe_not_tested"
    critical_ocr = [
        row
        for row in rows
        if row["operation"] == "ocr_txt" and (row["input_file"], row["operation"]) in CRITICAL_CHECKS
    ]
    if critical_ocr and all(row["final_status"] == "success" for row in critical_ocr):
        return "exe_ocr_passed"
    return "exe_ocr_failed"


def production_readiness_status(is_frozen: bool, rows: list[dict], summary: dict[str, int]) -> str:
    if not is_frozen:
        return "NOT READY"
    if summary.get("failed", 0) > 0:
        return "NOT READY"
    by_key = {(row["input_file"], row["operation"]): row["final_status"] for row in rows}
    critical_statuses = [by_key.get(check) for check in CRITICAL_CHECKS]
    if all(status == "success" for status in critical_statuses):
        return "READY FOR EXE MATRIX"
    return "NOT READY"


def production_gate_status(exe_info: dict, rows: list[dict], summary: dict[str, int]) -> dict:
    checks = []

    def add_check(name: str, status: str, notes: str) -> None:
        checks.append({"name": name, "status": status, "notes": notes})

    add_check(
        "Frozen Windows EXE",
        "pass" if exe_info.get("is_frozen") else "fail",
        f"runner={exe_info.get('python_or_exe')}",
    )
    add_check(
        "EXE operation matrix",
        "pass" if exe_info.get("exe_verification") == "exe_test_passed" else "fail",
        f"failed={summary.get('failed', 0)}, partial={summary.get('partial', 0)}",
    )
    add_check(
        "EXE OCR critical checks",
        "pass" if exe_info.get("exe_ocr_verification") == "exe_ocr_passed" else "fail",
        exe_info.get("exe_ocr_verification", "unknown"),
    )
    add_check(
        "Placeholder features hidden from production matrix",
        "pass" if summary.get("not_configured", 0) == 0 and summary.get("not_validated", 0) == 0 else "fail",
        f"not_configured={summary.get('not_configured', 0)}, not_validated={summary.get('not_validated', 0)}",
    )

    office_basic = [
        row
        for row in rows
        if row.get("operation") in {"word_to_pdf", "excel_to_pdf", "powerpoint_to_pdf"}
    ]
    add_check(
        "Office to PDF layout preservation",
        "blocked",
        f"{len(office_basic)} Basic Text result(s); production layout accuracy still requires LibreOffice/Office COM validation.",
    )

    installer_path = Path.cwd() / "dist" / "silukman_file_converter_setup.exe"
    add_check(
        "Inno Setup installer artifact",
        "pass" if installer_path.exists() else "manual_required",
        str(installer_path),
    )

    manual_required = [
        "Clean Windows no-Python install/run evidence.",
        "PaddleOCR first-run model download validation with internet.",
        "Offline OCR validation after PaddleOCR model cache exists.",
        "Installer install, shortcut, and uninstall evidence.",
    ]

    blockers = []
    for check in checks:
        if check["status"] in {"fail", "blocked"}:
            blockers.append(f"{check['name']}: {check['notes']}")
    if any(check["status"] == "manual_required" for check in checks):
        blockers.append("Installer artifact has not been generated in this environment.")

    return {
        "checks": checks,
        "blockers": blockers,
        "manual_required": manual_required,
    }


def final_production_readiness_status(gate: dict) -> str:
    if gate.get("blockers") or gate.get("manual_required"):
        return "NOT READY"
    checks = gate.get("checks", [])
    if checks and all(check.get("status") == "pass" for check in checks):
        return "READY FOR PRODUCTION"
    return "NOT READY"


def cli(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    samples_dir = Path("samples")
    output_root = Path("output") / "sample_file_matrix"
    source_label = "source"
    operation_filters: set[str] | None = None
    input_filters: set[str] | None = None
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--samples" and index + 1 < len(argv):
            samples_dir = Path(argv[index + 1])
            index += 2
        elif arg == "--output" and index + 1 < len(argv):
            output_root = Path(argv[index + 1])
            index += 2
        elif arg == "--source-label" and index + 1 < len(argv):
            source_label = argv[index + 1]
            index += 2
        elif arg in {"--matrix-op", "--operation"} and index + 1 < len(argv):
            operation_filters = operation_filters or set()
            operation_filters.add(argv[index + 1])
            index += 2
        elif arg in {"--matrix-input", "--input"} and index + 1 < len(argv):
            input_filters = input_filters or set()
            input_filters.add(Path(argv[index + 1]).as_posix())
            index += 2
        elif arg == "--matrix-group" and index + 1 < len(argv):
            operation_filters = operation_filters or set()
            operation_filters.update(operations_for_groups({argv[index + 1]}))
            index += 2
        else:
            index += 1
    try:
        result = run_sample_matrix(samples_dir, output_root, source_label, operation_filters, input_filters)
    except OSError as exc:
        result = {
            "success": False,
            "status": "controlled_error",
            "error_type": exc.__class__.__name__,
            "message": str(exc),
            "samples_dir": str(Path(samples_dir).resolve()),
            "output_root": str(Path(output_root).resolve()),
            "source_label": source_label,
            "operation_filters": sorted(operation_filters or []),
            "input_filters": sorted(input_filters or []),
        }
        print(json.dumps(result, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 1 if result["summary"].get("failed", 0) else 0


if __name__ == "__main__":
    raise SystemExit(cli())
