from pathlib import Path
import json
import re
import sys
from statistics import mean
from tempfile import TemporaryDirectory
from typing import Any

from app.core.image_service import ImageService
from app.core.ocr_bootstrap import OCRBootstrapManager
from app.core.pdf_service import PDFService
from app.utils.process import run_hidden_process


OCR_MODEL_NOT_READY_MESSAGE = "OCR model is not available locally. Please run OCR once with internet connection."

OCR_CONFIG = {
    "pdf_ocr_render": {
        "dpi": 300,
        "image_format": "png",
        "process_page_by_page": True,
    },
    "ocr_preprocess": {
        "min_width_for_upscale": 1200,
        "upscale_factor": 2,
        "enable_grayscale": True,
        "enable_contrast": True,
        "enable_denoise": True,
        "enable_threshold": False,
        "enable_deskew": True,
    },
}


class OCREngine:
    def __init__(self, lang: str = "en") -> None:
        self.lang = lang
        self._ocr = None
        self.image_service = ImageService()
        self.pdf_service = PDFService()
        self.bootstrap_manager = OCRBootstrapManager(lang=lang)
        self._bootstrap_status = None

    @property
    def ocr(self):
        if self._ocr is None:
            from paddleocr import PaddleOCR

            self._ocr = PaddleOCR(use_angle_cls=True, lang=self.lang)
        return self._ocr

    def extract_text_from_image(self, file_path: str) -> dict[str, Any]:
        try:
            with TemporaryDirectory() as temp_dir:
                return self.run_paddleocr_best(str(file_path), temp_dir, page_number=1)
        except Exception as exc:
            return self._failed(str(exc))

    def extract_text_from_pdf(self, file_path: str) -> dict[str, Any]:
        try:
            if self.has_text_layer(file_path):
                return self.extract_text_directly(file_path)

            return self.extract_text_from_pdf_with_ocr(file_path)
        except Exception as exc:
            return self._failed(str(exc))

    def has_text_layer(self, pdf_path: str, min_chars: int = 20) -> bool:
        import fitz

        with fitz.open(pdf_path) as document:
            if document.is_encrypted:
                raise ValueError("PDF terenkripsi dan tidak bisa diproses.")
            return sum(len(page.get_text("text").strip()) for page in document) >= min_chars

    def extract_text_directly(self, pdf_path: str) -> dict[str, Any]:
        import fitz

        pages = []
        texts = []
        with fitz.open(pdf_path) as document:
            if document.is_encrypted:
                raise ValueError("PDF terenkripsi dan tidak bisa diproses.")
            for index, page in enumerate(document, start=1):
                text = page.get_text("text").strip()
                text = clean_currency_ocr_noise(text)
                pages.append(
                    {
                        "page": index,
                        "text": text,
                        "confidence": 1 if text else 0,
                        "status": "success" if text else "failed",
                        "error": None if text else "No selectable text on page",
                        "source": "text_layer",
                    }
                )
                if text:
                    texts.append(text)

        return {
            "success": bool(texts),
            "status": "success" if texts else "failed",
            "engine": "direct_pdf_text",
            "text": "\n\n".join(texts),
            "confidence": 1 if texts else 0,
            "pages": pages,
            "error": None if texts else "No selectable text detected",
        }

    def render_pdf_to_images(self, pdf_path: str, output_dir: str) -> list[Path]:
        return self.pdf_service.render_pdf_pages_for_ocr(
            pdf_path,
            output_dir,
            dpi=OCR_CONFIG["pdf_ocr_render"]["dpi"],
        )

    def extract_text_from_pdf_with_ocr(self, pdf_path: str) -> dict[str, Any]:
        with TemporaryDirectory() as temp_dir:
            image_paths = self.render_pdf_to_images(pdf_path, temp_dir)
            batch_result = self.run_paddleocr_batch([str(path) for path in image_paths])
            batch_pages = batch_result.get("pages") or []
            if batch_pages and all(str(page.get("text", "")).strip() for page in batch_pages):
                return batch_result

            pages = []
            for index, image_path in enumerate(image_paths, start=1):
                page_result = self.run_paddleocr_best(str(image_path), temp_dir, page_number=index)
                page = page_result["pages"][0] if page_result.get("pages") else {
                    "page": index,
                    "text": "",
                    "confidence": 0,
                    "status": "failed",
                    "error": page_result.get("error") or "No OCR result",
                }
                pages.append(page)
            return self._result_from_pages(pages, "paddleocr")

    def preprocess_image(self, image_path: str, output_dir: str | None = None) -> Path:
        output_dir = output_dir or str(Path(image_path).parent)
        return self.image_service.preprocess_for_ocr(image_path, output_dir)

    def preprocess_image_variants(self, image_path: str, output_dir: str | None = None) -> list[Path]:
        output_dir = output_dir or str(Path(image_path).parent)
        return self.image_service.preprocess_variants_for_ocr(image_path, output_dir)

    def run_paddleocr(self, image_path: str):
        if hasattr(self.ocr, "predict"):
            return self.ocr.predict(image_path)
        return self.ocr.ocr(image_path, cls=True)

    def run_paddleocr_batch(self, image_paths: list[str]) -> dict[str, Any]:
        bootstrap = self.ensure_ocr_ready(allow_download=True)
        if not bootstrap.success:
            return {
                "success": False,
                "status": bootstrap.status,
                "engine": "paddleocr",
                "text": "",
                "confidence": 0,
                "pages": [
                    {
                        "page": index,
                        "image": image_path,
                        "text": "",
                        "confidence": 0,
                        "status": bootstrap.status,
                        "error": bootstrap.message,
                    }
                    for index, image_path in enumerate(image_paths, start=1)
                ],
                "error": bootstrap.message,
                "diagnostics": bootstrap.to_dict(),
            }

        external = self._run_external_paddleocr(image_paths)
        if external is not None:
            return self._normalize_ocr_result(external)

        pages = []
        for index, image_path in enumerate(image_paths, start=1):
            formatted = self.format_ocr_result(self.run_paddleocr(image_path))
            pages.append(
                {
                    "page": index,
                    "image": image_path,
                    "text": formatted["text"],
                    "confidence": formatted["confidence"],
                    "status": "success" if formatted["text"] else "failed",
                    "error": None if formatted["text"] else "No text detected",
                }
            )

        return self._result_from_pages(pages, "paddleocr")

    def run_paddleocr_best(self, image_path: str, output_dir: str, page_number: int) -> dict[str, Any]:
        variants = self.preprocess_image_variants(image_path, output_dir)
        best_page = None
        best_score = -1.0
        for variant in variants:
            result = self.run_paddleocr_batch([str(variant)])
            page = result["pages"][0] if result.get("pages") else None
            if not page:
                continue
            text = page.get("text", "")
            confidence = float(page.get("confidence", 0) or 0)
            score = confidence + min(len(text), 400) / 1000
            if score > best_score:
                best_score = score
                best_page = {**page, "variant": variant.name}

        if not best_page:
            best_page = {"page": page_number, "text": "", "confidence": 0, "status": "failed", "error": "No OCR result"}
        best_page["page"] = page_number
        best_page["text"] = clean_currency_ocr_noise(best_page.get("text", ""))
        best_page["status"] = "success" if best_page["text"].strip() else "failed"
        best_page["error"] = None if best_page["status"] == "success" else best_page.get("error") or "No text detected"
        return self._result_from_pages([best_page], "paddleocr")

    def _run_external_paddleocr(self, image_paths: list[str]) -> dict[str, Any] | None:
        root_dir = Path(__file__).resolve().parents[2]
        external_python = self.bootstrap_manager.find_external_python()
        worker = self.bootstrap_manager.find_worker_script()
        if external_python is None:
            return None
        if worker is None:
            raise RuntimeError("PaddleOCR worker script tidak ditemukan.")

        with TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "ocr_result.json"
            command = [
                str(external_python),
                str(worker),
                "--images",
                *image_paths,
                "--output",
                str(output),
                "--lang",
                self.lang,
            ]
            env = {
                **dict(),
                "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True",
            }
            proc = run_hidden_process(
                command,
                cwd=str(root_dir),
                timeout=1800,
                env={**self._subprocess_env(), **env},
            )
            if proc.returncode != 0:
                raise RuntimeError((proc.stderr or proc.stdout or "External PaddleOCR failed").strip())
            return json.loads(output.read_text(encoding="utf-8"))

    def _subprocess_env(self) -> dict[str, str]:
        import os

        return dict(os.environ)

    def ensure_ocr_ready(self, allow_download: bool = True):
        if self._bootstrap_status and self._bootstrap_status.success:
            return self._bootstrap_status
        self._bootstrap_status = self.bootstrap_manager.ensure_ready(allow_download=allow_download, retries=1)
        return self._bootstrap_status

    def _extract_existing_pdf_text(self, pdf_path: str, page_index: int) -> str:
        import fitz

        with fitz.open(pdf_path) as document:
            return document.load_page(page_index).get_text("text").strip()

    def format_ocr_result(self, result) -> dict[str, Any]:
        texts = []
        scores = []

        for page in result or []:
            if not page:
                continue
            if hasattr(page, "get"):
                rec_texts = page.get("rec_texts", [])
                rec_scores = page.get("rec_scores", [])
                texts.extend(str(text) for text in rec_texts if str(text).strip())
                scores.extend(float(score) for score in rec_scores)
                continue
            for line in page:
                text = line[1][0]
                score = float(line[1][1])
                texts.append(text)
                scores.append(score)

        return {
            "success": bool(texts),
            "status": "success" if texts else "failed",
            "engine": "paddleocr",
            "text": clean_currency_ocr_noise("\n".join(texts)),
            "confidence": mean(scores) if scores else 0,
            "pages": [],
            "error": None if texts else "No text detected",
        }

    def _normalize_ocr_result(self, result: dict[str, Any]) -> dict[str, Any]:
        pages = []
        for index, page in enumerate(result.get("pages", []), start=1):
            text = clean_currency_ocr_noise(str(page.get("text", "")))
            pages.append(
                {
                    **page,
                    "page": int(page.get("page") or index),
                    "text": text,
                    "confidence": float(page.get("confidence", 0) or 0),
                    "status": "success" if text.strip() else "failed",
                    "error": None if text.strip() else page.get("error") or "No text detected",
                }
            )
        return self._result_from_pages(pages, str(result.get("engine") or "paddleocr"))

    def _result_from_pages(self, pages: list[dict[str, Any]], engine: str) -> dict[str, Any]:
        scores = [float(page.get("confidence", 0) or 0) for page in pages if page.get("text")]
        text = "\n\n".join(page.get("text", "") for page in pages if page.get("text"))
        failed_pages = [page for page in pages if page.get("status") != "success"]
        if not pages or not text:
            status = "failed"
            error = "No text detected"
            success = False
        elif failed_pages:
            status = "partial"
            error = "Some pages failed OCR quality validation"
            success = False
        else:
            status = "success"
            error = None
            success = True
        return {
            "success": success,
            "status": status,
            "engine": "paddleocr" if str(engine).startswith("paddleocr") else engine,
            "text": text,
            "confidence": mean(scores) if scores else 0,
            "pages": pages,
            "error": error,
        }

    def _failed(self, error: str) -> dict[str, Any]:
        if is_ocr_model_not_ready_error(error):
            return {
                "success": False,
                "status": "ocr_model_not_ready",
                "engine": "paddleocr",
                "text": "",
                "confidence": 0,
                "pages": [],
                "error": OCR_MODEL_NOT_READY_MESSAGE,
            }
        return {
            "success": False,
            "status": "failed",
            "engine": "paddleocr",
            "text": "",
            "confidence": 0,
            "pages": [],
            "error": error or "OCR failed",
        }


def clean_currency_ocr_noise(text: str) -> str:
    """
    Fix common OCR noise before Indonesian currency values.
    Example:
    'R Rp 666.000' -> 'Rp 666.000'
    'RP 666.000' -> 'Rp 666.000'
    'Rp666.000' -> 'Rp 666.000'
    """
    return normalize_indonesian_currency(text)


def normalize_indonesian_currency(text: str) -> str:
    """
    Normalize common OCR mistakes in Indonesian currency format.
    Must preserve thousands separator and only apply around Rp / IDR patterns.
    """
    if not text:
        return text

    text = re.sub(r"\bR\s+(?=Rp\b)", "", text, flags=re.IGNORECASE)

    def repl(match: re.Match) -> str:
        raw_prefix = match.group("prefix")
        prefix = "IDR" if raw_prefix.upper() == "IDR" else "Rp"
        amount = match.group("amount")
        normalized = amount.replace(",", ".").replace(" ", "")
        if re.fullmatch(r"\d+\.0", normalized):
            normalized = normalized[:-2] + ".000"
        elif re.fullmatch(r"\d{4,}", normalized):
            groups = []
            while normalized:
                groups.insert(0, normalized[-3:])
                normalized = normalized[:-3]
            normalized = ".".join(groups)
        return f"{prefix} {normalized}"

    currency_pattern = re.compile(
        r"(?P<prefix>\b(?:Rp|IDR))\s*(?P<amount>\d[\d\s.,]*\d|\d)",
        flags=re.IGNORECASE,
    )
    return currency_pattern.sub(repl, text)


def is_ocr_model_not_ready_error(error: str) -> bool:
    """
    Detect PaddleOCR first-run/offline model failures without exposing raw traces.
    The exact message differs across PaddleOCR/PaddleX versions, so keep this
    intentionally focused on model download/cache failures.
    """
    if not error:
        return False

    lowered = error.lower()
    model_terms = (
        "model",
        "inference",
        "paddleocr",
        "paddlex",
    )
    download_terms = (
        "download",
        "httpconnectionpool",
        "httpsconnectionpool",
        "connectionerror",
        "connection error",
        "failed to establish a new connection",
        "name resolution",
        "temporary failure",
        "timed out",
        "timeout",
        "network is unreachable",
        "connection refused",
        "connection reset",
        "remotedisconnected",
        "ssl",
        "urlopen",
    )
    missing_cache_terms = (
        "no such file",
        "not found",
        "cannot find",
        "does not exist",
        "not available locally",
    )

    has_model_context = any(term in lowered for term in model_terms)
    has_download_problem = any(term in lowered for term in download_terms)
    has_missing_cache = any(term in lowered for term in missing_cache_terms)
    return has_model_context and (has_download_problem or has_missing_cache)
