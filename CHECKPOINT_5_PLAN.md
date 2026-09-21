# Checkpoint 5 — Correct basket comparison

Status: implementation plan only. Prepared 2026-09-21 against `main` @ `b759c18`, immediately
after Checkpoint 4 closed. Tactical breakdown for `PROJECT_PLAN.md` Checkpoint 5, in the same form
`CHECKPOINT_4_PLAN.md` gives Checkpoint 4 (S1–S7). Sub-checkpoints here are numbered **B1–B7**.

## Outcome

Turn a matched shopping list into a per-store itemized basket cost that is arithmetically correct,
honest about what it could not resolve, and refuses to name a winner it cannot justify. Checkpoint
4 decided *which product*; Checkpoint 5 decides *how many packages, at what cost, and whether the
comparison is legitimate at all*.

The deliverable is an engine plus ≥20 hand-calculated scenarios that pass exactly. This checkpoint
is arithmetic, not retrieval: its tests are hand-computed, never snapshotted from a run.

## What this inherits

- **The frozen matcher.** `embed_dimension_size_filter`, accept 0.75552 / review floor 0.691613,
  pinned in `evaluation_v3/frozen_config.json`. Its response is **three-way** — automatic match,
  review band, abstention.
- **The frozen catalog.** `benchmark_catalog_frozen.csv`, 31,398 rows, 5 stores, `price_cents` as
  integers with **zero nulls**. Stores are very unevenly sized: Ralphs 9,267 / Vons 9,002 /
  Sprouts 6,770 / ALDI 3,337 / DashMart 3,022.
- **Size resolution, measured:** 28,276 rows `resolved`, 2,122 `unresolved`, 1,000
  `variable_weight`; 3,122 rows have no `pkg_canonical_total` at all, and 2,692 rows are
  multipacks (`pkg_count > 1`).
- **`retrieval._requested_canonical_total`** — already multipack-phrase-aware, already
  total-vs-total. The basket engine reuses it rather than re-deriving a requested quantity.
- **`basket_demo.py`** — the demo matching layer, and explicitly *not* this engine (its own
  docstring says so). It reports one matched package's price per line.
- **`parse_shopping_line`** — returns a single `canonical_quantity`, which is the **total amount
  requested**, not "N packages of size S".

## The problem this checkpoint actually has to solve

`PROJECT_PLAN.md` asks for `packages needed = ceiling(requested quantity ÷ quantity per package)`.

**Today that ceiling is always 1, by construction.** `retrieval.filter_by_package_size` keeps a
candidate only when its total is within `PACKAGE_SIZE_ROUNDING_TOLERANCE` (1%) of the requested
total. A 16 oz request can only ever match a ~16 oz package, so the division is always ≈1 and the
ceiling never does any work. Every multipack, excess-quantity and cheapest-sufficient-package
requirement in Checkpoint 5 is unreachable through the current filter stack.

Checkpoint 4 S3 saw this coming and deferred it in writing: flexible mode "keeps
`filter_by_package_size`'s current same-total rule and the report states explicitly that
size-flexible matching lands in Checkpoint 5 with the basket engine." This is that landing.

So B2 is the load-bearing sub-checkpoint, and it is a **matching** change inside a basket
checkpoint. That is a real scope risk and is treated as one below.

## Out of scope for Checkpoint 5

- Any Streamlit/UI work (Checkpoint 6). The engine must be usable and testable without a UI, the
  same separation `basket_demo.py` already keeps from `demo_app.py`.
- Re-running, re-tuning or re-scoring the Checkpoint 4 benchmark. `evaluation/`, `evaluation_v2/`
  and `evaluation_v3/` are read-only inputs. **`frozen_config.json` does not move.**
- Latency optimization. Still a Checkpoint 6 prerequisite, still not fixed here.
- Fixing S2's brand extractor, or the failing constraint-violation check it causes. Recorded as an
  open Checkpoint 4 defect; touching it here would re-open a closed checkpoint.
- Re-scraping. Stock comes from snapshots already on disk.
- Any claim about real-world cheapest baskets. See Risks 1 and 4.

Outputs go to **`basket.py`** (engine) and **`evaluation_v4/`** (scenario suite and writeup),
following the v1→v2→v3 directory pattern.

---

## B1 — Package-count arithmetic, pure and integer

The primitive everything else sits on, built first and in isolation so it can be exhaustively
tested before any catalog row or matcher result reaches it.

**Inputs:** requested canonical total + unit (from `_requested_canonical_total`); a candidate's
`pkg_canonical_total`, `pkg_canonical_unit`, `pkg_count`, `price_cents`.

**Method**

1. New module `basket.py`. `packages_needed(requested_total, per_package_total)` →
   `math.ceil(requested / per_package)`, returning an **int**, raising on a non-positive or
   `None` per-package total rather than returning a sentinel.
2. `line_cost_cents(packages, price_cents)` → `packages * price_cents`, **integer cents
   throughout**. No float arrives in, passes through, or leaves this module. `PROJECT_PLAN.md`
   requires integer-cent summation; the way that requirement is normally lost is a float sneaking
   in at one boundary and being rounded back at another.
3. `excess_quantity(packages, per_package_total, requested_total)` → the overshoot in canonical
   units, reported and never silently absorbed.
4. **Unit compatibility is a precondition, not a conversion.** If the request's canonical unit and
   the row's canonical unit differ, this module raises. It does not convert. Cross-unit comparison
   is a known broken area (`PROJECT_PLAN.md` Appendix A item 8) and B2 decides what to do about
   it; B1 must not paper over it with an implicit conversion nobody reviewed.
5. Multipacks: a row's `pkg_canonical_total` is already the **total** across the pack, which is why
   `_requested_canonical_total` was made multipack-aware in Checkpoint 3.1. B1 divides totals by
   totals and never touches `pkg_count` arithmetically. `pkg_count` is carried for display only.

**Outputs:** `basket.py` arithmetic core, `test_basket_arithmetic.py`.

**Pass criteria:** hand-calculated tests for exact fit (12 ÷ 12 = 1), overshoot (13 ÷ 12 = 2 with
excess 11), a requested amount smaller than one package (5 ÷ 12 = 1, excess 7), a multipack row,
and a float-free assertion that every returned cost is an `int`. A test that unit mismatch raises.
A test that a zero or `None` per-package total raises rather than returning 0 or 1.

**Guardrails / anti-goals**

- No floats. Not for money, not for intermediate totals used to compute money.
- Do not "helpfully" convert oz↔g or fl oz↔L here.
- Do not special-case `variable_weight` rows into a guessed package size; they have none.

---

## B2 — Size-sufficient candidate selection for flexible mode

The unlock, and the riskiest step in this checkpoint.

**Inputs:** B1; `retrieval.filter_by_package_size`; the frozen matcher's candidate lists.

**Method**

1. **`filter_by_package_size` is not modified.** It is frozen behavior that Checkpoint 4's
   published numbers depend on. B2 adds a *sibling*, `filter_by_size_sufficient`, and the choice
   between them is made by matching mode — the same "new function, not a modified one" rule
   Checkpoint 3.1 and Checkpoint 4 S3 both followed.
2. **Exact mode keeps same-total matching, unchanged.** `PROJECT_PLAN.md`: in exact mode, multiply
   the selected package price by the requested package count. Exact mode does not shop for a
   different size.
3. **Flexible mode accepts a package whose total is *sufficient*,** i.e. any candidate where
   `packages_needed` is computable, then ranks by **actual purchase cost** — `line_cost_cents` —
   not by unit price and not by match score. `PROJECT_PLAN.md` Checkpoint 4 deferred exactly this
   sentence ("rank acceptable choices by actual purchase cost") to here.
   - Ties on cost are broken by **less excess**, then by higher match score, then by product id for
     determinism. Declared before the first run.
   - "Use one product choice per shopping-list line; do not mix different package sizes for the
     same line in v1" — so this selects a single row and multiplies it, never a basis of two
     package sizes.
4. **Rows with no resolvable size are not eligible for flexible size-sufficiency** — 3,122 rows
   have no `pkg_canonical_total` and 1,000 are `variable_weight`. They are not dropped from the
   result; they are returned as **unresolved-size candidates** with no computable line cost, so
   the basket can report them honestly instead of pretending or discarding.
5. **Measure the effect, do not assume it.** Relaxing size equality changes which products a
   flexible line can match, which is a matcher change. Score the frozen benchmark's flexible dev
   requests through the new path and report the delta in `evaluation_v4/`. This is **reported, not
   used to select anything** — the matcher selection is frozen and stays frozen. If size-sufficient
   matching makes flexible-line matching measurably worse, that is the finding and the engine ships
   with it disclosed.

**Outputs:** `retrieval.filter_by_size_sufficient`, `basket.select_cheapest_sufficient`,
`test_basket_selection.py`, `evaluation_v4/size_sufficient_delta.md`.

**Pass criteria:** hand-calculated tests for: a 32 oz request choosing 2×16 oz over 1×64 oz when
that is genuinely cheaper; the same request choosing 1×64 oz when *that* is cheaper despite more
excess; a cost tie broken by less excess; an exact-mode request refusing a differently-sized
package at any price; an unresolved-size row surfacing as unresolved rather than cheapest. A test
asserting `filter_by_package_size`'s behavior is byte-identical to Checkpoint 4's.

**Guardrails / anti-goals**

- Do not modify `filter_by_package_size`, `benchmark_config.MIN_SIMILARITY`, or anything under
  `evaluation/`, `evaluation_v2/`, `evaluation_v3/`.
- Do not re-tune the accept threshold or review floor because flexible coverage changed. The cut
  points were selected on dev under a declared cost function and are frozen.
- Do not rank by unit price. Unit price is a shopper heuristic; the plan asks for actual purchase
  cost, and the two disagree exactly when excess is large — which is the interesting case.
- Do not let a cheaper *unresolved* row win a line by treating unknown size as sufficient.

---

## B3 — Availability and eligibility

**Inputs:** `runs/*/*/items.csv` (11 snapshot files); the frozen catalog.

**Method**

1. **Stock is not in the frozen catalog and must be joined back.** `benchmark_catalog_frozen.csv`
   and `normalized_catalog.csv` carry no availability column — normalization dropped it. The raw
   snapshots carry `stock_status`.
2. **Unknown is the majority state and must not be read as "in stock."** *(Figures corrected
   2026-09-21 during B3 — the 54.6% / four-values numbers below were computed over all 11 snapshot
   directories on disk, but the frozen catalog draws on only 5 of them and that glob missed
   DashMart's legacy CSV entirely. Measured against the 5 real sources: **49.0% unverified**, and
   `In stock (20+)` is a fifth value. See `evaluation_v4/B3_AVAILABILITY.md`.)* The mapping must be
   explicit about every observed value, following the standing unknown-is-a-third-state rule:
   - `Out of stock` (334 rows) → **excluded** from the basket, and named in the explanation.
   - `Many in stock` (34,608) → eligible, marked **verified**.
   - `In stock (N)` (100 rows, e.g. `In stock (3)`) → eligible, marked **verified, low stock**,
     with N carried. Do not silently fold this into `Many in stock`; a basket needing 4 packages of
     something with 3 left is a real case and the engine should be able to see it.
   - null/absent → eligible, marked **unverified**. `PROJECT_PLAN.md`: "Label unknown availability
     as unverified."
3. A side-car, `evaluation_v4/availability.csv`, keyed `(store_id, product_id)` — never written
   back into the frozen catalog, so `catalog_version` does not move and no Checkpoint 4 label goes
   stale. Same discipline as `evaluation_v3/catalog_identity.csv`.
4. The join is by `(store_id, product_id)` against the snapshot each catalog row came from
   (`snapshot_id` is already a catalog column). Rows that fail to join are `unverified`, not
   dropped, and the **join failure rate is reported**, not swallowed.
5. A basket containing any unverified line is labeled unverified **at the basket level**, not only
   per line. A total that is mostly unverified should not present as a clean number.

**Outputs:** `build_availability.py`, `evaluation_v4/availability.csv`, `test_availability.py`.

**Pass criteria:** all four observed states round-trip; a null maps to `unverified` and never to eligible-
verified; the join-failure count is written to the side-car's manifest; a hand-built basket with one
out-of-stock line excludes exactly that line and says why.

**Guardrails / anti-goals**

- Never infer in-stock from the absence of a stock field. With 61% null in the one snapshot
  measured, that inference would silently fabricate the majority of the signal.
- Do not re-scrape to fill the nulls. Out of scope, and it would move the frozen catalog.

---

## B4 — Line resolution: duplicates, three-way responses, overrides

**Inputs:** B1–B3; the frozen matcher's three-way response.

**Method**

1. **Duplicate entries are resolved before matching**, not after. "2 lb chicken" and "1 lb chicken"
   on the same list are one line of 3 lb — `PROJECT_PLAN.md`: "Resolve duplicate shopping-list
   entries so quantities are counted once correctly." Merge rule: same `product_type` **and** same
   canonical unit **and** same matching mode → sum the canonical quantities. Anything else stays
   two lines. Declared narrow deliberately; a loose merge silently changes what the shopper asked
   for.
2. **The matcher's response is three-way, so a line has three eligibility states**, and the basket
   must distinguish them:
   - **automatic match** → line is priced.
   - **review band** → line is **not priced**; it carries its candidates and blocks basket
     completeness. On the Checkpoint 4 test split 36.7% of requests landed in review, so this is
     the common path, not an edge case, and an engine that quietly treats review as either "priced"
     or "missing" will be wrong most of the time.
   - **abstention** → line is missing; basket is incomplete.
3. **User overrides** (`PROJECT_PLAN.md` pass criterion): accepting a specific product for a line —
   typically resolving a review-band line — recalculates `packages_needed`, line cost, excess and
   the store total. An override is an input to the engine, not a UI concern, so it is testable here.
4. Lines whose parse itself failed (`needs_review`) never reach retrieval and are review-band by
   definition.

**Outputs:** `basket.resolve_lines`, `basket.apply_override`, `test_basket_lines.py`.

**Pass criteria:** hand-calculated tests for duplicate merge (and for two lines that must *not*
merge — same product type, different unit); each of the three response states producing a distinct,
asserted basket state; an override recalculating package count *and* total *and* excess, verified
against hand arithmetic; an override on a line the matcher abstained on.

**Guardrails / anti-goals**

- Review is not "close enough to priced." Never price a review-band line to improve completeness.
- Do not merge duplicates by fuzzy product similarity. Exact `product_type` + unit + mode only.

---

## B5 — Basket assembly, comparison and ranking

**Inputs:** B1–B4.

**Method**

1. Per store: sum line costs in integer cents; carry per-line excess, availability state and
   resolution state.
2. **Only stores with an acceptable match for every line are comparable.** A store missing a line
   is not cheaper — it is incomplete, and it is reported in a separate group.
   `PROJECT_PLAN.md`: "A smaller incomplete basket never outranks a complete basket." This is a
   hard invariant with its own test, not an emergent property of the sort.
3. **Show all ties.** Equal totals return a set, not an arbitrary first element. Determinism in the
   *presentation* order is fine; collapsing a tie to one winner is not.
4. **If no store can complete the basket, say so and name no winner.** There is no
   "cheapest of the incomplete baskets" ranking.
5. The comparison output carries, for every store: total cents, complete/incomplete, the count of
   verified vs unverified lines, and the count of review-band lines. A total is never presented
   without those three qualifiers attached.

**Outputs:** `basket.compare_stores`, `test_basket_comparison.py`.

**Pass criteria:** an incomplete basket with a lower total never outranks a complete one; a
three-way tie returns three stores; a no-store-can-complete case returns no winner and an explicit
reason; totals match hand arithmetic to the cent.

**Guardrails / anti-goals**

- Do not rank on partial baskets, not even "for information."
- Do not hide the unverified count inside a footnote-shaped field the caller can ignore.

---

## B6 — The hand-calculated scenario suite

The checkpoint's actual pass criterion: **at least 20 basket scenarios that pass exactly.**

**Method**

1. `evaluation_v4/basket_scenarios.json` — each scenario is a shopping list, a store subset, and a
   **hand-computed** expected result: per-line package count, per-line cost in cents, excess, store
   totals, ranking, and ties.
2. Every category `PROJECT_PLAN.md` names is covered, with at least one scenario each and the
   arithmetic written out in the file's comment field:
   multipacks · ties · missing products · unknown package sizes · duplicate entries ·
   incompatible units.
   Plus, from what Checkpoint 4 measured: **review-band lines** (the 36.7% case),
   **out-of-stock exclusion**, **unverified-majority baskets**, **cross-unit requests**
   (fl oz vs L, the r017 failure), and **an override**.
3. Expected values are computed by hand and written into the file **before** the engine is run
   against them. A scenario whose expectation was produced by the engine proves nothing; the file
   records for each scenario that its expectation is hand-derived.
4. Scenarios use real catalog rows and real prices from the frozen catalog, cited by
   `(store_id, product_id)`, so no invented products or prices appear anywhere.

**Outputs:** `evaluation_v4/basket_scenarios.json`, `test_basket_scenarios.py`.

**Pass criteria:** ≥20 scenarios, all passing exactly, every named category represented, every
expectation hand-derived and marked as such, every product referenced by real catalog id.

**Guardrails / anti-goals**

- Do not generate expected values from the engine. That is the one failure mode that makes this
  entire suite worthless.
- Do not adjust a scenario's expectation to match engine output. Fix the engine, or record that
  the hand calculation was wrong and why.

---

## B7 — Itemized explanations and writeup

**Inputs:** B1–B6.

**Method**

1. Per-store itemized explanation per line: the matched product and its id, package size, unit
   price shown for context only, packages needed, excess, line cost, availability state, and — for
   a flexible line — *why this package was chosen over the alternatives*, with the runner-up's cost.
2. `evaluation_v4/BASKET_RESULTS.md`: the scenario suite's results, the B2 size-sufficiency delta on
   flexible dev requests, the stock join-failure rate, and a plain statement of what a basket total
   here does and does not mean.
3. Update `PROJECT_PLAN.md` Appendix A.

**Outputs:** `evaluation_v4/BASKET_RESULTS.md`, updated Appendix A.

**Pass criteria:** a fresh run reproduces the scenario results exactly; every percentage carries its
numerator and denominator; no basket total is quoted without its completeness and verification
state.

---

## Risks

1. **Catalog size differs 3x across stores, which biases every comparison.** Ralphs has 9,267 rows
   and DashMart 3,022. A store with a third of the catalog will fail to complete baskets more often
   — not because it lacks the product in reality, but because the snapshot has fewer rows. Any
   "cheapest store" claim is therefore a claim about *these snapshots*, and the writeup must say so
   in those words. This is the single most misleading thing this checkpoint could produce.
2. **B2 is a matcher change inside a basket checkpoint.** Relaxing size equality for flexible lines
   is necessary for the arithmetic to mean anything, but it changes matching behavior after
   Checkpoint 4's numbers were frozen. Mitigations: `filter_by_package_size` is untouched, the new
   path is a sibling used only in flexible mode, the delta is measured and reported, and nothing in
   `frozen_config.json` moves. Residual risk: the shipped flexible behavior is no longer the
   behavior Checkpoint 4 measured, and the report must state that rather than implying continuity.
3. **Stock is 54.6% unknown across all snapshots** (61% in ALDI's). Availability will be mostly unverified,
   so "excludes out-of-stock items" is a much weaker guarantee than it sounds. Do not let the
   engine's confident-looking totals imply verified availability.
4. **A basket total is not a price quote.** Prices are snapshot values from a scrape, not live; no
   taxes, fees, delivery, promotions or loyalty pricing are modeled; substitution policy is not
   modeled. The writeup states this in the same place it states the totals.
5. **The parser discards a stated size whenever a container word appears — wider than recorded,
   and now the largest known failure cause.** Measured 2026-09-21:

   | request | parsed as |
   |---|---|
   | `a 67.6 fl oz bottle of Coke soda` | `count`, 1 ct |
   | `a 24 oz loaf of Bimbo Large White Bread` | `count`, 1 ct |
   | `a 12 fl oz x 12 ct pack of Diet Coke` | `count`, 1 ct |
   | `67.6 fl oz Coke soda` | `volume`, 67.6 fl oz |

   `PROJECT_PLAN.md` Appendix A item 5 recorded this as a "pack of" gap; `bottle of` and `loaf of`
   trigger it too, so it is not confined to multipacks. It accounts for **4 of the 9 false
   abstentions** on Checkpoint 4's dev and validation splits — the single largest cause, and one
   the S7 writeup originally split across three different mechanisms (corrected in
   `evaluation_v3/SEMANTIC_RESULTS.md` §5).

   Separately, `parse_shopping_line("3 boxes of 12 oz pasta")` returns `needs_review` ("ambiguous
   unit: 'boxes'"), so **"N packages of size S" cannot be expressed at all** and exact mode's
   "multiply by the requested package count" has no parser support today.

   Both are the same `<count> <container> of <size> <product>` shape. A basket engine fed
   `1 ct` when the shopper said `67.6 fl oz` will compute a confident, wrong package count, so
   this is load-bearing for Checkpoint 5 in a way it was not for Checkpoint 4 (where it only
   caused an abstention). **Decide in B4 whether to extend the parser or to ship with the
   limitation documented — do not discover it in B6.**
6. **Scope creep into Checkpoint 6.** `basket_demo.py` currently runs the TF-IDF stack, not the
   frozen embedding matcher. Moving it is genuinely needed, but it is CP6 demo work; B5 should
   expose a clean engine API and let CP6 rewire the demo, rather than rewriting the demo here.

## Open questions to settle before B2

1. ~~**Should flexible mode allow cross-unit sufficiency** (a 2 L bottle satisfying a 67.6 fl oz
   request)?~~ — **withdrawn 2026-09-21; the premise was wrong.** `normalize.py` already
   canonicalizes every weight to `oz` and every volume to `fl oz`, including litres (`2 L` →
   67.628 fl oz), so there is no within-dimension cross-unit case for B2 to handle. The only
   remaining "cross-unit" comparison is weight against volume (`oz` vs `fl oz`), which is a real
   dimension conflict and must stay a hard mismatch. **B1's `require_same_unit` is correct as
   written and needs no conversion table.** The r017 failure that motivated this question is not
   a unit problem at all — see Risk 5.
2. **Does an exact-mode line with a review-band response block the whole basket, or only that
   store's basket?** Proposal: only that store's, since a review is per (line, store) — but this
   needs deciding before B5's completeness invariant is written.
3. **Is excess quantity a cost?** Buying 2×16 oz to satisfy 17 oz wastes 15 oz. The plan says
   display excess, not price it. Proposal: display only; ranking stays on actual purchase cost, and
   excess is a tie-break. Revisit only with a declared reason.
