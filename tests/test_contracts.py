from dataclasses import FrozenInstanceError

import pytest

from context_optimizer import (
    ContextSegment,
    OptimizationPolicy,
    OptimizationRequest,
    OptimizationResult,
)


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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pinned", "false"),
        ("pinned", 0),
        ("source_id", 42),
        ("relevance_score", True),
        ("relevance_score", "0.5"),
    ],
)
def test_segment_rejects_malformed_typed_fields(field, value):
    with pytest.raises(TypeError, match=field):
        ContextSegment("a", "source", **{field: value})


@pytest.mark.parametrize("query", [None, 123, []])
def test_request_rejects_non_string_query(query):
    with pytest.raises(TypeError, match="query"):
        OptimizationRequest(query, (), 10)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("enabled", "false"),
        ("enabled", 1),
        ("min_input_tokens", True),
        ("min_input_tokens", 1.5),
        ("min_tokens_saved", False),
        ("min_tokens_saved", float("nan")),
        ("min_reduction_ratio", True),
        ("min_reduction_ratio", "0.1"),
        ("allowed_strategies", "greedy"),
        ("allowed_strategies", (123,)),
    ],
)
def test_policy_rejects_malformed_typed_fields(field, value):
    with pytest.raises(TypeError, match=field):
        OptimizationPolicy(**{field: value})


@pytest.mark.parametrize("field", ["relevance_score", "min_reduction_ratio", "latency_ms"])
def test_unrepresentable_finite_numbers_have_static_validation_error(field):
    with pytest.raises(ValueError, match="finite"):
        if field == "relevance_score":
            ContextSegment("a", "source", relevance_score=10**1000)
        elif field == "min_reduction_ratio":
            OptimizationPolicy(min_reduction_ratio=10**1000)
        else:
            OptimizationResult(None, (), None, None, False, "none", "disabled", 10**1000)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("context", []),
        ("original_tokens", True),
        ("original_tokens", 1.5),
        ("optimized_tokens", "1"),
        ("optimized_tokens", float("nan")),
        ("applied", "false"),
        ("latency_ms", True),
        ("strategy", 123),
        ("reason_code", None),
        ("selected_segment_ids", "abc"),
        ("selected_segment_ids", (123,)),
    ],
)
def test_result_rejects_malformed_typed_fields(field, value):
    fields = dict(
        context=None,
        selected_segment_ids=(),
        original_tokens=None,
        optimized_tokens=None,
        applied=False,
        strategy="none",
        reason_code="disabled",
        latency_ms=0,
    )
    fields[field] = value
    with pytest.raises(TypeError, match=field):
        OptimizationResult(**fields)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("selected_segment_ids", ("a", "a")),
        ("selected_segment_ids", (" ",)),
        ("strategy", ""),
        ("reason_code", " "),
    ],
)
def test_result_rejects_ambiguous_identifiers(field, value):
    fields = dict(
        context=None,
        selected_segment_ids=(),
        original_tokens=None,
        optimized_tokens=None,
        applied=False,
        strategy="none",
        reason_code="disabled",
        latency_ms=0,
    )
    fields[field] = value
    with pytest.raises(ValueError, match=field):
        OptimizationResult(**fields)


def test_contract_normalization_detaches_mutable_collections():
    strategies = ["greedy"]
    ids = ["a"]
    policy = OptimizationPolicy(allowed_strategies=strategies)
    result = OptimizationResult("source", ids, 6, 6, False, "none", "within_budget", 0)
    strategies.clear()
    ids.clear()
    assert policy.allowed_strategies == ("greedy",)
    assert result.selected_segment_ids == ("a",)


@pytest.mark.parametrize("value", [True, 1.5, "256"])
def test_segment_limit_requires_integer_or_none(value):
    with pytest.raises(TypeError, match="max_segments"):
        OptimizationPolicy(max_segments=value)


@pytest.mark.parametrize("value", [0, -1])
def test_segment_limit_requires_positive_value(value):
    with pytest.raises(ValueError, match="max_segments"):
        OptimizationPolicy(max_segments=value)
