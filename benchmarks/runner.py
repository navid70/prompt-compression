"""Run all perspectives through the real optimizer with isolated, measured dependencies."""

from __future__ import annotations

import hashlib
import math
import os
import platform
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from typing import Any

from benchmarks.dataset import DEFAULT_DATASET, load_dataset
from benchmarks.metrics import measure, ratio
from context_optimizer import ContextSegment, optimize_context
from context_optimizer.protocols import ContextRenderer, SegmentScorer, TokenCounter


class SyntheticCounter:
    """One synthetic token per Unicode code point, including punctuation and whitespace."""

    def count(self, text: str, /) -> int:
        return len(text)


class SyntheticRenderer:
    """Empty context is empty; otherwise frame with brackets and separate with |."""

    def render(self, segments: Sequence[ContextSegment], /) -> str:
        return "[" + "|".join(s.text for s in segments) + "]" if segments else ""


class FixtureScorer:
    """Only a score map is accepted; this scorer has no access to judgments."""

    def __init__(self, scores: Mapping[str, float]) -> None:
        self.scores = dict(scores)

    def score(self, query: str, segments: Sequence[ContextSegment], /) -> tuple[float, ...]:
        return tuple(self.scores[s.id] for s in segments)


class _MeasuredDependencies:
    def __init__(self, counter: TokenCounter, renderer: ContextRenderer, scorer: SegmentScorer):
        self.counter = counter
        self.renderer = renderer
        self.scorer = scorer
        self.calls = {"token_counter": 0, "renderer": 0, "scorer": 0}

    def count(self, text: str, /) -> int:
        self.calls["token_counter"] += 1
        return self.counter.count(text)

    def render(self, segments: Sequence[ContextSegment], /) -> str:
        self.calls["renderer"] += 1
        return self.renderer.render(segments)

    def score(self, query: str, segments: Sequence[ContextSegment], /) -> Sequence[float]:
        self.calls["scorer"] += 1
        return self.scorer.score(query, segments)


def latency_stats(samples: Sequence[float]) -> dict[str, float | int | None]:
    """P95 uses nearest rank ceil(0.95*N); median averages the two middle samples."""
    ordered = sorted(samples)
    return {
        "samples": len(ordered),
        "median_ms": median(ordered) if ordered else None,
        "p95_ms": ordered[math.ceil(0.95 * len(ordered)) - 1] if ordered else None,
    }


def aggregate(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    reductions = [row["reduction_ratio"] for row in rows if row["reduction_ratio"] is not None]
    recalls = [
        row["weighted_relevance_recall"]
        for row in rows
        if row["weighted_relevance_recall"] is not None
    ]
    applied = [row for row in rows if row["outcome"] == "applied"]
    return {
        "cases": len(rows),
        "original_tokens": sum(r["original_tokens"] for r in rows),
        "optimized_tokens": sum(r["optimized_tokens"] for r in rows),
        "tokens_saved": sum(r["tokens_saved"] for r in rows),
        "reduction_ratio": ratio(
            sum(r["tokens_saved"] for r in rows), sum(r["original_tokens"] for r in rows)
        ),
        "median_case_reduction_ratio": median(reductions) if reductions else None,
        "mean_case_reduction_ratio": sum(reductions) / len(reductions) if reductions else None,
        "weighted_relevance_recall": ratio(
            sum(r["retained_relevance"] for r in rows), sum(r["total_relevance"] for r in rows)
        ),
        "mean_case_relevance_recall": sum(recalls) / len(recalls) if recalls else None,
        "critical_retention": ratio(
            sum(r["retained_critical_segments"] for r in rows),
            sum(r["critical_segments"] for r in rows),
        ),
        "omitted_relevant_segments": sum(r["omitted_relevant_segments"] for r in rows),
        "omitted_critical_segments": sum(r["omitted_critical_segments"] for r in rows),
        "relevance_loss_cases": [r["case_id"] for r in rows if r["omitted_relevant_segments"]],
        "critical_loss_cases": [r["case_id"] for r in rows if r["omitted_critical_segments"]],
        "budget_violations": sum(not r["budget_compliant"] for r in rows),
        "applied_correctness_failures": sum(r["correctness_failure"] for r in applied),
        "invariant_failure_cases": [r["case_id"] for r in rows if r["invariant_failures"]],
        "applied": len(applied),
        "bypassed": sum(r["outcome"] == "bypassed" for r in rows),
        "bypass_reasons": dict(
            sorted(Counter(r["reason_code"] for r in rows if r["outcome"] == "bypassed").items())
        ),
        "insufficient_savings_cases": [
            r["case_id"] for r in rows if r["reason_code"] == "insufficient_savings"
        ],
        "no_token_benefit_cases": [r["case_id"] for r in rows if r["no_token_benefit"]],
    }


def _implementation_hash() -> str:
    root = Path(__file__).resolve().parents[1]
    files = sorted((root / "src/context_optimizer").glob("*.py"))
    files += sorted((root / "benchmarks").glob("*.py"))
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run_benchmark(
    path: Path = DEFAULT_DATASET,
    *,
    repetitions: int = 30,
    warmups: int = 3,
    token_counter: TokenCounter | None = None,
    renderer: ContextRenderer | None = None,
    scorer: SegmentScorer | None = None,
) -> dict[str, Any]:
    """Evaluate fixture/current scores and relevance scores using the same core and policy.

    Host protocol overrides apply to all renders/counts and the current scorer only.
    They must be deterministic and are reported as unverified, never as real measurements.
    Exceptions during independent measurement abort the benchmark, not the optimizer.
    """
    for value, minimum in ((repetitions, 1), (warmups, 0)):
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError("Invalid timing configuration")
    cases = load_dataset(path)
    counter = token_counter if token_counter is not None else SyntheticCounter()
    context_renderer = renderer if renderer is not None else SyntheticRenderer()
    names = ("no_optimization", "current_greedy", "oracle_ranked_greedy")
    results: dict[str, list[dict[str, Any]]] = {name: [] for name in names}
    timing: dict[str, Any] = {"no_optimization": None}
    for name in names[1:]:
        timing[name] = {"cases": {}, "aggregate": None}
    all_samples: dict[str, list[float]] = {name: [] for name in names[1:]}
    for case in cases:
        request = case.request
        original_context = context_renderer.render(request.segments)
        original_tokens = counter.count(original_context)
        if (
            isinstance(original_tokens, bool)
            or not isinstance(original_tokens, int)
            or original_tokens < 0
        ):
            raise ValueError("Independent token count must be a nonnegative integer")
        for name in names:
            failures = []
            if name == "no_optimization":
                ids = tuple(s.id for s in request.segments)
                output_tokens = original_tokens
                applied, outcome, reason = False, "baseline", "full_context"
                calls = {"renderer": 0, "token_counter": 0, "scorer": 0}
            else:
                values = (
                    case.predicted_scores
                    if name == "current_greedy"
                    else tuple(label.relevance for label in case.judgments)
                )
                ranking: SegmentScorer = FixtureScorer(
                    dict(zip((s.id for s in request.segments), values, strict=True))
                )
                if name == "current_greedy" and scorer is not None:
                    ranking = scorer
                first = None
                samples = []
                for iteration in range(warmups + repetitions):
                    deps = _MeasuredDependencies(counter, context_renderer, ranking)
                    start = perf_counter_ns()
                    result = optimize_context(
                        request, token_counter=deps, renderer=deps, scorer=deps, policy=case.policy
                    )
                    elapsed = (perf_counter_ns() - start) / 1_000_000
                    stable = (replace(result, latency_ms=0), deps.calls)
                    if first is None:
                        first = stable
                    elif stable != first:
                        raise ValueError("Non-deterministic optimization or dependency calls")
                    if iteration >= warmups:
                        samples.append(elapsed)
                all_samples[name].extend(samples)
                timing[name]["cases"][case.id] = {**latency_stats(samples), "samples_ms": samples}
                ids = result.selected_segment_ids
                applied, reason = result.applied, result.reason_code
                outcome = "applied" if applied else "bypassed"
                calls = deps.calls
                selected = tuple(s for s in request.segments if s.id in ids)
                expected = context_renderer.render(selected)
                actual_context = result.context if result.context is not None else original_context
                output_tokens = counter.count(actual_context)
                if (
                    isinstance(output_tokens, bool)
                    or not isinstance(output_tokens, int)
                    or output_tokens < 0
                ):
                    raise ValueError("Independent token count must be a nonnegative integer")
                if actual_context != expected:
                    failures.append("rendered_output_differs_from_original_segments")
                if any(s.pinned and s.id not in ids for s in request.segments):
                    failures.append("pinned_segment_missing")
                if not applied and ids != tuple(s.id for s in request.segments):
                    failures.append("bypass_changed_selection")
                if result.original_tokens is not None and result.original_tokens != original_tokens:
                    failures.append("original_token_count_mismatch")
                if result.optimized_tokens is not None and result.optimized_tokens != output_tokens:
                    failures.append("optimized_token_count_mismatch")
            metrics = measure(
                case,
                ids,
                original_tokens=original_tokens,
                optimized_tokens=output_tokens,
                applied=applied,
            )
            metrics["correctness_failure"] |= bool(failures)
            results[name].append(
                {
                    "case_id": case.id,
                    "scenario": case.scenario,
                    "token_budget": request.token_budget,
                    "policy": asdict(case.policy),
                    "selected_ids": list(ids),
                    "outcome": outcome,
                    "reason_code": reason,
                    "dependency_calls": calls,
                    "invariant_failures": failures,
                    **metrics,
                }
            )
    for name, samples in all_samples.items():
        timing[name]["aggregate"] = latency_stats(samples)
    return {
        "schema_version": 1,
        "metadata": {
            "dataset_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "implementation_sha256": _implementation_hash(),
            "python": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "logical_cpus": os.cpu_count(),
            "repetitions": repetitions,
            "warmups": warmups,
        },
        "measurements": {
            "dataset": "synthetic",
            "token_counter": {
                "kind": "synthetic" if token_counter is None else "host_supplied_unverified",
                "implementation": type(counter).__qualname__,
            },
            "renderer": {
                "kind": "synthetic" if renderer is None else "host_supplied_unverified",
                "implementation": type(context_renderer).__qualname__,
            },
            "current_scorer": "synthetic_fixture" if scorer is None else "host_supplied_unverified",
            "oracle_scorer": "ground_truth_relevance_reference",
            "real_tokenizer": None,
            "real_scorer": None,
            "downstream_answer_quality": None,
            "net_monetary_savings": None,
        },
        "limitations": [
            (
                "Synthetic Unicode-code-point tokens are not tokens of any LLM or billable savings."
                if token_counter is None
                else "Host counter is unverified; counts are not established "
                "as model tokens or billable savings."
            ),
            "Fixture scores are illustrative, not a measured production ranking strategy.",
            "Oracle ranking is a relevance-based reference, "
            "not a globally optimal subset or guaranteed upper bound.",
            "Segment recall does not measure answer quality, evidence sufficiency or citations.",
            "No held-out traffic, model evaluation, confidence interval "
            "or production quality gate is established.",
            "No pricing, cache effects, CPU cost or invoice data; economic benefit is unavailable.",
            "Latency includes wrapper instrumentation and optimizer call only; "
            "excludes setup and independent measurement.",
            "Fixed small fixtures do not establish production or long-context latency.",
            "No token benefit means tokens_saved <= 0; "
            "positive savings do not establish practical economic benefit.",
        ],
        "cases": results,
        "aggregate": {name: aggregate(rows) for name, rows in results.items()},
        "timing": timing,
    }
