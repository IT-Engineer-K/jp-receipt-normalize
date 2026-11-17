from __future__ import annotations

import datetime
import re
from collections.abc import Sequence

from jpdoc_normalize.models import Candidate, CandidateStatus, Edit, NormalizedText, SourceSpan
from jpdoc_normalize.utils import (
    build_norm_to_source_spans,
    ensure_normalized,
    make_extraction_edit,
    map_span_to_source,
)

# Japanese Era Start Dates
# 令和 (Reiwa): 2019-05-01 ~
# 平成 (Heisei): 1989-01-08 ~ 2019-04-30
# 昭和 (Showa): 1926-12-25 ~ 1989-01-07
# 大正 (Taisho): 1912-07-30 ~ 1926-12-24
ERA_OFFSETS = {
    "令和": 2018,
    "令": 2018,
    "R": 2018,
    "r": 2018,
    "平成": 1988,
    "平": 1988,
    "H": 1988,
    "h": 1988,
    "昭和": 1925,
    "昭": 1925,
    "S": 1925,
    "s": 1925,
}

# Valid date range of each era, keyed by year offset
ERA_RANGES: dict[int, tuple[datetime.date, datetime.date | None]] = {
    2018: (datetime.date(2019, 5, 1), None),  # 令和
    1988: (datetime.date(1989, 1, 8), datetime.date(2019, 4, 30)),  # 平成
    1925: (datetime.date(1926, 12, 25), datetime.date(1989, 1, 7)),  # 昭和
}

# Regex patterns
# 1. Western Full Date: 2026年11月15日, 2026/11/15, 2026-11-15, 2026.11.15
WESTERN_DATE_PATTERN = re.compile(
    r"""
    (?<![\dA-Za-z\-/._])
    (?P<year>[12]\d{3})
    (?:
        [ \t]*年[ \t]*(?P<month_jp>\d{1,2})[ \t]*月[ \t]*(?P<day_jp>\d{1,2})[ \t]*日
        |
        [ \t]*(?P<sep>[-/._])[ \t]*(?P<month_sep>\d{1,2})
        [ \t]*(?P=sep)[ \t]*(?P<day_sep>\d{1,2})(?:日)?
    )
    (?![\dA-Za-z\-/._])
    """,
    re.VERBOSE,
)

# 2. Japanese Wareki Date: 令和8年11月15日, 令和元年5月1日, R08.11.15, R8/11/15
WAREKI_DATE_PATTERN = re.compile(
    r"""
    (?<![A-Za-z\d\-−–—－/._])
    (?P<era>令和|令|平成|平|昭和|昭|[RrHhSs])
    [ \t]*
    (?P<year>元|\d{1,2})
    (?:
        [ \t]*年[ \t]*(?P<month_jp>\d{1,2})[ \t]*月[ \t]*(?P<day_jp>\d{1,2})[ \t]*日
        |
        [ \t]*(?P<sep>[-/._])[ \t]*(?P<month_sep>\d{1,2})
        [ \t]*(?P=sep)[ \t]*(?P<day_sep>\d{1,2})(?:日)?
    )
    (?![\dA-Za-z\-/._])
    """,
    re.VERBOSE,
)

# 3. Two-digit year date: 26/11/15, '26-11-15
TWO_DIGIT_DATE_PATTERN = re.compile(
    r"""
    (?<![\dA-Za-z\-/._])
    ['’]?
    (?P<year>\d{2})
    [ \t]*(?P<sep>[-/.])[ \t]*
    (?P<month>\d{1,2})
    [ \t]*(?P=sep)[ \t]*
    (?P<day>\d{1,2})
    (?![\dA-Za-z\-/._])
    """,
    re.VERBOSE,
)


def _check_real_date(year: int, month: int, day: int) -> tuple[datetime.date | None, list[str]]:
    """Validate calendar existence including leap years."""
    reasons: list[str] = []
    if month < 1 or month > 12:
        reasons.append(f"invalid_month_{month}")
        return None, reasons
    if day < 1 or day > 31:
        reasons.append(f"invalid_day_{day}")
        return None, reasons

    try:
        dt = datetime.date(year, month, day)
        return dt, reasons
    except ValueError as e:
        reasons.append(f"invalid_calendar_date: {e}")
        return None, reasons


def _build_date_tail_edits(
    match: re.Match[str],
    year_end: int,
    norm_end: int,
    month: int,
    day: int,
    normalized: NormalizedText,
    raw_spans: Sequence[tuple[int, int]],
) -> list[Edit]:
    """Record extraction edits for month/day separators, zero-padding, and Japanese date units."""
    text = normalized.text
    edits: list[Edit] = []

    if match.groupdict().get("month_jp"):
        m_start, m_end = match.start("month_jp"), match.end("month_jp")
        d_start, d_end = match.start("day_jp"), match.end("day_jp")
    elif "month_sep" in match.groupdict() and match.group("month_sep"):
        m_start, m_end = match.start("month_sep"), match.end("month_sep")
        d_start, d_end = match.start("day_sep"), match.end("day_sep")
    else:
        m_start, m_end = match.start("month"), match.end("month")
        d_start, d_end = match.start("day"), match.end("day")

    sep1 = text[year_end:m_start]
    if sep1 != "-":
        rule1 = "normalize_japanese_date_unit" if "年" in sep1 else "normalize_date_separator"
        edits.append(make_extraction_edit(rule1, year_end, m_start, "-", normalized, raw_spans))

    m_str = text[m_start:m_end]
    if m_str != f"{month:02d}":
        edits.append(
            make_extraction_edit(
                "pad_date_zero", m_start, m_end, f"{month:02d}", normalized, raw_spans
            )
        )

    sep2 = text[m_end:d_start]
    if sep2 != "-":
        rule2 = "normalize_japanese_date_unit" if "月" in sep2 else "normalize_date_separator"
        edits.append(make_extraction_edit(rule2, m_end, d_start, "-", normalized, raw_spans))

    d_str = text[d_start:d_end]
    if d_str != f"{day:02d}":
        edits.append(
            make_extraction_edit(
                "pad_date_zero", d_start, d_end, f"{day:02d}", normalized, raw_spans
            )
        )

    if d_end < norm_end:
        edits.append(
            make_extraction_edit(
                "normalize_japanese_date_unit", d_end, norm_end, "", normalized, raw_spans
            )
        )

    return edits


def find_dates(
    text_or_normalized: str | SourceSpan | NormalizedText,
    *,
    base_century: int = 2000,
) -> list[Candidate[datetime.date | None]]:
    """
    Extract calendar date candidates (Western and Japanese Wareki) from text.

    Args:
        text_or_normalized: Input text, SourceSpan, or NormalizedText.
        base_century: Century for two-digit years (default 2000).

    Returns:
        List of Candidate[datetime.date | None] objects.
    """
    normalized = ensure_normalized(text_or_normalized, profile="generic")
    text = normalized.text
    raw_spans = build_norm_to_source_spans(normalized)
    candidates: list[Candidate[datetime.date | None]] = []
    matched_ranges: set[tuple[int, int]] = set()

    # 1. Western dates (4-digit year)
    for match in WESTERN_DATE_PATTERN.finditer(text):
        norm_start = match.start()
        norm_end = match.end()
        matched_ranges.add((norm_start, norm_end))

        y_str = match.group("year")
        m_str = match.group("month_jp") or match.group("month_sep")
        d_str = match.group("day_jp") or match.group("day_sep")

        year = int(y_str)
        month = int(m_str)
        day = int(d_str)

        dt, reasons = _check_real_date(year, month, day)
        extra_edits = _build_date_tail_edits(
            match, match.end("year"), norm_end, month, day, normalized, raw_spans
        )
        source_span, edits = map_span_to_source(
            norm_start, norm_end, normalized, extra_edits=extra_edits, raw_spans=raw_spans
        )

        matched_raw = text[norm_start:norm_end]
        is_exact = not edits and (f"{year:04d}-{month:02d}-{day:02d}" == matched_raw)

        if dt is None:
            status: CandidateStatus = "invalid"
        elif is_exact:
            status = "exact"
        else:
            status = "normalized"

        reasons.append("western_calendar")
        candidates.append(
            Candidate(
                value=dt,
                source=source_span,
                edits=edits,
                status=status,
                reasons=tuple(reasons),
            )
        )

    # 2. Wareki dates
    for match in WAREKI_DATE_PATTERN.finditer(text):
        norm_start = match.start()
        norm_end = match.end()

        # Skip if overlapping with western date
        if any(norm_start < e and s < norm_end for s, e in matched_ranges):
            continue
        matched_ranges.add((norm_start, norm_end))

        era_str = match.group("era")
        y_str = match.group("year")
        m_str = match.group("month_jp") or match.group("month_sep")
        d_str = match.group("day_jp") or match.group("day_sep")

        era_offset = ERA_OFFSETS[era_str]
        month = int(m_str)
        day = int(d_str)

        extra_edits = []
        if y_str == "元":
            year = era_offset + 1
            dt, reasons = _check_real_date(year, month, day)
            extra_edits.append(
                make_extraction_edit(
                    "convert_wareki_year",
                    match.start("era"),
                    match.end("year"),
                    f"{year:04d}",
                    normalized,
                    raw_spans,
                )
            )
        else:
            era_year = int(y_str)
            if era_year <= 0:
                dt = None
                reasons = ["invalid_era_year_0"]
            else:
                year = era_offset + era_year
                dt, reasons = _check_real_date(year, month, day)
                extra_edits.append(
                    make_extraction_edit(
                        "convert_wareki_year",
                        match.start("era"),
                        match.end("year"),
                        f"{year:04d}",
                        normalized,
                        raw_spans,
                    )
                )

        extra_edits.extend(
            _build_date_tail_edits(
                match, match.end("year"), norm_end, month, day, normalized, raw_spans
            )
        )
        source_span, edits = map_span_to_source(
            norm_start, norm_end, normalized, extra_edits=extra_edits, raw_spans=raw_spans
        )

        reasons.append(f"wareki_calendar_{era_str}")

        if dt is None:
            status = "invalid"
        else:
            # Wareki conversion is always normalized
            status = "normalized"
            era_start, era_end = ERA_RANGES[era_offset]
            if dt < era_start or (era_end is not None and dt > era_end):
                # e.g. 平成31年5月1日 / 令和元年4月1日: does not exist in that era
                status = "ambiguous"
                reasons.append("outside_era_range")

        candidates.append(
            Candidate(
                value=dt,
                source=source_span,
                edits=edits,
                status=status,
                reasons=tuple(reasons),
            )
        )

    # 3. Two-digit year dates (e.g. 26/11/15)
    for match in TWO_DIGIT_DATE_PATTERN.finditer(text):
        norm_start = match.start()
        norm_end = match.end()

        if any(norm_start < e and s < norm_end for s, e in matched_ranges):
            continue
        matched_ranges.add((norm_start, norm_end))

        y_str = match.group("year")
        m_str = match.group("month")
        d_str = match.group("day")

        year = base_century + int(y_str)
        month = int(m_str)
        day = int(d_str)

        dt, reasons = _check_real_date(year, month, day)
        extra_edits = [
            make_extraction_edit(
                "expand_two_digit_year",
                norm_start,
                match.end("year"),
                f"{year:04d}",
                normalized,
                raw_spans,
            )
        ]
        extra_edits.extend(
            _build_date_tail_edits(
                match, match.end("year"), norm_end, month, day, normalized, raw_spans
            )
        )
        source_span, edits = map_span_to_source(
            norm_start, norm_end, normalized, extra_edits=extra_edits, raw_spans=raw_spans
        )

        reasons.append("two_digit_year")
        # Two-digit year is inherently ambiguous
        if dt is None:
            status = "invalid"
        else:
            status = "ambiguous"

        candidates.append(
            Candidate(
                value=dt,
                source=source_span,
                edits=edits,
                status=status,
                reasons=tuple(reasons),
            )
        )

    return candidates
