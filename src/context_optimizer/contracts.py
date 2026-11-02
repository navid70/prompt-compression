"""Immutable public data contracts shared by host integrations and strategies."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


def _nonempty_string(value: str, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _integer(value: int, name: str, minimum: int = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")


def _finite_number(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    try:
        finite = isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{name} must be finite")


def _string_tuple(values: tuple[str, ...], name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} must be a collection of strings")
    normalized = tuple(values)
    for value in normalized:
        _nonempty_string(value, name)
    return normalized


@dataclass(frozen=True, slots=True)
class ContextSegment:
    """A caller-approved, source-preserving unit of context."""

    id: str
    text: str
    source_id: str | None = None
    relevance_score: float | None = None
    pinned: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("segment id must be a non-empty string")
        if not isinstance(self.text, str):
            raise TypeError("segment text must be a string")
        if self.source_id is not None:
            _nonempty_string(self.source_id, "source_id")
        if self.relevance_score is not None:
            _finite_number(self.relevance_score, "relevance_score")
        if not isinstance(self.pinned, bool):
            raise TypeError("pinned must be a boolean")


@dataclass(frozen=True, slots=True)
class OptimizationRequest:
    """An ordered set of eligible context segments and its exact token budget."""

    query: str
    segments: tuple[ContextSegment, ...]
    token_budget: int

    def __post_init__(self) -> None:
        if not isinstance(self.query, str):
            raise TypeError("query must be a string")
        if isinstance(self.token_budget, bool) or not isinstance(self.token_budget, int):
            raise TypeError("token_budget must be an integer")
        if self.token_budget <= 0:
            raise ValueError("token_budget must be greater than zero")
        normalized_segments = tuple(self.segments)
        if any(not isinstance(segment, ContextSegment) for segment in normalized_segments):
            raise TypeError("segments must contain only ContextSegment instances")
        segment_ids = [segment.id for segment in normalized_segments]
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("segment ids must be unique within a request")
        object.__setattr__(self, "segments", normalized_segments)


@dataclass(frozen=True, slots=True)
class OptimizationPolicy:
    """Conservative runtime policy; optimization is disabled by default."""

    enabled: bool = False
    min_input_tokens: int = 256
    min_tokens_saved: int = 32
    min_reduction_ratio: float = 0.05
    allowed_strategies: tuple[str, ...] = ()
    max_segments: int | None = 256

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be a boolean")
        _integer(self.min_input_tokens, "min_input_tokens")
        _integer(self.min_tokens_saved, "min_tokens_saved")
        _finite_number(self.min_reduction_ratio, "min_reduction_ratio")
        if not 0.0 <= self.min_reduction_ratio < 1.0:
            raise ValueError("min_reduction_ratio must be finite and in [0.0, 1.0)")
        normalized_strategies = _string_tuple(self.allowed_strategies, "allowed_strategies")
        object.__setattr__(self, "allowed_strategies", normalized_strategies)
        if self.max_segments is not None:
            _integer(self.max_segments, "max_segments", minimum=1)


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    """Observable outcome; context=None tells the host to reuse its original request."""

    context: str | None
    selected_segment_ids: tuple[str, ...]
    original_tokens: int | None
    optimized_tokens: int | None
    applied: bool
    strategy: str
    reason_code: str
    latency_ms: float

    def __post_init__(self) -> None:
        if self.context is not None and not isinstance(self.context, str):
            raise TypeError("context must be a string or None")
        if self.original_tokens is not None:
            _integer(self.original_tokens, "original_tokens")
        if self.optimized_tokens is not None:
            _integer(self.optimized_tokens, "optimized_tokens")
        if not isinstance(self.applied, bool):
            raise TypeError("applied must be a boolean")
        _nonempty_string(self.strategy, "strategy")
        _nonempty_string(self.reason_code, "reason_code")
        _finite_number(self.latency_ms, "latency_ms")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must be finite and non-negative")
        ids = _string_tuple(self.selected_segment_ids, "selected_segment_ids")
        if len(ids) != len(set(ids)):
            raise ValueError("selected_segment_ids must be unique")
        object.__setattr__(self, "selected_segment_ids", ids)
