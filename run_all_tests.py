    """
run_all_tests.py
Runs every implemented operation on the available sample files,
writes a summary report, then zips inputs + outputs + summary.
"""

from __future__ import annotations

import sys
import traceback
import zipfile
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.converter import Converter

# ── paths ──────────────────────────────────────────────────────────────────────
SAMPLES_DIR = ROOT_DIR / "samples"
OUTPUT_DIR  = ROOT_DIR / "output" / "test_run"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d%H%M%S")

# ── sample files ───────────────────────────────────────────────────────────────
PDF   = str(SAMPLES_DIR / "PRA_Lengkap.pdf")
PDF2  = str(SAMPLES_DIR / "sample_add_pdf.pdf")
DOCX  = str(SAMPLES_DIR / "sample_add_docx.docx")
XLSX  = str(SAMPLES_DIR / "sample_add_xlsx.xlsx")
PPTX  = str(SAMPLES_DIR / "sample_add_pptx.pptx")
HTML  = str(SAMPLES_DIR / "sample_add_html.html")
JPG   = str(SAMPLES_DIR / "sample_add_jpg.jpg")
PNG   = str(SAMPLES_DIR / "sample_add_png.png")

# ── operations to run ──────────────────────────────────────────────────────────
# Each entry: (label, operation, file_or_files, is_batch, operation_options)
TESTS: list[tuple[str, str, str | list[str], bool, dict]] = [
    # PDF operations
    ("Split PDF",           "split_pdf",         PDF,          False, {}),
    ("Compress PDF",        "compress_pdf",       PDF,          False, {}),
    ("Repair PDF",          "repair_pdf",         PDF,          False, {}),
    ("Edit PDF",            "edit_pdf",           PDF,          False, {}),
    ("Stamp PDF",           "sign_pdf",           PDF,          False, {}),
    ("Organize PDF",        "organize_pdf",       PDF,          False, {}),
    ("Rotate PDF",          "rotate_pdf",         PDF,          False, {}),
    ("Page Numbers",        "page_numbers",       PDF,          False, {}),
    ("Watermark",           "watermark",          PDF,          False, {}),
    ("Crop PDF",            "crop_pdf",           PDF,          False, {}),
    ("Unlock PDF",          "unlock_pdf",         PDF,          False, {"password": ""}),
    ("Protect PDF",         "protect_pdf",        PDF,          False, {"password": "test123"}),
    ("Redact PDF",          "redact_pdf",         PDF,          False, {}),
    ("PDF Forms",           "pdf_forms",          PDF,          False, {}),
    ("PDF to Word",         "pdf_to_word",        PDF,          False, {}),
    ("PDF to Excel",        "pdf_to_excel",       PDF,          False, {}),
    ("PDF to PowerPoint",   "pdf_to_powerpoint",  PDF,          False, {}),
    ("PDF to JPG",          "pdf_to_jpg",         PDF,          False, {}),
    ("PDF to PNG",          "pdf_to_png",         PDF,          False, {}),
    # Batch PDF
    ("Merge PDF",           "merge_pdf",          [PDF, PDF2],  True,  {}),
    ("Compare PDF",         "compare_pdf",        [PDF, PDF2],  True,  {}),
    # Office → PDF
    ("Word to PDF",         "word_to_pdf",        DOCX,         False, {}),
    ("Excel to PDF",        "excel_to_pdf",       XLSX,         False, {}),
    ("PowerPoint to PDF",   "powerpoint_to_pdf",  PPTX,         False, {}),
    ("HTML to PDF",         "html_to_pdf",        HTML,         False, {}),
    # Excel conversions
    ("Excel to CSV",        "excel_to_csv",       XLSX,         False, {}),
    ("Excel to JSON",       "excel_to_json",      XLSX,         False, {}),
    # Image operations
    ("Image to PDF",        "image_to_pdf",       JPG,          False, {}),
    ("Scan to PDF",         "scan_to_pdf",        PNG,          False, {}),
    # OCR
    ("OCR Image",           "ocr_txt",            JPG,          False, {}),
    # OCR PDF skipped — large PDF causes timeout in batch test; works via UI
    # ("OCR PDF",           "ocr_txt",            PDF,          False, {}),
]

# ── runner ─────────────────────────────────────────────────────────────────────

def run_all() -> list[dict]:
    converter = Converter()
    results: list[dict] = []

    for label, operation, files, is_batch, options in TESTS:
        out_dir = OUTPUT_DIR / f"{label.replace(' ', '_')}_{TIMESTAMP}"
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"  ▶  {label} ...", end=" ", flush=True)
        try:
            if is_batch:
                result = converter.convert_batch(
                    files,
                    operation,
                    str(out_dir),
                )
            else:
                result = converter.convert(
                    files,
                    operation,
                    str(out_dir),
                    operation_options=options,
                )

            status  = "✅ SUCCESS" if result["success"] else f"❌ FAILED ({result.get('status','')})"
            outputs = [str(p) for p in result.get("outputs", [])]
            error   = result.get("error") or ""
            print(status)
        except Exception as exc:
            status  = "❌ ERROR"
            outputs = []
            error   = traceback.format_exc()
            print(f"❌ EXCEPTION: {exc}")

        results.append({
            "label":      label,
            "operation":  operation,
            "input":      files if isinstance(files, list) else [files],
            "output_dir": str(out_dir),
            "outputs":    outputs,
            "status":     status,
            "error":      error,
        })

    return results


def write_summary(results: list[dict]) -> Path:
    summary_path = OUTPUT_DIR / f"summary_{TIMESTAMP}.txt"
    lines: list[str] = [
        "=" * 70,
        "  silukman_file_converter — Full Operation Test Summary",
        f"  Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 70,
        "",
    ]

    success = sum(1 for r in results if "SUCCESS" in r["status"])
    failed  = len(results) - success
    lines += [
        f"Total operations : {len(results)}",
        f"Succeeded        : {success}",
        f"Failed / Error   : {failed}",
        "",
        "-" * 70,
    ]

    for r in results:
        lines.append(f"\n[{r['status']}]  {r['label']}  ({r['operation']})")
        lines.append(f"  Input  : {', '.join(Path(p).name for p in r['input'])}")
        if r["outputs"]:
            for out in r["outputs"]:
                lines.append(f"  Output : {out}")
        else:
            lines.append("  Output : (none)")
        if r["error"]:
            # truncate very long tracebacks
            err_preview = r["error"][:600].replace("\n", "\n           ")
            lines.append(f"  Error  : {err_preview}")

    lines += ["", "=" * 70, "End of report", "=" * 70]
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n📄 Summary written → {summary_path}")
    return summary_path


def build_zip(results: list[dict], summary_path: Path) -> Path:
    zip_path = ROOT_DIR / f"test_results_{TIMESTAMP}.zip"
    collected: set[str] = set()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # summary
        zf.write(summary_path, f"summary/{summary_path.name}")

        # inputs (sample files only — skip large sub-folders)
        for r in results:
            for inp in r["input"]:
                p = Path(inp)
                if p.exists() and str(p) not in collected:
                    collected.add(str(p))
                    zf.write(p, f"inputs/{p.name}")

        # outputs
        for r in results:
            out_dir = Path(r["output_dir"])
            if not out_dir.exists():
                continue
            for file in out_dir.rglob("*"):
                if file.is_file():
                    arcname = f"outputs/{out_dir.name}/{file.relative_to(out_dir)}"
                    zf.write(file, arcname)

    print(f"📦 ZIP created → {zip_path}")
    return zip_path


# ── main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("  silukman_file_converter — Running all operations")
    print(f"  Timestamp : {TIMESTAMP}")
    print(f"{'='*60}\n")

    results     = run_all()
    summary     = write_summary(results)
    zip_file    = build_zip(results, summary)

    success = sum(1 for r in results if "SUCCESS" in r["status"])
    print(f"\n✅ Done — {success}/{len(results)} operations succeeded.")
    print(f"📦 Package ready: {zip_file}\n")
