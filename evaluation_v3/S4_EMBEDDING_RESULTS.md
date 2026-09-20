# Checkpoint 4, S4 — embedding baselines

Run 2026-09-20. Same frozen catalog (31,398 rows), same 150 requests, same candidate pool and
same dev/validation/test split as v1 and v2. `evaluation/` and `evaluation_v2/` are unmodified.

Model: `sentence-transformers/all-MiniLM-L6-v2` pinned at HF revision `1110a243`, CPU-only,
384-dim, L2-normalized (see `model_manifest.json`).

**These are dev and validation results plus a test read that S7 will formally own. No model has
been selected yet, no threshold has been tuned (S6), and the hybrid baseline (S5) does not exist.
Nothing here is a final answer.**

## Judgment coverage

Full-catalog search surfaced **383 candidates** no earlier round had judged. All 383 were
adjudicated by `apply_new_candidate_review_v3.py`, reusing
`apply_new_candidate_review.adjudicate_new_candidate()` unchanged — 110 Acceptable, 243 Incorrect,
30 Needs clarification. **Zero of the 1,247 top-5 results across both baselines are unjudged**,
verified before any number below was computed.

## `embed_dimension_size_filter` vs its v2 counterpart

The two differ **only** in the retriever — same parser gate, same dimension filter, same
package-size filter, same prefilter depth, same tie-break.

| Metric | Split | v2 `tfidf_dimension_size_filter` | v3 `embed_dimension_size_filter` |
|---|---|---|---|
| Success@1 | dev | 84.4% (65/77) | **87.0% (67/77)** |
| Success@1 | validation | 88.0% (22/25) | **92.0% (23/25)** |
| Success@1 | test | **100.0% (20/20)** | 95.0% (19/20) |
| Hit@5 | dev | 90.9% (70/77) | **92.2% (71/77)** |
| Hit@5 | validation | **96.0% (24/25)** | 92.0% (23/25) |
| Hit@5 | test | 100.0% (20/20) | 100.0% (20/20) |
| Return coverage | dev | 82.2% | 82.2% |
| Return coverage | validation | **86.7%** | 80.0% |
| Return coverage | test | **73.3%** | 70.0% |
| False return (unanswerable) | dev | **0.154** | 0.231 |
| False return (unanswerable) | test | 0.200 | **0.100** |

### The real finding is flexible mode

| Success@1, flexible only | v2 | v3 |
|---|---|---|
| dev (n=34) | 76.5% | **82.4%** |
| validation (n=11) | 72.7% | **81.8%** |
| test (n=8) | **100.0%** | 87.5% |

Exact mode is unchanged on dev (90.7% both) and identical at 100% on validation and test. That is
the expected shape: an exact request carries brand and size tokens that TF-IDF already matches
literally, so there is nothing for semantics to add. A flexible request — "some tortillas",
"12 oz ground coffee" — has no such anchor, and that is where the embedding earns its place.

Pool Recall@5 moves the same way (dev 79.2% vs v2's 78.8% practical; validation 77.6% vs 77.x),
which is consistent with better ranking rather than a changed candidate set.

### Where it loses

Validation Hit@5 and return coverage both drop, and test Success@1 goes from 20/20 to 19/20.
**That single test request is 5 percentage points** — the test split has 20 answerable requests
and the incumbent was already saturated at 100%, so this split cannot distinguish the two methods
in either direction. It is a sanity check, not evidence. Any claim about which retriever is
better has to rest on dev (n=77) and validation (n=25), and even validation at n=25 moves 4 points
per request.

## `embed` (no gates), the counterpart of v1's `tfidf`

dev Success@1 71.4% (55/77), 100% return coverage, **false-return rate 1.0 on every split** — it
answers every unanswerable request, exactly as v1's ungated `tfidf` did. Its flexible-mode
Success@1 is 47.1% on dev against the gated baseline's 82.4%, which is the clearest single
statement of how much work the filters do: **the gates matter more than the retriever.**

## Latency — and an important caveat about this comparison

| Baseline | Median | p95 |
|---|---|---|
| v2 `tfidf_dimension_size_filter` | 1,510.7 ms | — |
| v3 `embed_dimension_size_filter` | **234.1 ms** | 259.1 ms |
| v3 `embed` | 263.4 ms | 364.4 ms |

Cold start (cached matrix load + model load) is 6,451 ms, paid once.

**Do not read this as "embeddings are 6x faster than TF-IDF."** The two paths do not share a
ranking implementation, and that is the whole difference:

`retrieval._ranked` builds a dict for every row scoring above zero, then sorts. TF-IDF cosine is
sparse, so most rows score exactly 0 and the list stays small. Embedding cosine is **dense** —
measured, 30,875 of 31,398 rows (98.3%) score positive against a real query — so `_ranked` built
and sorted a 31k-element list on every single query, at **4,165 ms**. The dot product itself is
~6 ms.

S4 therefore added `_ranked_top`: argpartition to the top 2,000, then the identical `score > 0`
rule and `cfg.tie_break_key` sort. Verified to return a byte-identical top-20 to the full sort on
12 real queries, plus two synthetic regression tests. That took the embedding path from 4,165 ms
to ~250 ms.

The lexical path never got that optimization, so **the honest reading is: the embedding path as
now implemented is ~6x faster than the lexical path as currently implemented.** Applying the same
prefilter to `lexical_search` would likely close much of the gap. That is a Checkpoint 6
prerequisite and deliberately not done here — changing the lexical path now would alter v1/v2
reproduction.

This does, though, settle the question `BASELINE_RESULTS.md` §5 left open and the demo raised
again: the per-query cost was never the similarity computation or the model. It was a ranking
helper written for sparse scores.

## What S5 and S6 inherit

1. **Embeddings help flexible mode and do nothing for exact mode.** A hybrid that fuses lexical
   and semantic ranking has a plausible mechanism to beat both, which is what S5 tests.
2. **The gates dominate.** `embed` → `embed_dimension_size_filter` is +15.6 points of flexible
   Success@1 on dev. Retriever choice is second-order next to that.
3. **Neither baseline has a threshold.** Both run at a 0.0 floor. S6 tunes accept/review cut
   points on dev, and the demo's finding still stands: right and wrong matches do not separate
   cleanly on a single score scale.
4. **Test is saturated and cannot arbitrate.** S7 must report it with counts and decline to draw
   a method conclusion from it.

## Reproduction

```bash
cd dash
.venv/bin/python run_experiments_v3.py            # predictions + new candidates + latency
.venv/bin/python apply_new_candidate_review_v3.py # judge the 383 new candidates
.venv/bin/python evaluation_metrics_v3.py         # metrics.json + RESULTS_TABLE.md
```
