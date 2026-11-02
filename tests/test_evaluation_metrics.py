import json
from copy import deepcopy
from pathlib import Path

import pytest

from benchmarks.dataset import load_dataset
from benchmarks.metrics import measure

FIXTURE = Path(__file__).resolve().parents[1] / "benchmarks/fixtures/synthetic_v1.json"


def test_dataset_has_independent_scores_and_labels():
    cases = load_dataset(FIXTURE)
    assert len(cases) >= 11
    assert len({case.id for case in cases}) == len(cases)
    low = next(case for case in cases if case.id == "low_rank_relevant")
    assert low.predicted_scores == (0.1, 0.9)
    assert tuple(label.relevance for label in low.judgments) == (3, 0)
    assert all(segment.relevance_score is None for segment in low.request.segments)
    assert all(segment.source_id for case in cases for segment in case.request.segments)


@pytest.mark.parametrize(
    "mutation",
    [
        "version",
        "duplicate_case",
        "duplicate_segment",
        "nan_score",
        "negative_grade",
        "bool_grade",
        "missing_score",
        "bad_pin",
        "bad_critical",
        "bad_budget",
        "unknown",
        "empty_dataset",
        "bad_query",
        "bad_policy",
        "bad_source",
    ],
)
def test_rejects_invalid_dataset(tmp_path, mutation):
    obj = json.loads(FIXTURE.read_text(encoding="utf-8"))
    case = obj["cases"][0]
    segment = case["segments"][0]
    if mutation == "version":
        obj["schema_version"] = 2
    elif mutation == "duplicate_case":
        obj["cases"].append(deepcopy(case))
    elif mutation == "duplicate_segment":
        case["segments"].append(deepcopy(segment))
    elif mutation == "nan_score":
        segment["predicted_score"] = float("nan")
    elif mutation == "negative_grade":
        segment["relevance"] = -1
    elif mutation == "bool_grade":
        segment["relevance"] = True
    elif mutation == "missing_score":
        del segment["predicted_score"]
    elif mutation == "bad_pin":
        segment["pinned"] = "false"
    elif mutation == "bad_critical":
        segment["critical"] = 1
    elif mutation == "bad_budget":
        case["token_budget"] = True
    elif mutation == "unknown":
        segment["answer"] = "leaked label"
    elif mutation == "empty_dataset":
        obj["cases"] = []
    elif mutation == "bad_query":
        case["query"] = []
    elif mutation == "bad_policy":
        case["policy"] = {"min_tokens_saved": True}
    elif mutation == "bad_source":
        segment["source_id"] = ""
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(obj), encoding="utf-8")
    with pytest.raises(ValueError):
        load_dataset(path)


def test_retention_reduction_and_critical_loss_are_independent():
    case = next(c for c in load_dataset(FIXTURE) if c.id == "critical_low_rank")
    row = measure(case, ("aside",), original_tokens=16, optimized_tokens=8, applied=True)
    assert row["tokens_saved"] == 8
    assert row["reduction_ratio"] == 0.5
    assert row["weighted_relevance_recall"] == 0
    assert row["critical_retention"] == 0
    assert row["omitted_relevant_ids"] == ["answer"]
    assert row["omitted_critical_ids"] == ["answer"]
    assert row["omitted_relevant_segments"] == row["omitted_critical_segments"] == 1
    assert row["retained_segments"] == 1
    assert row["original_segments"] == 2
    assert row["budget_compliant"] is True
    assert row["correctness_failure"] is False


def test_weighted_recall_uses_grades_not_counts():
    case = next(c for c in load_dataset(FIXTURE) if c.id == "graded")
    row = measure(case, ("a", "b"), original_tokens=16, optimized_tokens=11, applied=True)
    assert row["weighted_relevance_recall"] == pytest.approx(5 / 6)
    assert row["critical_retention"] is None
    assert row["reduction_ratio"] == pytest.approx(5 / 16)


def test_zero_denominators_are_unavailable():
    case = next(c for c in load_dataset(FIXTURE) if c.id == "empty")
    row = measure(case, (), original_tokens=0, optimized_tokens=0, applied=False)
    assert row["reduction_ratio"] is None
    assert row["weighted_relevance_recall"] is None
    assert row["critical_retention"] is None
    assert row["no_token_benefit"] is True


@pytest.mark.parametrize("applied", [False, True])
def test_budget_excess_is_correctness_failure_only_when_applied(applied):
    case = next(c for c in load_dataset(FIXTURE) if c.id == "pinned_overflow")
    row = measure(
        case,
        tuple(s.id for s in case.request.segments),
        original_tokens=30,
        optimized_tokens=30,
        applied=applied,
    )
    assert row["budget_compliant"] is False
    assert row["correctness_failure"] is applied


@pytest.mark.parametrize("ids", [("missing",), ("a", "a"), ("b", "a")])
def test_metrics_reject_unknown_duplicate_or_reordered_ids(ids):
    case = next(c for c in load_dataset(FIXTURE) if c.id == "graded")
    with pytest.raises(ValueError):
        measure(case, ids, original_tokens=16, optimized_tokens=11, applied=True)
