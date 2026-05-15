from pathlib import Path

import fitz
from PIL import Image


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
PDF_EXTENSIONS = {".pdf"}
WORD_EXTENSIONS = {".doc", ".docx"}
POWERPOINT_EXTENSIONS = {".ppt", ".pptx"}
EXCEL_EXTENSIONS = {".xls", ".xlsx"}
HTML_EXTENSIONS = {".html", ".htm"}
TEXT_EXTENSIONS = {".txt"}
CSV_EXTENSIONS = {".csv"}
JSON_EXTENSIONS = {".json"}
MAX_FILE_SIZE_MB = 200


class ValidationError(ValueError):
    pass


def validate_file_for_operation(file_path: str, operation: str) -> None:
    path = Path(file_path)
    _validate_common_file(path)

    suffix = path.suffix.lower()
    if operation in {"image_to_pdf", "image_ocr_txt", "scan_to_pdf"}:
        if suffix not in IMAGE_EXTENSIONS:
            raise ValidationError("Operasi ini hanya mendukung file PNG, JPG, atau JPEG.")
        _validate_image(path)
        return

    if operation == "ocr_txt":
        if suffix in IMAGE_EXTENSIONS:
            _validate_image(path)
            return
        if suffix in PDF_EXTENSIONS:
            _validate_pdf(path)
            return
        raise ValidationError("OCR hanya mendukung file PNG, JPG, JPEG, atau PDF.")

    pdf_operations = {
        "merge_pdf",
        "split_pdf",
        "compress_pdf",
        "pdf_to_word",
        "pdf_to_powerpoint",
        "pdf_to_excel",
        "edit_pdf",
        "pdf_to_png",
        "pdf_to_jpg",
        "sign_pdf",
        "watermark",
        "rotate_pdf",
        "unlock_pdf",
        "protect_pdf",
        "organize_pdf",
        "pdf_to_pdfa",
        "repair_pdf",
        "page_numbers",
        "compare_pdf",
        "redact_pdf",
        "crop_pdf",
        "pdf_forms",
        "translate_pdf",
        "pdf_ocr_txt",
    }
    if operation in pdf_operations:
        if suffix not in PDF_EXTENSIONS:
            raise ValidationError("Operasi ini hanya mendukung file PDF.")
        if operation == "unlock_pdf":
            _validate_pdf_container(path)
            return
        _validate_pdf(path)
        return

    if operation == "word_to_pdf":
        if suffix not in WORD_EXTENSIONS:
            raise ValidationError("Operasi ini hanya mendukung file DOC atau DOCX.")
        return

    if operation == "powerpoint_to_pdf":
        if suffix not in POWERPOINT_EXTENSIONS:
            raise ValidationError("Operasi ini hanya mendukung file PPT atau PPTX.")
        return

    if operation in {"excel_to_pdf", "excel_to_csv", "excel_to_json"}:
        if suffix not in EXCEL_EXTENSIONS:
            raise ValidationError("Operasi ini hanya mendukung file XLS atau XLSX.")
        return

    if operation == "csv_to_excel":
        if suffix not in CSV_EXTENSIONS:
            raise ValidationError("Operasi ini hanya mendukung file CSV.")
        return

    if operation == "json_to_excel":
        if suffix not in JSON_EXTENSIONS:
            raise ValidationError("Operasi ini hanya mendukung file JSON.")
        return

    if operation == "html_to_pdf":
        if suffix not in HTML_EXTENSIONS:
            raise ValidationError("Operasi ini hanya mendukung file HTML.")
        return

    if operation == "ai_summarizer":
        if suffix not in PDF_EXTENSIONS | WORD_EXTENSIONS | TEXT_EXTENSIONS:
            raise ValidationError("AI Summarizer mendukung PDF, DOC/DOCX, atau TXT.")
        if suffix in PDF_EXTENSIONS:
            _validate_pdf(path)
        return

    raise ValidationError("Operasi tidak didukung.")


def validate_output_dir(output_dir: str) -> None:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    test_file = path / ".write_test"
    try:
        test_file.write_text("ok", encoding="utf-8")
    finally:
        if test_file.exists():
            test_file.unlink()


def _validate_common_file(path: Path) -> None:
    if not path.exists():
        raise ValidationError("File tidak ditemukan.")
    if not path.is_file():
        raise ValidationError("Path bukan file.")
    if path.stat().st_size == 0:
        raise ValidationError("File kosong.")
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise ValidationError(f"Ukuran file terlalu besar. Maksimal {MAX_FILE_SIZE_MB} MB.")


def _validate_image(path: Path) -> None:
    try:
        with Image.open(path) as image:
            image.verify()
    except Exception as exc:
        raise ValidationError(f"File gambar tidak valid atau corrupt: {exc}") from exc


def _validate_pdf(path: Path) -> None:
    try:
        with fitz.open(path) as document:
            if document.is_encrypted:
                raise ValidationError("PDF terenkripsi dan tidak didukung.")
            if document.page_count == 0:
                raise ValidationError("PDF tidak memiliki halaman.")
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError(f"File PDF tidak valid atau corrupt: {exc}") from exc


def _validate_pdf_container(path: Path) -> None:
    try:
        with fitz.open(path) as document:
            if document.page_count == 0:
                raise ValidationError("PDF tidak memiliki halaman.")
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError(f"File PDF tidak valid atau corrupt: {exc}") from exc
