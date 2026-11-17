from __future__ import annotations

import re
from decimal import Decimal

from jpdoc_normalize.models import Candidate, CandidateStatus, Edit, NormalizedText, SourceSpan
from jpdoc_normalize.utils import (
    build_norm_to_source_spans,
    ensure_normalized,
    make_extraction_edit,
    map_span_to_source,
)

PERIOD_THOUSANDS_PATTERN = re.compile(r"[1-9]\d{0,2}(?:\.\d{3})+")
SPACE_THOUSANDS_PATTERN = re.compile(r"[1-9]\d{0,2}(?:[ \t]+\d{3})+")

NON_AMOUNT_UNIT_PATTERN = re.compile(
    r"(?:[%％年月日時分秒]|(?:ml|mL|kg|cm|mm|L|g)(?![A-Za-z])|[個点枚本件番号])"
)

PRECEDING_BARE_DIGITS_RE = re.compile(r"(?<![\d,./;:\-−–—－])\d+[ \t]+$")
FOLLOWING_BARE_DIGITS_RE = re.compile(r"[ \t]+\d+(?![\d,]*,)")

# Regex patterns for amounts
# Matches currency symbols, negative signs, digits with separators, and optional "円"
AMOUNT_PATTERN = re.compile(
    r"""
    (?P<prefix>
        (?:値引|割引|内税|外税|消費税|税込|税抜|小計|合計|合[ \t]*計
        |お預り|お釣り?|御買上|対象計|請求額|マイナス)[ \t]*[:：]?[ \t]*
    )?
    (?P<open_paren>\()?[ \t]*
    (?P<currency_sym>[¥￥\\$€])?[ \t]*
    (?P<sign>[▲△▼▽\-−–—－])?[ \t]*
    (?P<currency_sym2>[¥￥\\$€])?[ \t]*
    (?<![\d,./;])(?<!\d:)
    (?P<number>
        \d{1,3}(?:,\d{3})+(?:\.\d{1,2})? |  # comma separated: 1,840 / 1,234.56 / 10,000,000
        \d{1,3}(?:\.\d{3})+ |                # period as thousand separator: 1.840 / 1.840.000
        [1-9]\d{0,2}(?:[ \t]+\d{3})+ |       # space as thousand separator: 1 840 / 12 345
        \d+(?:\.\d{1,2})?                    # plain digits with optional decimal: 1840 / 1840.50
    )
    (?![\d,./;]|:\d)
    (?:[ \t]*(?P<closing_paren>\)))?
    (?:[ \t]*(?P<suffix_hyphen>[-−–—－])(?![-−–—－\d]))?
    (?:[ \t]*(?P<suffix>円))?
    """,
    re.VERBOSE,
)


def find_amounts(
    text_or_normalized: str | SourceSpan | NormalizedText,
    *,
    require_currency_or_context: bool = False,
) -> list[Candidate[int | Decimal]]:
    """
    Extract money amount candidates from Japanese document text.

    Args:
        text_or_normalized: Input text, SourceSpan, or NormalizedText.
        require_currency_or_context: If True, only extract amounts accompanied by
            a currency symbol (¥, ￥, 円) or financial keyword.

    Returns:
        List of Candidate[int | Decimal] objects.
    """
    normalized = ensure_normalized(text_or_normalized, profile="receipt")
    text = normalized.text
    raw_spans = build_norm_to_source_spans(normalized)
    candidates: list[Candidate[int | Decimal]] = []

    for match in AMOUNT_PATTERN.finditer(text):
        number_str = match.group("number")
        if not number_str:
            continue

        prefix = match.group("prefix") or ""
        open_paren = match.group("open_paren") or ""
        currency_sym = match.group("currency_sym") or ""
        sign_char = match.group("sign") or ""
        currency_sym2 = match.group("currency_sym2") or ""
        closing_paren = match.group("closing_paren") or ""
        suffix = match.group("suffix") or ""
        suffix_hyphen = match.group("suffix_hyphen") or ""

        is_accounting_parens = bool(open_paren and closing_paren)

        # Prevent '-' inside hyphenated IDs/phones/dates (e.g. 03-1234) from acting as negative sign
        if (
            sign_char in "-−–—－"
            and not prefix
            and not currency_sym
            and not is_accounting_parens
            and match.start("sign") > 0
        ):
            prev_char = text[match.start("sign") - 1]
            if (prev_char.isascii() and prev_char.isalnum()) or prev_char in "-−–—－,.":
                continue

        has_currency_hint = bool(currency_sym or currency_sym2 or suffix == "円")
        prefix_compact = re.sub(r"[ \t]+", "", prefix)
        has_context_hint = bool(
            any(
                kw in prefix_compact
                for kw in [
                    "値引",
                    "割引",
                    "税",
                    "小計",
                    "合計",
                    "お預",
                    "お釣",
                    "買上",
                    "対象計",
                    "請求",
                    "マイナス",
                ]
            )
        )

        # Skip values immediately followed by non-currency units (e.g. 8%, 500ml, 1.840kg, 2026年)
        if suffix != "円":
            after_number = text[match.end("number") :]
            if NON_AMOUNT_UNIT_PATTERN.match(after_number):
                continue
            if not has_currency_hint and NON_AMOUNT_UNIT_PATTERN.match(after_number.lstrip(" \t")):
                continue

        if require_currency_or_context and not (has_currency_hint or has_context_hint):
            continue

        # Accounting parentheses: e.g. (1,000) or (¥1,000)
        # Negative determination
        is_negative = False
        if any(kw in prefix_compact for kw in ["▲", "△", "▼", "▽", "値引", "割引"]):
            is_negative = True
        elif sign_char in ["▲", "△", "▼", "▽", "-", "−", "–", "—", "－"]:
            is_negative = True
        elif is_accounting_parens:
            is_negative = True

        # Determine actual token span (excluding preceding keyword context)
        token_start = match.start("number")
        if currency_sym2:
            token_start = min(token_start, match.start("currency_sym2"))
        if sign_char:
            token_start = min(token_start, match.start("sign"))
        if currency_sym:
            token_start = min(token_start, match.start("currency_sym"))
        if is_accounting_parens:
            token_start = min(token_start, match.start("open_paren"))

        token_end = match.end("number")
        if is_accounting_parens:
            token_end = max(token_end, match.end("closing_paren"))
        if suffix_hyphen and has_currency_hint:
            token_end = max(token_end, match.end("suffix_hyphen"))
        if suffix:
            token_end = max(token_end, match.end("suffix"))

        reasons: list[str] = []
        status: CandidateStatus = "normalized"

        # Check period vs comma and space vs comma ambiguity
        period_as_comma = bool(PERIOD_THOUSANDS_PATTERN.fullmatch(number_str))
        space_as_comma = bool(SPACE_THOUSANDS_PATTERN.fullmatch(number_str))

        # Reject partial matches of malformed space-separated numbers
        # (e.g. "合計 1 2345円", "1234 567円")
        if "," not in number_str and not period_as_comma and not space_as_comma:
            if (
                not prefix
                and not currency_sym
                and not sign_char
                and not currency_sym2
                and not is_accounting_parens
                and PRECEDING_BARE_DIGITS_RE.search(text[:token_start])
            ):
                continue
            if (
                not suffix
                and not suffix_hyphen
                and not is_accounting_parens
                and FOLLOWING_BARE_DIGITS_RE.match(text[token_end:])
            ):
                continue

        # Skip leading-zero multi-digit integers without currency/context hints (e.g. "(06)")
        if (
            not has_currency_hint
            and not has_context_hint
            and len(number_str) > 1
            and number_str.startswith("0")
            and "." not in number_str
            and "," not in number_str
        ):
            continue

        # Skip bare numbers (integers, decimals like 17.30, or bare space-separated digits)
        # with no currency symbol, context keyword, sign, comma, or period thousands
        has_any_amount_signal = (
            has_currency_hint
            or has_context_hint
            or is_negative
            or ("," in number_str)
            or period_as_comma
        )
        if not has_any_amount_signal:
            continue

        if period_as_comma:
            status = "ambiguous"
            reasons.append("period_used_as_thousands_separator_candidate")
        if space_as_comma:
            status = "ambiguous"
            reasons.append("space_used_as_thousands_separator_candidate")

        # Parse numeric value
        clean_num = number_str.replace(",", "")
        if period_as_comma:
            clean_num = clean_num.replace(".", "")
        if space_as_comma:
            clean_num = re.sub(r"[ \t]+", "", clean_num)

        has_decimal = "." in clean_num
        val_out: int | Decimal
        if has_decimal:
            amount = Decimal(clean_num)
            status = "ambiguous"
            reasons.append("decimal_amount")
            if amount == 0:
                is_negative = False
                val_out = amount
            elif is_negative:
                val_out = -abs(amount)
            else:
                val_out = amount
        else:
            val_int = int(clean_num)
            if val_int == 0:
                is_negative = False
            elif is_negative:
                val_int = -abs(val_int)
            val_out = val_int

        # Record extraction-stage edits within [token_start, token_end]
        extra_edits: list[Edit] = []
        num_start = match.start("number")
        num_end = match.end("number")

        if is_negative and not sign_char and not is_accounting_parens:
            extra_edits.append(
                make_extraction_edit(
                    "apply_negative_context", token_start, token_start, "-", normalized, raw_spans
                )
            )

        idx = token_start
        while idx < num_start:
            if is_accounting_parens and open_paren and idx == match.start("open_paren"):
                rep = "" if sign_char else ("-" if is_negative else "")
                extra_edits.append(
                    make_extraction_edit(
                        "normalize_accounting_parentheses",
                        idx,
                        idx + 1,
                        rep,
                        normalized,
                        raw_spans,
                    )
                )
                idx += 1
            elif currency_sym and idx == match.start("currency_sym"):
                extra_edits.append(
                    make_extraction_edit(
                        "strip_currency_symbol",
                        idx,
                        idx + len(currency_sym),
                        "",
                        normalized,
                        raw_spans,
                    )
                )
                idx += len(currency_sym)
            elif sign_char and idx == match.start("sign"):
                if not is_negative:
                    extra_edits.append(
                        make_extraction_edit(
                            "strip_zero_sign", idx, idx + 1, "", normalized, raw_spans
                        )
                    )
                elif sign_char != "-":
                    extra_edits.append(
                        make_extraction_edit(
                            "normalize_negative_sign", idx, idx + 1, "-", normalized, raw_spans
                        )
                    )
                idx += 1
            elif currency_sym2 and idx == match.start("currency_sym2"):
                extra_edits.append(
                    make_extraction_edit(
                        "strip_currency_symbol",
                        idx,
                        idx + len(currency_sym2),
                        "",
                        normalized,
                        raw_spans,
                    )
                )
                idx += len(currency_sym2)
            elif text[idx] in " \t":
                ws_end = idx + 1
                while ws_end < num_start and text[ws_end] in " \t":
                    ws_end += 1
                extra_edits.append(
                    make_extraction_edit(
                        "strip_amount_whitespace", idx, ws_end, "", normalized, raw_spans
                    )
                )
                idx = ws_end
            else:
                idx += 1

        # Edits inside number (thousands separators: ',', '.', or space)
        for sep_match in re.finditer(r",|\.|[ \t]+", number_str):
            sep_str = sep_match.group(0)
            if sep_str == "." and not period_as_comma:
                continue
            s_idx = num_start + sep_match.start()
            e_idx = num_start + sep_match.end()
            extra_edits.append(
                make_extraction_edit(
                    "strip_thousands_separator", s_idx, e_idx, "", normalized, raw_spans
                )
            )

        idx = num_end
        while idx < token_end:
            if is_accounting_parens and closing_paren and idx == match.start("closing_paren"):
                extra_edits.append(
                    make_extraction_edit(
                        "normalize_accounting_parentheses",
                        idx,
                        idx + 1,
                        "",
                        normalized,
                        raw_spans,
                    )
                )
                idx += 1
            elif suffix_hyphen and idx == match.start("suffix_hyphen"):
                extra_edits.append(
                    make_extraction_edit(
                        "strip_trailing_hyphen", idx, idx + 1, "", normalized, raw_spans
                    )
                )
                idx += 1
            elif suffix and idx == match.start("suffix"):
                extra_edits.append(
                    make_extraction_edit(
                        "strip_currency_symbol",
                        idx,
                        idx + len(suffix),
                        "",
                        normalized,
                        raw_spans,
                    )
                )
                idx += len(suffix)
            elif text[idx] in " \t":
                ws_end = idx + 1
                while ws_end < token_end and text[ws_end] in " \t":
                    ws_end += 1
                extra_edits.append(
                    make_extraction_edit(
                        "strip_amount_whitespace", idx, ws_end, "", normalized, raw_spans
                    )
                )
                idx = ws_end
            else:
                idx += 1

        # Determine exact vs normalized
        matched_slice = text[token_start:token_end]
        source_span, edits = map_span_to_source(
            token_start, token_end, normalized, extra_edits=extra_edits, raw_spans=raw_spans
        )

        if status != "ambiguous":
            if not edits and matched_slice == str(val_out):
                status = "exact"
            else:
                status = "normalized"

        if has_currency_hint:
            reasons.append("has_currency_symbol")
        if has_context_hint:
            reasons.append("has_context_keyword")
        if is_negative:
            reasons.append("negative_amount")

        candidates.append(
            Candidate(
                value=val_out,
                source=source_span,
                edits=edits,
                status=status,
                reasons=tuple(reasons),
            )
        )

    return candidates
