from __future__ import annotations

import json
from pathlib import Path

from jpdoc_normalize import normalize_text
from jpdoc_normalize.fields import (
    find_amounts,
    find_dates,
    find_invoice_registration_numbers,
    find_jan_codes,
    find_phone_numbers,
    find_times,
)


def test_synthetic_receipt_fixtures():
    """Verify end-to-end extraction on synthetic document fixtures."""
    fixtures_path = Path(__file__).parent / "fixtures" / "synthetic_receipts.json"
    with open(fixtures_path, encoding="utf-8") as f:
        fixtures = json.load(f)

    for item in fixtures:
        raw_text = item["ocr_text"]
        expected = item["expected"]

        normalized = normalize_text(raw_text, profile="receipt")

        if "amounts" in expected:
            amt_cands = find_amounts(normalized)
            actual_amounts = [c.value for c in amt_cands]
            assert actual_amounts == expected["amounts"], (
                f"Failed amounts for {item['id']}: {actual_amounts}"
            )

        if "dates" in expected:
            date_cands = find_dates(normalized)
            actual_dates = [c.value.isoformat() for c in date_cands if c.value is not None]
            assert actual_dates == expected["dates"], (
                f"Failed dates for {item['id']}: {actual_dates}"
            )

        if "times" in expected:
            time_cands = find_times(normalized)
            actual_times = [c.value.isoformat() for c in time_cands if c.value is not None]
            assert actual_times == expected["times"], (
                f"Failed times for {item['id']}: {actual_times}"
            )

        if "phones" in expected:
            phone_cands = find_phone_numbers(normalized)
            actual_phones = [c.value for c in phone_cands]
            assert actual_phones == expected["phones"], (
                f"Failed phones for {item['id']}: {actual_phones}"
            )

        if "registration_numbers" in expected:
            reg_cands = find_invoice_registration_numbers(normalized)
            actual_regs = [c.value for c in reg_cands]
            assert actual_regs == expected["registration_numbers"], (
                f"Failed regs for {item['id']}: {actual_regs}"
            )

        if "jan_codes" in expected:
            jan_cands = find_jan_codes(normalized)
            actual_jans = [c.value for c in jan_cands]
            assert actual_jans == expected["jan_codes"], (
                f"Failed jans for {item['id']}: {actual_jans}"
            )
