from __future__ import annotations

import re

from jpdoc_normalize.models import Candidate, CandidateStatus, Edit, NormalizedText, SourceSpan
from jpdoc_normalize.utils import (
    build_norm_to_source_spans,
    ensure_normalized,
    make_extraction_edit,
    map_span_to_source,
)

# Japanese Phone Number Pattern
# Matches phone numbers with optional parentheses, hyphens, and spaces
# Starts with 0 and total digits 10 or 11
PHONE_PATTERN = re.compile(
    r"""
    (?P<prefix>(?:TEL|電話|FAX|フリーダイヤル|ダイヤル|お問合(?:せ)?)[ \t]*[:：]?[ \t]*)?
    (?<![\dA-Za-z\-−–—－.,/¥￥\\$€])
    (?P<number>
        \(0\d{1,4}\)[ \t\-−–—－]?\d{1,4}[ \t\-−–—－]?\d{3,4} |
        0\d{1,4}[ \t]*\(\d{1,4}\)[ \t\-−–—－]?\d{3,4} |
        0\d{1,4}(?P<hsep>[-−–—－])\d{1,4}(?P=hsep)\d{3,4} |
        0\d{1,4}[ \t]+\d{1,4}[ \t]+\d{3,4} |
        0\d{9,10}
    )
    (?![\dA-Za-z\-−–—－.,/%％円年月日時分秒])
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _classify_phone_number(digits: str) -> tuple[bool, str]:
    """Validate digits and classify Japanese phone number type."""
    if not digits.startswith("0"):
        return False, "does_not_start_with_0"
    if digits.startswith("00"):
        return False, "invalid_prefix_00"

    total_len = len(digits)

    # 11 digits: only mobile, IP phone, data communication and 0800 toll-free exist
    if total_len == 11:
        if digits.startswith("0800"):
            return True, "toll_free"
        if digits.startswith(("070", "080", "090")):
            return True, "mobile"
        if digits.startswith("050"):
            return True, "ip_phone"
        if digits.startswith("020"):
            return True, "data_communication"
        return False, "invalid_prefix_for_11_digits"

    # 10 digits
    if total_len == 10:
        if digits.startswith("0120"):
            return True, "toll_free"
        if digits.startswith("0570"):
            return True, "navi_dial"
        if digits.startswith("0990"):
            return True, "special_service"
        # "0X0" prefixes (020, 050, 070, 080, 090, 0800, ...) are non-geographic
        # and never used for 10-digit landlines
        if digits[2] == "0":
            return False, "invalid_prefix_for_10_digits"
        return True, "landline"

    return False, f"invalid_length_{total_len}"


def find_phone_numbers(
    text_or_normalized: str | SourceSpan | NormalizedText,
    *,
    require_keyword: bool = False,
) -> list[Candidate[str]]:
    """
    Extract Japanese phone number candidates from text.

    Args:
        text_or_normalized: Input text, SourceSpan, or NormalizedText.
        require_keyword: If True, only extract when preceded by TEL/FAX/電話 keyword.

    Returns:
        List of Candidate[str] where value is the clean digits string.
    """
    normalized = ensure_normalized(text_or_normalized, profile="generic")
    text = normalized.text
    raw_spans = build_norm_to_source_spans(normalized)
    candidates: list[Candidate[str]] = []

    for match in PHONE_PATTERN.finditer(text):
        raw_num = match.group("number")
        prefix = match.group("prefix") or ""

        if require_keyword and not prefix:
            continue

        # Extract only digits
        digits = re.sub(r"\D", "", raw_num)
        is_valid, phone_type = _classify_phone_number(digits)

        # Skip numbers that clearly aren't phone numbers (e.g. less than 10 digits)
        if not is_valid and len(digits) not in (10, 11):
            continue

        norm_start = match.start("number")
        norm_end = match.end("number")

        extra_edits: list[Edit] = []
        for sep_match in re.finditer(r"\D", raw_num):
            s_idx = norm_start + sep_match.start()
            e_idx = norm_start + sep_match.end()
            extra_edits.append(
                make_extraction_edit(
                    "strip_phone_separator", s_idx, e_idx, "", normalized, raw_spans
                )
            )

        source_span, edits = map_span_to_source(
            norm_start, norm_end, normalized, extra_edits=extra_edits, raw_spans=raw_spans
        )
        reasons: list[str] = [f"phone_type_{phone_type}"]

        if prefix:
            reasons.append("has_phone_keyword")

        if not is_valid:
            status: CandidateStatus = "invalid"
            reasons.append("invalid_japanese_phone_number_format")
        else:
            if not edits and raw_num == digits:
                status = "exact"
            elif any(c in raw_num for c in " \t-()"):
                status = "normalized"
                reasons.append("stripped_separators")
            else:
                status = "normalized"

        candidates.append(
            Candidate(
                value=digits,
                source=source_span,
                edits=edits,
                status=status,
                reasons=tuple(reasons),
            )
        )

    return candidates
