from app.core.ocr_engine import (
    OCR_MODEL_NOT_READY_MESSAGE,
    OCREngine,
    is_ocr_model_not_ready_error,
)
from app.core.ocr_bootstrap import OCRBootstrapManager, OCR_BOOTSTRAP_NOT_READY_MESSAGE


def test_detects_offline_first_run_model_download_failure():
    error = (
        "PaddleOCR model download failed: HTTPSConnectionPool(host='paddleocr.bj.bcebos.com', "
        "port=443): Max retries exceeded with url: /model.tar caused by ConnectionError"
    )

    assert is_ocr_model_not_ready_error(error)


def test_detects_missing_local_model_cache():
    error = "PaddleOCR inference model not found: C:/Users/example/.paddleocr/whl/det/en"

    assert is_ocr_model_not_ready_error(error)


def test_does_not_treat_unrelated_ocr_errors_as_missing_model():
    assert not is_ocr_model_not_ready_error("No text detected")
    assert not is_ocr_model_not_ready_error("PDF terenkripsi dan tidak bisa diproses.")


def test_failed_ocr_result_uses_model_not_ready_status():
    result = OCREngine()._failed("PaddleOCR model download timed out")

    assert result["success"] is False
    assert result["status"] == "ocr_model_not_ready"
    assert result["error"] == OCR_MODEL_NOT_READY_MESSAGE
    assert result["text"] == ""


def test_bootstrap_reports_missing_runtime(tmp_path, monkeypatch):
    manager = OCRBootstrapManager(root_dir=tmp_path)
    monkeypatch.setattr(manager, "find_external_python", lambda: None)
    monkeypatch.setattr(manager, "find_worker_script", lambda: None)
    monkeypatch.setattr(manager, "in_process_paddle_available", lambda: False)
    monkeypatch.setattr(manager, "internet_available", lambda timeout=3.0: False)

    status = manager.quick_status()

    assert status.success is False
    assert status.status == "ocr_runtime_missing"
    assert status.runtime_mode == "missing"


def test_bootstrap_blocks_offline_empty_cache(tmp_path, monkeypatch):
    runtime = tmp_path / ".venv_ocr" / "Scripts"
    runtime.mkdir(parents=True)
    python_exe = runtime / "python.exe"
    python_exe.write_text("", encoding="utf-8")
    worker = tmp_path / "app" / "core"
    worker.mkdir(parents=True)
    (worker / "paddle_ocr_worker.py").write_text("", encoding="utf-8")

    manager = OCRBootstrapManager(root_dir=tmp_path)
    monkeypatch.setattr(manager, "in_process_paddle_available", lambda: False)
    monkeypatch.setattr(manager, "internet_available", lambda timeout=3.0: False)
    monkeypatch.setattr(manager, "model_cache_dirs", lambda: [tmp_path / "empty_cache"])

    status = manager.ensure_ready(allow_download=True)

    assert status.success is False
    assert status.status == "ocr_model_not_ready"
    assert status.message == OCR_BOOTSTRAP_NOT_READY_MESSAGE


def test_bootstrap_counts_model_cache_files(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "inference.pdmodel").write_text("model", encoding="utf-8")
    (cache / "inference.pdiparams").write_text("params", encoding="utf-8")

    manager = OCRBootstrapManager(root_dir=tmp_path)

    assert manager.count_cache_files([cache]) == 2
