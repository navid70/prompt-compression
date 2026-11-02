# Context Optimizer

A small, provider-agnostic Python library for conservative optimization of caller-approved context segments.

## Scope

The package owns context selection only. The host application supplies the exact model tokenizer, final context renderer, and eligibility policy. System/developer instructions, user messages, tool contracts, and structured-output constraints must remain outside the optimizer's input.

## Design constraints

- Source-preserving selection; no paraphrasing or generated replacement text.
- Deterministic behavior and stable provenance.
- Exact token accounting through a host-provided tokenizer.
- Fail-open behavior: uncertain or failed optimization returns the original context.
- No network calls, model downloads, provider SDKs, or mandatory runtime dependencies.
- Optimization stays disabled by default until quality and net-savings gates pass.

## Project status

The safe selection core is implemented. Optimization remains disabled by default; no ranking strategy has passed quality or economic evaluation. This repository does not yet claim production readiness or measured compression quality.

## API

Call `optimize_context(request, token_counter=..., renderer=..., scorer=..., policy=...)`.
The host implements `TokenCounter`, `ContextRenderer`, and `SegmentScorer`; the package
provides no tokenizer or scoring algorithm. The counter must count the exact rendered
context the host will send.

The default `OptimizationPolicy()` bypasses all dependencies. To explicitly opt in,
set `enabled=True` and `allowed_strategies=("greedy",)`. The selector reserves pinned
segments, scores the remaining segments (higher is better, ties follow input order),
and checks the fully rendered token count after each attempted addition. Retained
segments keep their original text, IDs, provenance, and order. Policy input-size and
savings thresholds still apply; a greedy selection need not maximize budget usage.

Only use `result.context` as optimized context when `result.applied` is true. Every
bypass preserves all original IDs and reports a `reason_code`; it may exceed the
budget. `context=None` means rendering was skipped or failed: reuse the original
host request. Token counts are `None` when unavailable. Dependency exceptions are
contained without logging or returning their potentially sensitive messages.

## Development

Python 3.11 or newer is required.

```bash
python -m venv .venv
# Activate the virtual environment, then:
python -m pip install -e ".[dev]"
pytest
ruff check .
ruff format --check .
mypy src
```

## Integration boundary

The consuming application remains responsible for retrieval, request construction, provider selection, prompt caching, pricing, rollout, and final serialization. See the public types in `src/context_optimizer/` for the initial contracts.
