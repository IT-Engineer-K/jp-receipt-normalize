from __future__ import annotations

# Invisible / Zero-width characters to remove
ZERO_WIDTH_CHARS = {
    "\u200B": "zero_width_space",
    "\uFEFF": "zero_width_no_break_space",
    "\u200C": "zero_width_non_joiner",
    "\u200D": "zero_width_joiner",
    "\u200E": "left_to_right_mark",
    "\u200F": "right_to_left_mark",
    "\u202A": "left_to_right_embedding",
    "\u202B": "right_to_left_embedding",
    "\u202C": "pop_directional_formatting",
    "\u202D": "left_to_right_override",
    "\u202E": "right_to_left_override",
}

# Whitespace normalization mapping (to standard half-width space ' ')
SPACE_CHARS = {
    "\u3000": "ideographic_space",
    "\u00A0": "no_break_space",
    "\u2002": "en_space",
    "\u2003": "em_space",
    "\u2004": "three_per_em_space",
    "\u2005": "four_per_em_space",
    "\u2006": "six_per_em_space",
    "\u2007": "figure_space",
    "\u2008": "punctuation_space",
    "\u2009": "thin_space",
    "\u202F": "narrow_no_break_space",
    "\u205F": "medium_mathematical_space",
}

# Hyphen / Dash variants
HYPHEN_CHARS = {
    "\u2010": "hyphen",
    "\u2011": "non_breaking_hyphen",
    "\u2012": "figure_dash",
    "\u2013": "en_dash",
    "\u2014": "em_dash",
    "\u2015": "horizontal_bar",
    "\u2212": "minus_sign",
    "\uFF0D": "fullwidth_hyphen_minus",
    "\uFE63": "small_hyphen_minus",
    "\u2500": "box_drawings_light_horizontal",
    "\uFF70": "halfwidth_katakana_hiragana_prolonged_sound_mark",
    "\u30FC": "katakana_hiragana_prolonged_sound_mark",
}

# Fullwidth ASCII to halfwidth mapping (range 0xFF01 - 0xFF5E)
# Maps ！"＃＄％＆'（）＊＋，－．／０-９：；＜＝＞？＠Ａ-Ｚ［＼］＾＿｀ａ-ｚ｛｜｝～
# Exclude characters already handled by HYPHEN_CHARS (e.g. U+FF0D '－')
# so rule names stay consistent.
FULLWIDTH_TO_HALFWIDTH: dict[str, str] = {}
for code in range(0xFF01, 0xFF5F):
    ch = chr(code)
    if ch not in HYPHEN_CHARS:
        FULLWIDTH_TO_HALFWIDTH[ch] = chr(code - 0xFEE0)

# Simplified Chinese / Han variant characters common in Japanese OCR
# Map from variant to standard Japanese JOD (Joyo / Jinmeiyo kanji)
SIMPLIFIED_TO_JAPANESE_COMMON: dict[str, tuple[str, str]] = {
    "圆": ("円", "simplified_yuan_to_yen"),
    "圓": ("円", "traditional_yuan_to_yen"),
    "计": ("計", "simplified_ji_to_kei"),
    "总": ("総", "simplified_zong_to_so"),
    "额": ("額", "simplified_e_to_gaku"),
    "领": ("領", "simplified_ling_to_ryo"),
    "收": ("収", "simplified_shou_to_shu"),
    "证": ("証", "simplified_zheng_to_sho"),
    "购": ("購", "simplified_gou_to_ko"),
    "录": ("録", "simplified_lu_to_roku"),
    "开": ("開", "simplified_kai_to_kai"),
    "发": ("発", "simplified_fa_to_hatsu"),
    "卖": ("売", "simplified_mai_to_uri"),
    "费": ("費", "simplified_fei_to_hi"),
    "银": ("銀", "simplified_yin_to_gin"),
    "联": ("聯", "simplified_lian_to_ren"),
    "码": ("碼", "simplified_ma_to_ma"),
}

# Receipt-specific variant mappings
# Note: "元" is intentionally NOT mapped to "円". It appears in ordinary words
# (元年, 地元) and may denote Chinese yuan, so converting it would be a guess.
RECEIPT_VARIANTS: dict[str, tuple[str, str]] = {
    **SIMPLIFIED_TO_JAPANESE_COMMON,
}

# Invoice-specific variant mappings
INVOICE_VARIANTS: dict[str, tuple[str, str]] = {
    **SIMPLIFIED_TO_JAPANESE_COMMON,
}
