from __future__ import annotations

from jpdoc_normalize.fields import find_jan_codes
from jpdoc_normalize.fields.jan import calculate_jan_check_digit, verify_jan_code


def test_jan_checksum_calculation():
    """Verify standard JAN-13 and JAN-8 test vectors."""
    # JAN-13: 4901234567894 (payload 490123456789 -> CD 4)
    assert calculate_jan_check_digit("490123456789") == 4
    assert verify_jan_code("4901234567894") is True

    # JAN-8: 49123456 (payload 4912345 -> CD 6)
    assert calculate_jan_check_digit("4912345") == 6
    assert verify_jan_code("49123456") is True

    # Bad checksum
    assert verify_jan_code("4901234567899") is False


def test_find_jan_codes_valid_and_invalid():
    """Verify extraction and validation of JAN barcodes."""
    text = "JAN: 4901234567894 不正: 4901234567899 短縮: 49123456"
    candidates = find_jan_codes(text)
    assert len(candidates) == 3

    # Candidate 1: valid 13-digit
    assert candidates[0].value == "4901234567894"
    assert candidates[0].status == "exact"
    assert "valid_modulus10_weight3_checksum" in candidates[0].reasons

    # Candidate 2: invalid checksum
    assert candidates[1].value == "4901234567899"
    assert candidates[1].status == "invalid"
    assert "invalid_checksum" in candidates[1].reasons

    # Candidate 3: valid 8-digit
    assert candidates[2].value == "49123456"
    assert candidates[2].status == "exact"
