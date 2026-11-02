from collections.abc import Sequence

import pytest

from context_optimizer import (
    ContextSegment,
    OptimizationPolicy,
    OptimizationRequest,
    optimize_context,
)


class UnexpectedDependency:
    def render(self, segments: Sequence[ContextSegment], /) -> str:
        raise AssertionError("renderer must not be called")

    def count(self, text: str, /) -> int:
        raise AssertionError("tokenizer must not be called")

    def score(self, query: str, segments: Sequence[ContextSegment], /) -> Sequence[float]:
        raise AssertionError("scorer must not be called")


def test_disabled_preserves_request_without_calling_dependencies() -> None:
    segment = ContextSegment("a", "original", source_id="document", pinned=True)
    request = OptimizationRequest("question", (segment,), 1)
    dependency = UnexpectedDependency()

    result = optimize_context(
        request, token_counter=dependency, renderer=dependency, scorer=dependency
    )

    assert not result.applied
    assert result.reason_code == "disabled"
    assert result.context is None
    assert result.selected_segment_ids == ("a",)
    assert result.original_tokens is None
    assert result.optimized_tokens is None
    assert request.segments == (segment,)


class FramedRenderer:
    def render(self, segments: Sequence[ContextSegment], /) -> str:
        return "[" + "|".join(segment.text for segment in segments) + "]"


class CharacterCounter:
    """Exact tokenizer for the synthetic test language: one token per character."""

    def count(self, text: str, /) -> int:
        return len(text)


class EqualScorer:
    def score(self, query: str, segments: Sequence[ContextSegment], /) -> Sequence[float]:
        return [1.0] * len(segments)


@pytest.fixture
def enabled_policy() -> OptimizationPolicy:
    return OptimizationPolicy(
        enabled=True,
        min_input_tokens=0,
        min_tokens_saved=1,
        min_reduction_ratio=0,
        allowed_strategies=("greedy",),
    )


def test_selection_preserves_pins_order_provenance_and_deterministic_ties() -> None:
    segments = (
        ContextSegment("a", "AA", source_id="source-a", relevance_score=0.1),
        ContextSegment("large", "too large to fit"),
        ContextSegment("b", "B", source_id="source-b"),
        ContextSegment("pin", "P", source_id="source-pin", pinned=True),
    )
    request = OptimizationRequest("question", segments, 6)
    policy = OptimizationPolicy(
        enabled=True,
        min_input_tokens=0,
        min_tokens_saved=1,
        min_reduction_ratio=0,
        allowed_strategies=("greedy",),
    )

    class Scorer(EqualScorer):
        def score(self, query: str, candidate: Sequence[ContextSegment], /) -> Sequence[float]:
            assert tuple(candidate) == segments[:3]
            return super().score(query, candidate)

    for _ in range(2):
        result = optimize_context(
            request,
            policy=policy,
            token_counter=CharacterCounter(),
            renderer=FramedRenderer(),
            scorer=Scorer(),
        )
        assert result.applied
        assert result.context == "[AA|P]"
        assert result.selected_segment_ids == ("a", "pin")
        assert result.optimized_tokens == 6
        assert result.strategy == "greedy"
        assert result.reason_code == "optimized"
    assert request.segments is segments
    assert segments[0] == ContextSegment("a", "AA", source_id="source-a", relevance_score=0.1)


def test_pinned_overflow_returns_original_without_scoring(
    enabled_policy: OptimizationPolicy,
) -> None:
    request = OptimizationRequest(
        "question", (ContextSegment("a", "A"), ContextSegment("p", "PIN", pinned=True)), 4
    )
    result = optimize_context(
        request,
        policy=enabled_policy,
        renderer=FramedRenderer(),
        token_counter=CharacterCounter(),
        scorer=UnexpectedDependency(),
    )
    assert not result.applied
    assert result.reason_code == "pinned_content_exceeds_budget"
    assert result.context == "[A|PIN]"
    assert result.selected_segment_ids == ("a", "p")
    assert result.original_tokens == result.optimized_tokens == 7


def test_ranking_and_exact_candidate_counts_use_original_segment_objects(
    enabled_policy: OptimizationPolicy,
) -> None:
    segments = (
        ContextSegment("a", "A", source_id="source-a"),
        ContextSegment("b", "B", source_id="source-b"),
        ContextSegment("c", "C", source_id="source-c"),
    )
    rendered: list[tuple[str, ...]] = []
    counted: list[str] = []

    class Renderer:
        def render(self, candidate: Sequence[ContextSegment], /) -> str:
            assert all(any(segment is source for source in segments) for segment in candidate)
            rendered.append(tuple(segment.id for segment in candidate))
            return "|".join(segment.text for segment in candidate)

    class Counter:
        def count(self, text: str, /) -> int:
            counted.append(text)
            # Boundary effects make A+B larger than the sum of their individual counts.
            return {"A|B|C": 20, "": 0, "B": 2, "B|C": 5, "A|B": 12}[text]

    class Scorer:
        def score(self, query: str, candidate: Sequence[ContextSegment], /) -> Sequence[float]:
            assert query == "question"
            assert tuple(candidate) == segments
            return [2.0, 3.0, 1.0]

    request = OptimizationRequest("question", segments, 5)
    result = optimize_context(
        request,
        policy=enabled_policy,
        renderer=Renderer(),
        token_counter=Counter(),
        scorer=Scorer(),
    )
    assert result.applied
    assert result.context == "B|C"
    assert result.selected_segment_ids == ("b", "c")
    assert result.original_tokens == 20
    assert result.optimized_tokens == 5
    assert rendered == [("a", "b", "c"), (), ("b",), ("a", "b"), ("b", "c")]
    assert counted == ["A|B|C", "", "B", "A|B", "B|C"]


@pytest.mark.parametrize(
    ("policy", "budget", "reason"),
    [
        (OptimizationPolicy(enabled=True), 3, "strategy_not_allowed"),
        (
            OptimizationPolicy(enabled=True, allowed_strategies=("greedy",)),
            3,
            "input_too_small",
        ),
        (
            OptimizationPolicy(enabled=True, min_input_tokens=0, allowed_strategies=("greedy",)),
            10,
            "within_budget",
        ),
    ],
)
def test_policy_bypasses_do_not_score(policy: OptimizationPolicy, budget: int, reason: str) -> None:
    request = OptimizationRequest("q", (ContextSegment("a", "A"), ContextSegment("b", "B")), budget)
    result = optimize_context(
        request,
        policy=policy,
        renderer=FramedRenderer(),
        token_counter=CharacterCounter(),
        scorer=UnexpectedDependency(),
    )
    assert not result.applied
    assert result.reason_code == reason
    assert result.selected_segment_ids == ("a", "b")
    assert result.context in (None, "[A|B]")


@pytest.mark.parametrize(
    ("minimum_tokens", "minimum_ratio", "applied"), [(2, 0.4, True), (3, 0, False), (0, 0.5, False)]
)
def test_savings_thresholds_are_enforced(
    minimum_tokens: int, minimum_ratio: float, applied: bool
) -> None:
    request = OptimizationRequest("q", (ContextSegment("a", "A"), ContextSegment("b", "B")), 3)
    result = optimize_context(
        request,
        policy=OptimizationPolicy(
            enabled=True,
            min_input_tokens=5,
            min_tokens_saved=minimum_tokens,
            min_reduction_ratio=minimum_ratio,
            allowed_strategies=("greedy",),
        ),
        renderer=FramedRenderer(),
        token_counter=CharacterCounter(),
        scorer=EqualScorer(),
    )
    assert result.applied is applied
    assert result.reason_code == ("optimized" if applied else "insufficient_savings")
    assert result.context == ("[A]" if applied else "[A|B]")
    assert result.selected_segment_ids == (("a",) if applied else ("a", "b"))


@pytest.mark.parametrize(
    "scores",
    [
        [],
        [1.0],
        [1.0, 2.0, 3.0],
        [float("nan"), 1],
        [1, float("inf")],
        [1, float("-inf")],
        [True, 1],
        ["1", 1],
    ],
)
def test_invalid_scores_fail_open(
    scores: Sequence[float], enabled_policy: OptimizationPolicy
) -> None:
    class Scorer:
        def score(self, query: str, segments: Sequence[ContextSegment], /) -> Sequence[float]:
            return scores

    request = OptimizationRequest("q", (ContextSegment("a", "A"), ContextSegment("b", "B")), 3)
    result = optimize_context(
        request,
        policy=enabled_policy,
        renderer=FramedRenderer(),
        token_counter=CharacterCounter(),
        scorer=Scorer(),
    )
    assert not result.applied
    assert result.reason_code == "invalid_scores"
    assert result.context == "[A|B]"
    assert result.selected_segment_ids == ("a", "b")


@pytest.mark.parametrize(
    "failure", ["renderer", "candidate_renderer", "tokenizer", "candidate_tokenizer", "scorer"]
)
def test_dependency_errors_preserve_original(
    failure: str, enabled_policy: OptimizationPolicy
) -> None:
    class Renderer(FramedRenderer):
        def render(self, segments: Sequence[ContextSegment], /) -> str:
            if failure == "renderer" or (failure == "candidate_renderer" and len(segments) == 2):
                raise RuntimeError("private content must not escape")
            return super().render(segments)

    class Counter(CharacterCounter):
        def count(self, text: str, /) -> int:
            if failure == "tokenizer" or (failure == "candidate_tokenizer" and text == "[A|B]"):
                raise RuntimeError("private content must not escape")
            return super().count(text)

    class Scorer(EqualScorer):
        def score(self, query: str, segments: Sequence[ContextSegment], /) -> Sequence[float]:
            if failure == "scorer":
                raise RuntimeError("private content must not escape")
            return super().score(query, segments)

    request = OptimizationRequest(
        "q", (ContextSegment("a", "A"), ContextSegment("b", "B"), ContextSegment("c", "C")), 3
    )
    result = optimize_context(
        request,
        policy=enabled_policy,
        renderer=Renderer(),
        token_counter=Counter(),
        scorer=Scorer(),
    )
    assert not result.applied
    assert result.reason_code == failure.removeprefix("candidate_") + "_error"
    assert result.context == (None if failure == "renderer" else "[A|B|C]")
    assert result.selected_segment_ids == ("a", "b", "c")
    expected_tokens = None if failure in ("renderer", "tokenizer") else 7
    assert result.original_tokens == result.optimized_tokens == expected_tokens
    assert result.latency_ms >= 0


def test_empty_input_skips_dependencies(enabled_policy: OptimizationPolicy) -> None:
    dependency = UnexpectedDependency()
    result = optimize_context(
        OptimizationRequest("q", (), 10),
        policy=enabled_policy,
        renderer=dependency,
        token_counter=dependency,
        scorer=dependency,
    )
    assert not result.applied
    assert result.reason_code == "empty_input"
    assert result.context is None
    assert result.selected_segment_ids == ()
