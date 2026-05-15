from pathlib import Path
from typing import Any, Callable

from app.core.image_service import ImageService
from app.core.pdf_service import PDFService


class Converter:
    def __init__(self) -> None:
        self.image_service = ImageService()
        self.pdf_service = PDFService()
        self._ocr_engine = None

    def convert(
        self,
        file_path: str,
        operation: str,
        output_dir: str,
        output_prefix: str = "",
        progress_callback: Callable[[int, int], None] | None = None,
        operation_options: dict[str, Any] | None = None,
    ) -> dict:
        source = Path(file_path)
        options = operation_options or {}

        if operation == "split_pdf":
            outputs = self.pdf_service.split_pdf(file_path, output_dir, progress_callback=progress_callback)
            return self._success(outputs)

        if operation == "compress_pdf":
            output = self.pdf_service.compress_pdf(file_path, output_dir)
            original_size = source.stat().st_size
            compressed_size = Path(output).stat().st_size
            if compressed_size >= original_size:
                return self._status(
                    False,
                    "not_effective",
                    [output],
                    "Compressed PDF is not smaller than original file",
                    original_size=original_size,
                    compressed_size=compressed_size,
                )
            return self._success([output], original_size=original_size, compressed_size=compressed_size)

        if operation == "repair_pdf":
            output = self.pdf_service.repair_pdf(file_path, output_dir)
            return self._success([output])

        if operation == "edit_pdf":
            output = self.pdf_service.edit_pdf(file_path, output_dir)
            return self._success([output])

        if operation == "sign_pdf":
            output = self.pdf_service.stamp_pdf(file_path, output_dir)
            return self._success([output])

        if operation == "organize_pdf":
            output = self.pdf_service.organize_pdf(file_path, output_dir)
            return self._success([output])

        if operation == "pdf_to_pdfa":
            output = self.pdf_service.pdf_to_pdfa_candidate(file_path, output_dir)
            return self._status(
                False,
                "not_validated",
                [output],
                "PDF/A validation tool is not configured",
            )

        if operation == "rotate_pdf":
            output = self.pdf_service.rotate_pdf(file_path, output_dir)
            return self._success([output])

        if operation == "page_numbers":
            output = self.pdf_service.add_page_numbers(file_path, output_dir)
            return self._success([output])

        if operation == "watermark":
            output = self.pdf_service.add_text_watermark(file_path, output_dir)
            return self._success([output])

        if operation == "crop_pdf":
            output = self.pdf_service.crop_pdf(file_path, output_dir)
            return self._success([output])

        if operation == "unlock_pdf":
            password = str(options.get("password", ""))
            try:
                output = self.pdf_service.unlock_pdf(file_path, output_dir, password=password)
                return self._success([output])
            except ValueError as exc:
                return self._status(False, "failed", [], str(exc))

        if operation == "protect_pdf":
            password = str(options.get("password", ""))
            if not password:
                return self._status(False, "failed", [], "Password PDF wajib diisi.")
            if len(password) < 6:
                return self._status(False, "failed", [], "Password PDF minimal 6 karakter.")
            try:
                output = self.pdf_service.protect_pdf(file_path, output_dir, password=password)
                return self._success([output])
            except ValueError as exc:
                return self._status(False, "failed", [], str(exc))

        if operation == "redact_pdf":
            output = self.pdf_service.redact_pdf(file_path, output_dir)
            return self._success([output])

        if operation == "pdf_forms":
            output = self.pdf_service.add_pdf_form_page(file_path, output_dir)
            return self._success([output])

        if operation == "pdf_to_word":
            output = self.pdf_service.pdf_to_text_docx(file_path, output_dir)
            return self._success([output])

        if operation == "pdf_to_excel":
            output = self.pdf_service.pdf_to_text_xlsx(file_path, output_dir)
            return self._success([output])

        if operation == "pdf_to_powerpoint":
            output = self.pdf_service.pdf_to_powerpoint(file_path, output_dir)
            return self._success([output])

        if operation == "word_to_pdf":
            output = self.pdf_service.docx_to_pdf(file_path, output_dir)
            return self._success([output])

        if operation == "powerpoint_to_pdf":
            output = self.pdf_service.pptx_to_pdf(file_path, output_dir)
            return self._success([output])

        if operation == "excel_to_pdf":
            output = self.pdf_service.xlsx_to_pdf(file_path, output_dir)
            return self._success([output])

        if operation == "excel_to_csv":
            outputs = self.pdf_service.xlsx_to_csv(file_path, output_dir)
            return self._success(outputs)

        if operation == "excel_to_json":
            output = self.pdf_service.xlsx_to_json(file_path, output_dir)
            return self._success([output])

        if operation == "csv_to_excel":
            output = self.pdf_service.csv_to_xlsx(file_path, output_dir)
            return self._success([output])

        if operation == "json_to_excel":
            output = self.pdf_service.json_to_xlsx(file_path, output_dir)
            return self._success([output])

        if operation == "html_to_pdf":
            output = self.pdf_service.html_to_pdf(file_path, output_dir)
            return self._success([output])

        if operation == "ai_summarizer":
            return self._status(False, "not_configured", [], "AI summarizer engine is not configured")

        if operation == "translate_pdf":
            return self._status(False, "not_configured", [], "Translation engine is not configured")

        if operation in {"image_to_pdf", "scan_to_pdf"}:
            output = self.image_service.image_to_pdf(file_path, output_dir, output_prefix)
            return self._success([output])

        if operation == "pdf_to_png":
            outputs = self.pdf_service.pdf_to_images(
                file_path,
                output_dir,
                "png",
                output_prefix=output_prefix,
                progress_callback=progress_callback,
            )
            return self._success(outputs)

        if operation == "pdf_to_jpg":
            outputs = self.pdf_service.pdf_to_images(
                file_path,
                output_dir,
                "jpg",
                output_prefix=output_prefix,
                progress_callback=progress_callback,
            )
            return self._success(outputs)

        if operation in {"image_ocr_txt", "ocr_txt"} and source.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            ocr = self.ocr_engine.extract_text_from_image(file_path)
            has_text = bool(ocr.get("text", "").strip())
            output = self._write_ocr_text(source, output_dir, self._format_ocr_text(ocr), output_prefix) if has_text else None
            return self._status(
                bool(ocr.get("success")),
                ocr.get("status") or ("success" if ocr.get("success") else "failed"),
                [output] if output else [],
                ocr.get("error"),
                ocr=ocr,
            )

        if operation in {"pdf_ocr_txt", "ocr_txt"} and source.suffix.lower() == ".pdf":
            ocr = self.ocr_engine.extract_text_from_pdf(file_path)
            has_text = bool(ocr.get("text", "").strip())
            output = self._write_ocr_text(source, output_dir, self._format_ocr_text(ocr), output_prefix) if has_text else None
            return self._status(
                bool(ocr.get("success")),
                ocr.get("status") or ("success" if ocr.get("success") else "failed"),
                [output] if output else [],
                ocr.get("error"),
                ocr=ocr,
            )

        return self._status(
            False,
            "not_configured",
            [],
            f"Fitur '{operation}' sudah ada di daftar, tapi membutuhkan parameter/engine tambahan sebelum bisa dijalankan.",
        )

    def convert_batch(
        self,
        file_paths: list[str],
        operation: str,
        output_dir: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict:
        if operation == "merge_pdf":
            output = self.pdf_service.merge_pdfs(file_paths, output_dir, "merged.pdf")
            if progress_callback:
                progress_callback(len(file_paths), len(file_paths))
            return self._success([output])

        if operation == "compare_pdf":
            output = self.pdf_service.compare_pdfs(file_paths, output_dir)
            if progress_callback:
                progress_callback(len(file_paths), len(file_paths))
            return self._success([output])

        return self._status(False, "failed", [], f"Operasi batch tidak dikenal: {operation}")

    @property
    def ocr_engine(self):
        if self._ocr_engine is None:
            from app.core.ocr_engine import OCREngine

            self._ocr_engine = OCREngine()
        return self._ocr_engine

    def _write_ocr_text(self, source: Path, output_dir: str, text: str, output_prefix: str = "") -> Path:
        output = Path(output_dir) / f"{output_prefix}{source.stem}_ocr.txt"
        output.write_text(text, encoding="utf-8")
        return output

    def _format_ocr_text(self, ocr: dict) -> str:
        pages = ocr.get("pages") or []
        if len(pages) <= 1:
            return ocr.get("text", "")
        sections = []
        for page in pages:
            page_no = page.get("page", "?")
            text = page.get("text", "").strip()
            sections.append(f"--- Page {page_no} ---\n{text}")
        return "\n\n".join(sections).strip()

    def _success(self, outputs: list[Path], **metadata) -> dict:
        return self._status(True, "success", outputs, None, **metadata)

    def _status(
        self,
        success: bool,
        status: str,
        outputs: list[Path],
        error: str | None,
        ocr: dict | None = None,
        **metadata,
    ) -> dict:
        return {
            "success": success,
            "status": status,
            "outputs": outputs,
            "ocr": ocr,
            "error": error,
            **metadata,
        }
