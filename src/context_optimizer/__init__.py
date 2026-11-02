"""Public contracts for the context optimizer package."""

from context_optimizer.contracts import (
    ContextSegment,
    OptimizationPolicy,
    OptimizationRequest,
    OptimizationResult,
)
from context_optimizer.optimizer import optimize_context
from context_optimizer.protocols import ContextRenderer, SegmentScorer, TokenCounter

__all__ = [
    "ContextRenderer",
    "ContextSegment",
    "OptimizationPolicy",
    "OptimizationRequest",
    "OptimizationResult",
    "SegmentScorer",
    "TokenCounter",
    "optimize_context",
]
