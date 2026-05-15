from pathlib import Path
from datetime import datetime
import importlib.util
import os
import traceback
from typing import Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.converter import Converter
from app.core.ocr_bootstrap import OCRBootstrapManager
from app.utils.file_helper import unique_paths
from app.utils.logger import get_logger
from app.utils.validator import ValidationError, validate_file_for_operation, validate_output_dir


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
PDF_EXTENSIONS = {".pdf"}
WORD_EXTENSIONS = {".doc", ".docx"}
POWERPOINT_EXTENSIONS = {".ppt", ".pptx"}
EXCEL_EXTENSIONS = {".xls", ".xlsx"}
HTML_EXTENSIONS = {".html", ".htm"}
CSV_EXTENSIONS = {".csv"}
JSON_EXTENSIONS = {".json"}
TEXT_EXTENSIONS = {".txt"}
SUPPORTED_EXTENSIONS = (
    IMAGE_EXTENSIONS
    | PDF_EXTENSIONS
    | WORD_EXTENSIONS
    | POWERPOINT_EXTENSIONS
    | EXCEL_EXTENSIONS
    | HTML_EXTENSIONS
    | CSV_EXTENSIONS
    | JSON_EXTENSIONS
    | TEXT_EXTENSIONS
)
DISABLED_PRODUCTION_OPERATIONS = {
    "ai_summarizer": "Not Configured: AI summarizer engine is not configured.",
    "translate_pdf": "Not Configured: translation engine is not configured.",
    "pdf_to_pdfa": "Not Validated: PDF/A validation tool is not configured.",
}
STATUS_MESSAGES = {
    "ocr_model_not_ready": "Model OCR belum tersedia. Hubungkan internet lalu jalankan OCR sekali untuk menyiapkan model.",
    "ocr_runtime_missing": "Runtime PaddleOCR tidak ditemukan. Pastikan paket OCR ikut terpasang bersama aplikasi.",
    "ocr_health_failed": "OCR belum siap. Periksa diagnostik runtime OCR.",
}
BASIC_OPERATION_NOTES = {
    "pdf_to_word": "Basic text extraction: belum mempertahankan layout asli 100%.",
    "pdf_to_powerpoint": "Basic page image export: belum menjadi slide editable penuh.",
    "pdf_to_excel": "Basic text/table extraction: layout asli belum dijamin sama.",
    "word_to_pdf": "Basic text conversion: belum layout-preserving seperti LibreOffice.",
    "powerpoint_to_pdf": "Basic text conversion: belum layout-preserving seperti LibreOffice.",
    "excel_to_pdf": "Basic text conversion: belum layout-preserving seperti LibreOffice.",
    "edit_pdf": "Basic: menambahkan teks demo pada posisi tetap.",
    "watermark": "Basic: memakai watermark text default.",
    "rotate_pdf": "Basic: rotasi default 90 derajat untuk semua halaman.",
    "crop_pdf": "Basic: crop default 3% untuk semua halaman.",
    "redact_pdf": "Basic: redact pattern default terbatas.",
    "sign_pdf": "Stamp visual saja, bukan digital signature berbasis sertifikat.",
}

TOOLS = [
    {"label": "Merge PDF", "operation": "merge_pdf", "exts": PDF_EXTENSIONS, "batch": True, "min_files": 2},
    {"label": "Split PDF", "operation": "split_pdf", "exts": PDF_EXTENSIONS},
    {"label": "Compress PDF", "operation": "compress_pdf", "exts": PDF_EXTENSIONS},
    {"label": "PDF to Word (Basic Text)", "operation": "pdf_to_word", "exts": PDF_EXTENSIONS},
    {"label": "PDF to PowerPoint (Basic)", "operation": "pdf_to_powerpoint", "exts": PDF_EXTENSIONS},
    {"label": "PDF to Excel (Basic Text)", "operation": "pdf_to_excel", "exts": PDF_EXTENSIONS},
    {"label": "Word to PDF (Basic Text)", "operation": "word_to_pdf", "exts": WORD_EXTENSIONS},
    {"label": "PowerPoint to PDF (Basic Text)", "operation": "powerpoint_to_pdf", "exts": POWERPOINT_EXTENSIONS},
    {"label": "Excel to PDF (Basic Text)", "operation": "excel_to_pdf", "exts": EXCEL_EXTENSIONS},
    {"label": "Excel to CSV", "operation": "excel_to_csv", "exts": EXCEL_EXTENSIONS},
    {"label": "Excel to JSON", "operation": "excel_to_json", "exts": EXCEL_EXTENSIONS},
    {"label": "CSV to Excel", "operation": "csv_to_excel", "exts": CSV_EXTENSIONS},
    {"label": "JSON to Excel", "operation": "json_to_excel", "exts": JSON_EXTENSIONS},
    {"label": "Edit PDF (Basic)", "operation": "edit_pdf", "exts": PDF_EXTENSIONS},
    {"label": "PDF to JPG", "operation": "pdf_to_jpg", "exts": PDF_EXTENSIONS},
    {"label": "PDF to PNG", "operation": "pdf_to_png", "exts": PDF_EXTENSIONS},
    {"label": "JPG/PNG to PDF", "operation": "image_to_pdf", "exts": IMAGE_EXTENSIONS},
    {"label": "Stamp PDF", "operation": "sign_pdf", "exts": PDF_EXTENSIONS},
    {"label": "Watermark (Basic)", "operation": "watermark", "exts": PDF_EXTENSIONS},
    {"label": "Rotate PDF (Basic)", "operation": "rotate_pdf", "exts": PDF_EXTENSIONS},
    {"label": "HTML to PDF", "operation": "html_to_pdf", "exts": HTML_EXTENSIONS},
    {"label": "Unlock PDF", "operation": "unlock_pdf", "exts": PDF_EXTENSIONS},
    {"label": "Protect PDF", "operation": "protect_pdf", "exts": PDF_EXTENSIONS},
    {"label": "Organize PDF", "operation": "organize_pdf", "exts": PDF_EXTENSIONS},
    {"label": "PDF to PDF/A (Coming Soon)", "operation": "pdf_to_pdfa", "exts": PDF_EXTENSIONS},
    {"label": "Repair PDF", "operation": "repair_pdf", "exts": PDF_EXTENSIONS},
    {"label": "Page numbers", "operation": "page_numbers", "exts": PDF_EXTENSIONS},
    {"label": "Scan to PDF", "operation": "scan_to_pdf", "exts": IMAGE_EXTENSIONS},
    {"label": "OCR PDF/Image", "operation": "ocr_txt", "exts": PDF_EXTENSIONS | IMAGE_EXTENSIONS},
    {"label": "Compare PDF", "operation": "compare_pdf", "exts": PDF_EXTENSIONS, "batch": True, "min_files": 2, "max_files": 2},
    {"label": "Redact PDF (Basic)", "operation": "redact_pdf", "exts": PDF_EXTENSIONS},
    {"label": "Crop PDF (Basic)", "operation": "crop_pdf", "exts": PDF_EXTENSIONS},
    {"label": "PDF Forms", "operation": "pdf_forms", "exts": PDF_EXTENSIONS},
    {"label": "AI Summarizer (Coming Soon)", "operation": "ai_summarizer", "exts": PDF_EXTENSIONS | WORD_EXTENSIONS | {".txt"}},
    {"label": "Translate PDF (Coming Soon)", "operation": "translate_pdf", "exts": PDF_EXTENSIONS},
]
OPERATIONS = {tool["label"]: tool["operation"] for tool in TOOLS}
BATCH_OPERATIONS = {tool["operation"] for tool in TOOLS if tool.get("batch")}
IMPLEMENTED_OPERATIONS = {
    "merge_pdf",
    "split_pdf",
    "compress_pdf",
    "pdf_to_word",
    "pdf_to_powerpoint",
    "pdf_to_excel",
    "word_to_pdf",
    "powerpoint_to_pdf",
    "excel_to_pdf",
    "excel_to_csv",
    "excel_to_json",
    "csv_to_excel",
    "json_to_excel",
    "edit_pdf",
    "pdf_to_jpg",
    "pdf_to_png",
    "image_to_pdf",
    "sign_pdf",
    "watermark",
    "rotate_pdf",
    "html_to_pdf",
    "unlock_pdf",
    "protect_pdf",
    "organize_pdf",
    "pdf_to_pdfa",
    "repair_pdf",
    "page_numbers",
    "scan_to_pdf",
    "ocr_txt",
    "compare_pdf",
    "redact_pdf",
    "crop_pdf",
    "pdf_forms",
    "ai_summarizer",
    "translate_pdf",
}


class ConversionWorker(QThread):
    progress = Signal(int)
    message = Signal(str)
    ocr_preview = Signal(str)
    finished_with_result = Signal(int, int)

    def __init__(
        self,
        files: list[str],
        operation: str,
        output_dir: str | None,
        output_timestamp: str,
        operation_options: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.files = files
        self.operation = operation
        self.output_dir = output_dir
        self.output_timestamp = output_timestamp
        self.operation_options = operation_options or {}
        self.converter = Converter()
        self.logger = get_logger()
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation. Current file will finish; next files are skipped."""
        self._cancelled = True
        self.message.emit("⚠ Pembatalan diminta — menunggu file saat ini selesai...")

    def run(self) -> None:
        success_count = 0
        failed_count = 0
        total = len(self.files)

        if self.operation == "ocr_txt":
            self.message.emit("Memeriksa runtime OCR...")
            self.progress.emit(2)
            bootstrap = OCRBootstrapManager().ensure_ready(allow_download=True, retries=1)
            if bootstrap.success:
                self.progress.emit(8)
                if bootstrap.cache_files:
                    self.message.emit(f"OCR siap. Cache model terdeteksi ({bootstrap.cache_files} file).")
                else:
                    self.message.emit("OCR siap. Model berhasil divalidasi.")
            else:
                failed_count = total
                self.progress.emit(100)
                self.message.emit(f"{bootstrap.status}: {bootstrap.message}")
                if bootstrap.error:
                    self.message.emit(f"Diagnostik OCR: {bootstrap.error}")
                self.finished_with_result.emit(success_count, failed_count)
                return

        if self.operation in BATCH_OPERATIONS:
            try:
                first_source = Path(self.files[0])
                output_base_dir = Path(self.output_dir) if self.output_dir else first_source.parent
                target_output_dir = output_base_dir / f"{self.operation}_{self.output_timestamp}"
                validate_output_dir(str(target_output_dir))
                for file_path in self.files:
                    validate_file_for_operation(file_path, self.operation)

                self.message.emit(f"Memproses batch: {self.operation}")

                def update_batch_progress(done: int, item_total: int) -> None:
                    if item_total <= 0:
                        return
                    self.progress.emit(round(done / item_total * 100))

                result = self.converter.convert_batch(
                    self.files,
                    self.operation,
                    str(target_output_dir),
                    progress_callback=update_batch_progress,
                )
                if result["success"]:
                    success_count = 1
                    outputs = ", ".join(str(path) for path in result["outputs"])
                    self.message.emit(f"Sukses: {outputs}")
                else:
                    failed_count = 1
                    self.message.emit(format_result_error(result))
            except Exception as exc:
                failed_count = 1
                self.message.emit(f"Gagal: {exc}")
                self.logger.error("Unhandled batch conversion error\n%s", traceback.format_exc())
            finally:
                self.progress.emit(100)
                self.finished_with_result.emit(success_count, failed_count)
            return

        for index, file_path in enumerate(self.files, start=1):
            # Check cancellation before starting each file
            if self._cancelled:
                self.message.emit(f"Dibatalkan: {total - index + 1} file dilewati.")
                failed_count += total - index + 1
                break

            try:
                file_base_progress = (index - 1) / total * 100
                file_progress_span = 100 / total

                def update_file_progress(done: int, page_total: int) -> None:
                    if page_total <= 0:
                        return
                    progress = file_base_progress + (done / page_total * file_progress_span)
                    self.progress.emit(round(progress))
                    self.message.emit(f"Halaman {done}/{page_total}: {file_path}")

                self.message.emit(f"Memproses: {file_path}")
                self.progress.emit(round(file_base_progress))
                source = Path(file_path)
                output_base_dir = Path(self.output_dir) if self.output_dir else source.parent
                target_output_dir = output_base_dir / f"{source.stem}_{self.output_timestamp}"
                validate_output_dir(str(target_output_dir))
                validate_file_for_operation(file_path, self.operation)
                result = self.converter.convert(
                    file_path,
                    self.operation,
                    str(target_output_dir),
                    progress_callback=update_file_progress,
                    operation_options=self.operation_options,
                )

                if result["success"]:
                    success_count += 1
                    outputs = ", ".join(str(path) for path in result["outputs"])
                    self.message.emit(f"Sukses: {outputs}")
                    if result["ocr"]:
                        self.ocr_preview.emit(result["ocr"]["text"])
                else:
                    failed_count += 1
                    self.message.emit(f"{file_path} - {format_result_error(result)}")
                    self.logger.error("Conversion failed for %s: %s", file_path, result["error"])
            except Exception as exc:
                failed_count += 1
                self.message.emit(f"Gagal: {file_path} - {exc}")
                self.logger.error("Unhandled conversion error for %s\n%s", file_path, traceback.format_exc())
            finally:
                self.progress.emit(round(index / total * 100))

        self.finished_with_result.emit(success_count, failed_count)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Silukman File Converter")
        self.resize(900, 680)
        self.files: list[str] = []
        self.output_dir: str | None = None
        self.output_timestamp = ""
        self.worker: ConversionWorker | None = None
        self._last_output_dir: str | None = None  # track last used output folder

        self.file_list = QListWidget()
        self.operation_combo = QComboBox()

        self.output_label = QLabel("Otomatis: folder file input\\nama_file_YmdHis")
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)

        # Banner shown when a "basic" operation is selected
        self.operation_note_label = QLabel("")
        self.operation_note_label.setWordWrap(True)
        self.operation_note_label.setStyleSheet(
            "color: #7a5c00; background: #fff8dc; border: 1px solid #e0c060; "
            "border-radius: 4px; padding: 4px 8px;"
        )
        self.operation_note_label.setVisible(False)

        self.status_log = QPlainTextEdit()
        self.status_log.setReadOnly(True)
        self.ocr_preview = QPlainTextEdit()
        self.ocr_preview.setReadOnly(True)
        self.ocr_preview.setPlaceholderText("Preview OCR akan tampil di sini.")

        self._build_ui()
        self.update_operation_options()

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)

        title = QLabel("Silukman File Converter")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(title)

        beta_note = QLabel("Production build. Advanced workflows remain labeled Basic or Coming Soon until their engines are fully implemented and validated.")
        beta_note.setWordWrap(True)
        beta_note.setStyleSheet("color: #555;")
        layout.addWidget(beta_note)

        self.ocr_status_label = QLabel(self.initial_ocr_status_text())
        self.ocr_status_label.setWordWrap(True)
        self.ocr_status_label.setStyleSheet("color: #555;")
        layout.addWidget(self.ocr_status_label)

        file_buttons = QHBoxLayout()
        add_button = QPushButton("Pilih File")
        add_button.clicked.connect(self.select_files)
        clear_button = QPushButton("Bersihkan")
        clear_button.clicked.connect(self.clear_files)
        file_buttons.addWidget(add_button)
        file_buttons.addWidget(clear_button)
        layout.addLayout(file_buttons)
        layout.addWidget(self.file_list)

        operation_layout = QHBoxLayout()
        operation_layout.addWidget(QLabel("Operasi"))
        operation_layout.addWidget(self.operation_combo)
        layout.addLayout(operation_layout)

        # Operation limitation banner
        layout.addWidget(self.operation_note_label)

        output_layout = QHBoxLayout()
        choose_output_button = QPushButton("Pilih Folder Output")
        choose_output_button.clicked.connect(self.select_output_dir)
        output_layout.addWidget(choose_output_button)
        output_layout.addWidget(self.output_label)
        layout.addLayout(output_layout)

        # Run + Cancel buttons side by side
        action_layout = QHBoxLayout()
        run_button = QPushButton("Mulai Proses")
        run_button.clicked.connect(self.start_conversion)
        self.run_button = run_button

        cancel_button = QPushButton("Batalkan")
        cancel_button.setEnabled(False)
        cancel_button.clicked.connect(self.cancel_conversion)
        cancel_button.setStyleSheet("color: #c0392b;")
        self.cancel_button = cancel_button

        open_output_button = QPushButton("Buka Folder Output")
        open_output_button.setEnabled(False)
        open_output_button.clicked.connect(self.open_last_output_dir)
        self.open_output_button = open_output_button

        action_layout.addWidget(run_button)
        action_layout.addWidget(cancel_button)
        action_layout.addWidget(open_output_button)
        layout.addLayout(action_layout)

        layout.addWidget(self.progress_bar)
        layout.addWidget(QLabel("Status"))
        layout.addWidget(self.status_log)
        layout.addWidget(QLabel("Preview OCR"))
        layout.addWidget(self.ocr_preview)

        self.setCentralWidget(root)

    # ── file selection ─────────────────────────────────────────────────────────

    def select_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Pilih file",
            "",
            "Supported Files (*.png *.jpg *.jpeg *.pdf *.doc *.docx *.ppt *.pptx "
            "*.xls *.xlsx *.html *.htm *.txt *.csv *.json);;"
            "PDF (*.pdf);;Images (*.png *.jpg *.jpeg);;"
            "Office (*.doc *.docx *.ppt *.pptx *.xls *.xlsx);;"
            "HTML (*.html *.htm);;CSV (*.csv);;JSON (*.json)",
        )
        if not files:
            return
        self.files = unique_paths([*self.files, *files])
        self.file_list.clear()
        self.file_list.addItems(self.files)
        self.output_dir = None
        self.update_output_label()
        self.update_operation_options()

    def clear_files(self) -> None:
        self.files = []
        self.file_list.clear()
        self.output_dir = None
        self.update_output_label()
        self.update_operation_options()
        self.progress_bar.setValue(0)

    def select_output_dir(self) -> None:
        start_dir = self.output_dir or (str(Path(self.files[0]).parent) if self.files else str(Path.cwd()))
        directory = QFileDialog.getExistingDirectory(self, "Pilih folder output", start_dir)
        if directory:
            self.output_dir = directory
            self.update_output_label()

    # ── conversion ─────────────────────────────────────────────────────────────

    def start_conversion(self) -> None:
        if not self.files:
            QMessageBox.warning(self, "File belum dipilih", "Pilih minimal satu file.")
            return

        if self.operation_combo.count() == 0:
            QMessageBox.warning(self, "Operasi tidak tersedia", "Tidak ada operasi yang cocok untuk file terpilih.")
            return

        operation = OPERATIONS[self.operation_combo.currentText()]
        if not self.is_operation_runnable(operation):
            QMessageBox.warning(
                self,
                "Fitur belum aktif",
                "Fitur ini sudah ada di daftar, tapi belum bisa dijalankan karena butuh parameter atau engine tambahan.",
            )
            return

        try:
            if self.output_dir:
                validate_output_dir(self.output_dir)
        except ValidationError as exc:
            QMessageBox.critical(self, "Folder output tidak valid", str(exc))
            return

        operation_options = self.collect_operation_options(operation)
        if operation_options is None:
            return

        self.status_log.clear()
        self.ocr_preview.clear()
        self.progress_bar.setValue(0)
        self.open_output_button.setEnabled(False)
        self.output_timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self.append_status(f"Menyiapkan proses dengan folder output timestamp: {self.output_timestamp}")
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        QApplication.setOverrideCursor(Qt.WaitCursor)

        self.worker = ConversionWorker(self.files, operation, self.output_dir, self.output_timestamp, operation_options)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.message.connect(self.append_status)
        self.worker.ocr_preview.connect(self.show_ocr_preview)
        self.worker.finished_with_result.connect(self.finish_conversion)
        self.worker.start()

    def cancel_conversion(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.cancel_button.setEnabled(False)

    # ── operation options ──────────────────────────────────────────────────────

    def update_operation_options(self) -> None:
        current = self.operation_combo.currentText()
        labels = self.available_operation_labels()
        self.operation_combo.clear()
        self.operation_combo.addItems(labels)
        model = self.operation_combo.model()
        first_enabled_index = -1
        for index, label in enumerate(labels):
            operation = OPERATIONS[label]
            runnable = self.is_operation_runnable(operation)
            item = model.item(index)
            if item and not runnable:
                item.setEnabled(False)
                item.setToolTip(DISABLED_PRODUCTION_OPERATIONS.get(operation, "Belum aktif: butuh parameter atau engine tambahan."))
            elif item and operation in BASIC_OPERATION_NOTES:
                item.setToolTip(BASIC_OPERATION_NOTES[operation])
            if runnable and first_enabled_index == -1:
                first_enabled_index = index

        if current in labels and self.is_operation_runnable(OPERATIONS[current]):
            self.operation_combo.setCurrentText(current)
        elif first_enabled_index >= 0:
            self.operation_combo.setCurrentIndex(first_enabled_index)
        self.run_button.setEnabled(first_enabled_index >= 0)

        # Connect combo change to update the note banner
        self.operation_combo.currentTextChanged.connect(self._update_operation_note)
        self._update_operation_note(self.operation_combo.currentText())

    def _update_operation_note(self, label: str) -> None:
        """Show/hide the limitation banner based on selected operation."""
        if not label or label not in OPERATIONS:
            self.operation_note_label.setVisible(False)
            return
        operation = OPERATIONS[label]
        note = BASIC_OPERATION_NOTES.get(operation)
        if note:
            self.operation_note_label.setText(f"ℹ️  {note}")
            self.operation_note_label.setVisible(True)
        else:
            self.operation_note_label.setVisible(False)

    def available_operation_labels(self) -> list[str]:
        suffixes = {Path(file_path).suffix.lower() for file_path in self.files}
        if not self.files:
            return [tool["label"] for tool in TOOLS]
        if suffixes - SUPPORTED_EXTENSIONS:
            return []

        labels = []
        for tool in TOOLS:
            allowed_exts = set(tool["exts"])
            if not suffixes <= allowed_exts:
                continue
            if len(self.files) < int(tool.get("min_files", 1)):
                continue
            if tool.get("max_files") and len(self.files) > int(tool["max_files"]):
                continue
            labels.append(tool["label"])
        return labels

    def is_operation_runnable(self, operation: str) -> bool:
        if operation not in IMPLEMENTED_OPERATIONS:
            return False
        if operation in DISABLED_PRODUCTION_OPERATIONS:
            return False
        if operation == "ocr_txt" and not self.has_ocr_runtime():
            return False
        return True

    def has_ocr_runtime(self) -> bool:
        manager = OCRBootstrapManager()
        return manager.find_external_python() is not None or importlib.util.find_spec("paddleocr") is not None

    def initial_ocr_status_text(self) -> str:
        manager = OCRBootstrapManager()
        if manager.find_external_python() is not None:
            return "OCR: runtime eksternal terdeteksi. Model akan dicek otomatis saat OCR pertama kali dijalankan."
        if importlib.util.find_spec("paddleocr") is not None:
            return "OCR: runtime internal terdeteksi. Model akan dicek otomatis saat OCR pertama kali dijalankan."
        return "OCR: runtime PaddleOCR belum terdeteksi. Fitur OCR akan nonaktif sampai runtime OCR tersedia."

    def collect_operation_options(self, operation: str) -> dict[str, Any] | None:
        if operation == "protect_pdf":
            password, ok = QInputDialog.getText(
                self,
                "Password Protect PDF",
                "Masukkan password PDF (minimal 6 karakter):",
                QLineEdit.Password,
            )
            if not ok:
                return None
            if not password:
                QMessageBox.warning(self, "Password wajib diisi", "Password PDF tidak boleh kosong.")
                return None
            if len(password) < 6:
                QMessageBox.warning(self, "Password terlalu pendek", "Password PDF minimal 6 karakter.")
                return None
            return {"password": password}

        if operation == "unlock_pdf":
            password, ok = QInputDialog.getText(
                self,
                "Password Unlock PDF",
                "Masukkan password PDF terenkripsi.\nKosongkan hanya jika PDF memang tidak memakai password:",
                QLineEdit.Password,
            )
            if not ok:
                return None
            return {"password": password}

        return {}

    # ── output helpers ─────────────────────────────────────────────────────────

    def open_last_output_dir(self) -> None:
        if self._last_output_dir and Path(self._last_output_dir).exists():
            os.startfile(self._last_output_dir)  # Windows: opens in Explorer
        else:
            QMessageBox.information(self, "Folder tidak ditemukan", "Folder output tidak ditemukan.")

    def update_output_label(self) -> None:
        if self.output_dir:
            self.output_label.setText(f"Manual: {self.output_dir}\\nama_file_YmdHis")
        elif self.files:
            self.output_label.setText("Otomatis: folder masing-masing file input\\nama_file_YmdHis")
        else:
            self.output_label.setText("Otomatis: folder file input\\nama_file_YmdHis")

    # ── status / OCR ──────────────────────────────────────────────────────────

    def append_status(self, message: str) -> None:
        self.status_log.appendPlainText(message)

    def show_ocr_preview(self, text: str) -> None:
        if self.ocr_preview.toPlainText():
            self.ocr_preview.appendPlainText("\n\n---\n")
        self.ocr_preview.appendPlainText(text)

    def finish_conversion(self, success_count: int, failed_count: int) -> None:
        QApplication.restoreOverrideCursor()
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

        # Determine last output folder for the "Buka Folder Output" button
        if self.files:
            first_source = Path(self.files[0])
            base = Path(self.output_dir) if self.output_dir else first_source.parent
            if self.operation in BATCH_OPERATIONS:
                candidate = base / f"{self.operation}_{self.output_timestamp}"
            else:
                candidate = base / f"{first_source.stem}_{self.output_timestamp}"
            if candidate.exists():
                self._last_output_dir = str(candidate)
                self.open_output_button.setEnabled(True)

        QMessageBox.information(
            self,
            "Proses selesai",
            f"Sukses: {success_count}\nGagal: {failed_count}\nTimestamp folder: {self.output_timestamp}",
        )

    # ── window close ──────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Proses sedang berjalan",
                "Ada proses yang sedang berjalan.\nTutup aplikasi sekarang? File yang sedang diproses mungkin tidak lengkap.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.worker.cancel()
                self.worker.wait(5000)  # wait up to 5 s for graceful stop
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def format_result_error(result: dict) -> str:
    status = result.get("status", "failed")
    message = STATUS_MESSAGES.get(status) or result.get("error") or "Proses gagal."
    return f"{status}: {message}"
