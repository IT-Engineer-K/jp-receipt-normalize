from __future__ import annotations

from jpdoc_normalize.fields import find_phone_numbers


def test_phone_landline_and_mobile():
    """Verify Tokyo 03, Osaka 06, Mobile 090, 080, 070."""
    text = "東京 03-1234-5678 大阪 (06) 6123-4567 携帯 090 1234 5678"
    candidates = find_phone_numbers(text)
    values = [c.value for c in candidates]
    assert values == ["0312345678", "0661234567", "09012345678"]
    assert all(c.status in {"exact", "normalized"} for c in candidates)


def test_phone_toll_free_and_ip():
    """Verify 0120 toll-free and 050 IP phone."""
    text = "フリーダイヤル 0120-123-456 IP電話 050-9876-5432"
    candidates = find_phone_numbers(text)
    values = [c.value for c in candidates]
    assert values == ["0120123456", "05098765432"]
    assert any("phone_type_toll_free" in c.reasons for c in candidates)
    assert any("phone_type_ip_phone" in c.reasons for c in candidates)


def test_phone_negative_test_invalid_length():
    """Numbers that do not start with 0 or have wrong length should be rejected."""
    # 7 digits (not full phone number)
    candidates = find_phone_numbers("123-4567")
    assert len(candidates) == 0
