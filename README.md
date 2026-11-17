# jp-receipt-normalize

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Typing: Typed](https://img.shields.io/badge/typing-typed-green.svg)](https://peps.python.org/pep-0561/)

**日本語帳票OCRの監査可能な正規化・候補抽出ライブラリ**

[English README is available here (README_en.md)](README_en.md) | [設計思想: なぜ曖昧なら直さないか (docs/design_principles.md)](docs/design_principles.md)

---

## 概要

日本語の領収書・レシート・請求書をOCR処理すると、全角半角、Unicode字形、簡体字・異体字、記号の誤読、空白、桁区切りなどが揺れる場合があります。

しかし、業務自動化において「それらしく見える値へ勝手に直す」ことは、誤請求や税務申告ミスを引き起こす危険があります。

`jp-receipt-normalize` は、OCRエンジンやLLMを内包しない、OCR後段の処理を対象とした監査可能な部品です。
元の文字列、変更箇所、適用規則、曖昧性の理由を記録・保持したうえで、候補を抽出します。

### 特徴

1. **監査可能性**:
   文字列の変更は `Edit(rule, source, replacement, start, end)` として記録され、元の位置と差分を追跡できます。
2. **曖昧な補正を自動確定しない**:
   「O」と「0」、「l」と「1」、ピリオド桁区切り（`￥1.840`）など、文脈なしに断定できない曖昧な補正は自動確定せず、`status="ambiguous"` や判定理由（`reasons`）を返します。
3. **日本語帳票向けの候補抽出**:
   - 金額（負数・値引き・税額・通貨記号・桁区切り）
   - 日付（西暦・和暦・令和元年・実在日うるう年検証）
   - 時刻（24時間表記・時分秒・コロン揺れ）
   - 日本の電話番号（市外局番体系・固定・携帯・フリーダイヤル・IP電話・ハイフン除去）
   - 適格請求書発行事業者登録番号（`T` + 13桁・国税庁法人番号チェックデジット検証）
   - JAN/EANコード（8桁・13桁・モジュラス10ウェイト3チェックデジット検証）
4. **外部通信なし・ゼロ依存**:
   Python標準ライブラリ中心で動作します。外部API呼び出しやネットワーク通信は行わず、決定論的に動作します。
5. **JSON直列化と型付け**:
   `to_dict()` によるJSON直列化と、`py.typed` による静的型チェック（mypy strict）に対応しています。

---

## インストール

```bash
pip install jp-receipt-normalize
```

---

## クイックスタート

```python
from jpdoc_normalize import normalize_text
from jpdoc_normalize.fields import (
    find_amounts,
    find_dates,
    find_invoice_registration_numbers,
    find_phone_numbers,
)

# 1. 文字列の監査可能正規化
ocr_text = "合 計　￥1,８４０"
normalized = normalize_text(ocr_text, profile="receipt")

print(normalized.text)
# => "合 計 ￥1,840"

# 変更履歴（Edit）の確認
for edit in normalized.edits:
    print(f"Rule: {edit.rule}, Source: {edit.source!r} -> {edit.replacement!r} [{edit.start}:{edit.end}]")
# => Rule: normalize_space, Source: '　' -> ' ' [2:3]
# => Rule: fullwidth_digit_to_halfwidth, Source: '８' -> '8' [5:6]
# => Rule: fullwidth_digit_to_halfwidth, Source: '４' -> '4' [6:7]
# => Rule: fullwidth_digit_to_halfwidth, Source: '０' -> '0' [7:8]

# 2. 金額候補の抽出
amounts = find_amounts(normalized)
print(amounts[0].value, amounts[0].status, amounts[0].reasons)
# => 1840 normalized ('has_currency_symbol',)

# 3. インボイス登録番号の抽出と法人番号チェックデジット検証
registrations = find_invoice_registration_numbers("登録番号 T７１２３４５６７８９０１２")
for candidate in registrations:
    print(candidate.value, candidate.status, candidate.reasons)
# => T7123456789012 normalized ('has_registration_keyword', 'valid_corporate_number_checksum')
```

---

## 主要データ型

### `SourceSpan`
元のOCR入力におけるテキストスパン、座標情報、信頼度を保持します。

```python
@dataclass(frozen=True)
class SourceSpan:
    text: str
    start: int
    end: int
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    confidence: float | None = None
    engine: str | None = None
```

### `Edit`
テキスト正規化における1つの編集操作。監査証跡として保存されます。

```python
@dataclass(frozen=True)
class Edit:
    rule: str
    source: str
    replacement: str
    start: int
    end: int
```

### `Candidate[T]`
抽出されたフィールドの候補値。判定ステータスと根拠理由を持ちます。

```python
@dataclass(frozen=True)
class Candidate(Generic[T]):
    value: T
    source: SourceSpan
    edits: tuple[Edit, ...]
    status: Literal["exact", "normalized", "ambiguous", "invalid"]
    reasons: tuple[str, ...]
```

#### 判定ステータス (`Candidate.status`)
- `exact`: 原文のまま有効な値（カンマなし数字など）
- `normalized`: 非曖昧な正規化（全角半角変換、カンマ除去等）を経て有効な値
- `ambiguous`: 複数解釈が可能（2桁西暦、ピリオドによる桁区切りの疑い等）
- `invalid`: チェックデジット不一致、存在しない実在日など形式的に不正

---

## フィールド抽出機能一覧

| 関数名 | 抽出対象 | 主な対応内容・検証 |
|---|---|---|
| `find_amounts` | 金額 | 円表記（`¥`, `￥`, `円`）、3桁区切り、値引き・負数（`▲`, `△`, `-`, 会計括弧 `(1,000)`）、ピリオド・空白桁区切りの曖昧性検出、小数金額の `Decimal` 保持 |
| `find_dates` | 日付 | 西暦（4桁・2桁）、和暦（令和、平成、昭和、元年、略記 `R8.11.15`）、実在日検証（うるう年、存在しない日の除外） |
| `find_times` | 時刻 | 24時間表記（`17:30`, `17:30:15`）、日本語表記（`17時30分`）、コロンOCR揺れ（`;`, `.`） |
| `find_phone_numbers` | 電話番号 | 日本の固定電話、携帯電話（070/080/090）、IP電話（050）、フリーダイヤル（0120/0800）、ハイフン・空白除去 |
| `find_invoice_registration_numbers` | 適格請求書登録番号 | `T` + 13桁、国税庁法人番号チェックデジット（モジュラス9 交互ウェイト）検証 |
| `find_jan_codes` | JAN/EANコード | JAN-8 / JAN-13、GS1規格モジュラス10 ウェイト3チェックデジット検証 |

---

## プロファイル

`normalize_text` には以下のプロファイルを指定できます：

- `generic`: 基本的な全角半角統一、不可視文字・空白の正規化。
- `receipt`: レシート頻出の通貨記号、簡体字・異体字辞書（`圆`・`圓` -> `円`、`计` -> `計`、`总` -> `総` など）を適用。
- `invoice`: 請求書特有のインボイス用語・異体字辞書を適用。

---

## 開発とテスト

テストと型検査は以下のコマンドで実行できます。

```bash
# テストの実行
pytest

# カバレッジレポート
pytest --cov=jpdoc_normalize --cov-report=term-missing

# 型検査
mypy src
```

---

## 設計思想と非目標

本ライブラリは以下を「非目標」としています：

- **非目標**: OCR推論そのもの、画像傾き補正、レイアウト解析
- **非目標**: LLMによる「おそらくこういう意味だろう」という文脈補完
- **非目標**: 帳票全体を1回でJSON化するエンドツーエンド製品
- **非目標**: 「どの日付・どの金額を採用するか」という業務意思決定

詳細は [設計思想ドキュメント (docs/design_principles.md)](docs/design_principles.md) をご覧ください。

---

## ライセンス

[MIT License](LICENSE)
