from app.core.ocr_engine import clean_currency_ocr_noise, normalize_indonesian_currency


def test_normalize_indonesian_currency_preserves_common_formats():
    cases = {
        "Rp 666.000": "Rp 666.000",
        "Rp666.000": "Rp 666.000",
        "Rp 666,000": "Rp 666.000",
        "Rp 600.000": "Rp 600.000",
        "Rp 66.000": "Rp 66.000",
        "R Rp 666.000": "Rp 666.000",
        "RP 666.000": "Rp 666.000",
        "Total Rp 1.250.000": "Total Rp 1.250.000",
        "Subtotal Rp 950.000": "Subtotal Rp 950.000",
        "Rp 666.0": "Rp 666.000",
    }
    for raw, expected in cases.items():
        assert normalize_indonesian_currency(raw) == expected


def test_normalize_indonesian_currency_does_not_change_non_currency_numbers():
    assert normalize_indonesian_currency("150000") == "150000"
    assert normalize_indonesian_currency("85000") == "85000"


def test_clean_currency_ocr_noise_handles_requested_cases():
    assert clean_currency_ocr_noise("R Rp 666.000") == "Rp 666.000"
    assert clean_currency_ocr_noise("RP 666.000") == "Rp 666.000"
    assert clean_currency_ocr_noise("Rp666.000") == "Rp 666.000"
    assert clean_currency_ocr_noise("Rp 666,000") == "Rp 666.000"
