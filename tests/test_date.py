from __future__ import annotations

import datetime

from jpdoc_normalize.fields import find_dates


def test_date_western():
    """Verify 4-digit western dates."""
    candidates = find_dates("2026年11月15日 2026/04/01 2026-12-31")
    assert len(candidates) == 3
    assert candidates[0].value == datetime.date(2026, 11, 15)
    assert candidates[1].value == datetime.date(2026, 4, 1)
    assert candidates[2].value == datetime.date(2026, 12, 31)
    assert all(c.status in {"exact", "normalized"} for c in candidates)


def test_date_wareki():
    """Verify Japanese era dates (Reiwa, Heisei, Showa, Gannen)."""
    text = "令和8年11月15日 令和元年5月1日 R06.02.29 平成31年4月30日"
    candidates = find_dates(text)
    assert len(candidates) == 4
    assert candidates[0].value == datetime.date(2026, 11, 15)
    assert candidates[1].value == datetime.date(2019, 5, 1)
    assert candidates[2].value == datetime.date(2024, 2, 29)  # Reiwa 6 leap year
    assert candidates[3].value == datetime.date(2019, 4, 30)  # Heisei 31
    assert all(c.status == "normalized" for c in candidates)


def test_date_leap_year_validation():
    """Verify leap year real-date validation."""
    # 2024 is leap year: Feb 29 valid
    cands_valid = find_dates("2024-02-29")
    assert len(cands_valid) == 1
    assert cands_valid[0].status in {"exact", "normalized"}
    assert cands_valid[0].value == datetime.date(2024, 2, 29)

    # 2023 is not leap year: Feb 29 is invalid
    cands_invalid = find_dates("2023-02-29")
    assert len(cands_invalid) == 1
    assert cands_invalid[0].status == "invalid"
    assert cands_invalid[0].value is None


def test_date_nonexistent_calendar_dates():
    """Verify nonexistent dates like Feb 30 or Month 13 are flagged invalid."""
    cands = find_dates("2026-02-30 2026-13-01")
    assert len(cands) == 2
    assert all(c.status == "invalid" for c in cands)
    assert all(c.value is None for c in cands)


def test_date_two_digit_year():
    """Verify 2-digit year is treated as ambiguous."""
    cands = find_dates("26/11/15")
    assert len(cands) == 1
    assert cands[0].value == datetime.date(2026, 11, 15)
    assert cands[0].status == "ambiguous"
    assert "two_digit_year" in cands[0].reasons
