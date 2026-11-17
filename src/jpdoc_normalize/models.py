from __future__ import annotations

import datetime
import re
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Generic, Literal, TypeVar

T = TypeVar("T")

CandidateStatus = Literal["exact", "normalized", "ambiguous", "invalid"]


@dataclass(frozen=True)
class SourceSpan:
    text: str
    start: int
    end: int
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    confidence: float | None = None
    engine: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "page": self.page,
            "bbox": list(self.bbox) if self.bbox is not None else None,
            "confidence": self.confidence,
            "engine": self.engine,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceSpan:
        bbox_raw = data.get("bbox")
        bbox = tuple(bbox_raw) if bbox_raw is not None else None
        return cls(
            text=data["text"],
            start=data["start"],
            end=data["end"],
            page=data.get("page"),
            bbox=bbox,
            confidence=data.get("confidence"),
            engine=data.get("engine"),
        )


@dataclass(frozen=True)
class Edit:
    rule: str
    source: str
    replacement: str
    start: int
    end: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Edit:
        return cls(
            rule=data["rule"],
            source=data["source"],
            replacement=data["replacement"],
            start=data["start"],
            end=data["end"],
        )


@dataclass(frozen=True)
class NormalizedText:
    text: str
    source: SourceSpan
    edits: tuple[Edit, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "source": self.source.to_dict(),
            "edits": [edit.to_dict() for edit in self.edits],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NormalizedText:
        return cls(
            text=data["text"],
            source=SourceSpan.from_dict(data["source"]),
            edits=tuple(Edit.from_dict(e) for e in data.get("edits", [])),
        )


@dataclass(frozen=True)
class Candidate(Generic[T]):
    value: T
    source: SourceSpan
    edits: tuple[Edit, ...]
    status: CandidateStatus
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        val = self.value
        if isinstance(val, datetime.date) or isinstance(val, datetime.time):
            val_out: Any = val.isoformat()
        elif isinstance(val, Decimal):
            val_out = str(val)
        else:
            val_out = val

        return {
            "value": val_out,
            "source": self.source.to_dict(),
            "edits": [edit.to_dict() for edit in self.edits],
            "status": self.status,
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Candidate[Any]:
        raw_val = data["value"]
        val: Any = raw_val
        if isinstance(raw_val, str):
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_val):
                try:
                    val = datetime.date.fromisoformat(raw_val)
                except ValueError:
                    val = raw_val
            elif re.fullmatch(r"\d{2}:\d{2}:\d{2}(?:\.\d+)?", raw_val):
                try:
                    val = datetime.time.fromisoformat(raw_val)
                except ValueError:
                    val = raw_val
            elif re.fullmatch(r"-?\d+\.\d+", raw_val):
                val = Decimal(raw_val)

        return cls(
            value=val,
            source=SourceSpan.from_dict(data["source"]),
            edits=tuple(Edit.from_dict(e) for e in data.get("edits", [])),
            status=data["status"],
            reasons=tuple(data.get("reasons", [])),
        )
