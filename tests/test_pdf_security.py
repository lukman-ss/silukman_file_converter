from pathlib import Path

import fitz

from app.core.converter import Converter
from app.utils.validator import validate_file_for_operation


def create_plain_pdf(path: Path) -> Path:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Security test PDF")
    document.save(path)
    document.close()
    return path


def create_encrypted_pdf(path: Path, password: str) -> Path:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Encrypted security test PDF")
    document.save(
        path,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw=password,
        user_pw=password,
        permissions=int(fitz.PDF_PERM_ACCESSIBILITY | fitz.PDF_PERM_PRINT),
    )
    document.close()
    return path


def test_protect_pdf_requires_user_password(tmp_path):
    source = create_plain_pdf(tmp_path / "plain.pdf")
    result = Converter().convert(str(source), "protect_pdf", str(tmp_path))

    assert result["success"] is False
    assert result["status"] == "failed"
    assert "Password PDF wajib diisi" in result["error"]


def test_protect_pdf_does_not_leak_password_in_filename(tmp_path):
    source = create_plain_pdf(tmp_path / "plain.pdf")
    password = "secret123"
    result = Converter().convert(
        str(source),
        "protect_pdf",
        str(tmp_path),
        operation_options={"password": password},
    )

    assert result["success"] is True
    output = Path(result["outputs"][0])
    assert output.name == "plain_protected.pdf"
    assert password not in output.name

    with fitz.open(output) as document:
        assert document.is_encrypted
        assert document.authenticate(password) > 0


def test_unlock_pdf_accepts_encrypted_container_and_password(tmp_path):
    password = "secret123"
    source = create_encrypted_pdf(tmp_path / "locked.pdf", password)
    validate_file_for_operation(str(source), "unlock_pdf")

    result = Converter().convert(
        str(source),
        "unlock_pdf",
        str(tmp_path),
        operation_options={"password": password},
    )

    assert result["success"] is True
    output = Path(result["outputs"][0])
    with fitz.open(output) as document:
        assert not document.is_encrypted


def test_unlock_pdf_rejects_wrong_password(tmp_path):
    source = create_encrypted_pdf(tmp_path / "locked.pdf", "secret123")
    result = Converter().convert(
        str(source),
        "unlock_pdf",
        str(tmp_path),
        operation_options={"password": "wrong123"},
    )

    assert result["success"] is False
    assert result["status"] == "failed"
    assert "Password PDF salah" in result["error"]
