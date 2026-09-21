# Checkpoint 4 — semantic matching: final evaluation

Run 2026-09-21. Configuration frozen in `frozen_config.json` and committed before the test split
was scored. `evaluation/` and `evaluation_v2/` were read as inputs and not modified;
`benchmark_config.MIN_SIMILARITY` is untouched.

Every label underneath every number here is AI adjudication from frozen catalog text and images —
not independent human review, and not live product-page verification. A difference measured here
is a difference against **that adjudication**. Nothing below establishes live stock availability
or real cheapest-basket accuracy.

## 1. What shipped

`embed_dimension_size_filter` — `all-MiniLM-L6-v2` cosine over the full 31,398-row frozen catalog,
with v2's dimension and package-size filters applied on top, then a three-way response:

| | value |
|---|---|
| accept threshold | 0.75552 |
| review floor | 0.691613 |
| model | `sentence-transformers/all-MiniLM-L6-v2` @ `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` |
| identity extraction | `product_identity` v1 |
| cut points tuned on | dev only, 88 of 90 requests (r052, r129 excluded) |

Validation selected it. At the dev-tuned cut points, validation average cost was:

| family | validation cost | dev cost |
|---|---|---|
| **`embed_dimension_size_filter`** | **0.1833** | 0.1932 |
| `hybrid_dimension_size_filter` | 0.1833 | 0.1364 |
| `hybrid_identity_filter` | 0.2833 | 0.2330 |
| `embed` | 0.3167 | 0.2841 |
| `tfidf_dimension_size_filter` (incumbent) | 0.3167 | 0.2102 |

The top two **tie**, on cost and on outcome split (23 accept / 3 review / 4 no-match each), and S5
found them tied on validation Success@1 too (92.0%, 23/25 each). The tie went to the simpler
method: one retriever instead of two plus a fusion step, and ~12x lower latency. Hybrid leads only
on dev — the split its cut points were tuned on — and that lead failed to reproduce on validation
on two different metrics, which is the signature of fitting dev rather than of a better method.

**The incumbent was swept for cut points too, by S7, before the selection.** S6 had tuned only the
four v3 families; the incumbent had never had a review band at all, because v1 and v2 responses are
two-way. Comparing a three-way system against a two-way one would not have been a comparison. The
sweep was dev-only, same cost function, same exclusions, and the four pairs S6 froze came out
bit-identical on the re-run — verified against the previous `threshold_selection.json`.

## 2. The 95% criterion — result

**Met on test: 100.0% (17/17) automatic-match precision, conservative view.**

Automatic-match precision is defined over automatic matches only. Review-band outcomes are in
neither the numerator nor the denominator — they are not automatic matches — and neither are
abstentions. An automatic match on a `needs_clarification` or `no_acceptable_match` request counts
against the numerator and never for it, regardless of how compatible the candidate looks.

| split | A / R / N | automatic-match rate | review rate | abstention rate | precision (conservative) | precision (practical) |
|---|---|---|---|---|---|---|
| dev | 65 / 12 / 13 | 72.2% (65/90) | 13.3% (12/90) | 14.4% (13/90) | 96.9% (63/65) | 96.9% (63/65) |
| validation | 23 / 3 / 4 | 76.7% (23/30) | 10.0% (3/30) | 13.3% (4/30) | 95.7% (22/23) | 95.7% (22/23) |
| **test** | 17 / 11 / 2 | **56.7% (17/30)** | **36.7% (11/30)** | **6.7% (2/30)** | **100.0% (17/17)** | **100.0% (17/17)** |

The three rates are a partition and sum to 1 on every split.

The two views agree exactly on all three splits. That is not a coincidence to wave at: it means no
top-1 that the matcher accepted automatically was ever a best-guess label, so on this data the
conservative lower bound and the practical view do not separate. The criterion is judged on the
conservative bound and clears it there.

**The denominator is 17.** One different request is 5.9 percentage points. This number is a
one-time check that the validation-selected configuration did not fall over, not evidence that the
matcher is 100% precise, and not evidence that it beats anything.

By matching mode, test:

| mode | n | A / R / N | precision (conservative) |
|---|---|---|---|
| exact | 16 | 12 / 2 / 2 | 100.0% (12/12) |
| flexible | 14 | 5 / 9 / 0 | 100.0% (5/5) |

With 16 exact and 14 flexible requests in a held-out split, **no single-split difference of a few
points here is interpretable.** The same caveat v1's report carries applies unchanged.

### The thing the headline number hides

Test's automatic-match rate is 56.7%, the *lowest* of the three splits, against 72.2% on dev and
76.7% on validation. Precision went up because coverage went down. Where the other 13 went:

- **6 are parser gates.** r120, r121, r123, r125, r126, r128 — "some tortillas", "cottage cheese",
  "a jar of peanut butter" — are genuinely `needs_clarification` and are routed to review before
  retrieval runs. These are correct, and the test split happens to carry six of them.
- **3 are flexible requests in the score band.** r093 (0.744), r116 (0.755), r118 (0.715) sit just
  under the 0.75552 accept threshold. r116 misses by 0.00031.
- **2 are correct abstentions** on `no_acceptable_match` requests (r131, r132).
- **2 more are unanswerable requests routed to review** rather than refused outright (r130, r154).

So the review band is doing a lot of the work on this split, and three of the eleven review
outcomes are requests the matcher had the right answer for and would not commit to. That is the
cost function behaving as declared — review (0.5) is cheaper than abstaining on an answerable
request (1.0) — but it is a real coverage cost and it is why coverage is reported here with the
same prominence as precision.

## 3. Every family, every split

Cut points per family are in `checkpoint4_config.CUT_POINTS`; full numbers in `final_metrics.json`.
Conservative view.

| family | dev A/R/N · precision | validation A/R/N · precision | test A/R/N · precision |
|---|---|---|---|
| `embed` | 33/41/16 · 100.0% (33/33) | 14/11/5 · 92.9% (13/14) | 12/5/13 · 100.0% (12/12) |
| **`embed_dimension_size_filter`** | 65/12/13 · 96.9% (63/65) | 23/3/4 · 95.7% (22/23) | 17/11/2 · 100.0% (17/17) |
| `hybrid_dimension_size_filter` | 67/14/9 · 100.0% (67/67) | 23/3/4 · 95.7% (22/23) | 20/8/2 · 95.0% (19/20) |
| `hybrid_identity_filter` | 58/15/17 · 100.0% (58/58) | 22/3/5 · 90.9% (20/22) | 12/10/8 · 100.0% (12/12) |
| `tfidf_dimension_size_filter` | 58/22/10 · 98.3% (57/58) | 21/7/2 · 85.7% (18/21) | 17/12/1 · 100.0% (17/17) |

**Every family clears 95% on test, including the incumbent at 100.0% (17/17).** Test does not
separate these methods and was never going to: 30 requests, 20 answerable, and the incumbent
already scored 100% Success@1 there in v2. Validation is where the separation is — and there the
spread is 85.7% (incumbent) to 95.7% (the two selected candidates), on denominators of 21 and 23.

`embed`, unfiltered, never automatically matches a single flexible request on any split (0/43 dev,
0/14 validation, 0/14 test). Its 100% dev precision is a precision on exact-mode requests only.
This is what a high threshold on a narrow score band buys: perfect accuracy on the subset it will
commit to, and silence everywhere else. It is in the table as a reminder that a precision number
without its denominator is meaningless, not as a candidate.

## 4. Constraint-violation check — **fails on test, 2 of 17**

This is a separate pass criterion from the 95% number and it did not pass.

The check re-derives each hard constraint from the catalog row and the request text rather than
reading it back from the retrieval filters, so that a filter bug surfaces as a violation instead of
hiding behind the filter that should have caught it. Unknown on either side is never a conflict,
the standing rule everywhere in this codebase.

| split | violations | automatic matches checked |
|---|---|---|
| dev | 0 | 65 |
| validation | 2 | 23 |
| **test** | **2** | **17** |

All four are **false positives from S2's request-side brand extractor.** Every one of the four
top-1 results is the exact product the request names:

| request | extracted request brand | candidate brand | matched title |
|---|---|---|---|
| r070 `6 ct Millville Chewy Dipped Peanut Butter Granola Bars` | `Peanut Butter` | `Millville` | Millville Chewy Dipped Peanut Butter Granola Bars (6 ct) |
| r081 `8.8 oz Savoritz Mini Peanut Butter Sandwich Crackers` | `Peanut Butter` | `Savoritz` | Savoritz Mini Peanut Butter Sandwich Crackers (8.8 oz) |
| r064 `18 ct Millville Chocolate Chip Chewy Granola Bars` | `Chewy Granola Bars` | `Millville` | Millville Chocolate Chip Chewy Granola Bars (18 ct) |
| r075 `16 oz Aldi Powdered Peanut Butter` | `Peanut Butter` | `Aldi` | Aldi Powdered Peanut Butter (16 oz) |

`extract_request_identity` searches the brand lexicon *anywhere* in the request text rather than at
its head, so it latches onto a product-noun run — "Peanut Butter", "Chewy Granola Bars" — that is in
the lexicon because some real brand starts with those tokens. The actual brand is present in the
request in all four cases and is simply not what the extractor returned.

**These are not being written off, and the check is not being loosened to clear them.** The
criterion as specified requires zero, and it is zero only if you accept that the predicate is
broken — which is a claim about S2, not a result. Checkpoint 4 ships with this recorded as an open
defect. It is the same S2 extraction-quality problem S5 identified as the reason
`hybrid_identity_filter` underperforms and S6 confirmed no threshold repairs; this is the third
independent measurement pointing at it.

**One evaluator bug was fixed after the first test run, and is disclosed here as one.** The initial
check counted 7 test violations. Five were pairs where both sides resolved a *different span of the
same brand*: `Chobani Flip` vs `Chobani`, `Land O'Lakes Unsalted` vs `Land`, `PurAqua Belle Vie` vs
`PurAqua`, `Peanut Butter` vs `Peanut` (twice). Treating a brand as conflicting with its own token
prefix reports a span disagreement as a product mismatch. `_brands_conflict` now compares on the
shared prefix length. The plan permits correcting a test result for an evaluator bug transparently;
this changed no matcher, no threshold and no label, only which pairs the check calls a conflict,
and the four remaining violations are unaffected by it.

## 5. Failure analysis

Every case below is a real request and a real catalog product. Scores are the matcher's own.

### Automatic matches that were wrong (3 in total, all dev/validation)

1. **r115 · dev · flexible · "96 fl oz almond milk" → Almond Breeze Vanilla Almondmilk (96 fl oz),
   0.808.** Size and dimension are right; the request did not ask for vanilla. *Variant
   over-specification on an under-specified request.* The catalog row's variant tokens are known,
   the request's are empty, and an empty request variant conflicts with nothing — so nothing
   filters it. This is the dominant flexible-mode error shape.
2. **r149 · dev · flexible · "16 oz honey ham" → Lunch Mate Black Forest Ham (16 oz), 0.786.** Same
   shape, worse: *the requested variant is contradicted*, not just unrequested. "Honey" and "Black
   Forest" are both cure styles and the embedding puts them close; `variants_conflict` does not
   treat them as mutually exclusive because neither is in the descriptor vocabulary as an
   antonym pair.
3. **r083 · validation · exact · "16 oz Ben & Jerry's Half Baked Chocolate & Vanilla Ice Cream" →
   Ben & Jerry's Half Baked Chocolate & Vanilla Ice Cream (16 oz), 0.988.** *The match is right.
   The request is labeled `needs_clarification`* — and a return on an unanswerable request counts
   against precision by the response-policy rule, correctly. This is a labeling-boundary case, not
   a retrieval failure, and it is the single request separating 95.7% from 100% on validation.

### Answerable requests the matcher abstained on (dev/validation)

4. **r017, r021, r142 and r151 are all one bug — the container-word parse gap.**
   *(Corrected 2026-09-21, after this report was first published. The original text attributed
   these to three different mechanisms — a cross-unit comparison failure, a row-level size
   mismatch, and the known "pack of" gap. Re-checked against the parser, they are a single cause.
   The corrected reading is below; no number in this report changes, only the diagnosis.)*

   `parse_shopping_line` discards the stated size whenever a request uses an
   `a <size> <container> of <product>` phrasing:

   | request | parsed as |
   |---|---|
   | `a 67.6 fl oz bottle of Coke soda` | `count`, 1 ct |
   | `a 24 oz loaf of Bimbo Large White Bread` | `count`, 1 ct |
   | `a 12 fl oz x 12 ct pack of Diet Coke Diet Cola Soda` | `count`, 1 ct |
   | `a 12 fl oz x 12 ct case of La Croix Razz-Cranberry Sparkling Water` | `count`, 1 ct |
   | `67.6 fl oz Coke soda` (no container word) | `volume`, 67.6 fl oz |

   The dimension becomes `count`, so `filter_by_dimension` drops every volume or weight candidate
   before size matching is ever reached. It is the known `parse_shopping_line` "pack of" gap
   (PROJECT_PLAN.md Appendix A item 5) — wider than recorded, since `bottle of` and `loaf of`
   trigger it too, and it is not confined to multipacks.

   **r017 is specifically not a cross-unit failure**, which is what this report originally said.
   `normalize.py` canonicalizes `2 L` to 67.628 fl oz, the same canonical unit the request would
   have had if it parsed — ALDI even stocks `Coke Cola Soda Bottle (67.6 fl oz)` at exactly
   67.600. Nothing about litres versus fluid ounces is involved.

   **Four of the nine false abstentions across dev and validation are this single parser bug** —
   the largest identified cause, where the original grouping made it look like three separate
   ones. Measured across the whole 150-request benchmark, 4 requests state a size the parser then
   discards.
7. **r100 · "14.9 oz frozen pizza", r108 · "21 oz crackers", r111 · "7 oz deli turkey", r147 ·
   "4.25 oz crackers"** → all four `no_acceptable_match`, all four flexible, all four
   *size-only requests with no product-identity signal*. The size filter is exact to 1% and the
   named size simply does not exist in this catalog at this store. These are arguably correct
   abstentions mislabeled as answerable, but they are labeled answerable and are scored as false
   abstentions here rather than argued away.
8. **r033 · dev · flexible · "a dozen large eggs, any brand is fine" → Happy Egg Co. Organic Grade A
   Free Range Large Brown Eggs (12 ct), 0.6596.** *The right answer, 0.032 below the review floor.*
   The request explicitly waives brand; the matcher found a correct product and discarded it on
   score. This is the clearest single illustration of the score/correctness separation problem —
   the same one the Checkpoint 6 demo slice found, where a wrong lexical match at 0.574 outscored a
   right one at 0.401.

### Grouped

| mechanism | cases | fixable where |
|---|---|---|
| variant over- or mis-specification on flexible requests | r115, r149 | S2 descriptor vocabulary |
| `parse_shopping_line` container-word gap (`bottle/loaf/pack/case of`) | r017, r021, r142, r151 | parser, known and open |
| size-only request, size absent from catalog | r100, r108, r111, r147 | not a matcher fix |
| right answer below the cut point | r033, r093, r116, r118 | cut points, or score calibration |
| labeling boundary | r083 | benchmark, not the matcher |

Four of the fourteen inspected failures are the container-word parser gap and four more are the
**score-doesn't-separate-correctness** problem, and
the review band mitigates rather than solves it: it gives the overlap region a non-destructive
destination instead of forcing a wrong accept or a wrong abstention.

## 6. Latency

Measured on **Apple M1, 8 GB, macOS 27.0, CPU only** (no MPS, no CUDA). Warm times are per
full-catalog query, n=150 per family.

| family | warm median | warm p95 |
|---|---|---|
| **`embed_dimension_size_filter`** | **421.4 ms** | **578.1 ms** |
| `embed` | 567.3 ms | 1,401.0 ms |
| `tfidf_dimension_size_filter` | 1,510.7 ms | 1,803.4 ms |
| `hybrid_dimension_size_filter` | 4,904.4 ms | 6,308.9 ms |
| `hybrid_identity_filter` | 5,262.4 ms | 6,254.7 ms |

Cold start, broken out (`cold_start_breakdown.json`):

| stage | time | paid |
|---|---|---|
| catalog CSV load | 1,988 ms | every process start |
| model load | 5,575 ms | every process start |
| cached embedding matrix load | 249 ms | every process start |
| full catalog encode (31,398 rows) | ~56 s | only when the cache key moves |

The encode figure is extrapolated from a timed 500-row sample rather than re-encoding a matrix that
is already cached. The cache key covers catalog hash, row order, model revision and package
versions, so it moves only when one of those genuinely changes.

**This is the one number that improved against the incumbent by a wide margin:** 421 ms vs 1,511 ms
median, 3.6x. A 10-item shopping list is ~4.2 s of retrieval instead of ~15 s. That is still above
Checkpoint 6's sub-3-second target for a whole list, so **the profiling pass remains a prerequisite
for Checkpoint 6**, as CHECKPOINT_4_PLAN.md risk 3 states — but it is now a gap of 1.4x rather than
5x, and hybrid at ~4.9 s/query is disqualified for the demo on latency alone regardless of accuracy.

## 7. What this checkpoint concluded

1. **Embeddings did improve on the incumbent — on validation, not on test.** Validation cost
   0.1833 vs 0.3167, validation precision 95.7% (22/23) vs 85.7% (18/21), and 3.6x faster. Test
   cannot corroborate this: every family scores ≥95% there.
2. **Hybrid retrieval was not adopted.** It leads on dev by 29% on cost and fails to reproduce that
   on validation twice, on two metrics, while costing 12x the latency. The evidence for it is
   specifically absent on the split meant to arbitrate.
3. **Exact-mode identity matching was implemented (S3) and does not pay off as built.**
   `hybrid_identity_filter` is the worst family on validation, and the constraint check now gives a
   third independent reading on why: the request-side brand extractor is wrong often enough to
   matter.
4. **The 95% criterion is met on test on a denominator of 17, at 56.7% automatic-match coverage.**
   Both halves of that sentence are the result.
5. **The constraint-violation criterion is not met.** 2 of 17 on test, all false positives from S2,
   recorded as an open defect rather than argued away or tuned around.

Nothing here was reached by changing the benchmark, the labels or the splits, and the test split
was scored exactly once, after `frozen_config.json` was committed.

## Reproduction

```bash
cd dash
.venv/bin/python tune_threshold_v3.py    # dev-only cut points -> threshold_selection.json
.venv/bin/python freeze_config.py        # -> frozen_config.json  (commit before the next step)
.venv/bin/python final_evaluation.py     # -> final_metrics.json + constraint_violation_check.json
.venv/bin/python -m pytest -q
```

A fresh run reproduces `final_metrics.json` and `constraint_violation_check.json` byte-for-byte;
this was checked, not assumed. There are zero unjudged top-1 results anywhere in this report, across
all five families and all three splits.
