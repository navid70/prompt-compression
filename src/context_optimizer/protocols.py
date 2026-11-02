"""Small host-injected interfaces; implementations stay outside the core package."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from context_optimizer.contracts import ContextSegment


class TokenCounter(Protocol):
    """Counts tokens using the exact tokenizer for the target model."""

    def count(self, text: str, /) -> int:
        """Return the exact token count for the supplied rendered text."""


class ContextRenderer(Protocol):
    """Renders segments exactly as they will appear in the provider request."""

    def render(self, segments: Sequence[ContextSegment], /) -> str:
        """Return the final context string sent by the host application."""


class SegmentScorer(Protocol):
    """Ranks eligible segments without performing network or model calls."""

    def score(self, query: str, segments: Sequence[ContextSegment], /) -> Sequence[float]:
        """Return one deterministic relevance score per input segment."""