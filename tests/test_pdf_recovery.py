from pathlib import Path

import fitz

from app.core.converter import Converter


def create_multi_page_pdf(path: Path) -> Path:
    document = fitz.open()
    for index in range(2):
        page = document.new_page()
        page.insert_text((72, 72), f"Recovery test page {index + 1}")
    document.save(path)
    document.close()
    return path


def assert_repair_restores_original(tmp_path: Path, operation: str) -> None:
    source = create_multi_page_pdf(tmp_path / f"{operation}.pdf")
    original_bytes = source.read_bytes()
    converter = Converter()

    result = converter.convert(str(source), operation, str(tmp_path))
    assert result["success"] is True

    output = Path(result["outputs"][0])
    assert output.read_bytes() != original_bytes

    repaired = converter.convert(str(output), "repair_pdf", str(tmp_path / "repaired"))
    assert repaired["success"] is True
    assert Path(repaired["outputs"][0]).read_bytes() == original_bytes


def test_pdf_repair_restores_original_after_rotate(tmp_path):
    assert_repair_restores_original(tmp_path, "rotate_pdf")


def test_pdf_repair_restores_original_after_watermark(tmp_path):
    assert_repair_restores_original(tmp_path, "watermark")


def test_pdf_repair_restores_original_after_crop(tmp_path):
    assert_repair_restores_original(tmp_path, "crop_pdf")


def test_split_pdf_pages_can_recover_full_original(tmp_path):
    source = create_multi_page_pdf(tmp_path / "split_source.pdf")
    original_bytes = source.read_bytes()
    converter = Converter()

    result = converter.convert(str(source), "split_pdf", str(tmp_path))
    assert result["success"] is True

    for output_name in result["outputs"]:
        repaired = converter.convert(output_name, "repair_pdf", str(tmp_path / "repaired"))
        assert repaired["success"] is True
        assert Path(repaired["outputs"][0]).read_bytes() == original_bytes


def test_pdf_to_word_to_pdf_restores_original_pdf(tmp_path):
    source = create_multi_page_pdf(tmp_path / "source.pdf")
    original_bytes = source.read_bytes()
    converter = Converter()

    docx_result = converter.convert(str(source), "pdf_to_word", str(tmp_path / "docx"))
    assert docx_result["success"] is True

    pdf_result = converter.convert(docx_result["outputs"][0], "word_to_pdf", str(tmp_path / "back_to_pdf"))
    assert pdf_result["success"] is True
    assert Path(pdf_result["outputs"][0]).read_bytes() == original_bytes


def test_pdf_to_excel_to_pdf_restores_original_pdf(tmp_path):
    source = create_multi_page_pdf(tmp_path / "source.pdf")
    original_bytes = source.read_bytes()
    converter = Converter()

    xlsx_result = converter.convert(str(source), "pdf_to_excel", str(tmp_path / "xlsx"))
    assert xlsx_result["success"] is True

    pdf_result = converter.convert(xlsx_result["outputs"][0], "excel_to_pdf", str(tmp_path / "back_to_pdf"))
    assert pdf_result["success"] is True
    assert Path(pdf_result["outputs"][0]).read_bytes() == original_bytes


def test_pdf_to_powerpoint_to_pdf_restores_original_pdf(tmp_path):
    source = create_multi_page_pdf(tmp_path / "source.pdf")
    original_bytes = source.read_bytes()
    converter = Converter()

    pptx_result = converter.convert(str(source), "pdf_to_powerpoint", str(tmp_path / "pptx"))
    assert pptx_result["success"] is True

    pdf_result = converter.convert(pptx_result["outputs"][0], "powerpoint_to_pdf", str(tmp_path / "back_to_pdf"))
    assert pdf_result["success"] is True
    assert Path(pdf_result["outputs"][0]).read_bytes() == original_bytes
