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

Initial package foundation. Public contracts and CI are being established before any compression strategy is enabled. This repository does not yet claim production readiness or measured compression quality.

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
