# Production-readiness audit

Assessment date: 2026-11-02. Repository: `navid70/prompt-compression`.
Base revision: `6c69ed4444757d98fabe6aaf8442f797118c88a1`; changes are uncommitted on
`main`. This work and the Metis assessment are educational activities within
Rahnama College, as confirmed by the requester. No commercial use is asserted.

## Executive assessment

The library provides a tested, conservative selection boundary. It remains
pre-alpha and **is not established as production-ready**. Default operation is
still a dependency-free bypass. No new scorer was introduced or enabled.

Hardening closes malformed-input and packaging gaps and adds an evidence-driven
limit on candidate work. Synthetic invariants, type checks, package builds and
isolated installations pass locally. These checks cannot establish downstream
answer quality, real model-token savings, production latency or net economics.
Metis access and an aggregate data-quality assessment succeeded; exact-token and
quality evaluations remain blocked by missing host implementations and labels.

The audit inspected all tracked Python modules, synthetic fixtures, tests,
README, package configuration and CI. Targeted predecessor research covered its
README/configuration, final `benchmark_v2.py` implementation and related tests,
legacy `core.py`, and final aggregate analysis/summary. No predecessor files were
edited and no expensive model evaluations were repeated.

## Prioritized findings

P0 means immediate critical exposure; P1 means high-impact correctness or a release
blocker; P2 means material hardening/integration work; P3 means lower-priority
maintainability work. Release blockers below are distinguished from code defects.

| Priority | Finding and evidence | Affected files | Disposition |
| --- | --- | --- | --- |
| P0 | No P0 issue found within the inspected boundary. This is not a formal security assessment. | Repository-wide | No claim beyond inspection |
| P1 | `enabled="false"` was truthy, allowing malformed configuration to enable selection. `pinned=0` could silently treat intended mandatory material as removable. | `src/context_optimizer/contracts.py` | Fixed: boolean-only flags, regression tests |
| P1 | Policy integer fields accepted booleans/fractions/NaN; query and several segment/result fields accepted invalid types. Some failures escaped as incidental attribute/overflow errors. | `contracts.py`, `tests/test_contracts.py` | Fixed: explicit types/ranges, static validation messages, finite-number overflow handling |
| P1 | No independently validated production ranking or downstream quality/economic evidence. Metis `relevancy` is a retrieval signal, not human ground truth. This is a release blocker, not a selector defect. | `optimizer.py`, `benchmarks/runner.py`, integration boundary | Deferred: default stays disabled |
| P2 | Exact greedy admission repeatedly renders/counts growing candidates. Uncapped 1,024-segment synthetic inputs exceed the 10 ms target; text size alone does not predict cost. | `optimizer.py`, `contracts.py`, `benchmarks/scaling.py` | Mitigated: configurable 256-segment default cap before dependencies; residual host latency remains unverified |
| P2 | CI tested editable installs only; wheel/sdist installation and the typed marker were unchecked. The initial sdist contained benchmark-dependent tests without their benchmark modules/fixture. | `.github/workflows/ci.yml`, `pyproject.toml`, `MANIFEST.in`, `scripts/smoke_install.py` | Fixed: build/install smoke checks and explicit safe source-manifest inclusions |
| P2 | Exact target tokenizer, final renderer, request builder, eligible-segment/pinning policy and production scorer are not supplied. An API credential/model name does not supply these contracts. | `protocols.py`, `docs/integration.md` | Documented blocker; no fabricated Gateway adapter |
| P2 | Metis has repeated retrieved content and repeated message/chunk pairs. `chunk_id` alone cannot be assumed to identify a request segment uniquely; shared conversations/documents can leak across splits. | Metis relational inputs, host adapter/evaluation | Documented: use request-row identities, source provenance, grouped evaluation; no automatic deduplication |
| P2 | Python requirement is `>=3.11`; CI is configured for 3.11–3.13 on Ubuntu. Only 3.12.10 on Windows was executed in this session; newer versions and fresh remote CI are unverified. | `pyproject.toml`, CI | Deferred: expand tested versions/platforms after compatibility verification |
| P2 | Repository has no package LICENSE. Dataset authorization does not determine the software's redistribution license. | Package metadata/root | Deferred: maintainer must choose terms; none invented |
| P3 | Development/build dependency ranges and action major tags are not immutable supply-chain pins. | `pyproject.toml`, CI | Deferred: pin/review in the consuming release process |
| P3 | mypy checks the runtime package only; offline tooling/tests have runtime coverage but are not under the strict type-check gate. | `pyproject.toml`, `benchmarks/`, `scripts/` | Deferred |

## Implemented contracts and safety checks

Changed public files (14):

- Core: `src/context_optimizer/contracts.py`, `src/context_optimizer/optimizer.py`.
- Tests: `tests/test_contracts.py`, `tests/test_optimizer.py`, `tests/test_scaling.py`.
- Diagnostics: `benchmarks/scaling.py`, `scripts/smoke_install.py`.
- Packaging/configuration: `pyproject.toml`, `MANIFEST.in`, `.gitignore`,
  `.github/workflows/ci.yml`.
- Documentation: `README.md`, `docs/integration.md`, this audit.

Valid existing constructor arguments and public function signatures remain intact.
`OptimizationPolicy.max_segments: int | None = 256` is appended to the existing
fields, preserving positional arguments. A positive integer changes the limit;
`None` removes it for a separately profiled workload. Enabled requests above the
limit return `segment_limit_exceeded`, all original IDs, unavailable counts and
`context=None`, without dependency calls. This intentionally changes large enabled
requests to a safe bypass. It is not a hard deadline or a total-memory limit.

Constructors raise `TypeError`/`ValueError` for invalid contracts. Valid requests
retain the optimizer's dependency-error fail-open behavior. The host must catch
construction errors when converting untyped external input and reuse its original
request. Process-termination exceptions are not swallowed. No source is normalized,
summarized, split or clipped; retained segment objects and provenance are preserved.
Result ID collections are normalized to immutable tuples and reject duplicates.

The selector reserves pins, bypasses pinned overflow, scores only unpinned
segments, breaks score ties by original order, restores source order, and counts
each complete rendered candidate. Bypasses can exceed budget intentionally.
Greedy selection is not globally optimal and cannot exploit every nonmonotonic
token-boundary interaction. Arbitrary faulty/stateful host dependencies cannot be
proven exact or source-preserving by this package.

Regression coverage includes malformed flags/numbers/collections, Unicode and
multilingual scripts, decomposed characters, embedded NUL, code/tables, pinning,
duplicate IDs, invalid dependency outputs, candidate-stage exceptions, nonlinear
synthetic token boundaries, deterministic repetition and input immutability.
The randomized invariant test uses 150 reproducible cases with seed `20261102`.

See [integration guidance](integration.md) for a concrete host-protocol example,
full-request accounting, shadow/canary gates, kill switch, rollback and privacy-safe
telemetry. Runtime imports remain standard-library-only. No raw data logging,
model/provider calls, persistent cache, server or routing was added to the library.

## Metis assessment

Source: [poriniki/metis](https://huggingface.co/datasets/poriniki/metis).
Pinned dataset revision: `30f578f283b903cdbd06cd1b5f7f962f76452ded`.
Authenticated metadata reports `private=true`, manual gating and license `other`.
The actual `LICENSE.txt` is the Metis Educational Benchmark License, effective
2026-10-28: it limits use to Rahnama College educational benchmarking, prohibits
commercial improvement and redistribution, and requires confidentiality. The
requester explicitly confirmed this educational scope. Records and excerpts are
not included in this repository or report.

Authentication read `HF_TOKEN` from ignored `.env` without displaying it. The
initial unauthenticated metadata/split requests returned 401. Authenticated metadata
succeeded; the dataset-viewer split endpoint returned 501. No configs or official
train/development/test definitions could be verified through the viewer. The card
and file listing describe relational tables, not an official evaluation split.
Tables with different schemas must be read separately, with matching message/chunk
shards merged only within their table.

All 31 Parquet footers were inspected before record sampling. Their total stored
size is **1,105,658,756 bytes**. Footer row counts verify the core card figures:

| Table | Files | Rows |
| --- | ---: | ---: |
| Users | 1 | 448 |
| Bots | 1 | 1,830 |
| Sessions | 1 | 80,179 |
| Messages | 13 | 710,640 |
| RAG queries | 1 | 192,245 |
| Retrieved chunks | 10 | 994,031 |
| Flattened inputs | 1 | 70,375 |
| Billing items | 1 | 350,529 |
| Moderation actions | 1 | 3,635 |
| Tool calls | 1 | 439 |

Schema inspection found message/session/user/bot join keys, timestamps, message
content and JSON-text payloads. Chunk fields include `message_id`, `chunk_id`,
`content`, `corpusId`, `relevancy`, and reference metadata. There are no dedicated
human relevance grades, critical-evidence flags, gold answer fields or annotated
supporting-evidence IDs in the inspected schemas/card. Chat responses, citations,
moderation actions and retrieval scores must not be relabeled as ground truth.

Footer null statistics cover every file: message/session/content identifiers and
chunk content/relevancy/corpus identifiers have zero nulls. Two message timestamps
are null. Message `input` is null in 640,265 rows; citations in 607,083 rows. Chunk
`reference` is null in every row; `reference.url` is null in 897,160 rows and
`reference.page` in 814,908. One moderation `reason` field lacks footer statistics;
no null count was invented for it. Non-null identifiers do not prove join integrity,
uniqueness, completeness or record-level quality.

A bounded convenience sample read the first 1,024 chunk rows from shards 0, 4 and 9
(3,072 rows, 196 distinct message groups, 135 distinct corpus groups). It is not
random, representative, split into train/test or used for tuning.

| Sample diagnostic | Result |
| --- | ---: |
| Null sampled fields / blank content | 0 / 0 |
| Repeated content occurrences beyond the first identical string | 2,169 |
| Repeated `(message_id, chunk_id)` pairs beyond the first | 1,036 |
| Content length, Unicode code points: min / median / max | 51 / 360.5 / 3,138 |
| Finite retrieval scores | 3,072 |
| Score range | 0.01311245–0.9966666666666666 |
| Scores in [0,.25] / (.25,.5] / (.5,.75] / (.75,1] | 654 / 504 / 548 / 1,366 |
| Arabic/Persian-script pattern matches | 3,070 |
| Latin-script pattern matches | 1,245 |
| URL-like / email-like / Iranian-mobile-like matches | 522 / 0 / 0 |

Repeated retrieval can be legitimate; these are not proven erroneous duplicates.
Pattern checks are screening only, not confirmed PII detection or language
identification. Names, identifiers, credentials and many phone formats were not
exhaustively screened. Anonymized usernames do not establish anonymized free text.
Full-population duplicate/distribution/PII and foreign-key audits remain pending.

For future evaluation, prefer official splits if the owner supplies them. Otherwise
freeze conversation groups using `message.session_id -> session.session_id`, and
prevent shared source documents/content across splits using corpus/reference keys
and content fingerprints inside the private evaluation environment. Audit connected
groups before assigning development/held-out partitions; quarantine overlaps. Do not
tune against test groups. Supply independent human relevance/critical judgments and
answer references before quality measurement. No split or label was fabricated here.

### Reproducibility and privacy

Assessment used `huggingface_hub 2.4.0`, `pyarrow 26.0.0`, Python 3.12.10 and the pinned
revision. Metadata came from the authenticated Hub dataset/tree APIs; footer/schema
reads used `HfFileSystem.open(..., revision=..., block_size=65536)` and
`pyarrow.parquet.ParquetFile`. Nulls were summed from row-group column statistics.
Sampling used `iter_batches(batch_size=1024, columns=["message_id", "chunk_id",
"content", "corpusId", "relevancy"])` and the first batch of each named shard.
Content repetition used exact-string SHA-256 equality in memory; hashes and record
identifiers were not emitted. No normalization or model-token approximation occurred.

The local-only assessment script and detailed aggregate report remain outside the
public artifact set. Metadata/aggregates are cached under
`~/.cache/huggingface/stage3-metis/<revision>/`; raw sample batches stayed in memory.
The local assessment script digest is
`89b883c8a415fb2bda800f452339c739c708bc972251ac1228d8cb17bc975426`.
No complete dataset download or model evaluation was performed. Optional HF/Parquet
tools were installed only into the ignored audit environment, not runtime dependencies.
Repository cache/output paths and `.env` are ignored. CI uses synthetic data only.

## Benchmarks and evidence boundaries

### Current synthetic evaluation

Reproduce from the checkout after `pip install -e ".[dev]"`:

```bash
python -m benchmarks --repetitions 100 --warmups 5 --output benchmarks/results/stage3-synthetic.json
python -m benchmarks.scaling --output benchmarks/results/stage3-scaling.json
```

Implementation digest over package/benchmark Python files:
`1234d3a3ca28017c556eb9d92e6e996301e8baf968759565c23cce76b0e895e0`.
Fourteen synthetic fixtures use exact Unicode-code-point counts of the final
bracketed/separated rendering. Fixture scores and judgments are separate. These
units are not tokens of any target model. There are 100 measured calls and five
warmups per case/perspective; baseline full context does not invoke the optimizer.

| Perspective | Aggregate unit reduction | Weighted relevance recall | Critical retention | Applied / bypassed | Applied correctness failures |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full context | 0% | 100% | 100% | 0 / 0 | 0 |
| Fixture-ranked greedy | 29.23% | 66.67% | 50% | 9 / 5 | 0 |
| Oracle-ranked greedy | 28.21% | 86.67% | 100% | 9 / 5 | 0 |

Each optimizer perspective has three intentional fail-open budget excesses and no
applied budget violations. Bypass reasons are disabled, empty input, insufficient
savings, pinned overflow and already within budget, one case each. The synthetic
fixture-ranked selector loses critical evidence despite valid budget accounting;
correctness tests do not demonstrate quality. Oracle ranking is a reference, not
optimal subset selection. Segment recall is not downstream answer quality.

### Scaling

Reference machine: Windows 11 build 26300, Intel64 Family 6 Model 183 Stepping 1,
Python 3.12.10. Scaling uses exactly 8,000 or 32,000 synthetic code-point units,
equal scores, half-size budgets, 100 measured calls and five warmups. P50 is the
median; P95/P99 use nearest rank. Serial throughput includes loop instrumentation.
Peak memory is a separate single-call `tracemalloc` measurement of Python
allocations, excluding prepared input objects; it is not process RSS.

| Units / segments / policy | P50 ms | P95 ms | P99 ms | Calls/s | Peak Python bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| 8,000 / 16 / enabled | 0.047 | 0.102 | 0.159 | 16,769 | 27,614 |
| 8,000 / 128 / enabled | 0.974 | 1.443 | 1.523 | 980 | 36,986 |
| 8,000 / 256 / enabled | 2.886 | 4.408 | 5.124 | 323 | 49,426 |
| 8,000 / 1,024 / cap bypass | 0.103 | 0.211 | 0.230 | 8,001 | 50,772 |
| 8,000 / 1,024 / explicit uncapped | 37.006 | 48.765 | 51.525 | 27 | 181,366 |
| 32,000 / 128 / enabled | 0.843 | 1.500 | 1.687 | 1,039 | 108,674 |
| 32,000 / 1,024 / cap bypass | 0.093 | 0.161 | 0.164 | 9,397 | 50,772 |
| 32,000 / 1,024 / explicit uncapped | 46.206 | 74.239 | 114.359 | 20 | 229,448 |

Timing reflects this local run and host load; it is not a service-level guarantee.
The cap mitigates the observed quadratic candidate workload without sacrificing
exact rendered counts. It does not prove the 8,000-model-token latency gate.

### Reused predecessor evidence

The predecessor final summary digest is
`ab7ea40f326481384d6b4b6698c22823d0ed36c86d46a39864bd50091f2194b0`.
Its final aggregate CSV and implementation verify the previously reported SQuAD
figures: 200 held-out questions, full-context F1 90.49%; TF-IDF at 0.50 budget F1
76.47%, API input reduction 36.83%, F1-delta CI [-20.34, -8.65] percentage points.
Split TF-IDF F1 is 75.63%; LLMLingua-2 F1 is 63.35%. The exploratory 50-question
0.75 TF-IDF result has F1 88.28%, reduction 20.36%, delta CI [-6.80, +5.41] points.
Neither TF-IDF result passes the -1-point lower-bound gate.

This is reused historical aggregate evidence, not a fresh independent replay of
private responses or proof for this package/Metis. Legacy `core.py` uses regex
proxies; the final `benchmark_v2.py` instead uses `o200k_base` for its recorded
`gpt-4o-mini` experiment. Those versions/rendering do not establish an exact
tokenizer for the current configured Metis model. No predecessor scorer was ported.

### Real-data evaluation status

Metis schema/null/sample statistics above are measured real-data assessment results.
Real-data token reduction, budget compliance, relevant/critical retention,
optimizer latency and failure/bypass rates were **not measured**. The actual target
tokenizer and final context renderer are unavailable, eligibility/pinning rules are
unverified, and independent quality labels are absent from the inspected evidence.
No answer-quality or economic claim is supported. A model API key alone does not
resolve these blockers; no paid API call was made.

## Verification

Local verification used an isolated audit environment and actual command output:

| Command/check | Actual result |
| --- | --- |
| `python -m pytest -q --basetemp build/pytest-final --tb=short` | 146 passed in 7.64 s |
| `python -m ruff check .` | All checks passed |
| `python -m ruff format --check .` | 19 files already formatted |
| `python -m mypy src` | No issues in 4 source files |
| `python -m build --outdir dist` | Wheel and source archive built successfully |
| Fresh wheel install, `python -I scripts/smoke_install.py`, `pip check` | Smoke passed; no broken requirements |
| Fresh sdist install, isolated smoke, `pip check` | Smoke passed; no broken requirements |
| Tests run from extracted sdist source | 146 passed in 6.21 s; benchmark modules and fixture present |
| Artifact/privacy inspection | No `.env`, private data, internal notes or results in sdist; no credential-value matches in 25 public files |
| Audit environment `pip check` | No broken requirements |
| `pip-audit --local` after isolated pip upgrade | No known vulnerabilities found; local unpublished package skipped |
| Independent read-only review | No actionable findings; focused tests 103 passed |

The initial environment's bare pytest run had 61 passes and 17 fixture setup errors
because the sandbox default temp directory was inaccessible. Creating a workspace
build parent and using an explicit `--basetemp` resolved that environmental blocker.
The existing `.venv` lacked pytest and was preserved; audit tools used a new ignored
environment. Initial pip-audit reported 12 advisory records for pip 25.0.1 (including
duplicate advisory IDs), all in that tool. Updating isolated pip to 26.2.2 produced
the clean rescan. The package has zero mandatory runtime requirements; a package
name lookup is not a source-code security audit. Host/global tools were not changed.
One subsequent wheel reinstall emitted nonfatal sandbox-temp cleanup warnings;
installation, isolated smoke and `pip check` still completed successfully.

Fresh remote CI, Python 3.11/3.13/newer execution and complete provider integration
were not verified locally. CI now builds and installs both artifacts in isolated
environments outside the checkout, checks `py.typed`, exercises disabled/enabled
selection, and runs `pip check`. No credentials or Metis records are sent to CI.

## Acceptance gates and prioritized roadmap

| Gate | Status | Remaining evidence |
| --- | --- | --- |
| Default disabled; deterministic source/pin preservation; exact candidate checks; fail-open | Implemented and tested synthetically | Verify host dependency implementations and full-request assembly |
| Tests/lint/format/runtime type checks | Pass locally | Remote CI on supported interpreters/platforms |
| Wheel/sdist build and clean installation | Pass locally, Python 3.12 Windows | Matrix artifact checks in remote CI |
| Metis permission/access and bounded assessment | Pass for educational scope | Broader quality/PII/join-integrity assessment before expanded replay |
| Quality CI lower bound >= -1 pp; no critical regressions | Pending; historical TF-IDF fails | Independent labels/references, grouped held-out data, locked scorer/model |
| Median exact reduction >=10% | Pending | Actual versioned tokenizer/renderer on eligible Metis requests |
| p95 <=10 ms up to 8,000 target-model tokens | Pending | Host counter/renderer/scorer on reference runtime; synthetic cap evidence only |
| Positive cache-aware net savings after CPU cost | Pending | Actual pricing/cache/cost accounting and controlled comparison |
| Canary, kill switch and rollback | Documented; unexercised in host | Host-owned deployment/configuration and monitored control group |

1. Obtain the actual host tokenizer, request renderer/builder and eligibility/pinning
   contracts. Inspect the Gateway repository before any adapter; no location/runtime
   was supplied here. Resolve the package's software license before redistribution.
2. Within the authorized educational scope, audit joins, duplicates and privacy,
   establish independent relevance/critical/answer labels, and freeze grouped
   development and held-out sets. Never treat retrieval scores as ground truth.
3. Compare full context and candidate ranking strategies on identical locked inputs,
   using paired confidence intervals, critical-class analysis and exact accounting.
   Add no default scorer unless every gate passes; retain the no-op outcome otherwise.
4. Profile the actual host runtime and costs, run the interpreter/artifact CI matrix,
   then exercise shadow/canary rollback with privacy-safe aggregates. Passing package
   tests alone does not authorize production activation.
