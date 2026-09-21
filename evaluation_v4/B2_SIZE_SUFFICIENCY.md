# Checkpoint 5, B2 — size-sufficient selection for flexible mode

Measured 2026-09-21 on the 34 flexible, answerable **dev** requests with a resolvable amount.
`evaluation/`, `evaluation_v2/` and `evaluation_v3/` are untouched, `filter_by_package_size` is
byte-identical to what Checkpoint 4 published, and nothing in `frozen_config.json` moves.

## What changed

`filter_by_package_size` keeps only candidates within 1% of the requested total, so
`packages_needed` against anything it returns is always 1 and `PROJECT_PLAN.md`'s package-count
arithmetic is unreachable through it. `filter_by_size_sufficient` is its **sibling**, used in
flexible mode only: a candidate qualifies when it is in the request's canonical unit and some whole
number of its packages covers the request. `basket.select_cheapest_sufficient` then ranks by actual
purchase cost.

Exact mode is unchanged. An exact request is for a specific package, not for an amount.

## Result

| | n |
|---|---|
| flexible dev requests measured | 34 |
| priced by both the frozen filter and B2 | 26 |
| — B2 selects a **cheaper** package | **5** |
| — identical selection | 21 |
| — B2 selects a dearer package | 0 |
| priced **only** with B2 (frozen filter found nothing acceptable) | **4** |
| priced by neither | 4 |
| selections needing more than one package | 4 |

Across the 5 cheaper selections the total saving is **771 cents**. Four requests that the
same-total filter could not price at all now price, all of them by buying more than one package —
`21 oz crackers` as 2 × 13.7 oz, `16 oz deli turkey` as 2 × 8 oz, `16 fl oz ice cream` as 2 × 8 fl
oz. That is the arithmetic the plan asked for, doing work it could not previously do.

| request | same-total | B2 |
|---|---|---|
| `15 oz cereal` | 469c Fruity Pebbles (15 oz) | **279c** Millville Raisin Bran (16.6 oz) |
| `10 oz frozen broccoli florets` | 399c Earthbound Organic (10 oz) | **139c** Season's Choice Steamable |
| `13.1 oz crackers` | 439c Savoritz Six Assortment | **259c** Savoritz Golden Round (13.7 oz) |
| `96 fl oz almond milk` | 599c Almond Breeze Vanilla | **538c** 2 × Friendly Farms Original (64 fl oz) |

## Finding 1 — cost may only choose among accepted products, never decide acceptance

The first implementation ranked by cost across the whole size-sufficient pool. It selected:

| request | selection |
|---|---|
| `2 lb Honeycrisp Apples` | **Sweet Onions Bag (2 lb)**, $1.69 |
| `10 oz potato chips` | **Happy Harvest Whole Potatoes (15 oz)**, $1.19 |
| `12 oz ground coffee` | a 15 oz caramel vanilla coffee, $4.49 |

The sufficiency gate is deliberately weak — any positive package size covers any request if you buy
enough — so it admits ~190 of 200 retrieved rows. The cheapest item in a bag of 190 groceries is
essentially never the thing the shopper asked for.

`PROJECT_PLAN.md` says flexible mode selects "the cheapest **accepted** product sufficient for the
requested quantity". The word *accepted* is load-bearing, and dropping it does not degrade the
ranking gracefully — it inverts it. `select_cheapest_sufficient` now takes a `min_score`
acceptance bar, and every number in this report is measured with the frozen accept threshold
(0.75552) applied. The bar is not optional in practice; the parameter defaults to `None` only so
the arithmetic stays testable without a matcher.

## Finding 2 — the same-total filter was incidentally hiding a matcher error

`5 oz canned tuna` is now priced at 69c against **Heart to Tail Canned Cat Food White Tuna
(5.5 oz)**.

This is not a cost-ranking failure. The cat food **outscores** the correct product:

| accepted candidate | score | price |
|---|---|---|
| Heart to Tail Canned Cat Food White Tuna (5.5 oz) | **0.8044** | 69c |
| Starkist Chunk Light Tuna in Water Can (5 oz) | 0.7887 | 149c |
| Chicken of the Sea Chunk Light Tuna in Water | 0.7850 | 689c |

The cat food was already the matcher's top-1 by score. It never surfaced before because it is
5.5 oz against a 5 oz request — 10% off, so `filter_by_package_size` dropped it. **The size filter
was acting as an accidental guard against a semantic matching error**, and relaxing it removes that
guard along with the limitation it was meant to impose.

That guard was never designed, was never measured, and protected only in the specific case where a
wrong product happens to be a differently-sized package. It should not be relied on. But its
removal is a real consequence of B2 and is recorded here rather than discovered later: **a wrong
match that is cheap now wins a line outright**, which is exactly the hazard `basket_demo.py`'s
docstring warned about — "wrong matches are systematically *cheap*, and a cheapest-basket ranking
therefore prefers them."

This is a matcher-quality problem (the S2/embedding failure mode Checkpoint 4 documented), not an
arithmetic one, and B1/B2 cannot fix it. It needs a decision in B5 and is carried forward as one.

## What B5 has to decide

1. **Does a cheapest-accepted selection need a second guard?** Options: require the cheapest to be
   within a score band of the best-scoring accepted candidate; or rank on score and use cost only
   to break near-ties; or surface both and let the shopper choose. All three are product calls, and
   the tuna case is the one to test them against.
2. **Should a large excess be surfaced more loudly than a line item?** `96 fl oz almond milk` as
   2 × 64 fl oz leaves 32 fl oz spare. Ranking on cost is correct per the plan, but a basket that
   silently buys 50% more than asked is a surprise.

## Reproduction

```bash
cd dash
.venv/bin/python -m pytest test_basket_selection.py -q
```

`b2_size_sufficient_delta.json` carries the per-request before/after selections, prices, package
counts, excess and accepted-candidate counts.
