# Host integration

The host owns the exact tokenizer, renderer, retrieval, eligibility, scoring,
request serialization and rollout. No Gateway adapter is supplied. Only pass
caller-approved context segments. Keep instructions, tool schemas, user messages
and response constraints outside this boundary; pin all mandatory evidence.

This example uses the existing protocols without guessing a provider API:

```python
from context_optimizer import (
    ContextRenderer,
    ContextSegment,
    OptimizationPolicy,
    OptimizationRequest,
    SegmentScorer,
    TokenCounter,
    optimize_context,
)


def select_context(
    original_context: str,
    query: str,
    segments: tuple[ContextSegment, ...],
    context_budget: int,
    counter: TokenCounter,
    renderer: ContextRenderer,
    scorer: SegmentScorer,
    policy: OptimizationPolicy = OptimizationPolicy(),
) -> str:
    # Construct segments inside this same try block when converting untyped input.
    try:
        request = OptimizationRequest(query, segments, context_budget)
    except (TypeError, ValueError):
        return original_context
    result = optimize_context(
        request,
        token_counter=counter,
        renderer=renderer,
        scorer=scorer,
        policy=policy,
    )
    return result.context if result.applied and result.context is not None else original_context
```

`original_context` must be the host's unchanged original rendering. Constructors
reject malformed input with `TypeError` or `ValueError`; they do not return a
result. Once valid contracts exist, dependency errors inside `optimize_context`
return a bypass without exposing exception text. Process termination signals such
as `KeyboardInterrupt` and `SystemExit` are not swallowed.

The injected counter counts the complete rendered context, including wrappers,
separators and provenance formatting. It must support empty context. Every accepted
candidate is counted as a whole; token counts are never summed per segment. Host
implementations must be deterministic for a request, preserve retained text and
avoid external calls. A dishonest or stateful renderer/counter cannot be verified
by this library. The host must use the returned string unchanged and verify the
complete provider request's limit after accounting for other messages, tools and
reserved output tokens. `context_budget` covers the eligible context only.

Selection is deterministic greedy ranking, with source-order ties and source-order
output. A candidate that does not fit is skipped; the host can provide boundaries
appropriate for code, tables or structured data. The package never splits, clips,
deduplicates or rewrites source. Greedy selection does not guarantee the best
subset, nor can it exploit every nonmonotonic tokenizer boundary interaction.

The default policy bypasses before invoking dependencies. Explicit experimental
opt-in requires both `enabled=True` and `allowed_strategies=("greedy",)`. More than
256 segments bypass with `segment_limit_exceeded` before dependency calls. Set
`max_segments` to a positive integer appropriate for host measurements; `None`
removes this limit. The limit bounds candidate work, not total memory, text length
or time spent in one host dependency. Caller-side deadlines and input limits remain
necessary. No scoring algorithm is provided or validated.

On every bypass, reuse the host's original context, even if it exceeds the context
budget. `context=None` means original rendering was skipped or failed. Counts are
`None` until available. Pinned overflow reports `pinned_content_exceeds_budget`.
The host owns subsequent overflow handling; silently deleting pinned segments is
not an acceptable fallback.

## Shadow, canary and rollback

1. Keep the serving policy disabled. On a bounded educational replay or a
   permission-cleared shadow sample, explicitly opt in and compare with full
   context while continuing to serve the original request. Verify tokenizer and
   renderer versions against the final provider request builder.
2. Establish independent relevance/critical labels and downstream references.
   Group by conversation and document/corpus before splitting; quarantine groups
   that cross official splits. Tune only on development groups and lock the
   strategy, thresholds and tokenizer before held-out evaluation.
3. Require the paired 95% quality-delta CI lower bound to be at least -1 percentage
   point, no critical-class regressions, at least 10% median eligible-request exact
   token reduction, positive cache-aware net savings after CPU cost, and measured
   p95 overhead at most 10 ms for the target workload up to 8,000 model tokens.
4. Only after those gates pass, the host may canary eligible requests with an
   explicitly configured scorer. Compare quality, budget counts, bypass/error
   rates, latency and actual cost against a concurrent full-context control.
5. Roll back immediately on a pin/budget/source invariant violation, quality-gate
   failure or host-defined error/latency threshold breach. The kill switch is
   `OptimizationPolicy(enabled=False)` and routing back to the original host
   request. Rollback requires no library state, migration or provider change.

Export only allowlisted aggregate fields: `applied`, `strategy`, `reason_code`,
`original_tokens`, `optimized_tokens`, `latency_ms`, and non-customer build/tokenizer
version identifiers. Compute savings only when both counts exist. Do not export
queries, context, selected IDs, source/customer IDs, credentials, provider responses
or exception messages. In-memory result IDs are for provenance, not telemetry.
