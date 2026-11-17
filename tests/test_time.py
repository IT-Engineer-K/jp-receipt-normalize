from __future__ import annotations

import datetime

from jpdoc_normalize.fields import find_times


def test_time_standard():
    """Verify standard colon format."""
    candidates = find_times("17:30 09:15:45")
    assert len(candidates) == 2
    assert candidates[0].value == datetime.time(17, 30)
    assert candidates[1].value == datetime.time(9, 15, 45)
    assert all(c.status in {"exact", "normalized"} for c in candidates)


def test_time_japanese():
    """Verify Japanese characters format."""
    candidates = find_times("17時30分 9時5分30秒")
    assert len(candidates) == 2
    assert candidates[0].value == datetime.time(17, 30)
    assert candidates[1].value == datetime.time(9, 5, 30)
    assert all(c.status == "normalized" for c in candidates)


def test_time_ocr_variations():
    """Verify semicolon variation and period ambiguity."""
    # Semicolon
    cands_semi = find_times("17;30")
    assert len(cands_semi) == 1
    assert cands_semi[0].value == datetime.time(17, 30)
    assert "semicolon_as_colon_ocr_variation" in cands_semi[0].reasons

    # Period (ambiguous with decimal)
    cands_dot = find_times("17.30")
    assert len(cands_dot) == 1
    assert cands_dot[0].value == datetime.time(17, 30)
    assert cands_dot[0].status == "ambiguous"


def test_time_out_of_range():
    """Verify out-of-range times (25:00, 12:60) are invalid."""
    candidates = find_times("25:00 12:60")
    assert len(candidates) == 2
    assert all(c.status == "invalid" for c in candidates)
    assert all(c.value is None for c in candidates)
