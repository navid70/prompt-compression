import json
import subprocess
import sys
from dataclasses import replace

import pytest

from benchmarks.dataset import DEFAULT_DATASET, load_dataset
from benchmarks.runner import FixtureScorer, SyntheticCounter, SyntheticRenderer, run_benchmark


def by_id(report, perspective, case_id):
    return next(row for row in report["cases"][perspective] if row["case_id"] == case_id)


def test_actual_optimizer_baselines_and_invocation_counts():
    report = run_benchmark(repetitions=2, warmups=0)
    full = by_id(report, "no_optimization", "critical_low_rank")
    current = by_id(report, "current_greedy", "critical_low_rank")
    oracle = by_id(report, "oracle_ranked_greedy", "critical_low_rank")
    assert full["selected_ids"] == ["answer", "aside"]
    assert full["tokens_saved"] == 0
    assert full["weighted_relevance_recall"] == 1
    assert full["outcome"] == "baseline"
    assert current["selected_ids"] == ["aside"]
    assert current["omitted_critical_ids"] == ["answer"]
    assert current["critical_retention"] == 0
    assert oracle["selected_ids"] == ["answer"]
    assert oracle["critical_retention"] == 1
    assert current["original_tokens"] == 16
    assert current["optimized_tokens"] == 8
    assert current["dependency_calls"] == {"renderer": 4, "token_counter": 4, "scorer": 1}
    summary = report["aggregate"]["current_greedy"]
    assert summary["omitted_critical_segments"] == 1
    assert summary["critical_loss_cases"] == ["critical_low_rank"]
    assert summary["applied_correctness_failures"] == 0
    assert report["measurements"]["real_tokenizer"] is None
    assert report["measurements"]["net_monetary_savings"] is None


@pytest.mark.parametrize(
    ("case_id", "reason"),
    [
        ("within_budget", "within_budget"),
        ("pinned_overflow", "pinned_content_exceeds_budget"),
        ("insufficient_savings", "insufficient_savings"),
        ("empty", "empty_input"),
        ("disabled", "disabled"),
    ],
)
def test_bypasses_preserve_full_context_and_measure_it_even_if_core_skips_counts(case_id, reason):
    report = run_benchmark(repetitions=1, warmups=0)
    full = by_id(report, "no_optimization", case_id)
    current = by_id(report, "current_greedy", case_id)
    assert current["outcome"] == "bypassed"
    assert current["reason_code"] == reason
    assert current["selected_ids"] == full["selected_ids"]
    assert current["original_tokens"] == current["optimized_tokens"] == full["original_tokens"]
    assert current["no_token_benefit"] is True
    if case_id == "disabled":
        assert current["dependency_calls"] == {"renderer": 0, "token_counter": 0, "scorer": 0}
        assert current["original_tokens"] > 0


def test_oracle_is_not_global_optimum_and_rendering_is_not_additive():
    report = run_benchmark(repetitions=1, warmups=0)
    current = by_id(report, "current_greedy", "size_competition")
    oracle = by_id(report, "oracle_ranked_greedy", "size_competition")
    assert current["selected_ids"] == ["east", "gate"]
    assert current["weighted_relevance_recall"] == pytest.approx(4 / 7)
    assert oracle["selected_ids"] == ["large"]
    assert oracle["weighted_relevance_recall"] == pytest.approx(3 / 7)
    overhead = by_id(report, "current_greedy", "render_overhead")
    assert overhead["original_tokens"] == 7
    assert overhead["optimized_tokens"] == 4
    assert overhead["selected_ids"] == ["a"]
    assert by_id(report, "current_greedy", "ties")["selected_ids"] == ["old"]


def test_predicted_scores_do_not_change_when_ground_truth_changes(tmp_path):
    raw = json.loads(DEFAULT_DATASET.read_text())
    low = next(case for case in raw["cases"] if case["id"] == "low_rank_relevant")
    low["segments"][0]["relevance"] = 0
    low["segments"][1]["relevance"] = 8
    low["segments"][1]["critical"] = True
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    first = run_benchmark(repetitions=1, warmups=0)
    second = run_benchmark(path, repetitions=1, warmups=0)
    a = by_id(first, "current_greedy", "low_rank_relevant")
    b = by_id(second, "current_greedy", "low_rank_relevant")
    assert a["selected_ids"] == b["selected_ids"] == ["aside"]
    assert a["weighted_relevance_recall"] == 0
    assert b["weighted_relevance_recall"] == 1
    scorer = FixtureScorer({"answer": 0.1, "aside": 0.9})
    case = next(c for c in load_dataset() if c.id == "low_rank_relevant")
    assert scorer.score(case.request.query, case.request.segments) == (0.1, 0.9)


def test_deterministic_report_excludes_only_timing_and_does_not_emit_source_text():
    first = run_benchmark(repetitions=3, warmups=1)
    second = run_benchmark(repetitions=3, warmups=1)
    timing = first.pop("timing")
    second.pop("timing")
    assert first == second
    assert timing["current_greedy"]["aggregate"]["samples"] == 42
    assert timing["no_optimization"] is None
    encoded = json.dumps(first, allow_nan=False)
    assert "Answer." not in encoded
    assert "Which facts" not in encoded


def test_host_protocols_and_fail_open_scorer_can_be_evaluated():
    class FailingScorer:
        def score(self, query, segments, /):
            raise RuntimeError("sensitive dependency message")

    report = run_benchmark(
        repetitions=1,
        warmups=0,
        token_counter=SyntheticCounter(),
        renderer=SyntheticRenderer(),
        scorer=FailingScorer(),
    )
    row = by_id(report, "current_greedy", "clear")
    assert row["reason_code"] == "scorer_error"
    assert row["tokens_saved"] == 0
    assert row["weighted_relevance_recall"] == 1
    assert "sensitive" not in json.dumps(report)
    assert report["measurements"]["token_counter"]["kind"] == "host_supplied_unverified"


def test_applied_budget_failure_is_reported(monkeypatch):
    from benchmarks import runner

    actual = runner.optimize_context

    def faulty(request, **kwargs):
        result = actual(request, **kwargs)
        if result.applied:
            return replace(
                result,
                selected_segment_ids=tuple(s.id for s in request.segments),
                context=kwargs["renderer"].render(request.segments),
                optimized_tokens=result.original_tokens,
            )
        return result

    monkeypatch.setattr(runner, "optimize_context", faulty)
    report = run_benchmark(repetitions=1, warmups=0)
    assert report["aggregate"]["current_greedy"]["applied_correctness_failures"] > 0
    assert by_id(report, "current_greedy", "clear")["correctness_failure"] is True


@pytest.mark.parametrize(("repetitions", "warmups"), [(0, 0), (1, -1), (True, 0)])
def test_invalid_timing_configuration(repetitions, warmups):
    with pytest.raises(ValueError):
        run_benchmark(repetitions=repetitions, warmups=warmups)


def test_cli_writes_strict_json_and_readable_summary(tmp_path):
    output = tmp_path / "nested" / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "benchmarks",
            "--repetitions",
            "2",
            "--warmups",
            "0",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert "current_greedy" in report["aggregate"]
    assert "SYNTHETIC" in result.stdout
    assert "critical_low_rank" in result.stdout
    assert "unavailable" in result.stdout
    assert "current_greedy" in result.stdout


def test_aggregate_uses_micro_averages_and_excludes_undefined_case_ratios():
    from benchmarks.metrics import measure
    from benchmarks.runner import aggregate

    cases = {case.id: case for case in load_dataset()}
    rows = []
    for case_id, ids, original, optimized in [
        ("graded", ("a", "b"), 16, 11),
        ("critical_low_rank", ("aside",), 20, 8),
        ("empty", (), 0, 0),
    ]:
        row = measure(
            cases[case_id],
            ids,
            original_tokens=original,
            optimized_tokens=optimized,
            applied=bool(ids),
        )
        rows.append(
            {
                "case_id": case_id,
                "outcome": "applied" if ids else "bypassed",
                "reason_code": "optimized" if ids else "empty_input",
                "invariant_failures": [],
                **row,
            }
        )
    result = aggregate(rows)
    assert result["tokens_saved"] == 17
    assert result["reduction_ratio"] == pytest.approx(17 / 36)
    assert result["mean_case_reduction_ratio"] == pytest.approx(0.45625)
    assert result["median_case_reduction_ratio"] == pytest.approx(0.45625)
    assert result["weighted_relevance_recall"] == 0.5
    assert result["mean_case_relevance_recall"] == pytest.approx(5 / 12)
    assert result["critical_retention"] == 0
    assert result["bypassed"] == 1
    assert aggregate([])["weighted_relevance_recall"] is None


def test_latency_statistics_use_nearest_rank_p95():
    from benchmarks.runner import latency_stats

    assert latency_stats([4, 1, 3, 2]) == {"samples": 4, "median_ms": 2.5, "p95_ms": 4}
    assert latency_stats(list(range(1, 21))) == {"samples": 20, "median_ms": 10.5, "p95_ms": 19}
    assert latency_stats([]) == {"samples": 0, "median_ms": None, "p95_ms": None}


def test_synthetic_count_rule_counts_code_points_without_normalization():
    assert SyntheticCounter().count("é🙂") == 2
    assert SyntheticCounter().count("e\u0301🙂") == 3


def test_host_overrides_are_not_mislabeled_as_synthetic_tokens():
    from benchmarks.__main__ import summary

    report = run_benchmark(
        repetitions=1, warmups=0, token_counter=SyntheticCounter(), renderer=SyntheticRenderer()
    )
    rendered = summary(report)
    assert "HOST-SUPPLIED UNVERIFIED" in rendered
    assert "synthetic tokens" not in rendered
    assert "unverified count units" in rendered
    assert report["measurements"]["renderer"] == {
        "kind": "host_supplied_unverified",
        "implementation": "SyntheticRenderer",
    }
