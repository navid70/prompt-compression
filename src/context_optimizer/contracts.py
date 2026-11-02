"""Immutable public data contracts shared by host integrations and strategies."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


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
        if self.source_id is not None and not self.source_id.strip():
            raise ValueError("source_id must be non-empty when provided")
        if self.relevance_score is not None and not isfinite(self.relevance_score):
            raise ValueError("relevance_score must be finite when provided")


@dataclass(frozen=True, slots=True)
class OptimizationRequest:
    """An ordered set of eligible context segments and its exact token budget."""

    query: str
    segments: tuple[ContextSegment, ...]
    token_budget: int

    def __post_init__(self) -> None:
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

    def __post_init__(self) -> None:
        if self.min_input_tokens < 0:
            raise ValueError("min_input_tokens cannot be negative")
        if self.min_tokens_saved < 0:
            raise ValueError("min_tokens_saved cannot be negative")
        if not isfinite(self.min_reduction_ratio) or not 0.0 <= self.min_reduction_ratio < 1.0:
            raise ValueError("min_reduction_ratio must be finite and in [0.0, 1.0)")
        normalized_strategies = tuple(self.allowed_strategies)
        if any(not strategy.strip() for strategy in normalized_strategies):
            raise ValueError("allowed strategy names must be non-empty")
        object.__setattr__(self, "allowed_strategies", normalized_strategies)


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
        if self.original_tokens is not None and self.original_tokens < 0:
            raise ValueError("original_tokens cannot be negative")
        if self.optimized_tokens is not None and self.optimized_tokens < 0:
            raise ValueError("optimized_tokens cannot be negative")
        if not isfinite(self.latency_ms) or self.latency_ms < 0:
            raise ValueError("latency_ms must be finite and non-negative")
        object.__setattr__(self, "selected_segment_ids", tuple(self.selected_segment_ids))
