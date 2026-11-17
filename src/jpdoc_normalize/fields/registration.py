from __future__ import annotations

import re

from jpdoc_normalize.models import Candidate, CandidateStatus, Edit, NormalizedText, SourceSpan
from jpdoc_normalize.utils import (
    build_norm_to_source_spans,
    ensure_normalized,
    make_extraction_edit,
    map_span_to_source,
)

# Invoice Registration Number Pattern: T followed by 13 digits, optional hyphens/spaces
# May be preceded by "登録番号" or "No."
INVOICE_PATTERN = re.compile(
    r"""
    (?P<prefix>(?:登録番号|登録No\.?|インボイス登録番号)[ \t]*[:：]?[ \t]*)?
    (?P<t>[TtＴｔ])
    [ \t\-−–—－]?
    (?P<digits>\d(?:[ \t\-−–—－]?\d){12})
    (?![\dA-Za-z\-−–—－])
    """,
    re.VERBOSE,
)


def calculate_corporate_number_check_digit(base_12_digits: str) -> int:
    """
    Calculate the check digit for a 12-digit Japanese corporate basic number
    according to the National Tax Agency (NTA) specification:
    Sum digits from least significant to most significant with alternating weights 1 and 2.
    Remainder R = Sum % 9. Check digit = 0 if R == 0 else 9 - R.
    """
    if len(base_12_digits) != 12 or not base_12_digits.isdigit():
        raise ValueError(f"Base number must be exactly 12 digits, got '{base_12_digits}'")

    digits = [int(c) for c in base_12_digits]
    # Weight 1 for odd positions (from right, 0-indexed: 0, 2, 4...) and 2 for even (1, 3, 5...)
    weights = [1 if i % 2 == 0 else 2 for i in range(12)]
    s = sum(d * w for d, w in zip(reversed(digits), weights, strict=True))
    rem = s % 9
    return 9 - rem


def verify_corporate_number(thirteen_digits: str) -> bool:
    """Verify if 13-digit number matches NTA corporate number check digit."""
    if len(thirteen_digits) != 13 or not thirteen_digits.isdigit():
        return False
    check_digit = int(thirteen_digits[0])
    base_12 = thirteen_digits[1:]
    expected_cd = calculate_corporate_number_check_digit(base_12)
    return check_digit == expected_cd


def find_invoice_registration_numbers(
    text_or_normalized: str | SourceSpan | NormalizedText,
    *,
    strict_corporate_check: bool = False,
) -> list[Candidate[str]]:
    """
    Extract Qualified Invoice Issuer registration numbers (T + 13 digits) from text.

    Args:
        text_or_normalized: Input text, SourceSpan, or NormalizedText.
        strict_corporate_check: If True, mark numbers with invalid corporate check digits
            as 'invalid'. If False (default), allow them as valid candidates (since sole
            proprietors have registration numbers without corporate check digit alignment).

    Returns:
        List of Candidate[str] where value is formatted as 'Txxxxxxxxxxxxx'.
    """
    normalized = ensure_normalized(text_or_normalized, profile="invoice")
    text = normalized.text
    raw_spans = build_norm_to_source_spans(normalized)
    candidates: list[Candidate[str]] = []

    for match in INVOICE_PATTERN.finditer(text):
        prefix = match.group("prefix") or ""
        raw_digits = match.group("digits")

        clean_digits = re.sub(r"\D", "", raw_digits)
        if len(clean_digits) != 13:
            continue

        value = f"T{clean_digits}"
        norm_start = match.start("t")
        norm_end = match.end("digits")

        # Without prefix, do not extract T+13digits embedded in alphanumeric/hyphenated model codes
        if not prefix and norm_start > 0:
            prev_char = text[norm_start - 1]
            if (prev_char.isascii() and prev_char.isalnum()) or prev_char in "-−–—－":
                continue

        extra_edits: list[Edit] = []
        t_char = match.group("t")
        if t_char != "T":
            extra_edits.append(
                make_extraction_edit(
                    "uppercase_registration_prefix",
                    match.start("t"),
                    match.end("t"),
                    "T",
                    normalized,
                    raw_spans,
                )
            )
        for sep_match in re.finditer(r"\D", text[match.end("t") : norm_end]):
            s_idx = match.end("t") + sep_match.start()
            e_idx = match.end("t") + sep_match.end()
            extra_edits.append(
                make_extraction_edit(
                    "strip_registration_separator", s_idx, e_idx, "", normalized, raw_spans
                )
            )

        source_span, edits = map_span_to_source(
            norm_start, norm_end, normalized, extra_edits=extra_edits, raw_spans=raw_spans
        )

        reasons: list[str] = []
        if prefix:
            reasons.append("has_registration_keyword")

        # Verify NTA Corporate Number Checksum
        is_corporate_valid = verify_corporate_number(clean_digits)
        if is_corporate_valid:
            reasons.append("valid_corporate_number_checksum")
        else:
            reasons.append("unmatched_corporate_checksum_possibly_sole_proprietor")

        status: CandidateStatus
        if strict_corporate_check and not is_corporate_valid:
            status = "invalid"
        else:
            raw_matched = text[norm_start:norm_end]
            if not edits and raw_matched == value:
                status = "exact"
            else:
                status = "normalized"

        candidates.append(
            Candidate(
                value=value,
                source=source_span,
                edits=edits,
                status=status,
                reasons=tuple(reasons),
            )
        )

    return candidates
