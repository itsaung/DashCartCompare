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

The comparison it makes: the shopper's requested canonical **total** against each catalog row's own
canonical total (`pkg_canonical_total`), within a 1% relative tolerance for genuine cross-unit
rounding (2 L / 67.6 fl oz), never a same-unit fudge factor. Both sides are always a total, never a
per-pack amount (see the 2026-09-19 fix note below) — `parse_shopping_line`'s own
`canonical_quantity` doesn't understand a trailing "x N ct" multipack multiplier in request text
(e.g. "12 fl oz x 12 ct Diet Coke" parses to 12, the per-can size, dropping "x 12 ct"), so a small
regex (`_MULTIPACK_PHRASE_RE`) looks for that exact phrase shape in the raw request text first and,
when found, re-parses just that phrase with `normalize.parse_package_size()` — the same, more
capable parser the catalog's own `raw_size` strings and `claude_auto_label.py`'s `expected.size`
comparisons already use — to get the true total (144 fl oz, not 12). Falling back to
`parse_shopping_line`'s own canonical quantity, which is already a correct total for any non-multipack
request. An unresolvable request size or catalog package is never filtered (unknown is not a
confirmed mismatch, the same rule `filter_by_dimension` already follows).

**2026-09-19 fix:** the first version of this filter compared per-pack amounts
(`pkg_canonical_total / pkg_count`) instead, to correctly handle the multipack case above without
understanding "x N ct" text at all. That worked for genuine multipacks but broke a plain request like
"5.3 oz cottage cheese," which was wrongly matched against a "5.3 oz **x 2 ct**" (10.6 oz total) pack
-- the shopper's number there is the total, not a per-cup size, and `apply_new_candidate_review.py`'s
labeling logic already compared totals and correctly rejected it, so the retrieval filter and the
labeling logic actively disagreed on this pattern (documented in the first version of this report,
§4). The multipack-phrase extraction above resolves it: every comparison is now total-vs-total, for
both the multipack and non-multipack cases, matching the labeling logic exactly. Verified against
real data: r109 (the exact case above) is no longer a failure (§4).

## 2. Side by side with `tfidf_dimension_filter` (its closest v1 sibling), practical view

| Metric | Split | v1 `tfidf_dimension_filter` | v2 `tfidf_dimension_size_filter` |
|---|---|---|---|
| Success@1 | dev | 76.6% (59/77) | **84.4% (65/77)** |
| Success@1 | validation | 76.0% (19/25) | **88.0% (22/25)** |
| Success@1 | test | 95.0% (19/20) | **100.0% (20/20)** |
| Hit@5 | dev | 85.7% (66/77) | **90.9% (70/77)** |
| Hit@5 | validation | 92.0% (23/25) | **96.0% (24/25)** |
| Hit@5 | test | 95.0% (19/20) | **100.0% (20/20)** |
| MRR@5 | dev | 0.794 | **0.871** |
| MRR@5 | validation | 0.811 | **0.913** |
| MRR@5 | test | 0.950 | **1.000** |
| Returned-match accuracy | dev | 74.7% | **87.8%** |
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

Conservative bounds (dev, answerable n=77): 65 confirmed correct, 6 confirmed incorrect, **1
unresolved** (the remaining 5 abstained) → lower bound 84.4%, upper bound 85.7% — the first case in this project where the
conservative/practical bounds genuinely diverge (a best-guess pair became this baseline's own
returned top-1). Zero of the other scored top-1 predictions touch a guessed label.

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

## 4. What's still wrong (10 remaining answerable-request top-1 failures, down from 22)

Of v1's `tfidf_dimension_filter` failures, exactly half are gone. The r109 per-pack-vs-total case
described above no longer appears in this list at all -- confirmed directly against real data after
the fix, not assumed.

**Genuinely unresolvable candidate sizes let a wrong candidate through** (the limitation flagged
when this baseline was first sanity-checked, now confirmed at scale): r098 `9 oz deli turkey breast`
and r111 `7 oz deli turkey` both still return "Deli Fresh Turkey Breast **Mega Pack**" — an
unspecified, unparseable size, so the filter has nothing to reject it on. r024/r117/r143 (`Honeycrisp
apples`, various phrasings) similarly return "Organic Honeycrisp Apples (**each**)" — a per-item,
variable-price listing with no fixed canonical total. The filter can reject a *confirmed* mismatch;
it cannot manufacture confidence the catalog data doesn't have, so an unresolvable-size candidate can
end up ranked above a real one that got correctly filtered out elsewhere. This is now the dominant
remaining failure mode (5 of 10) — see §6.

**Everything else is unchanged from v1's own analysis**: r021's loaf pan, r033's "Dozen Roses", and
r096/r144's tuna/cat-food confusions are lexical/wrong-product-type misses the size filter was never
going to fix (see `BASELINE_RESULTS.md` §4) — r114's `13.1 oz crackers` vs a `13 oz` candidate is a
new near-miss of the same close-size-still-wrong pattern §4 already documented for r105/r111 there.

A separate, known parsing gap (pre-existing in v1, not introduced or fixed here): `parse_shopping_line`
mis-parses "a 12 fl oz x 12 ct **pack of** ..." phrasing (r142's exact text) as a bare count with
dimension `"count"`, so `filter_by_dimension` rejects every real (volume) candidate before
`filter_by_package_size` ever runs — v1's `tfidf_dimension_filter` already returns
`no_acceptable_match` for r142 for the identical reason. Out of scope for this fix (which was about
`filter_by_package_size`'s own comparison, not `parse_shopping_line`'s dimension detection), noted
here so it isn't mistaken for a regression.

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

1. ~~Resolve the per-pack-vs-total disagreement between `filter_by_package_size` and the labeling
   logic~~ — **done 2026-09-19** (§1, §4).
2. The unresolvable-candidate-size limitation (r098/r111/r117-style) is now the dominant remaining
   failure mode (5 of 10) — suggests catalog data completeness, not matcher logic, is the real
   bottleneck for this slice. Worth measuring how much of the catalog has an unparseable `raw_size`
   before investing further in matcher-side fixes.
3. Consider a threshold-tuned variant (`tfidf_dimension_size_filter_threshold`), the same E6 step v1
   went through.
4. The `parse_shopping_line` "pack of" dimension-detection gap noted in §4 (pre-existing, affects
   both v1 and v2 identically) is worth fixing on its own merits, separate from this baseline.
