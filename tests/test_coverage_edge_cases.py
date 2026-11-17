from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from jpdoc_normalize import SourceSpan, normalize_text
from jpdoc_normalize.fields import (
    find_amounts,
    find_dates,
    find_invoice_registration_numbers,
    find_jan_codes,
    find_phone_numbers,
    find_times,
)
from jpdoc_normalize.fields.registration import calculate_corporate_number_check_digit
from jpdoc_normalize.utils import ensure_normalized


def test_normalizer_additional_options():
    """Test collapse_spaces, normalize_currency, and invoice profile."""
    # collapse_spaces records edits and keeps span mapping accurate
    res = normalize_text("商品A    1,000円", collapse_spaces=True)
    assert res.text == "商品A 1,000円"
    assert any(e.rule == "collapse_spaces" for e in res.edits)
    amts = find_amounts(res)
    assert len(amts) == 1
    assert amts[0].source.text == "1,000円"

    # normalize_currency
    res_curr = normalize_text("￥1000", normalize_currency=True)
    assert res_curr.text == "¥1000"
    assert any(e.rule == "fullwidth_yen_to_halfwidth" for e in res_curr.edits)

    # invoice profile
    res_inv = normalize_text("发票", profile="invoice")
    assert res_inv.text == "発票"

    # Halfwidth katakana word with prolonged sound mark becomes fullwidth katakana (never ｺ-ﾋ-)
    assert normalize_text("ｺｰﾋｰ").text == "コーヒー"
    # Halfwidth prolonged sound mark after fullwidth katakana becomes fullwidth ー
    res_kana = normalize_text("コーヒｰ")
    assert res_kana.text == "コーヒー"
    # Hiragana prolonged sound mark is preserved
    assert normalize_text("らーめん").text == "らーめん"
    # Prolonged sound mark between digits is converted to hyphen
    assert normalize_text("03ー1234ー5678").text == "03-1234-5678"

    # Lone CR newline normalization
    res_cr = normalize_text("A\rB")
    assert res_cr.text == "A\nB"
    assert any(e.rule == "normalize_cr" for e in res_cr.edits)

    # Receipt profile does not corrupt 元年 or 地元
    res_reiwa = normalize_text("令和元年5月1日 地元", profile="receipt")
    assert res_reiwa.text == "令和元年5月1日 地元"
    dates = find_dates(res_reiwa)
    assert len(dates) == 1
    assert dates[0].value == datetime.date(2019, 5, 1)

    # Passing SourceSpan to normalize_text preserves absolute coordinates
    span = SourceSpan(text="テスト　￥１，０００", start=10, end=20)
    res_span = normalize_text(span)
    assert res_span.text == "テスト ￥1,000"
    assert res_span.source.start == 10
    assert all(10 <= e.start <= e.end <= 20 for e in res_span.edits)
    amts_span = find_amounts(res_span)
    assert len(amts_span) == 1
    assert amts_span[0].source.start == 14
    assert amts_span[0].source.end == 20
    assert all(14 <= e.start <= e.end <= 20 for e in amts_span[0].edits)


def test_phone_number_edge_cases():
    """Test 020, 0570, 0800, require_keyword and invalid phone cases."""
    # 020 data
    cands_020 = find_phone_numbers("020-1234-5678")
    assert len(cands_020) == 1
    assert "phone_type_data_communication" in cands_020[0].reasons

    # 0570 navidial 10 digit
    cands_0570 = find_phone_numbers("0570-012-345")
    assert len(cands_0570) == 1
    assert cands_0570[0].status == "normalized"
    assert "phone_type_navi_dial" in cands_0570[0].reasons

    # 0990 special service 10 digit
    cands_0990 = find_phone_numbers("0990-123-456")
    assert len(cands_0990) == 1
    assert cands_0990[0].status == "normalized"
    assert "phone_type_special_service" in cands_0990[0].reasons

    # 0800 toll free 11 digit
    cands_0800 = find_phone_numbers("0800-123-4567")
    assert len(cands_0800) == 1
    assert "phone_type_toll_free" in cands_0800[0].reasons

    # Invalid prefix/length combinations
    for invalid_num in ("090-123-4567", "03123456789", "0120-123-4567", "0570-123-4567"):
        cands = find_phone_numbers(invalid_num)
        assert len(cands) == 1
        assert cands[0].status == "invalid"

    # Phone number with prolonged sound mark
    cands_prolonged = find_phone_numbers("03ー1234ー5678")
    assert len(cands_prolonged) == 1
    assert cands_prolonged[0].value == "0312345678"
    assert cands_prolonged[0].status == "normalized"

    # require_keyword=True
    assert len(find_phone_numbers("03-1234-5678", require_keyword=True)) == 0
    assert len(find_phone_numbers("TEL: 03-1234-5678", require_keyword=True)) == 1

    # Phone number with valid keyword
    cands_tel = find_phone_numbers("TEL: 03-1234-5678")
    assert len(cands_tel) == 1
    assert "has_phone_keyword" in cands_tel[0].reasons


def test_regressions_amounts_dates_times_jan_registration():
    """Verify regression fixes across amounts, dates, times, JAN, and registration."""
    # Multiple period thousands separator
    amts_multi = find_amounts("合計 ￥1.840.000")
    assert len(amts_multi) == 1
    assert amts_multi[0].value == 1840000
    assert amts_multi[0].status == "ambiguous"
    assert "period_used_as_thousands_separator_candidate" in amts_multi[0].reasons

    # Fractional amount preserves Decimal and is marked ambiguous
    amts_dec = find_amounts("$12.50")
    assert len(amts_dec) == 1
    assert amts_dec[0].value == Decimal("12.50")
    assert amts_dec[0].status == "ambiguous"
    assert "decimal_amount" in amts_dec[0].reasons

    # Corporate check digit when remainder is 0 -> 9
    assert calculate_corporate_number_check_digit("000000000009") == 9

    # Registration number followed by space retains exact status and tight source span
    regs = find_invoice_registration_numbers("T7100000000000 です")
    assert len(regs) == 1
    assert regs[0].status == "exact"
    assert regs[0].source.text == "T7100000000000"

    # Wareki outside era range is marked ambiguous
    dates_out = find_dates("令和元年4月1日 平成31年5月1日")
    assert len(dates_out) == 2
    assert all(d.status == "ambiguous" and "outside_era_range" in d.reasons for d in dates_out)

    # Dotted date does not produce a false time candidate
    assert find_times("2026.11.15") == []

    # Hyphenated date does not produce a false JAN-8 candidate
    assert find_jan_codes("2026-11-15") == []

    # Fullwidth hyphen-minus (U+FF0D) uses hyphen rule rather than fullwidth_ascii_to_halfwidth
    res_ff0d = normalize_text("03－1234")
    assert res_ff0d.text == "03-1234"
    assert any(e.rule == "normalize_hyphen_fullwidth_hyphen_minus" for e in res_ff0d.edits)

    # Amount spans: no trailing newline/divider, no unmatched parens, keeps leading symbol/sign
    amts_divider = find_amounts("値引 ▲50\n------------------------")
    assert len(amts_divider) == 1
    assert amts_divider[0].value == -50
    assert amts_divider[0].source.text == "▲50"

    amts_parens = find_amounts("(税抜金額: ￥1,000,000) 合計 (1,000円")
    assert [(a.value, a.source.text) for a in amts_parens] == [
        (1000000, "￥1,000,000"),
        (1000, "1,000円"),
    ]

    amts_bare_signs = find_amounts("¥1,000 -200 クーポン ▲50")
    assert [(a.value, a.source.text) for a in amts_bare_signs] == [
        (1000, "¥1,000"),
        (-200, "-200"),
        (-50, "▲50"),
    ]

    # Comma+decimal, malformed commas, units, and bare IDs/phones/dates
    amts_comma_dec = find_amounts("￥1,234.56")
    assert len(amts_comma_dec) == 1
    assert amts_comma_dec[0].value == Decimal("1234.56")
    assert amts_comma_dec[0].status == "ambiguous"
    assert "decimal_amount" in amts_comma_dec[0].reasons

    noise_text = (
        "￥1,2345 1,000,00 1.840kg 500ml 8% "
        "TEL: (06) 6123-4567 TEL: 03-1234-5678 T7123456789012"
    )
    assert find_amounts(noise_text) == []

    # Registration number is not matched as a JAN-13 code
    assert find_jan_codes("登録番号: T7100000000000") == []

    # Extractors do not join tokens across newlines
    assert find_dates("2026年11月\n1. 品目") == []
    assert find_phone_numbers("03\n1234\n5678") == []
    assert find_invoice_registration_numbers("T710000\n0000000") == []

    # Wareki year 0 is invalid, and 2-digit dates do not match inside longer hyphenated codes
    dates_yr0 = find_dates("令和0年5月1日")
    assert len(dates_yr0) == 1
    assert dates_yr0[0].status == "invalid"
    assert dates_yr0[0].value is None
    assert find_dates("番号 12-05-15-99") == []

    # Time exactness and currency/multi-dot exclusions
    times_semi = find_times("17:30;15")
    assert len(times_semi) == 1
    assert times_semi[0].status == "normalized"
    assert find_times("合計 ¥12.50 コード 12.34.56") == []

    # JAN-8 followed by space and number, standalone 4+4 numbers, and spaced registration number
    jan_followed = find_jan_codes("JAN: 49123456 100円")
    assert [j.value for j in jan_followed] == ["49123456"]
    assert find_jan_codes("1000 2000") == []
    assert find_jan_codes("登録番号 T 7100000000000") == []

    # Version/model strings are not misread as Wareki dates or registration numbers
    assert find_dates("VER1.2.3 MODEL-H2.3.4") == []
    assert find_invoice_registration_numbers("MODEL-T7100000000000") == []

    # Comma decimals, percentage decimals, 4-part colons, and bare period decimals
    assert find_times("¥1,012.50 消費税 10.00% 12:34:56:78") == []
    assert find_amounts("2026/11/15 17.30") == []
    amts_neg_zero = find_amounts("-0円")
    assert len(amts_neg_zero) == 1
    assert amts_neg_zero[0].value == 0
    assert "negative_amount" not in amts_neg_zero[0].reasons

    # Phone number separator consistency and prolonged sound mark after parentheses
    assert find_phone_numbers("番号 03-1234 1000円") == []
    assert [p.value for p in find_phone_numbers("(03)ー1234ー5678")] == ["0312345678"]
    cands_00 = find_phone_numbers("0012345678")
    assert len(cands_00) == 1
    assert cands_00[0].status == "invalid"


def test_extraction_stage_edits_recorded():
    """Verify all extractors record extraction-stage transformations in Candidate.edits."""
    # Amount: ¥ and comma stripped
    amt = find_amounts("¥1,840")[0]
    assert [(e.rule, e.source, e.replacement, e.start, e.end) for e in amt.edits] == [
        ("strip_currency_symbol", "¥", "", 0, 1),
        ("strip_thousands_separator", ",", "", 2, 3),
    ]

    # Amount: negative from context keyword without sign char
    amt_ctx_neg = find_amounts("値引 50")[0]
    assert amt_ctx_neg.value == -50
    assert any(
        e.rule == "apply_negative_context" and e.replacement == "-"
        for e in amt_ctx_neg.edits
    )

    # Phone: hyphens stripped
    phone = find_phone_numbers("03-1234-5678")[0]
    assert [(e.rule, e.source, e.replacement, e.start, e.end) for e in phone.edits] == [
        ("strip_phone_separator", "-", "", 2, 3),
        ("strip_phone_separator", "-", "", 7, 8),
    ]

    # Time: semicolon normalized to colon
    tm = find_times("17;30")[0]
    assert [(e.rule, e.source, e.replacement, e.start, e.end) for e in tm.edits] == [
        ("normalize_time_separator", ";", ":", 2, 3),
    ]

    # Date: Wareki converted and units normalized
    dt = find_dates("令和8年4月1日")[0]
    assert any(e.rule == "convert_wareki_year" and e.replacement == "2026" for e in dt.edits)
    assert any(e.rule == "pad_date_zero" and e.replacement == "04" for e in dt.edits)
    assert any(e.rule == "normalize_japanese_date_unit" for e in dt.edits)

    # Registration: lowercase t and hyphen
    reg = find_invoice_registration_numbers("登録番号 t-7123456789012")[0]
    assert any(e.rule == "uppercase_registration_prefix" for e in reg.edits)
    assert any(e.rule == "strip_registration_separator" for e in reg.edits)

    # JAN: space separator stripped
    jan = find_jan_codes("JAN: 4912 3456")[0]
    assert [(e.rule, e.source, e.replacement) for e in jan.edits] == [
        ("strip_jan_separator", " ", ""),
    ]

    # Additional amount/time/normalizer branches for extraction edits & NFKC combining
    amts_extra = find_amounts("▲ ¥ 50  1,000 円  -0.50円  -0.00円")
    assert [a.value for a in amts_extra] == [-50, 1000, Decimal("-0.50"), Decimal("0.00")]
    assert all(len(a.edits) > 0 for a in amts_extra)

    times_extra = find_times("9:05:30 9時5分5秒")
    assert [t.value for t in times_extra] == [
        datetime.time(9, 5, 5),
        datetime.time(9, 5, 30),
    ]
    assert all(any(e.rule == "pad_time_zero" for e in t.edits) for t in times_extra)

    norm_comb = normalize_text("カ\u3099ハ\u309A ﾞ ﾟ")
    assert norm_comb.text == "ガパ ゛ ゜"
    assert any(e.rule == "nfkc_combining_kana" for e in norm_comb.edits)

    # Pass SourceSpan directly to ensure_normalized
    span_in = SourceSpan(text="1,000円", start=5, end=11)
    assert ensure_normalized(span_in).source.start == 5


def test_utils_type_error():
    """Test invalid input type to ensure_normalized."""
    with pytest.raises(TypeError):
        ensure_normalized(12345)  # type: ignore[arg-type]
