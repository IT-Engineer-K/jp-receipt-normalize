from __future__ import annotations

import pytest

from jpdoc_normalize import SourceSpan, normalize_text


def test_normalize_basic_example():
    """Verify the exact example from the requirement document."""
    normalized = normalize_text("合 計　￥1,８４０", profile="receipt")
    assert normalized.text == "合 計 ￥1,840"
    assert len(normalized.edits) > 0

    # Ensure edits recorded space and digits correctly
    rules = [e.rule for e in normalized.edits]
    assert "normalize_space" in rules
    assert "fullwidth_digit_to_halfwidth" in rules


def test_normalize_zero_width_chars():
    """Verify zero-width spaces, BOM, etc. are stripped and logged."""
    raw = "合\u200B計\uFEFF1000\u200C円"
    normalized = normalize_text(raw)
    assert normalized.text == "合計1000円"
    assert len(normalized.edits) == 3
    assert all(e.replacement == "" for e in normalized.edits)


def test_normalize_spaces():
    """Verify various fullwidth/special spaces normalized to halfwidth space."""
    raw = "商品A\u3000100円\u00A02個\u202F合計"
    normalized = normalize_text(raw)
    assert normalized.text == "商品A 100円 2個 合計"
    assert len(normalized.edits) == 3
    assert all(e.replacement == " " for e in normalized.edits)


def test_normalize_newlines():
    """Verify CRLF normalized to LF."""
    raw = "AAA\r\nBBB\r\nCCC"
    normalized = normalize_text(raw)
    assert normalized.text == "AAA\nBBB\nCCC"
    assert len(normalized.edits) == 2


def test_normalize_han_variants_receipt():
    """Verify simplified and variant characters in receipt profile."""
    raw = "小计 1000圆 总额 1100圓 领收证"
    normalized = normalize_text(raw, profile="receipt")
    assert normalized.text == "小計 1000円 総額 1100円 領収証"
    # 8 characters transformed: 计, 圆, 总, 额, 圓, 领, 收, 证
    assert len(normalized.edits) == 8


def test_normalize_nfkc_halfwidth_kana_and_compatibility():
    """Verify NFKC foundation converts halfwidth katakana and compatibility chars."""
    raw = "ｶﾞｿﾘﾝ代 ｺｰﾋｰ ﾊﾟﾝ ｡｢｣､･ ㈱テスト ㈲サンプル ㍿ ㋿8年 領収書 ⼀〇〇"
    normalized = normalize_text(raw, profile="receipt")
    expected = (
        "ガソリン代 コーヒー パン 。「」、・ "
        "(株)テスト (有)サンプル 株式会社 令和8年 領収書 一〇〇"
    )
    assert normalized.text == expected
    rules = {e.rule for e in normalized.edits}
    assert "halfwidth_kana_to_fullwidth" in rules
    assert "halfwidth_kana_prolonged_sound_mark" in rules
    assert "halfwidth_cjk_punctuation_to_fullwidth" in rules
    assert "nfkc_compatibility" in rules


def test_normalize_unknown_profile_raises():
    """Verify unknown profile raises ValueError instead of silently falling back."""
    with pytest.raises(ValueError, match="Unknown profile"):
        normalize_text("テスト", profile="unknown")  # type: ignore[arg-type]


def test_normalize_sourcespan_absolute_coordinates():
    """Verify Edit coordinates use the same absolute coordinate space as SourceSpan."""
    span = SourceSpan(text="合 計　￥1,８４０", start=100, end=110)
    normalized = normalize_text(span, profile="receipt")
    assert normalized.source.start == 100
    assert normalized.source.end == 110
    assert [e.start for e in normalized.edits] == [103, 107, 108, 109]
    assert [e.end for e in normalized.edits] == [104, 108, 109, 110]


def test_negative_test_do_not_convert_katakana_prolonged_sound():
    """CRITICAL: Do NOT convert prolonged sound mark after Katakana into hyphen."""
    raw = "コーヒー ラーメン カレー スーパー"
    normalized = normalize_text(raw)
    assert normalized.text == "コーヒー ラーメン カレー スーパー"
    # No hyphen normalization should happen on katakana
    assert not any(e.replacement == "-" for e in normalized.edits)


def test_negative_test_do_not_replace_o_with_zero():
    """CRITICAL: Do NOT blindly convert letter 'O' to digit '0' or 'l' to '1'."""
    raw = "MODEL-O1 TYPE-l"
    normalized = normalize_text(raw)
    assert normalized.text == "MODEL-O1 TYPE-l"
    assert not any(e.replacement in ("0", "1") for e in normalized.edits)
