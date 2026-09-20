# Checkpoint 4, S5 — hybrid retrieval

Run 2026-09-20. Same frozen catalog, requests, pool and splits as v1/v2/S4. `evaluation/` and
`evaluation_v2/` unmodified.

Fusion is reciprocal rank fusion over the lexical and embedding rankings, `RRF_K = 60` and
per-retriever depth 50, both declared in `checkpoint4_config.py` before the first run. Ranks only,
never the raw similarities — a TF-IDF cosine and an embedding cosine are not on a common scale, so
a weighted blend would need a calibration constant and a weight, both free parameters to tune on
dev. RRF has neither.

**Dev and validation results plus a test read. No model is selected (S7), no threshold is tuned
(S6). Nothing here is final.**

## Judgment coverage

Full-catalog search across all four baselines surfaced **426 candidates** no earlier round had
judged; all 426 adjudicated by the unchanged `adjudicate_new_candidate()` (126 Acceptable / 263
Incorrect / 37 Needs clarification). **Zero of 2,125 top-5 results unjudged**, checked before any
number below.

## Four-way comparison, practical view

Retriever is the only variable across the first three rows — identical parser gate, dimension
filter, package-size filter, depth and tie-break.

### dev (n=90, answerable n=77)

| Baseline | Success@1 | Hit@5 | Coverage | exact | flexible |
|---|---|---|---|---|---|
| `tfidf_dimension_size_filter` | 84.4% (65/77) | 90.9% | 82.2% | 90.7% | 76.5% |
| `embed_dimension_size_filter` | 87.0% (67/77) | 92.2% | 82.2% | 90.7% | 82.4% |
| **`hybrid_dimension_size_filter`** | **92.2% (71/77)** | 92.2% | 82.2% | 90.7% | **94.1%** |
| `hybrid_identity_filter` | 80.5% (62/77) | 81.8% | 71.1% | 69.8% | 94.1% |

### validation (n=30, answerable n=25)

| Baseline | Success@1 | Hit@5 | Coverage | exact | flexible |
|---|---|---|---|---|---|
| `tfidf_dimension_size_filter` | 88.0% (22/25) | **96.0%** | 86.7% | 100% | 72.7% |
| `embed_dimension_size_filter` | 92.0% (23/25) | 92.0% | 80.0% | 100% | 81.8% |
| `hybrid_dimension_size_filter` | 92.0% (23/25) | 92.0% | 80.0% | 100% | 81.8% |
| `hybrid_identity_filter` | 84.0% (21/25) | 84.0% | 76.7% | 85.7% | 81.8% |

### test (n=30, answerable n=20) — reported, not used for selection

| Baseline | Success@1 | Hit@5 | Coverage | exact | flexible |
|---|---|---|---|---|---|
| `tfidf_dimension_size_filter` | 100% (20/20) | 100% | 73.3% | 100% | 100% |
| `embed_dimension_size_filter` | 95.0% (19/20) | 100% | 70.0% | 100% | 87.5% |
| `hybrid_dimension_size_filter` | 100% (20/20) | 100% | 70.0% | 100% | 100% |
| `hybrid_identity_filter` | 65.0% (13/20) | 65.0% | 46.7% | 41.7% | 100% |

## Finding 1 — fusion works on dev, and validation does not confirm it

S4's hypothesis was that lexical and semantic strengths are complementary. On **dev** that holds
emphatically: flexible-mode Success@1 goes 76.5% → 82.4% → **94.1%**, and overall 84.4% → 87.0% →
**92.2%**, six more requests correct than the incumbent. Exact mode is 90.7% for all three, as
expected — an exact request carries brand and size tokens TF-IDF already matches literally.

**On validation the hybrid gain disappears.** Hybrid and embedding tie exactly (92.0%, 23/25,
flexible 81.8% both), and the incumbent's Hit@5 is actually the best of the four (96.0%). On test,
hybrid and the incumbent both hit 100%.

So the honest statement is: **fusion produced a large dev gain that validation did not replicate.**
With 25 validation requests (11 flexible), one request is 4 points and the split cannot resolve a
difference this size. The dev gain is real in the sense that it is 6 requests on n=77, not a
rounding artifact — but the evidence that it generalizes is currently absent, not merely weak.
S7 should not call hybrid the winner on dev alone.

## Finding 2 — the identity gate is a net harm as currently built

`hybrid_identity_filter` is the worst baseline on every split: dev 80.5%, validation 84.0%,
**test 65.0%**. Its exact-mode Success@1 collapses to **41.7% on test** (5/12) against 100% for
every other baseline, and coverage falls to 46.7%.

The mechanism is exactly what `CHECKPOINT_4_PLAN.md` Risk 5 predicted, now measured. S3's identity
gate requires a confirmed brand on both sides for an exact request and routes anything
unconfirmable to review. S2's extraction resolves a brand on 84.6% of catalog rows and 82.1% of
asserted brands were judged correct — so on any request where extraction truncates one side
(`Nature's` for Nature's Truth) or misses it entirely, a correct candidate is sent to review
rather than returned.

Note what this is **not**: the gate is not returning wrong answers. Its flexible-mode Success@1 is
94.1% on dev, identical to the ungated hybrid, and it never substitutes for an exact request. It
is trading correct answers for abstentions, which is the conservative direction — but at 46.7%
coverage on test it is trading far too many.

**This is a real, reportable negative result about S2/S3, not a reason to weaken the identity
rule.** The rule is right; the extraction underneath it is not accurate enough to support it yet.
Options for S7 to weigh, none taken here: require identity only when the *request* states a brand
(rather than whenever the mode is exact), improve extraction coverage, or report exact mode as a
capability the current pipeline cannot support at usable coverage.

## Finding 3 — hybrid latency is disqualifying as implemented

| Baseline | Median | p95 |
|---|---|---|
| `embed_dimension_size_filter` | 421 ms | — |
| `tfidf_dimension_size_filter` | 1,511 ms | — |
| `hybrid_dimension_size_filter` | **4,904 ms** | — |
| `hybrid_identity_filter` | 5,262 ms | — |
| All four, pooled | 654 ms median | 5,745 ms p95 |

Per-baseline wall time for 300 queries: embed 104s, embed+filter 64s, **hybrid 588s, hybrid+identity 617s.**

Hybrid runs both retrievers, so it inherits the slowest part of each — and the lexical half still
uses the unoptimized `retrieval._ranked`. At ~4.9 s per query, a 10-item list is ~49 seconds
against Checkpoint 6's sub-3-second target.

S4 fixed this on the embedding side with a top-N prefilter (`_ranked_top`, 4,165 ms → ~250 ms) but
deliberately left `lexical_search` alone to avoid perturbing v1/v2 reproduction. That decision now
has a measurable cost: **if hybrid is selected, the lexical prefilter stops being optional
cleanup and becomes a prerequisite.** Still not done here, for the same reproduction reason.

## Bug fixed this sub-checkpoint

`retrieval._ranked` has always emitted a numpy `int64` for `store_id` (it is an int64 column),
which `json.dump` refuses. It never surfaced because no caller wrote those dicts straight to JSON
until S4, and S4 fixed it only in its own `_ranked_top` — so it reappeared the moment the hybrid
path called the lexical retriever, after a 25-minute run that produced nothing. Now fixed
centrally in `retrieval._unwrap`, with `embedding_retrieval` reusing that one definition.

Two robustness changes came out of the same incident: predictions are written and flushed per
baseline rather than once at the end, so a completed baseline survives a later failure, and the
per-baseline progress line is flushed with its elapsed time so a long run can be distinguished
from a hung one.

## What S6 and S7 inherit

1. **Hybrid leads on dev and ties on validation.** S7's selection rule is "simplest method with
   the best validation tradeoff" — on validation, hybrid and embedding are identical and embedding
   is both simpler and 12x faster. That is the currently-supported reading.
2. **RRF scores live on a third scale** (~0.03 for a top result, not ~0.4 or ~1.0). S6 must derive
   cut points per baseline family; there is no shared threshold.
3. **The identity gate needs a decision, not a tuning pass.** No threshold rescues 46.7% coverage.
4. **Latency gates the demo, not the metrics.** Hybrid at ~4.9 s/query cannot ship to Checkpoint 6
   without the lexical prefilter.

## Reproduction

```bash
cd dash
.venv/bin/python run_experiments_v3.py            # ~22 min, four baselines
.venv/bin/python apply_new_candidate_review_v3.py # judge the 426 new candidates
.venv/bin/python evaluation_metrics_v3.py
```
