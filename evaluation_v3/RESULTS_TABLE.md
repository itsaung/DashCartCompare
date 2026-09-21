# Checkpoint 4 -- final results table

Generated from `final_metrics.json` by `final_evaluation.py`. Full narrative, caveats
and failure analysis in `SEMANTIC_RESULTS.md`; this file is the numbers alone.

Shipped: **`embed_dimension_size_filter`**, accept 0.75552 / review floor 0.691613, selected on validation, frozen at `237b021fa6` before the test split was scored.

Every rate carries its numerator and denominator. Precision is automatic-match
precision: review-band outcomes and abstentions are excluded from numerator and
denominator both. The 95% criterion is judged on the conservative view, test split.

## `embed_dimension_size_filter` -- **shipped**

Cut points: accept 0.755520 / review floor 0.691613. Warm latency: median 421.4 ms, p95 578.1 ms (n=150).

| split | n | answerable | auto / review / abstain | auto-match rate | review rate | abstention rate | precision (conservative) | precision (practical) |
|---|---|---|---|---|---|---|---|---|
| dev | 90 | 77 | 65 / 12 / 13 | 72.2% (65/90) | 13.3% (12/90) | 14.4% (13/90) | 96.9% (63/65) | 96.9% (63/65) |
| validation | 30 | 25 | 23 / 3 / 4 | 76.7% (23/30) | 10.0% (3/30) | 13.3% (4/30) | 95.7% (22/23) | 95.7% (22/23) |
| test | 30 | 20 | 17 / 11 / 2 | 56.7% (17/30) | 36.7% (11/30) | 6.7% (2/30) | 100.0% (17/17) | 100.0% (17/17) |

| split | mode | n | auto / review / abstain | precision (conservative) |
|---|---|---|---|---|
| dev | exact | 47 | 39 / 0 / 8 | 100.0% (39/39) |
| dev | flexible | 43 | 26 / 12 / 5 | 92.3% (24/26) |
| validation | exact | 16 | 15 / 0 / 1 | 93.3% (14/15) |
| validation | flexible | 14 | 8 / 3 / 3 | 100.0% (8/8) |
| test | exact | 16 | 12 / 2 / 2 | 100.0% (12/12) |
| test | flexible | 14 | 5 / 9 / 0 | 100.0% (5/5) |

## `embed`

Cut points: accept 0.937030 / review floor 0.778590. Warm latency: median 567.3 ms, p95 1,401.0 ms (n=150).

| split | n | answerable | auto / review / abstain | auto-match rate | review rate | abstention rate | precision (conservative) | precision (practical) |
|---|---|---|---|---|---|---|---|---|
| dev | 90 | 77 | 33 / 41 / 16 | 36.7% (33/90) | 45.6% (41/90) | 17.8% (16/90) | 100.0% (33/33) | 100.0% (33/33) |
| validation | 30 | 25 | 14 / 11 / 5 | 46.7% (14/30) | 36.7% (11/30) | 16.7% (5/30) | 92.9% (13/14) | 92.9% (13/14) |
| test | 30 | 20 | 12 / 5 / 13 | 40.0% (12/30) | 16.7% (5/30) | 43.3% (13/30) | 100.0% (12/12) | 100.0% (12/12) |

| split | mode | n | auto / review / abstain | precision (conservative) |
|---|---|---|---|---|
| dev | exact | 47 | 33 / 10 / 4 | 100.0% (33/33) |
| dev | flexible | 43 | 0 / 31 / 12 | N/A |
| validation | exact | 16 | 14 / 1 / 1 | 92.9% (13/14) |
| validation | flexible | 14 | 0 / 10 / 4 | N/A |
| test | exact | 16 | 12 / 0 / 4 | 100.0% (12/12) |
| test | flexible | 14 | 0 / 5 / 9 | N/A |

## `hybrid_dimension_size_filter`

Cut points: accept 0.027424 / review floor 0.015625. Warm latency: median 4,904.4 ms, p95 6,308.9 ms (n=150).

| split | n | answerable | auto / review / abstain | auto-match rate | review rate | abstention rate | precision (conservative) | precision (practical) |
|---|---|---|---|---|---|---|---|---|
| dev | 90 | 77 | 67 / 14 / 9 | 74.4% (67/90) | 15.6% (14/90) | 10.0% (9/90) | 100.0% (67/67) | 100.0% (67/67) |
| validation | 30 | 25 | 23 / 3 / 4 | 76.7% (23/30) | 10.0% (3/30) | 13.3% (4/30) | 95.7% (22/23) | 95.7% (22/23) |
| test | 30 | 20 | 20 / 8 / 2 | 66.7% (20/30) | 26.7% (8/30) | 6.7% (2/30) | 95.0% (19/20) | 95.0% (19/20) |

| split | mode | n | auto / review / abstain | precision (conservative) |
|---|---|---|---|---|
| dev | exact | 47 | 39 / 1 / 7 | 100.0% (39/39) |
| dev | flexible | 43 | 28 / 13 / 2 | 100.0% (28/28) |
| validation | exact | 16 | 15 / 0 / 1 | 93.3% (14/15) |
| validation | flexible | 14 | 8 / 3 / 3 | 100.0% (8/8) |
| test | exact | 16 | 13 / 1 / 2 | 92.3% (12/13) |
| test | flexible | 14 | 7 / 7 / 0 | 100.0% (7/7) |

## `hybrid_identity_filter`

Cut points: accept 0.027424 / review floor 0.015625. Warm latency: median 5,262.4 ms, p95 6,254.7 ms (n=150).

| split | n | answerable | auto / review / abstain | auto-match rate | review rate | abstention rate | precision (conservative) | precision (practical) |
|---|---|---|---|---|---|---|---|---|
| dev | 90 | 77 | 58 / 15 / 17 | 64.4% (58/90) | 16.7% (15/90) | 18.9% (17/90) | 100.0% (58/58) | 100.0% (58/58) |
| validation | 30 | 25 | 22 / 3 / 5 | 73.3% (22/30) | 10.0% (3/30) | 16.7% (5/30) | 90.9% (20/22) | 90.9% (20/22) |
| test | 30 | 20 | 12 / 10 / 8 | 40.0% (12/30) | 33.3% (10/30) | 26.7% (8/30) | 100.0% (12/12) | 100.0% (12/12) |

| split | mode | n | auto / review / abstain | precision (conservative) |
|---|---|---|---|---|
| dev | exact | 47 | 30 / 2 / 15 | 100.0% (30/30) |
| dev | flexible | 43 | 28 / 13 / 2 | 100.0% (28/28) |
| validation | exact | 16 | 14 / 0 / 2 | 85.7% (12/14) |
| validation | flexible | 14 | 8 / 3 / 3 | 100.0% (8/8) |
| test | exact | 16 | 5 / 3 / 8 | 100.0% (5/5) |
| test | flexible | 14 | 7 / 7 / 0 | 100.0% (7/7) |

## `tfidf_dimension_size_filter`

Cut points: accept 0.637678 / review floor 0.275329. Warm latency: median 1,510.7 ms, p95 1,803.4 ms (n=150).

| split | n | answerable | auto / review / abstain | auto-match rate | review rate | abstention rate | precision (conservative) | precision (practical) |
|---|---|---|---|---|---|---|---|---|
| dev | 90 | 77 | 58 / 22 / 10 | 64.4% (58/90) | 24.4% (22/90) | 11.1% (10/90) | 98.3% (57/58) | 98.3% (57/58) |
| validation | 30 | 25 | 21 / 7 / 2 | 70.0% (21/30) | 23.3% (7/30) | 6.7% (2/30) | 85.7% (18/21) | 85.7% (18/21) |
| test | 30 | 20 | 17 / 12 / 1 | 56.7% (17/30) | 40.0% (12/30) | 3.3% (1/30) | 100.0% (17/17) | 100.0% (17/17) |

| split | mode | n | auto / review / abstain | precision (conservative) |
|---|---|---|---|---|
| dev | exact | 47 | 39 / 2 / 6 | 100.0% (39/39) |
| dev | flexible | 43 | 19 / 20 / 4 | 94.7% (18/19) |
| validation | exact | 16 | 15 / 0 / 1 | 93.3% (14/15) |
| validation | flexible | 14 | 6 / 7 / 1 | 66.7% (4/6) |
| test | exact | 16 | 12 / 3 / 1 | 100.0% (12/12) |
| test | flexible | 14 | 5 / 9 / 0 | 100.0% (5/5) |

## Constraint-violation check

Baseline `embed_dimension_size_filter`. A violation is a confirmed brand (exact mode), variant,
dimension or package-size conflict between the request and the automatically matched
top-1, re-derived from the catalog row rather than read back from the retrieval filters.

| split | automatic matches checked | violations | passes |
|---|---|---|---|
| dev | 65 | 0 | yes |
| validation | 23 | 2 | **no** |
| test | 17 | 2 | **no** |

**Test does not pass.** See `SEMANTIC_RESULTS.md` section 4, which lists every
violation with its matched title.

## Sample sizes

Held-out splits are 30 requests each (16 exact / 14 flexible; 20 answerable on test, 25
on validation). One request is 3.3 percentage points of a split rate and 5-6 points of a
precision denominator. **No single-split difference of a few points here is
interpretable.**
