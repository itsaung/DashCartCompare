# Checkpoint 3 baseline results (v1)

Frozen 2026-09-19. This is a portfolio-scale evaluation of a frozen, AI-adjudicated catalog
benchmark. It does not establish live stock availability, cheapest-basket accuracy, or independent
human ground truth. Full methodology and definitions are in [`EVALUATION_PLAN.md`](../EVALUATION_PLAN.md);
this document reports the results it specifies.

## 1. Dataset, splits, and versions

- **Catalog:** 31,398 products across 5 DoorDash DashMart stores, frozen 2026-09-17
  (`catalog_version.sha256 = 087a7bb...`).
- **Requests:** 150 authored shopping-list lines. `REQUEST_VERSION = v2`. 122 answerable, 17
  needing clarification, 11 with no acceptable match in their pool.
- **Labeled pairs:** 1,658 candidate pairs from the original pool (`LABELING_GUIDELINE_VERSION =
  v2`, a complete catalog-based re-audit + 95-photo review — see `LABEL_AUDIT_2026-09-18.md` /
  `PHOTO_REVIEW_2026-09-18.md`), plus 153 additional pairs the full-catalog search (Checkpoint E4)
  surfaced outside that pool, adjudicated separately and never merged back into the original pool's
  decisions. 1,811 judged pairs total; **zero unjudged** among anything this report scores.
- **Splits** (grouped by paraphrase, pilot pinned to dev, seed `20260916`): **dev 90 / validation 30
  / test 30**, hitting the 90/30/30 target exactly.
- **AI-labeling limitations:** every label in this project — the original audit, the photo review,
  and the 153 additional judgments — is AI adjudication from frozen catalog text/images, not
  independent human review or live product-page verification. 56 of the 1,658 pool labels are
  explicit best guesses (conservative view treats them as `Needs clarification`). Request-level
  answerability for 2 of the 11 `no_acceptable_match` requests (r052, r129, both in dev) is itself
  only "pattern-consistent, not independently re-searched," not confirmed (`NO_MATCH_AUDIT` in
  [`build_benchmark.py`](../build_benchmark.py)) — both were excluded from Checkpoint E6's threshold
  tuning for exactly that reason (`evaluation/threshold_selection.json`).
- **The 153 additional judgments went through two rounds of external review and correction** before
  this report was finalized. Round 1: an initial pass reused `claude_auto_label.py`'s `auto_label()`
  unmodified (the same rule set behind the main 1,658-pair audit) and let 5 real false positives
  through — "extra large" eggs accepted against a "large" eggs request, chocolate baking chips
  accepted against a generic "bag of chips," and a 15.4 oz box accepted against a "15 oz" request via
  `auto_label`'s own 3% size tolerance (which `LABELING_GUIDELINES.md` v2 explicitly rejects as
  arbitrary). `apply_new_candidate_review.py` gained four additional, principled checks beyond
  `auto_label()` (product-type word confirmation, known-variant shadowing, a small false-friend
  phrase list, and unit-equivalent-only size matching). Round 2: those four checks initially
  downgraded every failure to `Needs clarification` uniformly; review caught that three of them
  (known-variant shadowing, the false-friend list, and size matching) detect a CONFIRMED conflict —
  a specific different value actually present, not mere unconfirmability — and should assert
  `Incorrect` instead, matching `auto_label`'s own established convention for the same situation
  (a confirmed brand/variant/size mismatch is always `Incorrect`; only a genuinely absent,
  unconfirmable attribute is `Needs clarification`). Only the product-type check (the original
  oat-milk-vs-almond-milk fix, which detects an absent core noun rather than a confirmed conflicting
  one) still downgrades to `Needs clarification`. Final split: **77 Acceptable / 61 Incorrect / 15
  Needs clarification**. All numbers in this report reflect the corrected labels (in this run, the
  correction touched none of the specific pairs that are any split's own top-1 prediction, so no
  metric value in §2 actually moved — verified by recomputing `evaluation/metrics.json` and diffing
  it byte-for-byte against the version this correction started from).
- **The original 1,658-pair pool was separately re-audited for the same size-tolerance issue**
  (`audit_size_tolerance.py`, `audit/SIZE_TOLERANCE_AUDIT_2026-09-19.md`): every one of its 475
  `Acceptable` labels with an expected size was checked against the same unit-equivalent-only
  comparison, not `auto_label`'s 3% tolerance. **Zero violations found** — the 2026-09-18 complete
  audit (`codex_ai_audit`) never actually relied on that tolerance for its own Acceptable labels,
  unlike the separate, later 153-additional-candidate review above. This was a real, checked
  finding, not an assumption that the main pool was fine because it predates the bug report.

## 2. The three baselines, side by side

| Baseline | Gate | Dimension filter | Threshold |
|---|---|---|---|
| `tfidf` | none | none | none |
| `tfidf_dimension_filter` | parser clarification | yes (NaN-safe: unknown ≠ mismatch) | floor 0.0 (never rejects on score) |
| `tfidf_dimension_filter_threshold` | parser clarification | yes | `MIN_SIMILARITY = 0.65`, dev-tuned (Checkpoint E6) |

All three share one TF-IDF vectorizer fit once on the whole frozen catalog (`raw_title + brand +
variant`), one deterministic tie-break (`-score, store_id, product_id`), and the same `top_k=5` for
full-catalog search. `tfidf_dimension_filter_threshold`'s candidate set is, by construction, exactly
`tfidf_dimension_filter`'s pre-threshold set with the 0.65 cutoff applied — its predictions are
derived (`tfidf_baseline.apply_threshold`), not separately retrieved, so its latency below is
inherited from `tfidf_dimension_filter` rather than independently measured (the threshold check
itself is a single scalar comparison).

### Pool ranking (Experiment A — ranking within each request's own labeled candidates)

Pool Recall@5, practical view, averaged only over pools with ≥1 known Acceptable candidate:

| Baseline | dev | validation | test |
|---|---|---|---|
| `tfidf` | 71.0% (86 pools, 4 N/A) | 75.4% (29 pools, 1 N/A) | 71.7% (25 pools, 5 N/A) |
| `tfidf_dimension_filter` | 63.8% (86 pools, 4 N/A) | 65.3% (29 pools, 1 N/A) | 66.7% (25 pools, 5 N/A) |
| `tfidf_dimension_filter_threshold` | 53.9% (86 pools, 4 N/A) | 58.1% (29 pools, 1 N/A) | 58.6% (25 pools, 5 N/A) |

Adding gates monotonically *lowers* pool recall at every split — expected: pool recall only credits
a candidate that both scores in the pool's top 5 *and* survives the gate, so every additional filter
can only remove credit, never add it. This is ranking among already-supplied candidates, not
evidence the system can discover them independently — see §2's full-catalog numbers for that.

### Full-catalog search (Experiment B — all 31,398 rows, no injected references), practical view

Returned-match accuracy is stricter than it may look next to Success@1: it only credits a returned
top-1 when the request's ground truth is itself `answerable` *and* the candidate is Acceptable — a
return on a request that needed clarification or had no match is never credited, even when the
candidate looks fine, per the plan ("a response-policy error... even if the candidate is loosely
compatible"). Its denominator is every request that received a match, which for `tfidf` (never
abstains) is the full split size, not just the answerable subset — that's why `tfidf`'s
returned-match accuracy sits well below its own Success@1 on every split.

| Baseline | Split | Success@1 | Hit@5 | MRR@5 | Returned-match accuracy | Return coverage | False return (unanswerable) | False abstention |
|---|---|---|---|---|---|---|---|---|
| `tfidf` | dev | 81.8% (63/77) | 89.6% (69/77) | 0.843 | 70.0% (63/90) | 100.0% | 1.00 | 0.00 |
| `tfidf` | validation | 76.0% (19/25) | 88.0% (22/25) | 0.798 | 63.3% (19/30) | 100.0% | 1.00 | 0.00 |
| `tfidf` | test | 90.0% (18/20) | 95.0% (19/20) | 0.925 | 60.0% (18/30) | 100.0% | 1.00 | 0.00 |
| `tfidf_dimension_filter` | dev | 76.6% (59/77) | 85.7% (66/77) | 0.794 | 74.7% (59/79) | 87.8% | 0.385 | 0.039 |
| `tfidf_dimension_filter` | validation | 76.0% (19/25) | 92.0% (23/25) | 0.811 | 70.4% (19/27) | 90.0% | 0.400 | 0.000 |
| `tfidf_dimension_filter` | test | 95.0% (19/20) | 95.0% (19/20) | 0.950 | 82.6% (19/23) | 76.7% | 0.300 | 0.000 |
| `tfidf_dimension_filter_threshold` | dev | 68.8% (53/77) | 72.7% (56/77) | 0.700 | 89.8% (53/59) | 65.6% | 0.077 | 0.247 |
| `tfidf_dimension_filter_threshold` | validation | 72.0% (18/25) | 80.0% (20/25) | 0.738 | 81.8% (18/22) | 73.3% | 0.400 | 0.200 |
| `tfidf_dimension_filter_threshold` | test | 85.0% (17/20) | 85.0% (17/20) | 0.850 | 100.0% (17/17) | 56.7% | 0.000 | 0.150 |

The gated baselines' returned-match accuracy climbs noticeably as gates get stricter (`tfidf_dimension_filter_threshold`
reaches 89.8–100%) — that's the flip side of §3's coverage/precision tradeoff: fewer, more
conservative returns, but a much higher fraction of the ones it does make are actually appropriate.

**Practical vs. conservative view:** every Success@1/Hit@5 number above is unchanged between views on
this data — the best-guess pairs never happen to be a request's *returned top-1* in this run, so the
conservative/practical distinction doesn't move these particular headline numbers (it does move Pool
Recall@5 slightly, §2, and is reported precisely, not assumed, in the bounds below). This is a
property of this run, not a guarantee for future models scored against the same split.

**Conservative-view Success@1 bounds** (dev, answerable n=77, `tfidf`): 63 confirmed correct, 14
confirmed incorrect, 0 unresolved → lower bound 81.8%, upper bound 81.8% (identical here because no
best-guess pair was ever a returned top-1 for `tfidf` on dev). Classification is by the conservative
label's own value, not by whether a pair happens to be a best guess: `Acceptable` → confirmed
correct, `Incorrect` → confirmed incorrect, `Needs clarification` → unresolved. Every one of the 56
best-guess pairs carries a conservative label of `Needs clarification` (never `Acceptable`), so they
always land in "unresolved" regardless of which way their practical label leans — but so does any
genuinely non-guess `Needs clarification` decision, since neither kind is a confirmed error. All
three baselines' bounds are recorded per split in `evaluation/metrics.json`; none of the three has a
case where the lower and upper bounds meaningfully diverge on the headline Success@1 number in this
run.

**Practical-view guessed-label exposure:** zero of any split's ~17–90 *scored* top-1 predictions
touch one of the 56 best-guess labels, for any of the three baselines (`practical_guessed_label_exposure`
in `evaluation/metrics.json`) — which is also why every conservative bound above is a point value
(lower bound == upper bound): none of the three baselines' actual top-1 picks happened to land on a
guessed pair in this run. This is a property of what these particular baselines return, not a
guarantee that a future model's top-1 picks won't touch a guessed label.

**Exact vs. flexible** (dev, practical view): `tfidf` scores 95.3% Success@1 (41/43) on `exact`
requests (specific brand/size) vs. 64.7% (22/34) on `flexible` ones (generic product type);
`tfidf_dimension_filter` scores 86.0% (37/43) exact vs. 64.7% (22/34) flexible. A generic request has
many acceptable candidates but TF-IDF's single top pick isn't guaranteed to be one of them; this gap
holds across all three baselines and both other splits (see `evaluation/metrics.json`,
`by_matching_mode`).

With roughly 20–30 answerable requests per split, none of the above should be read as more precise
than its own sample size — a few requests moving between splits could shift any single split's rate
by several points.

## 3. The precision/coverage tradeoff (why the threshold exists)

`tfidf` never abstains — 100% return coverage — but returns *something* on essentially every
unanswerable request too (false-return rate ~1.0 everywhere). `tfidf_dimension_filter` adds a real
gate: dev's false-return rate on unanswerable requests drops from 1.00 to 0.385, at the cost of
coverage falling to 87.8% and a small false-abstention rate (3.9%) appearing. `tfidf_dimension_filter_threshold`
pushes further: dev false-return drops again, to 0.077, but coverage falls to 65.6% and false
abstention rises to 24.7% — almost 1 in 4 genuinely answerable dev requests now gets no answer at
all. This is the tradeoff Checkpoint E6's dev-only cost curve was built to navigate
(`evaluation/threshold_selection.json`), not an accident of one run: the curve is a clean U-shape
with a real interior minimum, not a boundary value.

One instructive exception: **validation's false-return rate on unanswerable requests is identical
(0.4) for both the un-thresholded and thresholded baseline** — the same 2 of 5 unanswerable
validation requests get a false return even after gating, because both candidates score *above*
0.65 despite being wrong:

- r054 `5 gal whole milk` (`no_acceptable_match` — no catalog product is remotely close to 5 gal of
  milk) still returns "Organic Valley Whole Milk (**0.5 gal**)" at score 0.775 — a 10x size
  mismatch that scores well above the threshold purely on "whole milk" word overlap.
- r083 `16 oz Ben & Jerry's Half Baked Chocolate & Vanilla Ice Cream` (`needs_clarification` — bare
  `oz` on ice cream is a genuinely ambiguous weight-vs-volume case, §4's "uncertain source data"
  example) matches the identically-titled catalog product at score **1.0** — a perfect lexical
  match that the dimension filter and any plausible threshold both wave through, because the
  ambiguity here isn't lexical at all.

A stricter score threshold isn't automatically enough for a wrong-but-lexically-identical candidate,
and can't resolve an ambiguity that was never about wording in the first place. With n=5 in that
denominator this shouldn't be over-read as a general rate, but both cases are real and reproducible,
not noise.

## 4. Failure analysis (14 representative examples)

Drawn from `tfidf_dimension_filter`'s and `tfidf_dimension_filter_threshold`'s full-catalog
predictions on real requests. Every example below is an actual query against the real frozen
catalog — no invented scores.

**Package/count error — the dominant failure mode (9 of 14 below, across 11 distinct requests
counting paraphrase pairs).** The dimension filter only
checks weight-vs-volume-vs-count *category*, never the request's actual numeric size or count, so a
same-dimension, wrong-size candidate always survives it:

| Request | Top-ranked wrong result | What's wrong |
|---|---|---|
| r004 `0.5 gal Oatly Original Oat Milk` (dev) | Oatly Original Oat Milk (**32 fl oz**), score 0.82 | same product line, half the requested size (0.5 gal = 64 fl oz, exactly double 32 fl oz) — scores well above the 0.65 threshold on brand/variant overlap alone, same pattern as §3's r054/r083 |
| r041 `5.3 oz flavored greek yogurt` | The Greek Gods Honey Greek Yogurt (**24 oz**) | ~4.5x too large; all 5 top candidates are 24-32 oz, none anywhere near 5.3 oz |
| r078 `5.3 oz Good Culture 2% Milkfat Simply Cottage Cheese` | Good Culture 2% Milkfat Simply Cottage Cheese (**16 oz**), score 0.977 | otherwise a near-perfect brand/variant match, wrong purely on size (3x too large) |
| r098 `9 oz deli turkey breast` | Deli Fresh Turkey Breast **Mega Pack** (unspecified, much larger) | generic-brand large-format pack outranks any 9 oz option |
| r102 / r147 `7 oz` / `4.25 oz crackers` | Club Crackers Snack Stacks (**12.5 oz**) | same wrong answer for two different small sizes — the catalog's small-format cracker options rank behind the 12.5 oz one lexically |
| r105 `10 oz frozen broccoli florets` | Kroger Frozen Broccoli Florets (**12 oz**), score 0.866 | close miss (20% oversize) — illustrates that "close" package mismatches score high enough to survive most reasonable thresholds |
| r109 `5.3 oz cottage cheese` | Lactaid Cottage Cheese (**16 oz**) | same pattern as r078, different brand |
| r111 `7 oz deli turkey` | Oscar Mayer Black Pepper Turkey Breast (**8 oz**) | close miss (14% oversize) |
| r117 `3 lb Honeycrisp Apples` | Honeycrisp Apples Bag (**2 lb**) | count/weight-adjacent but wrong size; r143 (`three pounds Honeycrisp apples`, a paraphrase) fails the same way against an "each"-priced single apple |

**Wrong product type — lexical overlap without any real category match (2 of 14).**

| Request | Top-ranked wrong result | What's wrong |
|---|---|---|
| r021 `a 24 oz loaf of Bimbo Large White Bread` | GoodCook Large 9"x5" **Loaf Pan** | "loaf" and "large" match a bakeware product; not food at all |
| r096 `5 oz canned tuna` | Heart to Tail Canned Cat Food White Tuna (5.5 oz); further down: a sushi roll, canned mandarin oranges | pure "tuna"/"canned" word overlap pulls in pet food and unrelated canned goods; the correct human-food tuna cans don't even reach the top 5 |

**Retrieval miss — no acceptable candidate anywhere in the top 5, not just at rank 1 (1 of 14).**

| Request | Top-5 (all wrong) |
|---|---|
| r037 `7 oz pasta` | five pasta products ranging 5.1-16 oz, none within the tolerance of 7 oz |

**Uncertain source data (1 of 14, from the labeling side rather than retrieval).** Ice cream
products frequently print only a bare `oz` with no explicit weight-vs-volume marker (e.g. r036's
Ben & Jerry's Half Baked hard negative). `build_normalized_catalog.py`'s `dimension_review_flag`
exists specifically because this is a real, catalog-wide ambiguity (Checkpoint 2's audit measured
it directly) — the labeling guidelines treat these as genuinely uncertain rather than a confirmed
match or mismatch, and this evaluation inherits that uncertainty rather than resolving it.

**No parser-gate false positives were found** in this run's full-catalog answerable-request
predictions (`needs_clarification` returned for a request the ground truth calls `answerable`) — a
real, checked absence, not an omitted category.

## 5. Latency

Warm full-catalog query time (excludes model fit — the vectorizer is fit once, up front, and cached;
excludes labeling entirely), n=150 per baseline:

| Baseline | Median | p95 |
|---|---|---|
| `tfidf` | 1,519.6 ms | 1,919.3 ms |
| `tfidf_dimension_filter` | 1,520.9 ms | 1,946.7 ms |
| `tfidf_dimension_filter_threshold` | 1,520.9 ms (inherited, see §2) | 1,946.7 ms (inherited) |

Per-query latency is **bimodal**, not a tight distribution around this median: a request the parser
gate rejects outright resolves in well under 1 ms, while a request that reaches an actual TF-IDF
search against all 31,398 rows takes on the order of 1-2.4 seconds. That gap is far larger than a
31k-row sparse cosine similarity should cost in isolation, which points at per-query overhead
elsewhere in the request path (`parse_shopping_line` and/or `vectorizer.transform`'s tokenizer) as
the likely cost driver rather than the similarity computation itself — flagged here, not diagnosed;
profiling this is a natural next step before treating current latency as production-representative
(§7).

## 6. Reproduction

Every step below is deterministic given the checked-in inputs (frozen catalog, seed `20260916`,
`REQUEST_VERSION`/`LABELING_GUIDELINE_VERSION = v2`) and reproduces the exact predictions and
metric values in this report from a clean checkout:

```bash
cd dash
.venv/bin/python build_benchmark.py                        # Checkpoint E1: validate + export
.venv/bin/python build_splits.py                            # Checkpoint E2: dev/validation/test
.venv/bin/python run_experiments.py                          # Checkpoint E4: pool + full-catalog predictions
.venv/bin/python apply_new_candidate_review.py                # Checkpoint E4: judge newly-discovered candidates
.venv/bin/python tune_threshold.py                            # Checkpoint E6: freezes MIN_SIMILARITY=0.65
.venv/bin/python materialize_threshold_predictions.py         # derive baseline 3's own predictions
.venv/bin/python evaluation_metrics.py                        # Checkpoint E5: metrics.json + RESULTS_TABLE.md
```

`.venv/bin/pytest -q` runs the full suite (hand-calculated fixtures for every metric, cost-curve
point, and validation check referenced in this report).

## 7. Next improvement, justified by the evidence

**Add explicit numeric package-size/count matching to the baseline.** §4's failure analysis is not
ambiguous: 9 of 14 representative failures are the *same* mechanical mistake, including r004 from
§3's own worked example: the current dimension filter checks only whether a candidate's package is
weight, volume, or count (already NaN-safe against unknown dimensions, Checkpoint E3), but never
compares the actual number. A "5.3 oz" request and a "16 oz" candidate of the identical product are
both "weight," so the filter has nothing to say about them, and TF-IDF's lexical score alone can't
distinguish "5.3 oz" from "16 oz" reliably enough (r078 scored 0.977 — high confidence, wrong size).
`normalize.py`'s `parse_package_size()` and `convert_amount()` already exist, are tested, and already
power `claude_auto_label.py`'s own size comparison — with the caveat that its 3% relative tolerance
was itself found too loose during this checkpoint's own label review (§1) and should not be copied
verbatim; the unit-equivalent-only comparison written for `apply_new_candidate_review.py`'s
`_size_confirmed_without_arbitrary_tolerance` is the version to reuse. The missing piece is wiring
that numeric comparison into `retrieval.py`'s `attribute_filter_baseline`/`filter_by_dimension`, not
building new size-parsing logic from scratch.

Two smaller, lower-priority findings from this report worth tracking separately rather than acting
on immediately: the retrieval-miss and wrong-product-type cases in §4 (r021's loaf pan, r096's cat
food) suggest lexical TF-IDF has a real ceiling on short, generic queries that a semantic/embedding
retriever could raise — but per the plan, that's a deliberate v2 direction, not something to fold
into this baseline. And §5's latency gap is worth a profiling pass before this pipeline is treated
as interactive-speed-ready.

Low scores in some slices here (flexible-mode Success@1 around 65-70%, dev return coverage dropping
to 65.6% once thresholded) are a useful, honest finding about where a lexical baseline's ceiling is
— not a failed checkpoint. No score target was required to complete this checkpoint.
