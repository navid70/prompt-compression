from dataclasses import FrozenInstanceError

import pytest

from context_optimizer import ContextSegment, OptimizationPolicy, OptimizationRequest


def test_context_segment_requires_non_empty_id() -> None:
    with pytest.raises(ValueError, match="segment id"):
        ContextSegment(id="  ", text="content")


def test_context_segment_rejects_non_finite_relevance_score() -> None:
    with pytest.raises(ValueError, match="finite"):
        ContextSegment(id="segment-1", text="content", relevance_score=float("nan"))


def test_context_segment_is_immutable() -> None:
    segment = ContextSegment(id="segment-1", text="source text")

    with pytest.raises(FrozenInstanceError):
        segment.text = "rewritten text"  # type: ignore[misc]


def test_request_normalizes_segments_and_preserves_order() -> None:
    first = ContextSegment(id="first", text="A")
    second = ContextSegment(id="second", text="B")

    request = OptimizationRequest(
        query="question",
        segments=[first, second],  # type: ignore[arg-type]
        token_budget=100,
    )

    assert request.segments == (first, second)
    assert tuple(segment.id for segment in request.segments) == ("first", "second")


def test_request_rejects_duplicate_segment_ids() -> None:
    first = ContextSegment(id="duplicate", text="A")
    second = ContextSegment(id="duplicate", text="B")

    with pytest.raises(ValueError, match="unique"):
        OptimizationRequest(query="question", segments=(first, second), token_budget=100)


@pytest.mark.parametrize("budget", [0, -1])
def test_request_requires_positive_budget(budget: int) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        OptimizationRequest(query="question", segments=(), token_budget=budget)


def test_request_rejects_boolean_budget() -> None:
    with pytest.raises(TypeError, match="integer"):
        OptimizationRequest(query="question", segments=(), token_budget=True)


def test_policy_is_disabled_by_default() -> None:
    assert OptimizationPolicy().enabled is False


def test_policy_rejects_invalid_reduction_ratio() -> None:
    with pytest.raises(ValueError, match="min_reduction_ratio"):
        OptimizationPolicy(min_reduction_ratio=1.0)


def test_policy_rejects_empty_strategy_names() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        OptimizationPolicy(allowed_strategies=("bm25", " "))
