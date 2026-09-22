# Checkpoint 5, B5 — basket assembly, comparison and ranking

Built 2026-09-21. Two questions the plan parked were settled before implementation, and both are
recorded here as decisions rather than discoveries.

## Decision 1 — a review line blocks that store only

Review is per `(line, store)`: a score below the accept threshold at one store says nothing about
another, which may carry the same product under a cleaner title. Blocking the whole comparison on
one store's review would suppress the ranking on most real lists, since review runs ~17% of lines
across the frozen benchmark (13.3% dev, 10.0% validation, 36.7% test).

So a store with a review line is **incomplete** and moves to the separate incomplete group; the
other stores still rank normally.

## Decision 2 — score ranks, cost breaks near-ties

B2 measured what happens when cost is the primary key: it selected **Sweet Onions** for
`2 lb Honeycrisp Apples` and **Whole Potatoes** for `10 oz potato chips`. `PROJECT_PLAN.md` asks
for the cheapest **accepted** product; acceptance has to come first.

`select_for_line` narrows to candidates within `SCORE_NEAR_TIE_BAND` of the best accepted score,
then lets cost decide inside that set.

**Where 0.01 comes from.** Across the 347 accepted-but-not-best candidates on 30 flexible dev
lines, the score gap below the best accepted candidate has its 5th percentile at **0.0106**. A
candidate inside that band is in the tightest 5% of the accepted distribution — effectively the
same match quality, which is exactly when price should decide. Deriving it from dev scores is a use
of the tuning split; that is permitted and stated, the same disclosure S6 made about its grid.

Sensitivity on those 30 lines:

| band | basket total | lines differing from pure score |
|---|---|---|
| 0.000 (pure score) | 20,389c | 0 |
| 0.005 | 19,959c | 2 |
| **0.010 (declared)** | **19,769c** | **3** |
| 0.020 | 18,277c | 6 |
| 0.050 | 13,454c | 16 |
| unbounded (B2's original) | 10,482c | 20 |

Widening the band buys a cheaper basket by accepting worse matches, and the far end of that trade
is the onions. **0.01 is a declared design preference, not a tuned optimum.**

**It does not rescue a matcher error, and is not claimed to.** The tuna case still selects canned
cat food, because the cat food *outscores* the correct StarKist (0.8044 vs 0.7887) and is top-1 on
match quality. The band stops cost from amplifying matcher errors; it cannot fix one. There is a
test asserting exactly this, so the limitation stays visible.

## Finding — strict completeness plus per-line difficulty makes comparison rare

Measured over 40 dev answerable lines × 5 stores:

| | lines | share |
|---|---|---|
| priced at **all 5** stores | 10 | 25.0% |
| priced at **some** stores | 27 | 67.5% |
| priced at **no** store | 3 | 7.5% |

| lines priced at exactly *k* stores | k=0 | k=1 | k=2 | k=3 | k=4 | k=5 |
|---|---|---|---|---|---|---|
| | 3 | 3 | 4 | 7 | 13 | 10 |

A line prices at a given store 67% of the time, so a 5-line basket would complete at a given store
only ~13.5% of the time if lines were independent — **and they are not independent.** A hard line
is hard everywhere: the 3 lines that price nowhere, and much of the k=1/k=2 mass, are the same
requests failing at every store at once. Review is a property of the *line*, not of the store.

A live 4-line example, run across all five stores: `32 oz peanut butter`, `15 oz cereal`,
`2 lb chicken breast`, `1 lb chicken breast` → 3 lines after duplicate resolution → **every store
incomplete**, all of them blocked by the same chicken line. The engine correctly returns no winner
and an explicit reason.

This is not a defect in B5. It is the honest consequence of the plan's own invariant ("only stores
with an acceptable match for every line are comparable") meeting the matcher's real review rate,
and it is exactly what that invariant is for — a ranking produced by ignoring the chicken line
would be comparing baskets that bought different things.

But it does mean **the shipped product will frequently have no ranking to show**, and that is a
Checkpoint 6 design problem, not something to tune away here. The review band is where the
resolution belongs: those lines carry their candidates, and one override each is enough to make the
comparison possible. `apply_override` exists precisely for that path.

## What a comparison carries

Every comparison reports, for every store: total cents (complete baskets only), complete/incomplete,
verified vs unverified line counts, and review/missing counts. **An incomplete basket has no total
at all** — not a hidden partial sum — so "a smaller incomplete basket never outranks a complete
basket" holds by construction rather than by sorting carefully.

Ties return **all** tied stores. Verification counts travel with every comparison, carrying the B3
caveat that verification rate is a storefront artifact and never an input to ranking.

## Reproduction

```bash
cd dash
.venv/bin/python -m pytest test_basket_comparison.py -q
```
