# Checkpoint 5, B6 — the hand-calculated scenario suite

**28 scenarios, all passing exactly.** `PROJECT_PLAN.md` asks for at least 20. This is Checkpoint
5's actual pass criterion.

## How the expectations were produced

Every expected value in `basket_scenarios.json` was computed **by hand** and written into the file
before the engine was run against it, with the arithmetic spelled out in each scenario's
`hand_calculation` field:

> S07 — "32 oz + 16 oz = 48 oz on one line. 48 / 40 = 1.2 → ceil 2 jars. 2 × 399 = 798c.
> Excess 80 − 48 = 32 oz."

`test_basket_scenarios.py` only *executes* them. It deliberately contains no arithmetic of its own:
a runner that recomputed an expectation would be checking the engine against itself. A test asserts
every scenario carries written-out working, since a scenario without it is indistinguishable from
one whose numbers were copied from a run.

**Prices and package sizes are real** — 30 of the 33 products cited are rows of
`benchmark_catalog_frozen.csv`, and a test asserts each one's price matches the frozen catalog
exactly. The 3 exceptions carry a `SYNTHETIC-` product id and are declared in the file's
provenance; they exist because no real row has the property those scenarios need (an unresolvable
size at a low price, an out-of-stock row cheaper than its alternative). **Scores are chosen**, not
measured — they set which response state a line lands in, and the file says so.

## Coverage

Every category `PROJECT_PLAN.md` names, plus the states Checkpoint 4 measured:

| requirement | scenarios |
|---|---|
| multipacks | S04 (288 fl oz = 2 cases), S05 (partial case) |
| ties | S19, S22 (a real tie: Vons and Ralphs both price 16 oz at 349c) |
| missing products | S12, S24 |
| unknown package sizes | S10, S11 |
| duplicate entries | S06, S07 (merge), S08 (must *not* merge) |
| incompatible units | S09 |
| review band | S13, S14 (below the floor), S15 (parser gate) |
| out of stock | S16 (excluded), S17 (everything excluded) |
| unverified | S18 |
| overrides | S25 (resolves a review line), S26 (overrides an abstention) |
| near-tie band | S19, S20 (cheaper wins in band), S21 (best match wins outside it) |
| completeness invariant | S23, S24 |
| B1.5 container phrasing | S27 |
| label-rounding tolerance | S28 |

## Two errors the suite caught in its first run

Both were in **my scenario construction**, not in the engine — which is what a hand-calculated
suite is for.

**1. A shared candidate pool let a line buy the wrong product.** S23 offered each store one list of
candidates for a two-line basket (peanut butter + crackers). The engine priced the crackers line
against the *peanut butter* row — 16 oz is sufficient for a 13.7 oz request and scored the same, so
at 169c it was correctly the cheapest sufficient accepted candidate. My hand calculation had
assumed each line would match its own product. The engine was right and the scenario was wrong;
candidates are now **per line** where a scenario has more than one.

**2. Invented prices on real product ids.** S11 and S16 needed a cheap row with an awkward property
and borrowed a real `product_id` while inventing a 99c price. The
`test_every_product_is_a_real_catalog_row` check failed on exactly that — `assert 855 == 99` — which
is the check doing its job. Those rows now carry `SYNTHETIC-` ids and the test asserts that any
product id not so marked exists in the frozen catalog at the price claimed.

## Reproduction

```bash
cd dash
.venv/bin/python -m pytest test_basket_scenarios.py -q
```

693 tests pass overall.
