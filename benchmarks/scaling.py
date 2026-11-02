"""Synthetic scaling diagnostic; counts Unicode code points, never model tokens."""

from __future__ import annotations

import argparse
import json
import math
import platform
import tracemalloc
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from statistics import median
from time import perf_counter

from benchmarks.runner import SyntheticCounter, SyntheticRenderer, _implementation_hash
from context_optimizer import (
    ContextSegment,
    OptimizationPolicy,
    OptimizationRequest,
    optimize_context,
)


class Dependencies(SyntheticCounter, SyntheticRenderer):
    def score(self, query: str, segments: Sequence[ContextSegment], /) -> Sequence[float]:
        return [1.0] * len(segments)


def profile(*, repetitions: int = 100, warmups: int = 5) -> dict[str, object]:
    for value, minimum in ((repetitions, 1), (warmups, 0)):
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError("Invalid timing configuration")
    rows = []
    deps = Dependencies()
    policy = OptimizationPolicy(True, 0, 1, 0, ("greedy",))
    for units, count in (
        (8000, 16),
        (8000, 128),
        (8000, 256),
        (8000, 1024),
        (32000, 128),
        (32000, 1024),
    ):
        # Brackets and separators count too. This constructs exactly `units` synthetic tokens.
        width, remainder = divmod(units - count - 1, count)
        segments = tuple(
            ContextSegment(str(i), "x" * (width + (i < remainder))) for i in range(count)
        )
        request = OptimizationRequest("synthetic scaling", segments, units // 2)
        assert deps.count(deps.render(segments)) == units
        policies = [policy]
        if count > 256:
            policies.extend((replace(policy, max_segments=None), OptimizationPolicy()))
        for current in policies:

            def run(request=request, current=current):
                return optimize_context(
                    request, token_counter=deps, renderer=deps, scorer=deps, policy=current
                )

            for _ in range(warmups):
                run()
            samples = []
            start_all = perf_counter()
            for _ in range(repetitions):
                start = perf_counter()
                result = run()
                samples.append((perf_counter() - start) * 1000)
            elapsed = perf_counter() - start_all
            # Memory profiling is separate so it cannot distort latency percentiles.
            tracemalloc.start()
            run()
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            ordered = sorted(samples)
            rows.append(
                {
                    "synthetic_units": units,
                    "segments": count,
                    "enabled": current.enabled,
                    "max_segments": current.max_segments,
                    "reason_code": result.reason_code,
                    "applied": result.applied,
                    "p50_ms": median(samples),
                    "p95_ms": ordered[math.ceil(0.95 * repetitions) - 1],
                    "p99_ms": ordered[math.ceil(0.99 * repetitions) - 1],
                    "serial_calls_per_second": repetitions / elapsed,
                    "peak_python_bytes": peak,
                }
            )
    return {
        "kind": "synthetic_code_point_scaling_only",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor(),
        "implementation_sha256": _implementation_hash(),
        "repetitions": repetitions,
        "warmups": warmups,
        "cases": rows,
        "limitations": [
            "Exact for the synthetic language only; no production tokenizer, renderer or scorer.",
            "Median averages the middle pair; P95/P99 use nearest rank. "
            "Throughput includes timing-loop instrumentation.",
            "Memory is peak traced Python allocations in one separate call; not process RSS.",
            "No quality labels, downstream model calls, invoices or production latency claims.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/scaling.json"))
    parser.add_argument("--repetitions", type=int, default=100)
    args = parser.parse_args()
    report = profile(repetitions=args.repetitions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
