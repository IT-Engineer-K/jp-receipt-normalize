from __future__ import annotations

from collections.abc import Sequence

from jpdoc_normalize.models import Edit, NormalizedText, SourceSpan
from jpdoc_normalize.normalizer import ProfileType, normalize_text


def ensure_normalized(
    input_val: str | SourceSpan | NormalizedText,
    profile: ProfileType = "generic",
) -> NormalizedText:
    """Ensure the input is a NormalizedText object."""
    if isinstance(input_val, NormalizedText):
        return input_val
    elif isinstance(input_val, SourceSpan):
        return normalize_text(input_val, profile=profile)
    elif isinstance(input_val, str):
        return normalize_text(input_val, profile=profile)
    raise TypeError(f"Unsupported input type: {type(input_val)}")


def build_norm_to_source_spans(normalized: NormalizedText) -> list[tuple[int, int]]:
    """
    Build a mapping from each character index in normalized.text to its
    (abs_start, abs_end) in the original source coordinate space.
    """
    raw_text = normalized.source.text
    base_start = normalized.source.start
    edit_map = {e.start - base_start: e for e in normalized.edits}

    raw_spans: list[tuple[int, int]] = []
    raw_idx = 0

    while raw_idx < len(raw_text):
        if raw_idx in edit_map:
            e = edit_map[raw_idx]
            rep_len = len(e.replacement)
            for _ in range(rep_len):
                raw_spans.append((e.start, e.end))
            raw_idx = e.end - base_start
        else:
            raw_spans.append((base_start + raw_idx, base_start + raw_idx + 1))
            raw_idx += 1

    return raw_spans


def map_norm_range_to_source(
    norm_start: int,
    norm_end: int,
    normalized: NormalizedText,
    raw_spans: Sequence[tuple[int, int]] | None = None,
) -> tuple[int, int]:
    """
    Map a slice [norm_start, norm_end] in normalized.text to absolute (src_start, src_end)
    coordinates in normalized.source.
    """
    base_start = normalized.source.start
    spans = raw_spans if raw_spans is not None else build_norm_to_source_spans(normalized)

    if not spans:
        return base_start + norm_start, base_start + norm_end

    if norm_end <= norm_start:
        if norm_start < len(spans):
            pos = spans[norm_start][0]
        else:
            pos = spans[-1][1]
        return pos, pos

    if norm_start >= len(spans):
        pos = spans[-1][1]
        return pos, pos

    actual_start_idx = norm_start
    actual_end_idx = norm_end - 1 if norm_end - 1 < len(spans) else len(spans) - 1
    return spans[actual_start_idx][0], spans[actual_end_idx][1]


def make_extraction_edit(
    rule: str,
    norm_start: int,
    norm_end: int,
    replacement: str,
    normalized: NormalizedText,
    raw_spans: Sequence[tuple[int, int]] | None = None,
) -> Edit:
    """
    Create an Edit representing an extraction-stage transformation on
    normalized.text[norm_start:norm_end], mapped to absolute source coordinates.
    """
    src_start, src_end = map_norm_range_to_source(norm_start, norm_end, normalized, raw_spans)
    return Edit(
        rule=rule,
        source=normalized.text[norm_start:norm_end],
        replacement=replacement,
        start=src_start,
        end=src_end,
    )


def map_span_to_source(
    norm_start: int,
    norm_end: int,
    normalized: NormalizedText,
    extra_edits: Sequence[Edit] = (),
    raw_spans: Sequence[tuple[int, int]] | None = None,
) -> tuple[SourceSpan, tuple[Edit, ...]]:
    """
    Map an offset range [norm_start, norm_end] in normalized text back to original source span
    and collect relevant normalization and extraction edits within this range.
    """
    raw_text = normalized.source.text
    base_start = normalized.source.start
    spans = raw_spans if raw_spans is not None else build_norm_to_source_spans(normalized)

    if not spans or norm_start >= len(spans) or norm_end <= norm_start:
        src_start = base_start + norm_start
        src_end = base_start + norm_end
        src_text = raw_text[norm_start:norm_end]
    else:
        src_start, src_end = map_norm_range_to_source(norm_start, norm_end, normalized, spans)
        src_text = raw_text[src_start - base_start : src_end - base_start]

    relevant_edits: list[Edit] = []
    for e in normalized.edits:
        if not (e.end <= src_start or e.start >= src_end):
            relevant_edits.append(e)

    relevant_edits.extend(extra_edits)

    source_span = SourceSpan(
        text=src_text,
        start=src_start,
        end=src_end,
        page=normalized.source.page,
        bbox=normalized.source.bbox,
        confidence=normalized.source.confidence,
        engine=normalized.source.engine,
    )

    return source_span, tuple(relevant_edits)
