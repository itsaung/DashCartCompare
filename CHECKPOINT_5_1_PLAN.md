# Checkpoint 5.1 — Brand identity and the two-basket comparison

Status: implementation plan only. Prepared 2026-09-22 against `main` @ `47c20fb`, after Checkpoint 5
closed. An unplanned follow-up in the same spirit as Checkpoint 3.1, which slotted in after E7 when
the failure analysis pointed at one specific fixable thing. Sub-checkpoints are **I1–I5**.

## Why this exists

The interface Checkpoint 6 is meant to build has two recommendations: the cheapest **equivalent**
basket (store brands allowed) and the cheapest basket of the shopper's **own brands**. The delta
between them — "switching to store brands saves you $27.88" — is the product.

**Half of that does not work today, and fails silently.** Asking the shipped matcher for
`16 oz Jif creamy peanut butter` returns **Peanut Delight Creamy Peanut Butter (18 oz)**, ALDI's
private label, at score 0.836 — above the accept threshold, so it is an automatic match, not a
review. The selected matcher `embed_dimension_size_filter` has **no brand gate at all**.
`filter_by_identity` exists from Checkpoint 4 S3, but the only baseline that used it
(`hybrid_identity_filter`) was the worst family on validation, so it did not ship.

This is also `PROJECT_PLAN.md` Appendix A item 7 — the open defect that leaves Checkpoint 4's
constraint-violation check failing 2 of 17 on test. It is the same root cause, and this checkpoint
closes both.

## What this inherits

- `product_identity.extract_request_identity` and `build_brand_lexicon` (Checkpoint 4 S2).
- `retrieval.filter_by_identity` (S3) — written, tested, never shipped.
- The frozen matcher and cut points in `evaluation_v3/frozen_config.json`. **These do not move.**
- The basket engine, B1–B7, including `matching_mode` already threaded through `resolve_lines`.
- Checkpoint 4's constraint-violation check, currently failing on test.

## Measured scope, before any work

Against the 69 benchmark requests that carry an authored `expected.brand`:

| | exact match | prefix/span variant | **outright wrong** |
|---|---|---|---|
| current extractor | 49 | 13 | **7** |

**The mechanism is precise.** `extract_request_identity` tries every 3-gram in the line, then every
2-gram, then every 1-gram, and takes the first hit. Length precedence outranks position. For
`6 ct Millville Chewy Dipped Peanut Butter Granola Bars` it finds the 2-gram `Peanut Butter` at
token 5 before it ever tries 1-grams, where the real brand `Millville` sits at token 2.

The catalog side already has a position rule — a brand must *begin* the product title. The request
side discarded it. (There is also dead code: the function computes a lowercased token list and
`del`s it without use, so its case handling is vestigial.)

**Prototyped fix, measured:** prefer the earliest position, trying longest-first only within a
position.

| | exact | prefix/span | outright wrong |
|---|---|---|---|
| current | 49 | 13 | **7** |
| earliest-position-wins | **53** | 16 | **0** |

**Zero regressions** — no request that is exact today becomes non-exact. The 3 remaining
non-exact cases are `Peanut` against an expected `Peanut Delight`, a prefix variant that
`final_evaluation._brands_conflict` already treats as compatible.

Two secondary lexicon facts, both measured: `Peanut Butter` is in the brand lexicon with exactly
**5** products and `Chewy Granola Bars` with **7**, against `MIN_BRAND_PRODUCTS = 5` — they scrape
in at the floor. And `Peanut Delight` is **absent** from the lexicon entirely, because
`BRAND_EXTENSION_DOMINANCE = 0.50` refuses to extend `Peanut` when its continuations are split
across several brands.

## Out of scope

- **Any change to `frozen_config.json`, the cut points, or the selected matcher.** I3 adds a
  *sibling* configuration, the same rule B2 followed.
- **Re-running the Checkpoint 4 test split for model selection.** Test was used once, after the
  freeze. It stays used once. I4 re-runs the *constraint-violation check* on test, which is a
  declared pass/fail criterion and not a selection — stated and disclosed, changing nothing about
  which matcher ships.
- Re-scraping, re-labeling, or touching `evaluation/`, `evaluation_v2/`, `evaluation_v3/`.
- Streamlit or any UI (Checkpoint 6). I5 produces the *engine-level* two-basket result the UI will
  render.
- The latency profiling pass. Still a Checkpoint 6 prerequisite, still not this.

Outputs go to **`evaluation_v5/`**.

---

## I1 — Fix the request-side brand extractor

**Inputs:** `product_identity.extract_request_identity`; the 69 authored `expected.brand` values.

**Method**

1. Replace length-first scanning with **position-first**: iterate token positions left to right and,
   at each position, try 3-gram then 2-gram then 1-gram. First hit wins. This mirrors the
   catalog-side position rule rather than inventing a new one.
2. Delete the vestigial `lowered` computation, and make the lexicon lookup's case handling explicit
   one way or the other — currently `Millville` is a key and `millville` is not, which no caller
   relies on and every caller could trip over.
3. `IDENTITY_VERSION` moves to `"v2"`. The side-car `evaluation_v3/catalog_identity.csv` is
   **rebuilt into `evaluation_v5/`**, never overwritten, so Checkpoint 4's inputs stay byte-identical.
4. Report the before/after table above as the acceptance evidence, regenerated rather than quoted.

**Outputs:** updated `product_identity.py`, `evaluation_v5/catalog_identity.csv`,
tests in `test_product_identity.py`, `evaluation_v5/I1_EXTRACTOR_FIX.md`.

**Pass criteria:** outright-wrong count is **0/69**; exact count is **≥ 53/69**; **zero regressions**
against the current extractor, asserted by a test that compares both implementations across all 150
requests, not by inspection. Hand-written tests for each of the 7 named failures (r064, r070, r075,
r081, r134, r135, r136).

**Guardrails / anti-goals**

- Do not tune `MIN_BRAND_PRODUCTS` or `BRAND_EXTENSION_DOMINANCE` here. I2 decides whether they
  need touching, on evidence, and mixing a threshold change into a rule change makes neither
  attributable.
- Do not special-case the seven failing requests. A fix that names them is not a fix.
- Do not change the catalog-side extractor. It already uses the position rule and is not implicated.

---

## I2 — Lexicon quality: product nouns admitted as brands

**Inputs:** I1; `build_brand_lexicon`.

**Method**

1. Quantify first: how many lexicon entries are product nouns rather than brands? `Peanut Butter`
   (5 products) and `Chewy Granola Bars` (7) clear `MIN_BRAND_PRODUCTS = 5` by one and two.
   Measure the distribution near the floor before proposing a number.
2. **Only then** decide between: raising the floor, requiring a brand n-gram to appear across more
   than one `raw_category`, or an explicit product-noun stoplist. Each has a cost; the plan does not
   pre-commit to one.
3. Whatever is chosen is declared with its measured effect on I1's table **and** on the catalog-side
   extraction, since the same lexicon feeds both.

**Outputs:** `evaluation_v5/I2_LEXICON_AUDIT.md`, any change to `build_brand_lexicon` with tests.

**Pass criteria:** the chosen rule is stated with the number of lexicon entries it adds and removes,
and with its effect on I1's 69-request table. **If the measurement shows the floor is not the
problem — I1 already takes outright-wrong to zero — the honest outcome is to change nothing and say
so.** That is a legitimate completion of I2.

**Guardrails / anti-goals**

- Do not raise the floor to make one example disappear. `Peanut Butter` at 5 products is one data
  point, not a distribution.
- A stoplist is a maintenance burden and an admission the rule is wrong; prefer a rule if a rule
  works.

---

## I3 — Exact mode on the shipped matcher

**Inputs:** I1/I2; `retrieval.filter_by_identity`; the frozen matcher.

**Method**

1. New sibling baseline `embed_identity_filter` = `embed_dimension_size_filter` +
   `filter_by_identity`. A **new function**, not a modification — `embed_dimension_size_filter`
   stays byte-identical, the rule Checkpoint 3.1, Checkpoint 4 S3 and Checkpoint 5 B2 all followed.
2. It is used **only for exact-mode lines**. Flexible mode is unchanged and keeps shipping exactly
   what Checkpoint 5 measured.
3. Score on **dev and validation only**. Report Success@1, automatic-match precision, and the
   three-way outcome split, both label views, every rate with its numerator and denominator.
4. The comparison that matters is against the *same* matcher without the gate, on exact-mode
   requests only — the gate's whole claim is that it stops `Jif` returning `Peanut Delight`.
5. **A missing brand on either side routes to review, at any score** — S3's rule, unchanged.
   Expect this to raise the exact-mode review rate; report it rather than tuning it away.

**Outputs:** `embedding_retrieval.run_embed_identity_baseline`, `evaluation_v5/predictions.jsonl`,
`evaluation_v5/I3_EXACT_MODE.md`.

**Pass criteria:** a hand-written test that `16 oz Jif creamy peanut butter` does **not** return a
Peanut Delight product at any score; exact-mode automatic-match precision reported on dev and
validation with counts; the review-rate increase reported with the same prominence. `frozen_config.json`
unchanged, asserted by a test.

**Guardrails / anti-goals**

- Do not re-tune cut points because the gate changed the score distribution. If they need retuning,
  that is a finding to report, not a step to take quietly.
- Do not use test. If exact-mode coverage collapses on validation, that is the result.
- Never downgrade an exact request to a substitute to protect coverage.

---

## I4 — Close the constraint-violation check

**Inputs:** I1; `final_evaluation.py`.

**Method**

1. Re-run the constraint-violation check with the v2 extractor. All 4 previously-flagged cases
   (r070, r081 on test; r064, r075 on validation) were false positives produced by exactly the
   failure I1 fixes, so the expectation is **0 violations**.
2. This reads the test split. It is a **declared pass/fail criterion, not a selection**, it changes
   nothing about which matcher ships, and the re-read is disclosed in the writeup and in the JSON.
3. Results go to `evaluation_v5/constraint_violation_check.json`. **`evaluation_v3/` is not
   rewritten** — Checkpoint 4's published artifacts stay as published, with a pointer added.

**Outputs:** `evaluation_v5/constraint_violation_check.json`, a note appended to
`evaluation_v3/SEMANTIC_RESULTS.md` §4 pointing at the resolution.

**Pass criteria:** 0 violations on test and validation; the test re-read is disclosed; the original
Checkpoint 4 numbers are left intact and still reproduce at their own SHA.

**Guardrails / anti-goals**

- If violations remain, report them. Do not relax `_brands_conflict` to reach zero — that predicate
  was already corrected once, transparently, and a second "fix" to hit a number would be tuning.

---

## I5 — The two-basket comparison

**Inputs:** I3; the Checkpoint 5 basket engine.

**Method**

1. `basket.compare_two_ways(lines, ...)` returns both baskets over one list: **own-brand** (exact
   mode, identity gate) and **equivalent** (flexible mode, as shipped), each with its own winner,
   totals and per-line explanations.
2. The headline is the **delta**: cheapest own-brand total against cheapest equivalent total, with
   both store names, because they will usually be different stores.
3. **Per-line comparability is reported**, because it is the thing most likely to mislead: measured
   2026-09-22, only **2 of 26,508 normalized titles exist in all five stores** (cucumber, iceberg
   lettuce), 87% are single-store, and ALDI and Sprouts are 99% and 97% own-label. An own-brand
   basket will frequently exclude them entirely. Each line reports how many stores carry a
   comparable product.
4. Where titles *are* shared across stores, 3,111 of 3,430 differ in price, median relative spread
   **15.4%**. That is where the comparison is real, and it should be visible.

**Outputs:** `basket.compare_two_ways`, `test_basket_two_way.py`,
`evaluation_v5/I5_TWO_BASKET.md` with a worked example.

**Pass criteria:** hand-calculated tests for a list where the two baskets pick different stores; a
list where the own-brand basket cannot complete anywhere; per-line comparability counts asserted
against the catalog. The saving is never quoted without both store names and the comparability
counts.

**Guardrails / anti-goals**

- Do not present a saving as if both baskets were available at one store.
- Do not hide an incomplete own-brand basket by falling back to equivalents. If the shopper's brands
  are not stocked, that is the answer.

---

## Risks

1. **The identity gate may cost more coverage than the brand guarantee is worth.** Checkpoint 4
   measured `hybrid_identity_filter` as the worst family on validation, and S3's
   missing-brand-routes-to-review rule is the reason. I1 removes the extraction defect that
   explanation rested on, but it may not be the whole story. If exact-mode coverage on validation is
   bad enough that the own-brand basket rarely completes, the honest outcome is to report that the
   two-basket product is not supportable on this data — and Checkpoint 6 then ships one
   recommendation, not two. **That is a legitimate completion of this checkpoint.**
2. **Own-brand baskets will exclude the cheapest stores.** ALDI is 99% own-label. A shopper asking
   for national brands will mostly be choosing between Ralphs, Vons and DashMart, and the
   equivalent basket will almost always win on price. The interface must not present that as a
   discovery each time; it is a structural fact about this catalog.
3. **A second matcher change after the freeze.** B2 was the first. Each one widens the gap between
   what Checkpoint 4 measured and what ships. Mitigation is unchanged — sibling functions, frozen
   config untouched, deltas measured and published — but the writeup should state plainly that the
   shipped system is now two documented steps from the frozen evaluation.
4. **`Peanut Delight` stays unresolvable as a full brand** without touching
   `BRAND_EXTENSION_DOMINANCE`, which I2 may well decline to do. Prefix compatibility makes it
   harmless for matching, but an interface that *displays* an extracted brand will show "Peanut"
   and look broken. Display and matching may need to diverge.
