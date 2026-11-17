from __future__ import annotations

import unicodedata
from typing import Literal

from jpdoc_normalize.char_maps import (
    FULLWIDTH_TO_HALFWIDTH,
    HYPHEN_CHARS,
    INVOICE_VARIANTS,
    RECEIPT_VARIANTS,
    SIMPLIFIED_TO_JAPANESE_COMMON,
    SPACE_CHARS,
    ZERO_WIDTH_CHARS,
)
from jpdoc_normalize.models import Edit, NormalizedText, SourceSpan

ProfileType = Literal["generic", "receipt", "invoice"]

DIGIT_CHARS = frozenset("0123456789０１２３４５６７８９")
PROLONGED_SOUND_MARKS = frozenset("ーｰ")
STANDALONE_VOICED_MARKS = frozenset("\u309B\u309C\uFFE3")


def normalize_text(
    text_or_span: str | SourceSpan,
    profile: ProfileType = "generic",
    *,
    collapse_spaces: bool = False,
    normalize_currency: bool = False,
) -> NormalizedText:
    """
    Normalize Japanese OCR text while recording all edits.

    Args:
        text_or_span: The input raw text or SourceSpan.
        profile: Normalization profile ("generic", "receipt", "invoice").
        collapse_spaces: If True, collapse multiple consecutive spaces into one.
        normalize_currency: If True, convert ￥ to ¥.

    Returns:
        NormalizedText containing the normalized string, source span, and tuple of edits.
    """
    if isinstance(text_or_span, SourceSpan):
        source_span = text_or_span
        raw_text = source_span.text
    else:
        raw_text = str(text_or_span)
        source_span = SourceSpan(text=raw_text, start=0, end=len(raw_text))

    base_start = source_span.start
    edits: list[Edit] = []
    output_chars: list[str] = []

    # Select variant dictionary based on profile
    variant_dict: dict[str, tuple[str, str]]
    if profile == "receipt":
        variant_dict = RECEIPT_VARIANTS
    elif profile == "invoice":
        variant_dict = INVOICE_VARIANTS
    elif profile == "generic":
        variant_dict = SIMPLIFIED_TO_JAPANESE_COMMON
    else:
        raise ValueError(
            f"Unknown profile: {profile!r}. Expected 'generic', 'receipt', or 'invoice'."
        )

    i = 0
    n = len(raw_text)

    while i < n:
        # 1. CRLF newline normalization
        if raw_text[i : i + 2] == "\r\n":
            edits.append(
                Edit(
                    rule="normalize_crlf",
                    source="\r\n",
                    replacement="\n",
                    start=base_start + i,
                    end=base_start + i + 2,
                )
            )
            output_chars.append("\n")
            i += 2
            continue

        ch = raw_text[i]

        # 1b. Lone CR newline normalization
        if ch == "\r":
            edits.append(
                Edit(
                    rule="normalize_cr",
                    source="\r",
                    replacement="\n",
                    start=base_start + i,
                    end=base_start + i + 1,
                )
            )
            output_chars.append("\n")
            i += 1
            continue

        # 2. Zero-width / invisible characters removal
        if ch in ZERO_WIDTH_CHARS:
            rule_name = f"remove_{ZERO_WIDTH_CHARS[ch]}"
            edits.append(
                Edit(
                    rule=rule_name,
                    source=ch,
                    replacement="",
                    start=base_start + i,
                    end=base_start + i + 1,
                )
            )
            i += 1
            continue

        # 3. Currency symbol normalization if requested (keep ￥ by default)
        if ch == "￥":
            if normalize_currency:
                edits.append(
                    Edit(
                        rule="fullwidth_yen_to_halfwidth",
                        source="￥",
                        replacement="¥",
                        start=base_start + i,
                        end=base_start + i + 1,
                    )
                )
                output_chars.append("¥")
            else:
                output_chars.append("￥")
            i += 1
            continue

        # 4. Whitespace normalization (and optional collapsing of consecutive spaces)
        if ch == " " or ch in SPACE_CHARS:
            if collapse_spaces and output_chars and output_chars[-1] == " ":
                edits.append(
                    Edit(
                        rule="collapse_spaces",
                        source=ch,
                        replacement="",
                        start=base_start + i,
                        end=base_start + i + 1,
                    )
                )
                i += 1
                continue
            if ch != " ":
                edits.append(
                    Edit(
                        rule="normalize_space",
                        source=ch,
                        replacement=" ",
                        start=base_start + i,
                        end=base_start + i + 1,
                    )
                )
            output_chars.append(" ")
            i += 1
            continue

        # 5. Fullwidth ASCII to halfwidth (Digits, Letters, Punctuation)
        if ch in FULLWIDTH_TO_HALFWIDTH:
            rep = FULLWIDTH_TO_HALFWIDTH[ch]
            rule = "fullwidth_ascii_to_halfwidth"
            if "0" <= rep <= "9":
                rule = "fullwidth_digit_to_halfwidth"
            elif ("a" <= rep <= "z") or ("A" <= rep <= "Z"):
                rule = "fullwidth_alpha_to_halfwidth"
            elif rep in ",.":
                rule = "fullwidth_punctuation_to_halfwidth"

            edits.append(
                Edit(
                    rule=rule,
                    source=ch,
                    replacement=rep,
                    start=base_start + i,
                    end=base_start + i + 1,
                )
            )
            output_chars.append(rep)
            i += 1
            continue

        # 6. Han variants / Simplified Chinese mapping for receipt/invoice
        if ch in variant_dict:
            rep, rule_suffix = variant_dict[ch]
            if rep != ch:
                edits.append(
                    Edit(
                        rule=f"han_variant_{rule_suffix}",
                        source=ch,
                        replacement=rep,
                        start=base_start + i,
                        end=base_start + i + 1,
                    )
                )
                output_chars.append(rep)
                i += 1
                continue

        # 7. Hyphen / minus normalization
        # Prolonged sound marks (ー, ｰ) are converted to '-' only when surrounded by
        # digits (e.g. 03ー1234ー5678). Elsewhere (コーヒー, らーめん, ｺｰﾋｰ) they are kept as ー.
        if ch in HYPHEN_CHARS:
            prev_char = raw_text[i - 1] if i > 0 else ""
            next_char = raw_text[i + 1] if i + 1 < n else ""
            prev_is_num = prev_char in DIGIT_CHARS or (
                prev_char in ")）" and i >= 2 and raw_text[i - 2] in DIGIT_CHARS
            )
            next_is_num = next_char in DIGIT_CHARS or (
                next_char in "(（" and i + 2 < n and raw_text[i + 2] in DIGIT_CHARS
            )
            in_numeric_context = prev_is_num and next_is_num
            if ch in PROLONGED_SOUND_MARKS and not in_numeric_context:
                if ch == "ｰ":
                    # Halfwidth prolonged sound mark outside numeric context -> fullwidth ー
                    edits.append(
                        Edit(
                            rule="halfwidth_kana_prolonged_sound_mark",
                            source="ｰ",
                            replacement="ー",
                            start=base_start + i,
                            end=base_start + i + 1,
                        )
                    )
                    output_chars.append("ー")
                else:
                    output_chars.append(ch)
                i += 1
                continue

            edits.append(
                Edit(
                    rule=f"normalize_hyphen_{HYPHEN_CHARS[ch]}",
                    source=ch,
                    replacement="-",
                    start=base_start + i,
                    end=base_start + i + 1,
                )
            )
            output_chars.append("-")
            i += 1
            continue

        # 8. Halfwidth Katakana and CJK punctuation (U+FF61 .. U+FF9F)
        code = ord(ch)
        if 0xFF61 <= code <= 0xFF9F:
            # Check for voiced (ﾞ U+FF9E) or semi-voiced (ﾟ U+FF9F) combination
            if 0xFF66 <= code <= 0xFF9D and i + 1 < n and raw_text[i + 1] in ("\uFF9E", "\uFF9F"):
                pair = raw_text[i : i + 2]
                combined = unicodedata.normalize("NFKC", pair)
                if len(combined) == 1:
                    edits.append(
                        Edit(
                            rule="halfwidth_kana_to_fullwidth",
                            source=pair,
                            replacement=combined,
                            start=base_start + i,
                            end=base_start + i + 2,
                        )
                    )
                    output_chars.append(combined)
                    i += 2
                    continue

            if ch in ("\uFF9E", "\uFF9F"):
                rep = "゛" if ch == "\uFF9E" else "゜"
                rule = "halfwidth_kana_to_fullwidth"
            elif 0xFF61 <= code <= 0xFF65:
                rep = unicodedata.normalize("NFKC", ch)
                rule = "halfwidth_cjk_punctuation_to_fullwidth"
            else:
                rep = unicodedata.normalize("NFKC", ch)
                rule = "halfwidth_kana_to_fullwidth"

            edits.append(
                Edit(
                    rule=rule,
                    source=ch,
                    replacement=rep,
                    start=base_start + i,
                    end=base_start + i + 1,
                )
            )
            output_chars.append(rep)
            i += 1
            continue

        # 9. Combining voiced/semi-voiced sound marks after fullwidth kana (e.g. カ + U+3099 -> ガ)
        if i + 1 < n and raw_text[i + 1] in ("\u3099", "\u309A"):
            pair = raw_text[i : i + 2]
            combined = unicodedata.normalize("NFKC", pair)
            if len(combined) == 1:
                edits.append(
                    Edit(
                        rule="nfkc_combining_kana",
                        source=pair,
                        replacement=combined,
                        start=base_start + i,
                        end=base_start + i + 2,
                    )
                )
                output_chars.append(combined)
                i += 2
                continue

        # 10. General NFKC compatibility normalization (enclosed CJK, era symbols, radicals, etc.)
        if ch not in STANDALONE_VOICED_MARKS:
            nfkc_rep = unicodedata.normalize("NFKC", ch)
            if nfkc_rep != ch and not any(unicodedata.combining(c) for c in nfkc_rep):
                # Apply Han variant dictionary if decomposed form contains mapped characters
                nfkc_rep = "".join(
                    variant_dict[c][0] if c in variant_dict else c for c in nfkc_rep
                )
                edits.append(
                    Edit(
                        rule="nfkc_compatibility",
                        source=ch,
                        replacement=nfkc_rep,
                        start=base_start + i,
                        end=base_start + i + 1,
                    )
                )
                output_chars.append(nfkc_rep)
                i += 1
                continue

        # Default: keep char unchanged
        output_chars.append(ch)
        i += 1

    normalized_str = "".join(output_chars)

    return NormalizedText(
        text=normalized_str,
        source=source_span,
        edits=tuple(edits),
    )
