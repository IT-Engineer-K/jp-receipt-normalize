# Changelog

All notable changes to `jp-receipt-normalize` will be documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.7] - 2026-11-18

### Fixed
- Updated relative documentation links in `README.md` and `README_en.md` to absolute GitHub URLs so links work on PyPI.

## [0.1.6] - 2026-11-18

### Changed
- Replaced example invoice registration numbers and store names in documentation and test fixtures with synthetic values.
- Enabled `skip-existing: true` for the PyPI publishing workflow step.

## [0.1.5] - 2026-11-16

### Added
- **Extraction-Stage Edit Audit Trail**: All 6 field extractors (`find_amounts`, `find_dates`, `find_times`, `find_phone_numbers`, `find_invoice_registration_numbers`, `find_jan_codes`) now record extraction transformations (e.g. `strip_currency_symbol`, `strip_thousands_separator`, `strip_phone_separator`, `normalize_time_separator`, `convert_wareki_year`, `strip_registration_separator`, `strip_jan_separator`) in `Candidate.edits`.
- **NFKC Foundation for Halfwidth Kana and Compatibility Characters**: `normalize_text` now converts halfwidth katakana (including voiced/semi-voiced combinations like `ｶﾞ` -> `ガ`, `ﾊﾟ` -> `パ`, `ｺｰﾋｰ` -> `コーヒー`), halfwidth CJK punctuation (`｡｢｣､･`), combining kana marks, and NFKC compatibility characters (`㈱`, `㈲`, `㍿`, `㋿`, CJK compatibility ideographs, Kangxi radicals) while recording `Edit` entries.
- **CI Workflow**: Added `.github/workflows/ci.yaml` and updated `.github/workflows/publish.yaml` with Python 3.10–3.14 matrix testing, Ruff lint check, `mypy` strict check, and branch coverage gate (`--cov-branch --cov-fail-under=90`).

### Fixed
- **Space-Separated Thousands in `find_amounts`**: Space-grouped thousands (`合計 1 840円`, `12 345円`, `1 840円`) are now extracted as a single `ambiguous` candidate (`1840`, `12345`) with reason `space_used_as_thousands_separator_candidate` instead of splitting into partial confirmed candidates (`1` and `840`, or `345`). Malformed space-split numbers (`合計 1 2345円`, `1234 567円`) are rejected rather than partially matched.
- **Decimal Amounts Preserved as `Decimal`**: Fractional/decimal amounts (`0.50円`, `$12.50`, `￥1,234.56`) now preserve their exact `Decimal` value (`Decimal("0.50")`, `Decimal("12.50")`, `Decimal("1234.56")`) with `status="ambiguous"` and reason `decimal_amount`, instead of rounding to integers (`1`, `13`, `1235`).
- **`Candidate.from_dict()` Type Restoration**: `Candidate.from_dict()` now restores `datetime.date`, `datetime.time`, and `Decimal` values from ISO/string representations instead of leaving them as raw strings.
- **Profile Validation**: `normalize_text` now raises `ValueError` when given an unknown `profile` instead of silently falling back to `generic`.
- **Unified Absolute Coordinate System**: `Edit.start` and `Edit.end` now consistently use the same absolute coordinate space as `SourceSpan.start` and `SourceSpan.end` when `SourceSpan` has a non-zero offset.

## [0.1.4] - 2026-11-16

### Added
- `Candidate.from_dict()` for JSON deserialization across all core data models.

### Fixed
- Unified fullwidth hyphen-minus (`－`, U+FF0D) rule handling under `HYPHEN_CHARS` (`normalize_hyphen_fullwidth_hyphen_minus`) and normalized prolonged sound marks adjacent to parenthesized area codes (e.g. `(03)ー1234ー5678`).
- `map_span_to_source()` now guards against empty spans (`norm_end <= norm_start`).
- `find_amounts()`:
  - Restricted whitespace matching to horizontal whitespace `[ \t]*` so trailing divider lines (`▲50\n---`) are not merged.
  - Separated leading currency symbols, signs, and opening parentheses from `prefix` keywords; included accounting parentheses only when both opening and closing parentheses are present.
  - Added support for comma-grouped decimals (`￥1,234.56`), rejected malformed comma groupings (`1,2345`, `1,000,00`), skipped values followed by non-currency units (`%`, `ml`, `kg`, `年`, etc.), skipped bare numbers (including bare decimals like `17.30`), leading-zero area codes (`(06)`), hyphenated IDs/phones, and suppressed `negative_amount` on `-0`.
- `find_jan_codes()`:
  - Prevented trailing numbers from breaking JAN-8 matching (`JAN: 49123456 100円`), rejected unprefixed space-separated `4+4` digits (`1000 2000`), and excluded invoice registration numbers (`T...` / `T ...`).
- `find_dates()`:
  - Restricted whitespace to `[ \t]*`, required `日` in `年/月/日` expressions, rejected year `0` in Wareki (`令和0年5月1日`), enforced consistent separators and alphanumeric boundaries (excluding `VER1.2.3`, `MODEL-H2.3.4`, `12-05-15-99`), and fixed range overlap checks.
- `find_times()`:
  - Restricted whitespace to `[ \t]*`, fixed `exact` status matching (`17:30;15` is `normalized`), fixed range overlap checks, and excluded currency/comma/unit decimals (`¥1,012.50`, `10.00%`) and 4-part colon chains (`12:34:56:78`).
- `find_phone_numbers()`:
  - Restricted whitespace to `[ \t]*`, enforced consistent separators (preventing `03-1234 1000円`), rejected unit suffixes and `00...` prefixes.
- `find_invoice_registration_numbers()`:
  - Restricted whitespace to `[ \t]*` and excluded embedded alphanumeric/hyphenated model codes (`MODEL-T7100000000000`).

### Changed
- `ensure_normalized()` now accepts `ProfileType` directly without `# type: ignore[arg-type]`.
- Tightened fixture assertions in `tests/test_fixtures.py` and `tests/fixtures/synthetic_receipts.json` to exact list equality.

## [0.1.3] - 2026-11-16

### Fixed
- `receipt` profile no longer converts `元` to `円` (it broke `令和元年` dates and words like `地元`).
- Corporate number check digit: remainder 0 now yields 9 (NTA formula `9 - (Σ mod 9)`); previously returned 0.
- Phone number validation: 10-digit numbers with `0X0` prefixes (e.g. `090`, `050`, `0800`) and 11-digit numbers other than mobile / IP / `020` / `0800` are now `invalid`. `0990` is classified as a 10-digit special service number.
- Amounts with multiple period separators (`￥1.840.000`) are now `ambiguous` with value 1840000 instead of `invalid` with value 0.
- Fractional amounts (`$12.50`) are now `ambiguous` with reason `decimal_fraction_rounded` instead of being silently rounded as `normalized`. Rounding uses `ROUND_HALF_UP` on `Decimal`.
- `collapse_spaces=True` now records `collapse_spaces` edits, so source spans stay correct.
- Prolonged sound marks (`ー`, `ｰ`) are converted to `-` only between digits (`03ー1234ー5678` is now detected as a phone number). Halfwidth katakana such as `ｺｰﾋｰ` is no longer corrupted to `ｺ-ﾋ-`.
- Registration numbers followed by a space or hyphen no longer include it in the source span (status stays `exact`).
- Wareki dates outside the era range (e.g. `平成31年5月1日`, `令和元年4月1日`) are now `ambiguous` with reason `outside_era_range`.
- `find_times` no longer extracts parts of dotted dates (`2026.11.15` -> 11:15).
- `find_jan_codes` no longer accepts hyphens between digits, so dates like `2026-11-15` are not extracted.
- Lone `\r` is normalized to `\n` (rule `normalize_cr`).

### Changed
- Publish workflow runs `pytest` and `mypy` before building.

## [0.1.2] - 2026-11-16

### Changed
- Documentation: removed redundant parenthetical English/Katakana translations in Japanese docs.
- Internal cleanup: removed unused imports (`unicodedata`, `Any`, `Edit`), unused constant (`CURRENCY_MAP`), and unused local variables.

## [0.1.1] - 2026-11-16

### Changed
- Documentation: revised wording in README, README_en, design principles, and changelog to be more neutral (removed intensifiers and overstated claims). No code changes.

## [0.1.0] - 2026-11-15

### Added
- **Core Models**:
  - `SourceSpan`: Preserves original OCR text, coordinates, bounding box, and confidence.
  - `Edit`: Immutable audit trail tracking transformation rule, source substring, replacement, and start/end offsets.
  - `NormalizedText`: Container for normalized string, original SourceSpan, and tuple of edits.
  - `Candidate[T]`: Structured extraction candidate with value, source span, edits, status (`exact`, `normalized`, `ambiguous`, `invalid`), and reasons.
  - JSON serialization via `.to_dict()` for all models, and `.from_dict()` for `SourceSpan`, `Edit`, and `NormalizedText`.
- **Auditable Normalization (`normalize_text`)**:
  - Fullwidth ASCII (alphanumerics and symbols) to halfwidth conversion without silent character loss. Halfwidth katakana is left unchanged.
  - Explicit handling and removal of zero-width and invisible control characters.
  - Whitespace normalization (fullwidth space `\u3000`, NBSP `\u00A0`, narrow spaces).
  - Profiles: `generic`, `receipt`, and `invoice`.
  - Han/CJK simplified and variant character mapping for OCR misreads (`计`->`計`, `圆`/`圓`->`円`, `总`->`総`, `额`->`額`, `领`->`領`, `收`->`収`, `证`->`証`, etc.).
  - Contextual hyphen/prolonged-sound distinction (keeps the prolonged sound mark in Katakana words like `コーヒー` instead of converting it to a hyphen).
- **Field Candidate Extractors (`jpdoc_normalize.fields`)**:
  - `find_amounts`: Money amounts with Yen signs, negative indicators (▲, △, -, accounting parens), tax context, and period/comma ambiguity detection.
  - `find_dates`: Western calendar (4-digit and 2-digit) and Japanese Wareki (令和, 平成, 昭和, 元年), with calendar existence validation (leap years, nonexistent dates).
  - `find_times`: 24-hour time representation with OCR colon variations (`;`, `.`) and Japanese character format (`時分秒`).
  - `find_phone_numbers`: Japanese phone number extraction (landlines, mobile 070/080/090, IP 050, toll-free 0120/0800, navidial 0570, data 020) with hyphen stripping.
  - `find_invoice_registration_numbers`: Qualified invoice issuer registration number (`T` + 13 digits) with National Tax Agency (NTA) corporate number check digit verification.
  - `find_jan_codes`: JAN-8 and JAN-13 barcode candidate extraction with Modulus 10 Weight 3 check digit verification.
- **Fixtures & Tests**:
  - Synthetic receipt and invoice fixture dataset (`synthetic_receipts.json`).
  - Unit test suite with 94% branch/statement coverage.
  - Type hints with `py.typed`; no mypy errors in strict mode.

---

## 移行ガイド

### 既存の個別正規化スクリプトからの移行

既存の独自スクリプトで正規化を行っていた場合、以下の手順で段階的に移行できます：

1. **文字列正規化の置き換え**:
   ```python
   # 従来: 単純なNFKCやreplace
   # text = unicodedata.normalize("NFKC", raw_text)

   # 移行後: 変更履歴が追跡可能な normalize_text
   from jpdoc_normalize import normalize_text
   normalized = normalize_text(raw_text, profile="receipt")
   text = normalized.text
   ```

2. **フィールド抽出の導入**:
   ```python
   # 従来: 個別の正規表現による手動パース
   # 移行後: 監査可能なCandidate抽出
   from jpdoc_normalize.fields import find_amounts, find_dates, find_invoice_registration_numbers

   amounts = find_amounts(normalized)
   dates = find_dates(normalized)
   registrations = find_invoice_registration_numbers(normalized)
   ```

3. **フィーチャーフラグによる並行稼働**:
   - `Candidate.status` が `"ambiguous"` または `"invalid"` の場合は人間オペレーターのレビューに回すか、既存のフォールバックロジックを呼び出す設計にすることで、誤補正が自動で確定するリスクを減らせます。
