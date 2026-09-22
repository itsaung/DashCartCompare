# Checkpoint 5 — basket comparison: results

Completed 2026-09-22. The engine is `basket.py`, the availability side-car is
`evaluation_v4/availability.csv`, and the pass criterion is
`evaluation_v4/basket_scenarios.json`. `evaluation/`, `evaluation_v2/` and `evaluation_v3/` were
read as inputs and not modified; `frozen_config.json` did not move.

## What a basket total here is, and is not

Read this before any number below.

- **Prices are snapshot values** from a scrape on 2026-09-16, not live prices. No taxes, fees,
  delivery charges, promotions or loyalty pricing are modelled.
- **49.0% of catalog rows have no availability signal at all**, so a total is a best effort, not a
  confirmed price. Any unverified line makes the whole basket unverified.
- **Store catalogs differ threefold** — Ralphs 9,267 rows against DashMart's 3,022 — so a store
  failing to complete a basket may simply have fewer rows in the snapshot, not fewer products on
  its shelves.
- **Every match underneath every total is AI adjudication** against a frozen catalog, inherited
  from Checkpoint 4. A cheaper basket here is cheaper *against this adjudication*.
- This establishes **no** claim about real cheapest-basket accuracy.

## Pass criterion: met

**28 hand-calculated scenarios, all passing exactly** (`PROJECT_PLAN.md` asks for at least 20).
Expectations were computed by hand and written down before the engine ran against them, with the
arithmetic spelled out per scenario; the runner contains no arithmetic of its own. 30 of the 33
products cited are real frozen-catalog rows whose prices are asserted against the catalog, and the
3 exceptions are marked `SYNTHETIC-`. Details and the two construction errors the suite caught in
its first run are in `B6_SCENARIOS.md`.

715 tests pass overall. A fresh run reproduces the scenario results exactly.

## A worked comparison

List: `32 oz peanut butter`, `15 oz cereal`, `13.7 oz crackers`, `a 67.6 fl oz bottle of Coke soda`.
Thresholds: accept 0.75552, review floor 0.691613, near-tie band 0.01.

| store | total | state | verified lines |
|---|---|---|---|
| **ALDI** | **$15.16** | complete | 2 of 4 |
| Vons | $52.30 | complete | 2 of 4 |
| DashMart | $53.01 | complete | 3 of 4 |
| Ralphs | $55.10 | complete | 4 of 4 |
| Sprouts | — | **incomplete** | priced 2 of 4, review 1, missing 1 |

ALDI wins at $15.16. Sprouts is not ranked at all: it priced only two lines, so it has no total —
not a partial sum that might read as a competitive price.

Note that the **best-verified basket is the most expensive one**, and the winner has only two
verified lines of four. Verification is not evidence of a better basket; per B3 it is largely a
storefront artifact.

ALDI itemised:

| | product | line cost | why |
|---|---|---|---|
| 1× | Peanut Delight Creamy Peanut Butter (40 oz) | 399c | best match; the 18 oz jar is 21c cheaper but outside the near-tie band |
| 1× | Fruity Pebbles Cereal Large Size (15 oz) | 469c | best match; Millville Raisin Bran (16.6 oz) is **190c cheaper** but outside the band |
| 1× | Savoritz Club House Crackers (13.7 oz) | 349c | cheapest accepted option, against 878c for the runner-up |
| 1× | Coke Cola Soda Bottle (67.6 fl oz) | 299c | the only candidate that could be priced |

The cereal line is the near-tie band costing the shopper 190c, stated plainly. That is the trade
B5 declared: a cheaper option that matches the request less well does not win, and the explanation
names it so the shopper can overrule it. Without carrying out-of-band candidates into the
explanation the line would have read "the only candidate that could be priced", which is false —
a gap a B7 test caught and the engine now closes.

## What each sub-checkpoint measured

**B1 — arithmetic.** Money is integer cents end to end; a float price is rejected, not coerced.
One deviation from the plan, deliberate: `normalize.py` canonicalizes through lossy float factors,
so `500 g` is 17.637 oz against `17.6 oz` = 17.6 — a quotient of 1.0021 that a naive `ceil` turns
into two packages, doubling a shopper's cost over a label-rounding difference. `packages_needed`
snaps down within `retrieval.PACKAGE_SIZE_ROUNDING_TOLERANCE`, one-sided so it can never let an
insufficient package satisfy a request.

**B1.5 — the parser fix**, pulled ahead of B2. `parse_shopping_line` discarded the stated size in
any `a <size> <container> of <product>` phrasing. **4 of 150 benchmark requests** were affected,
all dev, and all four went from abstention to a **correct automatic match**: dev moved 65/12/13 to
69/12/9 automatic/review/abstain, precision 96.9% (63/65) to 97.1% (67/69). Validation and test did
not move. Checkpoint 4's artifacts were deliberately not regenerated; the divergence is in
`PARSER_FIX_DELTA.md`.

**B2 — size sufficiency.** Over 34 flexible dev requests: 5 cheaper selections (771c saved), 21
identical, 0 dearer, and **4 requests that the same-total filter could not price at all now price**
by buying more than one package. Two findings: cost may only choose among *accepted* products
(ranking across the whole sufficient pool selected Sweet Onions for `2 lb Honeycrisp Apples`), and
the same-total filter had been **incidentally hiding a matcher error** — `5 oz canned tuna` now
prices against canned cat food, which outscores the correct StarKist 0.8044 to 0.7887 and was
already top-1.

**B3 — availability.** Of 31,398 rows: **49.0% unverified** (15,388), 41.6% `in_stock` (13,060),
8.8% `in_stock_limited` (2,750), 0.6% `out_of_stock` (200). **248 rows (0.8%) failed to join**, all
DashMart, recorded unverified rather than dropped. Verified share by store: DashMart 89%, Ralphs
55%, Vons 44%, Sprouts 41%, ALDI 37% — a storefront artifact, since DashMart publishes a per-product
count and the others do not. Availability is never an input to ranking.

**B4 — line resolution.** Duplicates merge on exact product type, unit and mode. The review state
is never priced to improve completeness.

**B5 — comparison.** Score ranks, cost breaks near-ties inside a 0.01 band anchored on the 5th
percentile (0.0106) of observed score gaps below the best accepted candidate; the sensitivity table
runs from pure-score (20,389c) to cost-only (10,482c) on 30 dev lines, and the declared 0.01 sits
at 19,769c. Widening the band buys a cheaper basket by accepting worse matches.

## The finding Checkpoint 6 has to design around

Over **40 dev answerable lines × 5 stores**:

| | lines | share |
|---|---|---|
| priced at **all 5** stores | 10 | 25.0% |
| priced at **some** stores | 27 | 67.5% |
| priced at **no** store | 3 | 7.5% |

A line prices at a given store 67% of the time, so a 5-line basket would complete at a given store
only ~13.5% of the time **if lines were independent — and they are not.** Review is a property of
the *line*, not the store, so a hard line blocks every store at once. A live 4-line list earlier in
this checkpoint left **all five stores incomplete**, every one blocked by the same chicken line.

This is the plan's own completeness invariant meeting the matcher's real review rate, and it is
working as designed — a ranking produced by ignoring the blocked line would compare baskets that
bought different things. But it means **the shipped product will frequently have no ranking to
show**, which is a Checkpoint 6 design problem, not something to tune away here. The override path
is the resolution: blocked lines carry their candidates, and one override each makes the comparison
possible. `apply_override` exists for exactly that.

The worked comparison above completes at four of five stores because its lines are unusually clean;
it is the favourable case, not the typical one.

## Reproduction

```bash
cd dash
.venv/bin/python build_availability.py       # availability side-car
.venv/bin/python run_basket_demo.py          # the worked comparison above
.venv/bin/python -m pytest -q                # 715 tests
```
