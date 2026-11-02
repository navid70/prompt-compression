# Production Context Optimizer — Design Specification

> **Status:** Proposed — awaiting product/design approval  
> **Date:** 2026-11-02  
> **Repository:** `navid70/prompt-compression`  
> **Document type:** Product and architecture design; not an implementation or release claim

## 1. Executive summary

Build a small, standalone context-optimization library that Metis can integrate into its request pipeline without depending on Metis Gateway internals.

The library will optimize only explicitly eligible context supplied by the caller (for example, retrieved passages). It will not rewrite or compress an entire chat request. Its primary operation is conservative selection of source-preserving context segments under an exact token budget.

The product objective is **positive net cost reduction with no unacceptable loss of answer quality or request reliability**. Token reduction alone is not success.

The first release is deliberately narrow:
- deterministic, offline, CPU-only core;
- exact token counting supplied by the host application;
- source-preserving segment selection;
- explicit policy and fail-open behavior;
- no LLM calls, external API calls, model downloads, server, database, UI, or gateway-specific adapter;
- an evidence-gated strategy: compression remains disabled by default until the evaluation gates in this document are met.

## 2. Metis context and responsibility boundary

Metis's broader cost-optimization objective includes multiple independent levers:
1. response caching;
2. context optimization;
3. model routing.

This repository owns **context optimization only**. It must not implement caching, model selection, provider pricing, or gateway orchestration. Those concerns remain with the host application.

The library reports exact input-token counts and selected context. The host application owns:
- deciding which request content is eligible for optimization;
- model/provider selection and prompt construction;
- cache-aware cost calculation and pricing;
- final request serialization;
- rollout configuration and operational kill switch.

The intended integration point is after retrieval/context assembly and before provider request construction. The caller passes only the context it has explicitly approved for optimization.

## 3. Evidence and lessons from the predecessor research

The predecessor repository is useful as a research reference, not as a production codebase. Its final SQuAD v1.1 experiment used 30 development questions and 200 held-out questions, with one answering model. The final main test reported:

| Method | API input reduction | Answer F1 | F1 delta vs. full context |
|---|---:|---:|---:|
| Full context | 0% | 90.49% | 0.00 pp |
| Query-Aware TF-IDF, 0.50 budget | 36.83% | 76.47% | -14.02 pp |
| Query-Aware Split, 0.50 budget | 34.31% | 75.63% | -14.86 pp |
| LLMLingua-2, 0.50 budget | 35.64% | 63.35% | -27.14 pp |

An exploratory 0.75-budget run on 50 questions gave Query-Aware TF-IDF 20.36% input reduction and 88.28% F1. Its 95% confidence interval for F1 delta was -6.80 to +5.41 pp. This is not sufficient evidence of non-inferiority and must not be treated as a production acceptance result.

On short contexts of roughly 187 model tokens, the lexical Query-Aware implementation had low single-digit-millisecond compression time. That timing does not establish performance on long documents, multilingual traffic, concurrent production load, or a different runtime.

The predecessor's own predeclared practical acceptance criterion was not met. HotpotQA was unavailable, human review was not completed, the evaluation was English-only, and actual invoice savings were not reconciled. Therefore:
- no predecessor algorithm is approved as a production default;
- the existing TF-IDF approach is an experimental baseline, not a proven solution;
- LLMLingua-2 is not suitable as the default path based on the measured latency and quality results;
- all candidate strategies must be re-evaluated on representative Metis workloads before activation.

Only aggregate, non-customer benchmark findings are recorded here. No private brief, customer data, raw prompts, API credentials, private dataset, response cache, or per-example private experiment output belongs in this public repository.

## 4. Goals

1. Reduce eligible, billable/uncached context input tokens when doing so is demonstrably safe and economically useful.
2. Preserve answer quality within a predeclared non-inferiority margin.
3. Keep optimization overhead small and predictable.
4. Preserve exact source text, provenance, and original ordering for retained segments.
5. Make behavior deterministic, explainable, testable, and provider-agnostic.
6. Fail open: on uncertainty, unsupported input, tokenizer failure, or internal error, return the original context unchanged.
7. Provide a minimal stable API that another team can wrap in its own architecture.

## 5. Non-goals

The library will not:
- summarize, paraphrase, or generate replacement facts;
- modify system/developer instructions, user messages, tool definitions, function schemas, JSON schemas, or response-format constraints;
- make LLM or embedding API calls;
- own RAG retrieval, reranking, caching, model routing, provider clients, pricing tables, or request retries;
- expose an HTTP service or require a database;
- store prompts, context, customer data, or API responses;
- claim dollar savings from token deltas alone;
- promise support for every language before language-specific evaluation.

## 6. Design principles

### 6.1 Safe no-op before aggressive compression

The optimizer must be able to decide that no optimization is appropriate. No-op is a successful result, not an error. Compression is opt-in through explicit policy and should remain disabled in production until the quality gate is passed.

### 6.2 Optimize eligible context, never an arbitrary prompt

The caller provides a collection of eligible context segments. The library does not accept an untyped list of chat messages and attempt to infer what is safe to remove.

System/developer instructions, user intent, tool contracts, structured-output constraints, and caller-pinned segments are outside the optimizer's authority.

### 6.3 Select source text; do not rewrite it

The default strategies select complete source spans. They must not paraphrase or synthesize content. Retained text must remain byte-for-byte equivalent to the source segment. If safe boundaries cannot be identified, keep the segment intact or bypass optimization.

### 6.4 Exact token budgets are injected

The core must not use regex token proxies or assume a particular model tokenizer. The host injects a `TokenCounter` implementation for the target model/provider and the exact rendering convention used by the host. If exact counting is unavailable, optimization is bypassed.

### 6.5 No hidden network or model work

Importing or calling the core must not download models, load credentials, initialize provider SDKs, or access the network. Any future optional scorer must be injected by the host and must declare its own latency/cost.

### 6.6 Deterministic and observable

Given the same request, policy, tokenizer, and scorer, the optimizer returns the same selection. Diagnostics explain whether optimization was applied and why, without logging raw context.

## 7. Proposed architecture

Keep the implementation small and dependency-light.

### 7.1 Core components

1. **Public data contracts**
   - `ContextSegment`: stable segment ID, exact text, source/provenance identifier, optional priority, optional caller-supplied relevance score, and a pinned/must-keep flag.
   - `OptimizationRequest`: query, ordered segments, exact context token budget, and rendering configuration.
   - `OptimizationPolicy`: minimum input size, minimum useful token saving, maximum compression aggressiveness, and allowed strategies.
   - `OptimizationResult`: rendered optimized context, selected segment IDs, original/optimized token counts, applied flag, selected strategy, bypass/fallback reason, and elapsed time.

2. **Token counter protocol**
   - A small interface that counts the final rendered context exactly for the target model.
   - The host can provide its existing tokenizer implementation.
   - An optional tokenizer adapter may be added only when it does not force a heavyweight runtime dependency.

3. **Context renderer protocol**
   - Counts must apply to the same final text the host will send.
   - The default renderer may join segments with a documented separator.
   - A host-specific renderer can be injected when titles, citations, or delimiters are added by the gateway.

4. **Scoring protocol**
   - The scorer ranks eligible segments against the query.
   - Candidate implementations are isolated behind one interface.
   - The optimizer can consume already-computed retrieval/embedding scores; it must not generate embeddings itself.

5. **Budgeted selector**
   - Reserves pinned segments first.
   - Adds remaining segments within the exact budget using stable tie-breaking.
   - Returns retained segments in original source order, not score order.
   - Never silently exceeds the supplied token budget.

6. **Policy and fallback layer**
   - Bypasses small inputs, empty queries, unsupported content, unavailable tokenizers, invalid budgets, low expected savings, and low-confidence cases.
   - Returns original context unchanged on unexpected failures.
   - Exposes a machine-readable reason code.

### 7.2 Candidate strategies

The implementation should compare, rather than assume, the winning strategy:

- **No-op:** full context; mandatory control and fallback.
- **Exact deduplication:** remove only byte-identical duplicate segments when provenance can be safely merged and retained.
- **BM25 lexical ranking:** deterministic lexical relevance baseline.
- **Character n-gram TF-IDF:** predecessor baseline; retained for comparison, not presumed default.
- **Hybrid lexical ranking:** combine BM25/phrase signals with caller-provided retrieval scores. Weights must be selected using held-out evaluation, not intuition.
- **Optional external relevance scores:** consume scores already available from the host (including embeddings computed upstream); no new embedding call inside this library.

No strategy becomes the default solely because it reduces more tokens. The selected default must pass quality, latency, and net-savings gates.

### 7.3 Conservative segmentation

Prefer the retriever's existing chunks. If a segment exceeds the available budget, split only at reliable sentence/paragraph boundaries while preserving exact source offsets and provenance. Do not split code blocks, tables, identifiers, or structured payloads heuristically. If safe segmentation is not possible, retain the segment or bypass.

Do not add abstractive summarization to the first release.

## 8. Public API direction

The exact names can be finalized during implementation, but the public surface should remain close to:

```python
result = optimizer.optimize(
    query=query,
    segments=eligible_context_segments,
    token_budget=context_token_budget,
    token_counter=host_token_counter,
    renderer=host_context_renderer,
    policy=policy,
)
```

The result should expose at least:
- `context`: exact text to pass to the host's request builder;
- `selected_segment_ids`: provenance for retained content;
- `original_tokens` and `optimized_tokens`;
- `tokens_saved` and `reduction_ratio`;
- `applied` and `strategy`;
- `reason_code` / `fallback_reason`;
- `latency_ms`.

The library reports token deltas, not dollar savings. The host calculates net economics using the actual model tariff, prompt-cache state, and compute cost.

## 9. Safety, privacy, and reliability requirements

- Fail open to the original context for every unexpected error.
- Never remove caller-pinned segments.
- Never exceed the exact token budget for the rendered output.
- Preserve retained text exactly; no hallucinated or generated replacement text.
- Preserve stable segment IDs, source IDs, and source order.
- Treat retrieved text as untrusted data, not instructions to the optimizer.
- Do not log raw queries, context, customer identifiers, credentials, or provider responses.
- Telemetry may include counts, strategy, reason codes, latency, and opaque request correlation IDs only.
- Do not mutate caller-owned input objects.
- Reject duplicate segment IDs or ambiguous provenance rather than silently corrupting references.
- Avoid hidden retries, network calls, global mutable state, and non-deterministic randomness.
- Expose a kill-switch-compatible policy so the host can disable optimization without redeploying the library.

## 10. Quality, performance, and economic acceptance gates

These are proposed release gates, not claims about current performance. The thresholds must be fixed before the final acceptance benchmark.

### Quality gate

- Evaluate on representative, held-out Metis workloads with the same downstream model, prompt, retrieval results, and generation settings for full-context and optimized variants.
- Use paired evaluation and confidence intervals; include human review for answer correctness, evidence sufficiency, citations, numbers, entities, and negation.
- Proposed overall non-inferiority threshold: the lower bound of the 95% confidence interval for the quality-score delta must be no worse than **-1.0 percentage point** versus full context.
- No critical regression is allowed for high-risk or policy-sensitive request classes.
- Report per-language, per-task, and per-context-length results; aggregate scores must not hide a failing segment.

### Token and economic gate

- Report exact target-model input-token reduction, not regex proxies.
- Evaluate uncached and cached prompt portions separately.
- Proposed minimum: at least **10% median reduction on eligible requests**, with positive net savings after tokenizer/scoring CPU cost and actual cache-aware pricing.
- Bypass requests where expected savings are below the configured minimum.
- Do not hardcode provider prices in this package.

### Latency and resource gate

- Proposed initial target: p95 optimizer latency no greater than **10 ms for contexts up to 8,000 tokens** on a documented reference machine.
- Measure p50/p95/p99, throughput, memory, cold/warm behavior, and concurrent load.
- Benchmark realistic long contexts as well as the small contexts used by the predecessor research.
- If the latency target is not met, simplify the scorer or bypass large inputs; do not add a model call to hide a weak selector.

### Reliability gate

- Deterministic results for identical inputs/configuration.
- 100% budget compliance in property and fuzz tests.
- Fail-open behavior verified for tokenizer, renderer, scorer, and malformed-input failures.
- No raw prompt/context in logs or telemetry.
- Supported Python versions and dependency constraints tested in CI.

## 11. Evaluation plan

The benchmark must compare full context, no-op, lead truncation, predecessor TF-IDF, BM25, hybrid ranking, and any optional upstream-score strategy under identical token budgets.

The evaluation corpus should include:
- representative, permission-cleared Metis requests and retrieved context, anonymized before entering the benchmark;
- long-context and multi-document RAG cases;
- multilingual cases only for languages the team intends to support;
- adversarial and edge cases involving negation, dates, numbers, identifiers, names, code, tables, citations, and conflicting evidence;
- public QA/RAG datasets where licensing and task fit are appropriate.

Use separate development and held-out test sets. Avoid tuning on the final test set. Use paired bootstrap confidence intervals and blinded human review for a representative subset. Record dataset provenance, model/version, prompts, tokenizer, budget, hardware, dependencies, and code revision. Never invent missing scores or use answer labels during compression.

## 12. Package boundaries and repository structure

Proposed minimal layout:

```text
prompt-compression/
├── README.md
├── pyproject.toml
├── LICENSE
├── src/
│   └── context_optimizer/
│       ├── __init__.py
│       ├── contracts.py
│       ├── tokenizer.py
│       ├── rendering.py
│       ├── scoring/
│       ├── selection.py
│       ├── policy.py
│       └── optimizer.py
├── tests/
│   ├── unit/
│   ├── property/
│   └── integration/
├── benchmarks/
│   ├── README.md
│   └── harness/
└── docs/
    ├── architecture.md
    ├── evaluation.md
    ├── integration.md
    └── operations.md
```

The exact file split should follow actual implementation size; do not create empty abstraction layers. Keep benchmark tooling outside the runtime package.

### Runtime and dependency proposal

- Python 3.11+ as the initial reference package, consistent with the predecessor implementation.
- Core runtime should use the standard library wherever practical.
- No mandatory scikit-learn, transformers, torch, LLMLingua, OpenAI SDK, web framework, or database.
- Optional tokenizer/scorer adapters must be extras or host-injected implementations.
- Type annotations, `py.typed`, semantic versioning, and a small documented public API.
- If the Metis backend cannot consume Python packages, the integration team can port the language-neutral contracts and algorithm; this repository will not add a sidecar service merely to bridge runtimes.

The Metis Gateway repository/runtime was not available during this design review. Provider-specific and gateway-specific integration is intentionally left to the receiving team.

## 13. Alternatives considered

| Approach | Decision | Reason |
|---|---|---|
| Extend the predecessor repository in place | Reject | Research artifacts, benchmark code, API experiments, and optional ML dependencies make a clean production handoff harder. |
| Make LLMLingua-2 or another LLM compressor the default | Reject for v1 | The predecessor showed materially higher latency and quality loss; inference/model dependencies also add operational cost. |
| Build a hosted compression microservice | Reject | Adds network hop, deployment, availability, privacy, and operational complexity without a demonstrated need. |
| Build a small standalone, deterministic library with pluggable scoring | **Selected** | Minimal integration surface, no hidden network/model dependency, measurable behavior, and a safe path to evolve algorithms. |

## 14. High-level delivery roadmap

1. **Design and contract approval** — approve scope, public API, safety boundary, runtime assumption, and release gates.
2. **Minimal package foundation** — packaging, typed contracts, token-counter/renderer protocols, no-op behavior, and fail-open semantics.
3. **Safe selection engine** — pinned segments, exact deduplication, deterministic budget packing, provenance, and conservative segmentation.
4. **Candidate scoring** — BM25, predecessor TF-IDF baseline, and hybrid use of upstream retrieval scores behind one scorer interface.
5. **Evaluation and strategy selection** — representative datasets, paired quality evaluation, human review, confidence intervals, and a documented winning strategy (or decision to keep no-op).
6. **Performance and hardening** — long-context profiling, property/fuzz tests, multilingual edge cases, privacy review, and dependency audit.
7. **Integration handoff** — minimal examples, stable API, host-owned tokenizer/renderer adapter contract, shadow-mode instructions, and telemetry schema.
8. **Controlled rollout** — shadow mode, canary, automatic bypass/kill switch, rollback procedure, and production acceptance review.
9. **Release** — versioned package, changelog, compatibility policy, security/contact guidance, and team handoff checklist.

No phase should skip the quality gate. If no strategy passes, release the library with safe no-op and diagnostics rather than shipping an unsafe compressor.

## 15. Open assumptions to confirm

1. Python 3.11+ is the reference implementation language because the research baseline is Python; the receiving Gateway runtime has not been inspected.
2. The host team will provide exact token counting and final context rendering for each supported model/provider.
3. The host team will identify which context segments are eligible and which must be pinned.
4. Representative, permission-cleared evaluation data and the downstream evaluation model will be made available before production activation.
5. The proposed quality, token-saving, and latency thresholds are release gates to approve before the final benchmark.

## 16. Approval requested

Please review this design before implementation. In particular, confirm:
- the selected approach: a new, minimal, deterministic library rather than extending the research project;
- the conservative, source-preserving scope and fail-open default;
- Python 3.11+ as the reference implementation;
- the proposed acceptance thresholds and phased roadmap.

**No production code or scaffolding should be added until this design is approved.**
