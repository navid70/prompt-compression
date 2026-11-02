"""Strict, versioned synthetic fixtures; labels never enter production segments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any

from context_optimizer import ContextSegment, OptimizationPolicy, OptimizationRequest

DEFAULT_DATASET = Path(__file__).with_name("fixtures") / "synthetic_v1.json"


@dataclass(frozen=True)
class Judgment:
    relevance: float
    critical: bool


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    scenario: str
    request: OptimizationRequest
    predicted_scores: tuple[float, ...]
    judgments: tuple[Judgment, ...]
    policy: OptimizationPolicy


def _object(value: Any, required: set[str], optional: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or not required <= value.keys():
        raise ValueError("Missing required fixture fields")
    if value.keys() - required - (optional or set()):
        raise ValueError("Unknown fixture fields")
    return value


def _string(value: Any, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise ValueError("Expected a fixture string")
    return value


def _number(value: Any, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError("Expected a finite fixture number")
    if minimum is not None and value < minimum:
        raise ValueError("Fixture number below minimum")
    return float(value)


def _integer(value: Any, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError("Expected a fixture integer within range")
    return value


def _boolean(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError("Expected a fixture boolean")
    return value


def load_dataset(path: Path = DEFAULT_DATASET) -> tuple[BenchmarkCase, ...]:
    """Load schema v1; reject ambiguous or malformed data before evaluation."""
    obj = _object(json.loads(path.read_text(encoding="utf-8-sig")), {"schema_version", "cases"})
    if _integer(obj["schema_version"], 1) != 1:
        raise ValueError("Unsupported fixture schema version")
    if not isinstance(obj["cases"], list) or not obj["cases"]:
        raise ValueError("Expected nonempty fixture cases")
    cases = []
    for raw in obj["cases"]:
        raw = _object(raw, {"id", "scenario", "query", "segments", "token_budget"}, {"policy"})
        if not isinstance(raw["segments"], list):
            raise ValueError("Expected a segment list")
        segments, scores, judgments = [], [], []
        for item in raw["segments"]:
            item = _object(
                item,
                {"id", "text", "source_id", "predicted_score", "relevance", "pinned", "critical"},
            )
            segments.append(
                ContextSegment(
                    id=_string(item["id"]),
                    text=_string(item["text"], nonempty=False),
                    source_id=_string(item["source_id"]),
                    pinned=_boolean(item["pinned"]),
                )
            )
            scores.append(_number(item["predicted_score"]))
            judgments.append(
                Judgment(_number(item["relevance"], minimum=0), _boolean(item["critical"]))
            )
        overrides = _object(
            raw.get("policy", {}),
            set(),
            {"enabled", "min_input_tokens", "min_tokens_saved", "min_reduction_ratio"},
        )
        policy = OptimizationPolicy(
            enabled=_boolean(overrides.get("enabled", True)),
            min_input_tokens=_integer(overrides.get("min_input_tokens", 0), 0),
            min_tokens_saved=_integer(overrides.get("min_tokens_saved", 1), 0),
            min_reduction_ratio=_number(overrides.get("min_reduction_ratio", 0), minimum=0),
            allowed_strategies=("greedy",),
        )
        cases.append(
            BenchmarkCase(
                id=_string(raw["id"]),
                scenario=_string(raw["scenario"]),
                request=OptimizationRequest(
                    _string(raw["query"], nonempty=False),
                    tuple(segments),
                    _integer(raw["token_budget"], 1),
                ),
                predicted_scores=tuple(scores),
                judgments=tuple(judgments),
                policy=policy,
            )
        )
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("Fixture case IDs must be unique")
    return tuple(cases)
