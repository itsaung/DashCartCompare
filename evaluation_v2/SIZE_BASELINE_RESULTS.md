# Checkpoint 3.1: numeric package-size matching — results

Frozen 2026-09-19. Evaluates the `tfidf_dimension_size_filter` baseline — the direct evidence-based
follow-up to [`BASELINE_RESULTS.md`](../evaluation/BASELINE_RESULTS.md)'s E7 finding that 9 of 14
representative failures were a candidate with the *right* package dimension (weight/volume/count)
but the *wrong* actual number — against the same frozen catalog and the same dev/validation/test
split as Checkpoint 3's v1 report. **`evaluation/BASELINE_RESULTS.md` and everything under
`evaluation/` are unmodified by this work**, per the plan's rule that v1 stays immutable and a later
model gets its own report.

## 1. What's new

`retrieval.filter_by_package_size()` adds a numeric check on top of `filter_by_dimension`'s existing
category check (weight/volume/count), applied by a new function, `attribute_and_size_filter_baseline`
— not a modification of `attribute_filter_baseline`. `tfidf_dimension_size_filter` is
`attribute_and_size_filter_baseline` at `min_similarity=0.0`, mirroring `tfidf_dimension_filter`'s own
shape; there is no threshold-tuned variant of this baseline yet (Checkpoint E6 was not re-run for it
— see §5).

The comparison it makes: `parse_shopping_line`'s requested canonical quantity/unit against each
catalog row's canonical **per-pack** amount (`pkg_canonical_total / pkg_count`), within a 1% relative
tolerance for genuine cross-unit rounding (2 L / 67.6 fl oz), never a same-unit fudge factor. Per-pack
rather than total, because `parse_shopping_line` doesn't understand a trailing "x N ct" multipack
multiplier in request text — see §4 for where this choice helps and where it doesn't. An unresolvable
request size or catalog package is never filtered (unknown is not a confirmed mismatch, the same rule
`filter_by_dimension` already follows).

## 2. Side by side with `tfidf_dimension_filter` (its closest v1 sibling), practical view

| Metric | Split | v1 `tfidf_dimension_filter` | v2 `tfidf_dimension_size_filter` |
|---|---|---|---|
| Success@1 | dev | 76.6% (59/77) | **83.1% (64/77)** |
| Success@1 | validation | 76.0% (19/25) | **88.0% (22/25)** |
| Success@1 | test | 95.0% (19/20) | **100.0% (20/20)** |
| Hit@5 | dev | 85.7% (66/77) | **90.9% (70/77)** |
| Hit@5 | validation | 92.0% (23/25) | **96.0% (24/25)** |
| Hit@5 | test | 95.0% (19/20) | **100.0% (20/20)** |
| MRR@5 | dev | 0.794 | **0.863** |
| MRR@5 | validation | 0.811 | **0.913** |
| MRR@5 | test | 0.950 | **1.000** |
| Returned-match accuracy | dev | 74.7% | **86.5%** |
| Returned-match accuracy | validation | 70.4% | **84.6%** |
| Returned-match accuracy | test | 82.6% | **90.9%** |
| Return coverage | dev | 87.8% | 82.2% |
| Return coverage | validation | 90.0% | 86.7% |
| Return coverage | test | 76.7% | 73.3% |
| False return on unanswerable | dev | 0.385 | **0.154** |
| False return on unanswerable | validation | 0.400 | **0.200** |
| False return on unanswerable | test | 0.300 | **0.200** |
| False abstention | dev | 0.039 | 0.065 |
| False abstention | validation | 0.000 | 0.000 |
| False abstention | test | 0.000 | 0.000 |

A consistent, real win across every split on every retrieval-quality metric, and a meaningful drop
in false returns on unanswerable requests — the size filter is catching real problems, not just
reshuffling ties. The cost: return coverage drops a few points on every split (more requests
correctly get no confident answer rather than a confidently wrong one), and dev's false-abstention
rate roughly doubles (3.9% → 6.5%, still small in absolute terms — 5 requests). Exact/flexible
breakdown (dev): exact 86.0%→90.7% Success@1, flexible 64.7%→73.5% — the size filter helps generic
requests more, which makes sense: a flexible request has no brand/variant signal to lean on, so a
wrong-size candidate was more likely to win on lexical score alone before this filter existed.

Conservative bounds (dev, answerable n=77): 64 confirmed correct, 7 confirmed incorrect, **1
unresolved** → lower bound 83.1%, upper bound 84.4% — the first case in this project where the
conservative/practical bounds genuinely diverge (a best-guess pair became this baseline's own
returned top-1). Zero of 72 scored top-1 predictions touch a guessed label otherwise.

Pool Recall@5 also improved on every split (dev: 63.8% → 78.8% practical), for the same structural
reason as v1's pool-ranking numbers: the filter changes what's counted as "retrieved," and a
correctly-sized candidate that was previously outranked by a wrong-size one now surfaces.

## 3. Latency

| Baseline | Median | p95 |
|---|---|---|
| v1 `tfidf_dimension_filter` | 1,520.9 ms | 1,946.7 ms |
| v2 `tfidf_dimension_size_filter` | 1,919.5 ms | 2,690.1 ms |

Roughly 25-40% slower — the added `filter_by_package_size` pass iterates the same candidate list a
second time. Not optimized in this pass; worth profiling before treating either baseline's latency as
production-representative (a pre-existing, disclosed concern from `BASELINE_RESULTS.md` §5).

## 4. What's still wrong (11 remaining answerable-request top-1 failures, down from 22)

Roughly half of v1's `tfidf_dimension_filter` failures are gone. Of the 11 that remain:

**Genuinely unresolvable candidate sizes let a wrong candidate through** (the limitation flagged
when this baseline was first sanity-checked, now confirmed at scale): r098 `9 oz deli turkey breast`
and r111 `7 oz deli turkey` both still return "Deli Fresh Turkey Breast **Mega Pack**" — an
unspecified, unparseable size, so the filter has nothing to reject it on. r024/r117/r143 (`Honeycrisp
apples`, various phrasings) similarly return "Organic Honeycrisp Apples (**each**)" — a per-item,
variable-price listing with no fixed canonical total. The filter can reject a *confirmed* mismatch;
it cannot manufacture confidence the catalog data doesn't have, so an unresolvable-size candidate can
end up ranked above a real one that got correctly filtered out elsewhere.

**A new, distinct limitation found in this pass: comparing per-pack rather than total is wrong for a
"buy-one-of-these" multipack the shopper meant as the TOTAL, not the per-unit size.** r109 `5.3 oz
cottage cheese` now returns "Daisy 4% Cottage Cheese Classic 2 Pack (**5.3 oz x 2 ct**)" — this
product's canonical total is 10.6 oz (two 5.3 oz cups), and its per-pack amount (5.3 oz) is what
`filter_by_package_size` compares against, so it passes the filter even though buying it gets you
double the requested amount. This is the exact opposite of the design tradeoff that made the "12 fl
oz x 12 ct Diet Coke" case work correctly (§1) — there, the shopper's stated number *was* the
per-can size; here, the shopper's stated number is the *total* they want, and a multi-cup pack
doesn't satisfy that. `apply_new_candidate_review.py`'s own labeling logic already gets this case
right (it compares total, not per-pack, and correctly marks a "5.3 oz x 2 ct" candidate `Incorrect`
against a "5.3 oz" request) — the retrieval filter and the labeling logic now disagree with each
other on this one pattern, which is worth resolving before this baseline is trusted further. A
principled fix likely needs to distinguish "the shopper named a per-unit size" from "the shopper
named a total" using more context than `parse_shopping_line` currently extracts (e.g. an explicit
multipack phrase in the request text) rather than a blanket per-pack-vs-total choice.

**Everything else is unchanged from v1's own analysis**: r021's loaf pan, r033's "Dozen Roses", and
r096/r144's tuna/cat-food confusions are lexical/wrong-product-type misses the size filter was never
going to fix (see `BASELINE_RESULTS.md` §4) — r114's `13.1 oz crackers` vs a `13 oz` candidate is a
new near-miss of the same close-size-still-wrong pattern §4 already documented for r105/r111 there.

## 5. Reproduction

```bash
cd dash
# v1's E1/E2/candidate pool are reused as-is -- no need to re-run build_benchmark.py/build_splits.py
.venv/bin/python run_experiments_v2.py            # E4: pool + full-catalog predictions for the new baseline
.venv/bin/python apply_new_candidate_review_v2.py  # E4: judge the 94 newly-discovered candidates
.venv/bin/python evaluation_metrics_v2.py          # E5: evaluation_v2/metrics.json + RESULTS_TABLE.md
```

All outputs live under `evaluation_v2/`, separate from `evaluation/`. `.venv/bin/pytest -q` runs the
full suite, including hand-calculated fixtures for `filter_by_package_size` and the new baseline
functions.

## 6. Next steps

1. **Resolve the per-pack-vs-total disagreement (§4)** between `filter_by_package_size` and the
   labeling logic before trusting this baseline's numbers as final — it's a real, disclosed
   inconsistency, not yet a correctness bug fix.
2. Consider a threshold-tuned variant (`tfidf_dimension_size_filter_threshold`), the same E6 step v1
   went through, once (1) is resolved.
3. The unresolvable-candidate-size limitation (r098/r111/r117-style) suggests catalog data
   completeness, not matcher logic, is now a real bottleneck for a meaningful slice of remaining
   failures — worth measuring how much of the catalog has an unparseable `raw_size` before
   investing further in matcher-side fixes.
