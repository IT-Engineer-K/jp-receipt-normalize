from __future__ import annotations

import re

from jpdoc_normalize.models import Candidate, CandidateStatus, Edit, NormalizedText, SourceSpan
from jpdoc_normalize.utils import (
    build_norm_to_source_spans,
    ensure_normalized,
    make_extraction_edit,
    map_span_to_source,
)

# JAN code pattern: 8 or 13 digits (optionally with GS1 space grouping),
# rejecting adjacent punctuation/units and standalone 4+4 numbers without keyword.
JAN_PATTERN = re.compile(
    r"""
    (?P<prefix>(?:JAN|EAN|バーコード|コード)[ \t]*[:：]?[ \t]*)?
    (?<![\dA-Za-z\-−–—－.,/¥￥\\$€])
    (?P<digits>
        \d{13} |
        \d[ ]\d{6}[ ]\d{6} |
        \d{8} |
        \d{4}[ ]\d{4}
    )
    (?![\dA-Za-z\-−–—－.,/%％円年月日時分秒])
    """,
    re.VERBOSE | re.IGNORECASE,
)

JAN_REG_PREFIX_RE = re.compile(
    r"(?:[Tt][ \t\-−–—－]*|登録番号[ \t]*[:：]?[ \t]*[Tt]?[ \t\-−–—－]*)$"
)


def calculate_jan_check_digit(digits_without_cd: str) -> int:
    """
    Calculate Modulus 10 Weight 3 check digit for JAN-8 or JAN-13.
    Counting from rightmost digit of the payload:
    Weight 3 for odd positions, Weight 1 for even positions.
    Check digit = (10 - (Sum % 10)) % 10.
    """
    digits = [int(c) for c in digits_without_cd]
    weights = [3 if i % 2 == 0 else 1 for i in range(len(digits))]
    s = sum(d * w for d, w in zip(reversed(digits), weights, strict=True))
    return (10 - (s % 10)) % 10


def verify_jan_code(digits: str) -> bool:
    """Verify if JAN-8 or JAN-13 check digit is correct."""
    if len(digits) not in (8, 13) or not digits.isdigit():
        return False
    payload = digits[:-1]
    expected_cd = calculate_jan_check_digit(payload)
    actual_cd = int(digits[-1])
    return expected_cd == actual_cd


def find_jan_codes(
    text_or_normalized: str | SourceSpan | NormalizedText,
    *,
    require_keyword: bool = False,
) -> list[Candidate[str]]:
    """
    Extract JAN/EAN barcode candidates (8-digit or 13-digit) with check digit verification.

    Args:
        text_or_normalized: Input text, SourceSpan, or NormalizedText.
        require_keyword: If True, only extract candidates preceded by JAN/EAN/バーコード keyword.

    Returns:
        List of Candidate[str] where value is the clean digits string.
    """
    normalized = ensure_normalized(text_or_normalized, profile="receipt")
    text = normalized.text
    raw_spans = build_norm_to_source_spans(normalized)
    candidates: list[Candidate[str]] = []

    for match in JAN_PATTERN.finditer(text):
        raw_digits = match.group("digits")
        prefix = match.group("prefix") or ""

        if require_keyword and not prefix:
            continue

        clean_digits = re.sub(r"\D", "", raw_digits)
        if len(clean_digits) not in (8, 13):
            continue

        norm_start = match.start("digits")
        norm_end = match.end("digits")

        # Without keyword, two space-separated 4-digit numbers (e.g. "1000 2000") are not JAN-8
        if " " in raw_digits and not prefix and len(clean_digits) == 8:
            continue

        # Skip invoice registration numbers with a space/hyphen after T
        if not prefix and JAN_REG_PREFIX_RE.search(text[:norm_start]):
            continue

        extra_edits: list[Edit] = []
        for sep_match in re.finditer(r"\D", raw_digits):
            s_idx = norm_start + sep_match.start()
            e_idx = norm_start + sep_match.end()
            extra_edits.append(
                make_extraction_edit(
                    "strip_jan_separator", s_idx, e_idx, "", normalized, raw_spans
                )
            )

        source_span, edits = map_span_to_source(
            norm_start, norm_end, normalized, extra_edits=extra_edits, raw_spans=raw_spans
        )

        code_type = f"JAN-{len(clean_digits)}"
        reasons: list[str] = [code_type]

        if prefix:
            reasons.append("has_jan_keyword")

        is_valid = verify_jan_code(clean_digits)
        status: CandidateStatus
        if is_valid:
            reasons.append("valid_modulus10_weight3_checksum")
            if not edits and raw_digits == clean_digits:
                status = "exact"
            else:
                status = "normalized"
        else:
            reasons.append("invalid_checksum")
            status = "invalid"

        candidates.append(
            Candidate(
                value=clean_digits,
                source=source_span,
                edits=edits,
                status=status,
                reasons=tuple(reasons),
            )
        )

    return candidates
