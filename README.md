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
Enabled requests with more than 256 segments bypass before dependency calls with
`segment_limit_exceeded`. Configure `max_segments` after host profiling; `None`
removes the cap. This bounds candidate work, not host dependency duration.

Only use `result.context` as optimized context when `result.applied` is true. Every
bypass preserves all original IDs and reports a `reason_code`; it may exceed the
budget. `context=None` means rendering was skipped or failed: reuse the original
host request. Token counts are `None` when unavailable. Dependency exceptions are
contained without logging or returning their potentially sensitive messages.
Public constructors validate field types and ranges, raising `TypeError` or
`ValueError` before optimization. See [host integration](docs/integration.md) for
validation fallback, exact rendering, shadow rollout and the kill switch, and the
[readiness audit](docs/production-readiness-audit.md) for evidence and open gates.

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
python -m build
```

## Integration boundary

The consuming application remains responsible for retrieval, request construction, provider selection, prompt caching, pricing, rollout, and final serialization. See the public types in `src/context_optimizer/` for the initial contracts.

## Offline evaluation

From the repository root after the development install above:

```bash
python -m benchmarks --output benchmarks/results/latest.json
```

The command prints a per-case summary and writes strict JSON. Results stay ignored
by Git. Options: `--dataset PATH`, `--repetitions 30`, and `--warmups 3`.
A correctness failure returns exit code 1; invalid input returns exit code 2.
The harness uses the actual `optimize_context` function and adds no dependencies.
Evaluation code is outside `src/` and is not part of the installed runtime package.

`benchmarks/fixtures/synthetic_v1.json` is a versioned, synthetic-only dataset.
Each case has an ID, scenario, query, ordered segments, positive budget and optional
policy overrides. Each segment has an ID, unchanged text, source ID, pinned flag,
predicted score, nonnegative relevance grade and independent critical flag.
The loader rejects malformed fields, nonfinite scores/grades and duplicate IDs.
Predicted scores and ground-truth judgments remain separate; the normal scorer
receives only a score map and source segments, never the judgments.

The 14 fixtures cover relevance grades, bad rankings, critical evidence loss,
large versus small segments, pins, deterministic ties, rendering overhead,
already-fitting context, pinned overflow, insufficient savings, empty context,
zero relevance and disabled policy. They are diagnostic examples, not a held-out
quality corpus; no strategy is trained or tuned on them.

Three perspectives share context, renderer, counter, budget and case policy:

- **No optimization:** retain everything; optimizer latency is unavailable because
  the optimizer is not invoked. This is a reference, not a budget-fitting baseline.
- **Current greedy:** use deterministic fixture scores. These illustrate ranking
  errors; they do not represent a validated production scorer.
- **Oracle-ranked greedy:** use relevance grades as scores in the same optimizer.
  This is an optimistic ranking reference, not optimal subset selection or a
  guaranteed upper bound. The size-competition case shows a large, higher-graded
  segment displacing two segments with greater combined relevance.

For these fixtures only, one **synthetic token** is one Python Unicode code point
(`len(text)`, without normalization). Empty context renders as `""`; otherwise the
renderer brackets the unchanged text and separates segments with `|`. The counter
always measures the complete rendered string, including brackets and separators.
It does not add individual segment counts. This rule is exact for the synthetic
language and is not an approximation of any model's tokenizer.

| Metric | Definition |
| --- | --- |
| Tokens saved | Original rendered count minus output rendered count |
| Reduction ratio | Tokens saved / original count; multiply by 100 for percent |
| Weighted relevance recall | Sum of retained grades / sum of all grades |
| Critical retention | Retained critical segment count / total critical segment count |
| Omitted relevant / critical | Count and IDs of removed segments with grade > 0 / critical flag |
| Segment counts | Original and retained whole-segment counts |
| Budget compliance | Output rendered count <= case budget |
| Applied correctness failure | Applied output exceeds budget or violates checked source/count/pin invariants |
| Bypasses | Non-applied optimizer outcomes, grouped by actual reason code |
| Insufficient savings | Actual `insufficient_savings` bypass, using the explicit case policy |
| No token benefit | Tokens saved <= 0; this does not determine economic usefulness |
| Latency | External elapsed time around the optimizer call in milliseconds |

Zero denominators produce `null` in JSON and `unavailable` in text, including an
empty context's reduction and cases with no relevance or critical labels. The
harness independently renders/counts baseline and output, even when the optimizer
bypasses counting. Fail-open output can exceed budget; this is reported as a budget
violation separately from an applied correctness failure. Every case retains its
quality metrics and omitted IDs so aggregates cannot hide critical failures.

Aggregate reduction is total tokens saved / total original tokens. Aggregate
relevance and critical retention use summed numerators and denominators (micro
averages). Mean/median case reduction and mean case relevance exclude undefined
ratios. Bypass and violation counts count cases once, not timing repetitions.
Latency uses warmups followed by the configured repetitions for every case,
including bypasses. Median averages the middle pair for an even sample count;
P95 uses nearest rank `ceil(0.95 * N)`. The aggregate latency pools all measured
calls. It includes instrumentation overhead and excludes fixture loading,
rendering/counting for independent metrics, scorer construction and report writing.
Dependency invocation counts are per optimizer call; all repetitions must produce
the same selections, reasons, counts and invocation counts or evaluation fails.
Timing is reported, never used as a fragile unit-test threshold.

The JSON records dataset and implementation SHA-256 hashes, policy per case,
Python/platform/CPU details, measurement kinds and limitations. All variable
latency samples and summaries live under `timing`; repeated runs with identical
code, data and environment must match after removing that key. Generated reports
contain no query or source text. Python callers can inject existing `TokenCounter`,
`ContextRenderer` and `SegmentScorer` implementations into
`benchmarks.runner.run_benchmark`; overrides are marked `host_supplied_unverified`.
Real tokenizer, real scorer, downstream quality and monetary measurements remain
explicitly unavailable until separately verified evidence exists.

Synthetic reduction is not production token savings or invoice savings. Segment
recall does not measure downstream answer correctness or citation sufficiency.
Small fixture latency does not establish production latency. Before an economic
or release decision, the host must provide a versioned exact target tokenizer and
request renderer, a real scorer, representative permission-cleared held-out data,
downstream answer-quality evaluation, and cache-aware pricing and CPU/invoice
costs. No such gate passes merely because this offline harness runs successfully;
optimization remains disabled by default.

For a synthetic scaling profile with p50/p95/p99, serial throughput and separately
measured Python allocation peaks:

```bash
python -m benchmarks.scaling --output benchmarks/results/scaling.json
```

It compares 8,000/32,000 code-point contexts across segment counts, including the
segment-limit bypass and an explicit uncapped diagnostic. These are synthetic
language units, not model tokens or a production latency guarantee. Dataset and
evaluation tooling stays outside the runtime package; Hugging Face and Parquet
tools, when needed, are optional. Keep private records in an external cache and
credentials in ignored local configuration. Metis data use in this project is
limited to the authorized Rahnama College educational benchmark scope.
