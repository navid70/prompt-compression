"""Execute with python -m benchmarks; no external services or dependencies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from benchmarks.dataset import DEFAULT_DATASET
from benchmarks.runner import run_benchmark


def _percent(value: float | None) -> str:
    return "unavailable" if value is None else f"{100 * value:.2f}%"


def summary(report: dict[str, Any]) -> str:
    synthetic = report["measurements"]["token_counter"]["kind"] == "synthetic"
    label = "SYNTHETIC" if synthetic else "HOST-SUPPLIED UNVERIFIED"
    units = "synthetic tokens" if synthetic else "unverified count units"
    lines = [f"{label} offline selection evaluation (not verified LLM tokens or monetary savings)"]
    for name, row in report["aggregate"].items():
        timing = report["timing"][name]
        latency = (
            "unavailable"
            if timing is None
            else f"median {timing['aggregate']['median_ms']:.4f} ms, "
            f"p95 {timing['aggregate']['p95_ms']:.4f} ms"
        )
        lines.extend(
            [
                f"{name}: {row['original_tokens']} -> {row['optimized_tokens']} {units}; "
                f"saved {row['tokens_saved']} ({_percent(row['reduction_ratio'])}); "
                f"weighted relevance {_percent(row['weighted_relevance_recall'])}; "
                f"critical retention {_percent(row['critical_retention'])}",
                f"  applied {row['applied']}; bypassed {row['bypassed']}; "
                f"budget excesses {row['budget_violations']}; "
                f"applied correctness failures {row['applied_correctness_failures']}; "
                f"latency {latency}",
                f"  bypass reasons: {row['bypass_reasons']}",
            ]
        )
        for case in report["cases"][name]:
            lines.append(
                f"  {case['case_id']}: {case['outcome']}/{case['reason_code']}; "
                f"saved {case['tokens_saved']}; "
                f"relevance {_percent(case['weighted_relevance_recall'])}; "
                f"omitted critical IDs {case['omitted_critical_ids']}; "
                f"budget {'ok' if case['budget_compliant'] else 'EXCEEDED'}"
            )
    lines.append(
        "Real tokenizer, real scorer, downstream answer quality and economic benefit: unavailable."
    )
    lines.extend(f"Limitation: {item}" for item in report["limitations"])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/latest.json"))
    parser.add_argument("--repetitions", type=int, default=30)
    parser.add_argument("--warmups", type=int, default=3)
    args = parser.parse_args()
    try:
        report = run_benchmark(args.dataset, repetitions=args.repetitions, warmups=args.warmups)
    except (ValueError, OSError):
        parser.error(
            "Evaluation failed: check dataset schema, local paths and timing configuration"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(summary(report))
    print(f"JSON: {args.output}")
    return int(any(r["correctness_failure"] for rows in report["cases"].values() for r in rows))


if __name__ == "__main__":
    raise SystemExit(main())
