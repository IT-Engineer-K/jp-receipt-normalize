from __future__ import annotations

import datetime
import json
from decimal import Decimal

from jpdoc_normalize.models import Candidate, Edit, NormalizedText, SourceSpan


def test_models_json_serialization():
    """Verify all models can be serialized to JSON safely."""
    span = SourceSpan(
        text="テスト ￥100",
        start=0,
        end=7,
        page=1,
        bbox=(0.1, 0.2, 0.3, 0.4),
        confidence=0.98,
        engine="rapidocr",
    )
    edit = Edit(
        rule="normalize_space",
        source="　",
        replacement=" ",
        start=3,
        end=4,
    )
    norm = NormalizedText(
        text="テスト ¥100",
        source=span,
        edits=(edit,),
    )

    cand_int = Candidate(
        value=100,
        source=span,
        edits=(edit,),
        status="normalized",
        reasons=("has_currency_symbol",),
    )

    cand_date = Candidate(
        value=datetime.date(2026, 11, 15),
        source=span,
        edits=(),
        status="exact",
        reasons=("western_calendar",),
    )

    cand_time = Candidate(
        value=datetime.time(17, 30, 15),
        source=span,
        edits=(),
        status="exact",
        reasons=(),
    )

    cand_dec = Candidate(
        value=Decimal("12.50"),
        source=span,
        edits=(),
        status="ambiguous",
        reasons=("decimal_amount",),
    )

    # Convert to dict and JSON dumps
    dumped_norm = json.dumps(norm.to_dict())
    assert "rapidocr" in dumped_norm

    dumped_int = json.dumps(cand_int.to_dict())
    assert "100" in dumped_int

    dumped_date = json.dumps(cand_date.to_dict())
    assert "2026-11-15" in dumped_date

    dumped_time = json.dumps(cand_time.to_dict())
    assert "17:30:15" in dumped_time

    dumped_dec = json.dumps(cand_dec.to_dict())
    assert "12.50" in dumped_dec

    # Verify from_dict roundtrip preserves exact Python types
    restored_span = SourceSpan.from_dict(span.to_dict())
    assert restored_span == span

    restored_norm = NormalizedText.from_dict(norm.to_dict())
    assert restored_norm.text == norm.text
    assert restored_norm.source == norm.source

    restored_cand = Candidate.from_dict(cand_int.to_dict())
    assert restored_cand == cand_int

    restored_date = Candidate.from_dict(json.loads(dumped_date))
    assert restored_date == cand_date
    assert isinstance(restored_date.value, datetime.date)

    restored_time = Candidate.from_dict(json.loads(dumped_time))
    assert restored_time == cand_time
    assert isinstance(restored_time.value, datetime.time)

    restored_dec = Candidate.from_dict(json.loads(dumped_dec))
    assert restored_dec == cand_dec
    assert isinstance(restored_dec.value, Decimal)
