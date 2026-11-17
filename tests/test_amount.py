from __future__ import annotations

from decimal import Decimal

from jpdoc_normalize import normalize_text
from jpdoc_normalize.fields import find_amounts


def test_amount_receipt_example():
    """Verify example from requirement doc."""
    normalized = normalize_text("合 計　￥1,８４０", profile="receipt")
    amounts = find_amounts(normalized)
    assert len(amounts) == 1
    assert amounts[0].value == 1840
    assert amounts[0].status in {"exact", "normalized"}


def test_amount_formats():
    """Verify various valid currency and comma formats."""
    text = "¥1,840 ￥2,500 3,000円 \\500- 10,000,000円"
    candidates = find_amounts(text)
    values = [c.value for c in candidates]
    assert values == [1840, 2500, 3000, 500, 10000000]
    assert all(c.status in {"exact", "normalized"} for c in candidates)


def test_amount_discounts_and_negatives():
    """Verify discounts and negative signs (▲, △, -, parentheses)."""
    text = "値引 ▲50 割引 △100 マイナス -200 (300)"
    candidates = find_amounts(text)
    values = [c.value for c in candidates]
    assert values == [-50, -100, -200, -300]
    assert all("negative_amount" in c.reasons for c in candidates)


def test_amount_period_as_comma_ambiguity():
    """Verify period used instead of comma is flagged as ambiguous."""
    # 1.840 in Japanese receipts is often OCR misread for 1,840
    candidates = find_amounts("合計 ￥1.840")
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.value == 1840
    assert cand.status == "ambiguous"
    assert "period_used_as_thousands_separator_candidate" in cand.reasons


def test_amount_space_as_thousands_separator_ambiguity():
    """Verify space-grouped thousands (e.g. '合計 1 840円', '12 345円') are flagged as ambiguous."""
    cands1 = find_amounts("合計 1 840円")
    assert len(cands1) == 1
    assert cands1[0].value == 1840
    assert cands1[0].status == "ambiguous"
    assert "space_used_as_thousands_separator_candidate" in cands1[0].reasons
    assert any(e.rule == "strip_thousands_separator" for e in cands1[0].edits)

    cands2 = find_amounts("12 345円")
    assert len(cands2) == 1
    assert cands2[0].value == 12345
    assert cands2[0].status == "ambiguous"
    assert "space_used_as_thousands_separator_candidate" in cands2[0].reasons

    # Malformed space-separated digits do not produce partial confirmed candidates
    assert find_amounts("合計 1 2345円") == []
    assert find_amounts("1234 567円") == []


def test_amount_decimal_preserved():
    """Verify decimal amounts preserve Decimal value instead of rounding to int."""
    for raw, expected in [
        ("0.50円", Decimal("0.50")),
        ("$12.50", Decimal("12.50")),
        ("￥1,234.56", Decimal("1234.56")),
    ]:
        cands = find_amounts(raw)
        assert len(cands) == 1
        assert cands[0].value == expected
        assert isinstance(cands[0].value, Decimal)
        assert cands[0].status == "ambiguous"
        assert "decimal_amount" in cands[0].reasons


def test_amount_negative_test_plain_small_number():
    """Plain 1-2 digit number without currency symbol or context is excluded if required."""
    text = "ページ 12 個数 2"
    candidates = find_amounts(text, require_currency_or_context=True)
    assert len(candidates) == 0
