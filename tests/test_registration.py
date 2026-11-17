from __future__ import annotations

from jpdoc_normalize.fields import find_invoice_registration_numbers
from jpdoc_normalize.fields.registration import verify_corporate_number


def test_registration_example_from_spec():
    """Verify example from requirement doc."""
    registrations = find_invoice_registration_numbers("登録番号 T７１２３４５６７８９０１２")
    assert len(registrations) == 1
    cand = registrations[0]
    assert cand.value == "T7123456789012"
    assert cand.status in {"exact", "normalized"}
    assert "has_registration_keyword" in cand.reasons
    assert "valid_corporate_number_checksum" in cand.reasons


def test_corporate_number_checksum_known_companies():
    """Verify synthetic corporate numbers match NTA formula."""
    # Synthetic test vector 1: 7100000000000
    assert verify_corporate_number("7100000000000") is True
    # Synthetic test vector 2: 8000000000001
    assert verify_corporate_number("8000000000001") is True
    # Synthetic test vector 3: 7123456789012
    assert verify_corporate_number("7123456789012") is True

    # Invalid check digit
    assert verify_corporate_number("9100000000000") is False


def test_registration_strict_mode():
    """Verify strict_corporate_check flags invalid checksum as invalid."""
    # Valid corporate number
    cands_valid = find_invoice_registration_numbers("T7100000000000", strict_corporate_check=True)
    assert len(cands_valid) == 1
    assert cands_valid[0].status == "exact"

    # Invalid check digit (7 -> 9)
    cands_invalid = find_invoice_registration_numbers("T9100000000000", strict_corporate_check=True)
    assert len(cands_invalid) == 1
    assert cands_invalid[0].status == "invalid"
