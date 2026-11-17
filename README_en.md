# jp-receipt-normalize

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Typing: Typed](https://img.shields.io/badge/typing-typed-green.svg)](https://peps.python.org/pep-0561/)

**Auditable Normalization and Candidate Extraction for Japanese Document OCR**

[Japanese Documentation (README.md)](https://github.com/IT-Engineer-K/jp-receipt-normalize/blob/main/README.md) | [Design Principles (docs/design_principles.md)](https://github.com/IT-Engineer-K/jp-receipt-normalize/blob/main/docs/design_principles.md)

---

## Overview

When processing Japanese receipts, invoices, and financial documents with OCR, text often suffers from wide character variations, CJK Han glyph variants (Simplified Chinese characters leaking into Japanese OCR outputs), punctuation inconsistencies, and ambiguous numbers.

In automated business workflows (e.g. accounting, ERP, tax filing), silent auto-corrections carry risk. A guess that turns an ambiguous character into the wrong digit can lead to incorrect invoices or tax reports.

`jp-receipt-normalize` does not contain an OCR engine or LLM. It is an auditable post-OCR processing component with no external dependencies. It preserves raw strings, bounding boxes, character offsets, the edit rules applied, and reasons for ambiguity.

### Key Features

1. **Auditability**:
   Each transformation is recorded as an `Edit(rule, source, replacement, start, end)`, so character offsets can be traced back to the raw OCR text.
2. **No Silent Corrections**:
   Ambiguous character replacements (such as letter `O` vs digit `0`, or `1.840` as period-thousands-separator vs decimal) are not committed automatically; they are returned with `status="ambiguous"` and reason tags.
3. **Japanese Document Field Extractors**:
   - **Amounts**: Japanese Yen (`¥`, `￥`, `円`), negative amounts (▲, △, `-`, accounting parentheses `(1,000)`), discounts, tax contexts.
   - **Dates**: Western calendar (4-digit and 2-digit) and Japanese Wareki (令和, 平成, 昭和, 元年), validated against the real calendar including leap years.
   - **Times**: 24-hour representations, Japanese characters (`17時30分`), OCR colon misreads (`;`, `.`).
   - **Phone Numbers**: Japanese landlines, mobile (`070`, `080`, `090`), IP phones (`050`), toll-free (`0120`, `0800`), navidial (`0570`).
   - **Qualified Invoice Issuer Registration Numbers**: `T` + 13 digits with Japanese National Tax Agency (NTA) corporate number check digit verification.
   - **JAN/EAN Codes**: 8-digit and 13-digit barcodes with GS1 Modulus 10 Weight 3 check digit verification.
4. **No Network Access & No External Dependencies**:
   Built mainly on the Python standard library. Output is deterministic.
5. **JSON Serialization & Type Hints**:
   Includes `.to_dict()` and `py.typed`; checked with `mypy --strict`.

---

## Installation

```bash
pip install jp-receipt-normalize
```

---

## Quickstart

```python
from jpdoc_normalize import normalize_text
from jpdoc_normalize.fields import (
    find_amounts,
    find_dates,
    find_invoice_registration_numbers,
    find_phone_numbers,
)

# 1. Auditable text normalization
ocr_text = "合 計　￥1,８４０"
normalized = normalize_text(ocr_text, profile="receipt")

print(normalized.text)
# => "合 計 ￥1,840"

# Inspect transformation edits
for edit in normalized.edits:
    print(f"Rule: {edit.rule}, {edit.source!r} -> {edit.replacement!r} [{edit.start}:{edit.end}]")

# 2. Extract money amounts
amounts = find_amounts(normalized)
print(amounts[0].value, amounts[0].status, amounts[0].reasons)
# => 1840 normalized ('has_currency_symbol',)

# 3. Extract Invoice Registration Number with check digit validation
registrations = find_invoice_registration_numbers("登録番号 T７１２３４５６７８９０１２")
for candidate in registrations:
    print(candidate.value, candidate.status, candidate.reasons)
# => T7123456789012 normalized ('has_registration_keyword', 'valid_corporate_number_checksum')
```

---

## Core Data Models

- **`SourceSpan`**: Holds raw OCR string, coordinates, bounding box (`bbox`), and confidence.
- **`Edit`**: Represents a single immutable text substitution with rule name and character range.
- **`Candidate[T]`**: Extracted candidate value with `source`, `edits`, `status` (`exact`, `normalized`, `ambiguous`, `invalid`), and `reasons`.

---

## Non-Goals

`jp-receipt-normalize` does not cover:
- OCR inference, image rotation, and layout analysis.
- LLM-based contextual completion.
- End-to-end receipt-to-JSON business assumptions (e.g. deciding which of multiple dates is the due date).

---

## License

[MIT License](https://github.com/IT-Engineer-K/jp-receipt-normalize/blob/main/LICENSE)
