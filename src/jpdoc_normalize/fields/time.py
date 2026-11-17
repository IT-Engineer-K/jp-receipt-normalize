from __future__ import annotations

import datetime
import re

from jpdoc_normalize.models import Candidate, CandidateStatus, Edit, NormalizedText, SourceSpan
from jpdoc_normalize.utils import (
    build_norm_to_source_spans,
    ensure_normalized,
    make_extraction_edit,
    map_span_to_source,
)

# Patterns for time
# 1. Standard colon / semicolon / dot: 17:30, 17:30:15, 17;30, 17.30
COLON_TIME_PATTERN = re.compile(
    r"""
    (?<![\d,:;./\-¥￥\\$€])
    (?P<hour>\d{1,2})
    [ \t]*[:;.][ \t]*
    (?P<minute>\d{2})
    (?:[ \t]*[:;.][ \t]*(?P<second>\d{2}))?
    (?![\d,:;./\-%％円年月日時分秒])
    """,
    re.VERBOSE,
)

TIME_PERIOD_UNIT_PATTERN = re.compile(
    r"[ \t]*(?:[%％円]|(?:ml|mL|kg|cm|mm|L|g)(?![A-Za-z])|[個点枚本件倍])"
)

# 2. Japanese time: 17時30分, 17時30分15秒
JAPANESE_TIME_PATTERN = re.compile(
    r"""
    (?<!\d)
    (?P<hour>\d{1,2})
    [ \t]*時[ \t]*
    (?P<minute>\d{1,2})
    [ \t]*分
    (?:[ \t]*(?P<second>\d{1,2})[ \t]*秒)?
    """,
    re.VERBOSE,
)


def find_times(
    text_or_normalized: str | SourceSpan | NormalizedText,
) -> list[Candidate[datetime.time | None]]:
    """
    Extract time candidates from text, handling OCR variations.

    Args:
        text_or_normalized: Input text, SourceSpan, or NormalizedText.

    Returns:
        List of Candidate[datetime.time | None] objects.
    """
    normalized = ensure_normalized(text_or_normalized, profile="generic")
    text = normalized.text
    raw_spans = build_norm_to_source_spans(normalized)
    candidates: list[Candidate[datetime.time | None]] = []
    matched_ranges: set[tuple[int, int]] = set()

    # 1. Japanese format (17時30分)
    for match in JAPANESE_TIME_PATTERN.finditer(text):
        norm_start = match.start()
        norm_end = match.end()
        matched_ranges.add((norm_start, norm_end))

        h_str = match.group("hour")
        m_str = match.group("minute")
        s_str = match.group("second")

        hour = int(h_str)
        minute = int(m_str)
        second = int(s_str) if s_str else 0

        extra_edits: list[Edit] = []
        if h_str != f"{hour:02d}":
            extra_edits.append(
                make_extraction_edit(
                    "pad_time_zero",
                    match.start("hour"),
                    match.end("hour"),
                    f"{hour:02d}",
                    normalized,
                    raw_spans,
                )
            )
        extra_edits.append(
            make_extraction_edit(
                "normalize_japanese_time_unit",
                match.end("hour"),
                match.start("minute"),
                ":",
                normalized,
                raw_spans,
            )
        )
        if m_str != f"{minute:02d}":
            extra_edits.append(
                make_extraction_edit(
                    "pad_time_zero",
                    match.start("minute"),
                    match.end("minute"),
                    f"{minute:02d}",
                    normalized,
                    raw_spans,
                )
            )
        if s_str is not None:
            extra_edits.append(
                make_extraction_edit(
                    "normalize_japanese_time_unit",
                    match.end("minute"),
                    match.start("second"),
                    ":",
                    normalized,
                    raw_spans,
                )
            )
            if s_str != f"{second:02d}":
                extra_edits.append(
                    make_extraction_edit(
                        "pad_time_zero",
                        match.start("second"),
                        match.end("second"),
                        f"{second:02d}",
                        normalized,
                        raw_spans,
                    )
                )
            extra_edits.append(
                make_extraction_edit(
                    "normalize_japanese_time_unit",
                    match.end("second"),
                    norm_end,
                    "",
                    normalized,
                    raw_spans,
                )
            )
        else:
            extra_edits.append(
                make_extraction_edit(
                    "normalize_japanese_time_unit",
                    match.end("minute"),
                    norm_end,
                    "",
                    normalized,
                    raw_spans,
                )
            )

        reasons: list[str] = ["japanese_time_format"]
        source_span, edits = map_span_to_source(
            norm_start, norm_end, normalized, extra_edits=extra_edits, raw_spans=raw_spans
        )

        if 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59:
            t_val = datetime.time(hour, minute, second)
            status: CandidateStatus = "normalized"
        else:
            t_val = None
            status = "invalid"
            reasons.append(f"time_out_of_range_{hour}_{minute}_{second}")

        candidates.append(
            Candidate(
                value=t_val,
                source=source_span,
                edits=edits,
                status=status,
                reasons=tuple(reasons),
            )
        )

    # 2. Colon / OCR separator format (17:30, 17;30, 17.30)
    for match in COLON_TIME_PATTERN.finditer(text):
        norm_start = match.start()
        norm_end = match.end()

        if any(norm_start < e and s < norm_end for s, e in matched_ranges):
            continue

        raw_match = text[norm_start:norm_end]
        h_str = match.group("hour")
        m_str = match.group("minute")
        s_str = match.group("second")

        # Period separator is ambiguous with decimal numbers (e.g. 12.50)
        is_period_sep = "." in raw_match

        if is_period_sep:
            # Period separator with seconds (e.g. 12.34.56) is not treated as time
            if s_str is not None:
                continue
            # Skip currency decimals such as ¥12.50 or $ 12.50
            before_text = text[:norm_start].rstrip(" \t")
            if before_text and before_text[-1] in "¥￥\\$€":
                continue
            # Skip period decimals followed by units (e.g. 10.00%, 10.00 円, 1.50 kg)
            if TIME_PERIOD_UNIT_PATTERN.match(text[norm_end:]):
                continue
            # Skip parts of dotted/slashed/hyphenated dates or multi-part numbers
            before = text[max(0, norm_start - 2) : norm_start]
            after = text[norm_end : norm_end + 2]
            if (len(before) == 2 and before[1] in "./-" and before[0].isdigit()) or (
                len(after) == 2 and after[0] in "./-" and after[1].isdigit()
            ):
                continue

        matched_ranges.add((norm_start, norm_end))

        hour = int(h_str)
        minute = int(m_str)
        second = int(s_str) if s_str else 0

        reasons = []
        if ";" in raw_match:
            reasons.append("semicolon_as_colon_ocr_variation")
        if is_period_sep:
            reasons.append("period_as_colon_ambiguous_with_decimal")

        extra_edits = []
        if h_str != f"{hour:02d}":
            extra_edits.append(
                make_extraction_edit(
                    "pad_time_zero",
                    match.start("hour"),
                    match.end("hour"),
                    f"{hour:02d}",
                    normalized,
                    raw_spans,
                )
            )
        sep1 = text[match.end("hour") : match.start("minute")]
        if sep1 != ":":
            extra_edits.append(
                make_extraction_edit(
                    "normalize_time_separator",
                    match.end("hour"),
                    match.start("minute"),
                    ":",
                    normalized,
                    raw_spans,
                )
            )
        if s_str is not None:
            sep2 = text[match.end("minute") : match.start("second")]
            if sep2 != ":":
                extra_edits.append(
                    make_extraction_edit(
                        "normalize_time_separator",
                        match.end("minute"),
                        match.start("second"),
                        ":",
                        normalized,
                        raw_spans,
                    )
                )

        source_span, edits = map_span_to_source(
            norm_start, norm_end, normalized, extra_edits=extra_edits, raw_spans=raw_spans
        )

        expected_exact = (
            f"{hour:02d}:{minute:02d}:{second:02d}"
            if s_str is not None
            else f"{hour:02d}:{minute:02d}"
        )

        if 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59:
            t_val = datetime.time(hour, minute, second)
            if is_period_sep:
                status = "ambiguous"
            elif not edits and raw_match == expected_exact:
                status = "exact"
            else:
                status = "normalized"
        else:
            t_val = None
            status = "invalid"
            reasons.append(f"time_out_of_range_{hour}_{minute}_{second}")

        candidates.append(
            Candidate(
                value=t_val,
                source=source_span,
                edits=edits,
                status=status,
                reasons=tuple(reasons),
            )
        )

    return candidates
