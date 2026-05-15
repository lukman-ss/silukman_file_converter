from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import os
import socket
import sys
from tempfile import TemporaryDirectory
from typing import Any

from PIL import Image, ImageDraw

from app.utils.process import run_hidden_process


OCR_BOOTSTRAP_READY_MESSAGE = "OCR runtime is ready."
OCR_BOOTSTRAP_NOT_READY_MESSAGE = "Model OCR belum tersedia. Hubungkan internet lalu jalankan OCR sekali untuk menyiapkan model."
OCR_RUNTIME_MISSING_MESSAGE = "Runtime PaddleOCR tidak ditemukan. Pastikan paket OCR ikut terpasang bersama aplikasi."


@dataclass
class OCRRuntimeStatus:
    success: bool
    status: str
    message: str
    runtime_mode: str = "unknown"
    external_python: str | None = None
    worker_script: str | None = None
    internet_available: bool = False
    cache_dirs: list[str] = field(default_factory=list)
    cache_files: int = 0
    diagnostics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OCRBootstrapManager:
    def __init__(self, root_dir: Path | None = None, lang: str = "en") -> None:
        self.root_dir = root_dir or Path(__file__).resolve().parents[2]
        self.lang = lang

    def quick_status(self) -> OCRRuntimeStatus:
        external_python = self.find_external_python()
        worker = self.find_worker_script()
        cache_dirs = self.model_cache_dirs()
        cache_files = self.count_cache_files(cache_dirs)
        in_process_available = self.in_process_paddle_available()

        if external_python and worker:
            return OCRRuntimeStatus(
                True,
                "ocr_runtime_available",
                "Runtime OCR tersedia. Model akan divalidasi saat OCR dijalankan.",
                runtime_mode="external",
                external_python=str(external_python),
                worker_script=str(worker),
                internet_available=self.internet_available(),
                cache_dirs=[str(path) for path in cache_dirs],
                cache_files=cache_files,
            )
        if in_process_available:
            return OCRRuntimeStatus(
                True,
                "ocr_runtime_available",
                "Runtime OCR tersedia di aplikasi.",
                runtime_mode="in_process",
                internet_available=self.internet_available(),
                cache_dirs=[str(path) for path in cache_dirs],
                cache_files=cache_files,
            )
        return OCRRuntimeStatus(
            False,
            "ocr_runtime_missing",
            OCR_RUNTIME_MISSING_MESSAGE,
            runtime_mode="missing",
            internet_available=self.internet_available(),
            cache_dirs=[str(path) for path in cache_dirs],
            cache_files=cache_files,
            error=OCR_RUNTIME_MISSING_MESSAGE,
        )

    def ensure_ready(self, allow_download: bool = True, retries: int = 1, timeout: int = 900) -> OCRRuntimeStatus:
        runtime = self.quick_status()
        if not runtime.success:
            return runtime

        if not allow_download and runtime.cache_files <= 0:
            return OCRRuntimeStatus(
                False,
                "ocr_model_not_ready",
                OCR_BOOTSTRAP_NOT_READY_MESSAGE,
                runtime_mode=runtime.runtime_mode,
                external_python=runtime.external_python,
                worker_script=runtime.worker_script,
                internet_available=runtime.internet_available,
                cache_dirs=runtime.cache_dirs,
                cache_files=runtime.cache_files,
                error="No local OCR model cache detected.",
            )

        if allow_download and not runtime.internet_available and runtime.cache_files <= 0:
            return OCRRuntimeStatus(
                False,
                "ocr_model_not_ready",
                OCR_BOOTSTRAP_NOT_READY_MESSAGE,
                runtime_mode=runtime.runtime_mode,
                external_python=runtime.external_python,
                worker_script=runtime.worker_script,
                internet_available=False,
                cache_dirs=runtime.cache_dirs,
                cache_files=runtime.cache_files,
                error="Internet is unavailable and OCR model cache is empty.",
            )

        last_status: OCRRuntimeStatus | None = None
        attempts = max(1, retries + 1)
        for attempt in range(1, attempts + 1):
            last_status = self.health_check(allow_download=allow_download, timeout=timeout)
            if last_status.success:
                return last_status
            if attempt < attempts and self.is_retryable_error(last_status.error or ""):
                continue
            break
        return last_status or runtime

    def health_check(self, allow_download: bool = False, timeout: int = 600) -> OCRRuntimeStatus:
        runtime = self.quick_status()
        if not runtime.success:
            return runtime

        if runtime.runtime_mode == "external":
            return self._external_health_check(runtime, allow_download=allow_download, timeout=timeout)
        return self._in_process_health_check(runtime, allow_download=allow_download)

    def _external_health_check(self, runtime: OCRRuntimeStatus, allow_download: bool, timeout: int) -> OCRRuntimeStatus:
        assert runtime.external_python
        assert runtime.worker_script
        with TemporaryDirectory() as temp_dir:
            probe_image = Path(temp_dir) / "ocr_health_probe.png"
            output_json = Path(temp_dir) / "ocr_health.json"
            self.write_probe_image(probe_image)
            proc = run_hidden_process(
                [
                    runtime.external_python,
                    runtime.worker_script,
                    "--images",
                    str(probe_image),
                    "--output",
                    str(output_json),
                    "--lang",
                    self.lang,
                    "--health-check",
                ],
                cwd=str(self.root_dir),
                timeout=timeout,
                env=self.subprocess_env(allow_download=allow_download),
            )
            if proc.returncode != 0:
                return self._failed_health(runtime, proc.stderr or proc.stdout or "OCR health check failed.")
            try:
                data = json.loads(output_json.read_text(encoding="utf-8"))
            except Exception as exc:
                return self._failed_health(runtime, f"OCR health output is invalid: {exc}")
            if not data.get("success"):
                return self._failed_health(runtime, str(data.get("error") or "OCR health check failed."))
            return self._ready_status(runtime, {"health": data})

    def _in_process_health_check(self, runtime: OCRRuntimeStatus, allow_download: bool) -> OCRRuntimeStatus:
        try:
            with TemporaryDirectory() as temp_dir:
                probe_image = Path(temp_dir) / "ocr_health_probe.png"
                self.write_probe_image(probe_image)
                old_value = os.environ.get("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK")
                if not allow_download:
                    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
                from paddleocr import PaddleOCR

                ocr = PaddleOCR(lang=self.lang)
                result = ocr.predict(str(probe_image)) if hasattr(ocr, "predict") else ocr.ocr(str(probe_image), cls=True)
                if old_value is None:
                    os.environ.pop("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", None)
                else:
                    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = old_value
                return self._ready_status(runtime, {"health_result_type": type(result).__name__})
        except Exception as exc:
            return self._failed_health(runtime, str(exc))

    def _ready_status(self, runtime: OCRRuntimeStatus, diagnostics: dict[str, Any] | None = None) -> OCRRuntimeStatus:
        cache_dirs = self.model_cache_dirs()
        return OCRRuntimeStatus(
            True,
            "ocr_ready",
            OCR_BOOTSTRAP_READY_MESSAGE,
            runtime_mode=runtime.runtime_mode,
            external_python=runtime.external_python,
            worker_script=runtime.worker_script,
            internet_available=self.internet_available(),
            cache_dirs=[str(path) for path in cache_dirs],
            cache_files=self.count_cache_files(cache_dirs),
            diagnostics=diagnostics or {},
        )

    def _failed_health(self, runtime: OCRRuntimeStatus, error: str) -> OCRRuntimeStatus:
        from app.core.ocr_engine import is_ocr_model_not_ready_error

        status = "ocr_model_not_ready" if is_ocr_model_not_ready_error(error) else "ocr_health_failed"
        message = OCR_BOOTSTRAP_NOT_READY_MESSAGE if status == "ocr_model_not_ready" else "OCR belum siap. Periksa diagnostik runtime OCR."
        return OCRRuntimeStatus(
            False,
            status,
            message,
            runtime_mode=runtime.runtime_mode,
            external_python=runtime.external_python,
            worker_script=runtime.worker_script,
            internet_available=self.internet_available(),
            cache_dirs=runtime.cache_dirs,
            cache_files=self.count_cache_files(self.model_cache_dirs()),
            error=error.strip(),
        )

    def find_external_python(self) -> Path | None:
        candidates = [
            self.root_dir / ".venv_ocr" / "Scripts" / "python.exe",
            Path.cwd() / ".venv_ocr" / "Scripts" / "python.exe",
            Path(sys.executable).resolve().parent.parent / ".venv_ocr" / "Scripts" / "python.exe",
            Path(sys.executable).resolve().parent / "runtime" / "ocr" / "python.exe",
        ]
        return next((path for path in candidates if path.exists()), None)

    def find_worker_script(self) -> Path | None:
        candidates = [
            self.root_dir / "app" / "core" / "paddle_ocr_worker.py",
            Path.cwd() / "app" / "core" / "paddle_ocr_worker.py",
            Path(getattr(sys, "_MEIPASS", Path.cwd())) / "app" / "core" / "paddle_ocr_worker.py",
            Path(sys.executable).resolve().parent / "app" / "core" / "paddle_ocr_worker.py",
        ]
        return next((path for path in candidates if path.exists()), None)

    def in_process_paddle_available(self) -> bool:
        try:
            import importlib.util

            return importlib.util.find_spec("paddleocr") is not None
        except Exception:
            return False

    def model_cache_dirs(self) -> list[Path]:
        candidates = [
            Path(os.environ["PADDLEOCR_HOME"]) if os.environ.get("PADDLEOCR_HOME") else None,
            Path(os.environ["PADDLE_HOME"]) if os.environ.get("PADDLE_HOME") else None,
            Path.home() / ".paddleocr",
            Path.home() / ".paddlex",
            Path.home() / ".paddle",
            Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SilukmanFileConverter" / "ocr_models",
        ]
        return [path for path in candidates if path is not None]

    def count_cache_files(self, cache_dirs: list[Path]) -> int:
        markers = {".pdmodel", ".pdiparams", ".yml", ".yaml", ".json", ".txt", ".nb"}
        count = 0
        for directory in cache_dirs:
            if not directory.exists():
                continue
            try:
                count += sum(1 for path in directory.rglob("*") if path.is_file() and (path.suffix.lower() in markers or "inference" in path.name.lower()))
            except OSError:
                continue
        return count

    def internet_available(self, timeout: float = 3.0) -> bool:
        for host, port in (("paddleocr.bj.bcebos.com", 443), ("1.1.1.1", 443)):
            try:
                with socket.create_connection((host, port), timeout=timeout):
                    return True
            except OSError:
                continue
        return False

    def subprocess_env(self, allow_download: bool) -> dict[str, str]:
        env = dict(os.environ)
        if not allow_download:
            env["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        env.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True" if not allow_download else "False")
        return env

    def write_probe_image(self, path: Path) -> None:
        image = Image.new("RGB", (720, 220), "white")
        draw = ImageDraw.Draw(image)
        draw.text((48, 72), "SILUKMAN OCR HEALTH 123", fill="black")
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)

    def is_retryable_error(self, error: str) -> bool:
        lowered = error.lower()
        return any(term in lowered for term in ("timeout", "connection", "temporary", "reset", "download"))
