"""Selection metrics; all undefined ratios are None (JSON null)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from benchmarks.dataset import BenchmarkCase


def ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def measure(
    case: BenchmarkCase,
    selected_ids: Sequence[str],
    *,
    original_tokens: int,
    optimized_tokens: int,
    applied: bool,
) -> dict[str, Any]:
    """Measure whole retained segments against labels, never against predicted scores."""
    selected = set(selected_ids)
    segments = case.request.segments
    if list(selected_ids) != [s.id for s in segments if s.id in selected]:
        raise ValueError("Selected IDs must be unique, known and in source order")
    if min(original_tokens, optimized_tokens) < 0:
        raise ValueError("Token counts cannot be negative")
    total_relevance = sum(label.relevance for label in case.judgments)
    retained_relevance = sum(
        label.relevance
        for s, label in zip(segments, case.judgments, strict=True)
        if s.id in selected
    )
    critical = [s.id for s, label in zip(segments, case.judgments, strict=True) if label.critical]
    omitted_critical = [sid for sid in critical if sid not in selected]
    omitted_relevant = [
        s.id
        for s, label in zip(segments, case.judgments, strict=True)
        if label.relevance > 0 and s.id not in selected
    ]
    saved = original_tokens - optimized_tokens
    compliant = optimized_tokens <= case.request.token_budget
    return {
        "original_tokens": original_tokens,
        "optimized_tokens": optimized_tokens,
        "tokens_saved": saved,
        "reduction_ratio": ratio(saved, original_tokens),
        "total_relevance": total_relevance,
        "retained_relevance": retained_relevance,
        "weighted_relevance_recall": ratio(retained_relevance, total_relevance),
        "critical_segments": len(critical),
        "retained_critical_segments": len(critical) - len(omitted_critical),
        "critical_retention": ratio(len(critical) - len(omitted_critical), len(critical)),
        "omitted_relevant_ids": omitted_relevant,
        "omitted_critical_ids": omitted_critical,
        "omitted_relevant_segments": len(omitted_relevant),
        "omitted_critical_segments": len(omitted_critical),
        "retained_segments": len(selected),
        "original_segments": len(segments),
        "budget_compliant": compliant,
        "correctness_failure": applied and not compliant,
        "no_token_benefit": saved <= 0,
    }
