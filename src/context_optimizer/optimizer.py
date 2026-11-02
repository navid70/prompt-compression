"""Deterministic, source-preserving selection with host-owned dependencies."""

from math import isfinite
from time import perf_counter

from context_optimizer.contracts import (
    ContextSegment,
    OptimizationPolicy,
    OptimizationRequest,
    OptimizationResult,
)
from context_optimizer.protocols import ContextRenderer, SegmentScorer, TokenCounter

_DEFAULT_POLICY = OptimizationPolicy()


def optimize_context(
    request: OptimizationRequest,
    *,
    token_counter: TokenCounter,
    renderer: ContextRenderer,
    scorer: SegmentScorer,
    policy: OptimizationPolicy = _DEFAULT_POLICY,
) -> OptimizationResult:
    """Greedily select whole segments using exact rendered candidate counts.

    Requires enabled=True and "greedy" in allowed_strategies. Higher scorer
    values rank first; ties follow input order. Only unpinned segments are
    scored. Dependencies receive immutable tuples of the original segments.

    On any bypass, reuse the original request. context=None means original
    rendering was skipped or failed; token counts remain None if unavailable.
    """
    started = perf_counter()
    original_context: str | None = None
    original_tokens: int | None = None
    failure_reason = "internal_error"

    def bypass(reason: str) -> OptimizationResult:
        return OptimizationResult(
            context=original_context,
            selected_segment_ids=tuple(segment.id for segment in request.segments),
            original_tokens=original_tokens,
            optimized_tokens=original_tokens,
            applied=False,
            strategy="none",
            reason_code=reason,
            latency_ms=(perf_counter() - started) * 1000,
        )

    def render(segments: tuple[ContextSegment, ...]) -> str:
        nonlocal failure_reason
        failure_reason = "renderer_error"
        text = renderer.render(segments)
        if not isinstance(text, str):
            raise TypeError("renderer must return a string")
        failure_reason = "internal_error"
        return text

    def count(text: str) -> int:
        nonlocal failure_reason
        failure_reason = "tokenizer_error"
        tokens = token_counter.count(text)
        if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
            raise ValueError("tokenizer must return a non-negative integer")
        failure_reason = "internal_error"
        return tokens

    try:
        if not policy.enabled:
            return bypass("disabled")
        if "greedy" not in policy.allowed_strategies:
            return bypass("strategy_not_allowed")
        if not request.segments:
            return bypass("empty_input")

        original_context = render(request.segments)
        original_tokens = count(original_context)
        if original_tokens < policy.min_input_tokens:
            return bypass("input_too_small")
        if original_tokens <= request.token_budget:
            return bypass("within_budget")

        selected = {index for index, segment in enumerate(request.segments) if segment.pinned}
        pinned = tuple(request.segments[index] for index in sorted(selected))
        selected_context = render(pinned)
        selected_tokens = count(selected_context)
        if selected_tokens > request.token_budget:
            return bypass(
                "pinned_content_exceeds_budget" if pinned else "rendered_context_exceeds_budget"
            )

        eligible_indices = tuple(
            index for index, segment in enumerate(request.segments) if not segment.pinned
        )
        eligible = tuple(request.segments[index] for index in eligible_indices)
        failure_reason = "scorer_error"
        scores = scorer.score(request.query, eligible)
        failure_reason = "invalid_scores"
        scores = tuple(scores)
        if len(scores) != len(eligible) or any(
            isinstance(score, bool) or not isinstance(score, (int, float)) or not isfinite(score)
            for score in scores
        ):
            return bypass("invalid_scores")
        failure_reason = "internal_error"
        ranked = sorted(range(len(eligible)), key=lambda index: (-scores[index], index))
        for rank_index in ranked:
            candidate_indices = selected | {eligible_indices[rank_index]}
            candidate = tuple(request.segments[index] for index in sorted(candidate_indices))
            candidate_context = render(candidate)
            candidate_tokens = count(candidate_context)
            if candidate_tokens <= request.token_budget:
                selected = candidate_indices
                selected_context = candidate_context
                selected_tokens = candidate_tokens

        saved = original_tokens - selected_tokens
        if (
            saved <= 0
            or saved < policy.min_tokens_saved
            or saved / original_tokens < policy.min_reduction_ratio
        ):
            return bypass("insufficient_savings")
        return OptimizationResult(
            context=selected_context,
            selected_segment_ids=tuple(request.segments[index].id for index in sorted(selected)),
            original_tokens=original_tokens,
            optimized_tokens=selected_tokens,
            applied=True,
            strategy="greedy",
            reason_code="optimized",
            latency_ms=(perf_counter() - started) * 1000,
        )
    except Exception:
        # Do not expose exception messages: host dependencies may include private input.
        return bypass(failure_reason)
