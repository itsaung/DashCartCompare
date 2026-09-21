# Checkpoint 4, S6 — acceptance threshold and review band

Tuned 2026-09-21, dev split only. Cut points frozen in `checkpoint4_config.CUT_POINTS`.
`evaluation/`, `evaluation_v2/` and `benchmark_config.MIN_SIMILARITY` unmodified.

## Why four thresholds and not one

The three retriever families' scores are not on a common scale, so no single number means the
same thing to all of them:

| Family | dev top-1 score range |
|---|---|
| `embed` | 0.567 – 0.990 |
| `embed_dimension_size_filter` | 0.649 – 0.990 |
| `hybrid_*` (RRF) | 0.0156 – 0.0328 |

An RRF score is ~0.03 for a top result *by construction* — it is a sum of `1/(60 + rank)` terms,
not a similarity. Applying `MIN_SIMILARITY = 0.65` to it would reject everything. Each family
therefore gets its own grid, derived from its own dev top-1 distribution over 17 points plus 0.0.

Deriving a grid from dev scores is itself a use of dev data. That is permitted — dev is the tuning
split — and is stated here rather than left implicit.

## Method

Three-way outcome on the top-1 score `s`: `s >= ACCEPT` is an automatic match,
`REVIEW <= s < ACCEPT` is the review band, `s < REVIEW` is no match. A `needs_clarification`
response stays review and a `no_acceptable_match` stays no-match regardless of score — a parser
gate or an empty candidate list is not something a threshold can overturn.

Cost per included dev request, averaged: **0** acceptable automatic match or correct abstention,
**0.5** deferred to review (any request), **1** abstaining on an answerable request, **2** an
incorrect automatic match, a match on an unanswerable request, or an unresolved best-guess top-1.

Excluded: **r052 and r129**, the two dev `no_acceptable_match` requests whose own E1
`NO_MATCH_AUDIT` confidence was "pattern-consistent, not independently re-searched". 88 of 90 dev
requests included. Same rule and same two requests as E6.

Tie-break, declared before the sweep: lowest average cost, then more confirmed-correct automatic
matches, then a narrower band, then a lower accept threshold.

## Frozen cut points

| Family | Accept | Review floor | Dev cost | **Validation cost** | Dev outcomes (A/R/N) |
|---|---|---|---|---|---|
| `embed` | 0.9370 | 0.7786 | 0.2841 | 0.3167 | 33 / 40 / 15 |
| `embed_dimension_size_filter` | 0.7555 | 0.6916 | 0.1932 | **0.1833** | 65 / 12 / 11 |
| `hybrid_dimension_size_filter` | 0.0274 | 0.0156 | **0.1364** | **0.1833** | 67 / 14 / 7 |
| `hybrid_identity_filter` | 0.0274 | 0.0156 | 0.2330 | 0.2833 | 58 / 15 / 15 |

Validation was inspected once, at the dev-chosen pair, after the cut points were already fixed.
It never fed back into selection.

## Finding 1 — hybrid's dev advantage disappears on validation, again

On dev, `hybrid_dimension_size_filter` is clearly best: 0.1364 against the embedding baseline's
0.1932, a 29% lower cost.

**On validation the two are identical — 0.1833 each, with the same 23/3/4 outcome split.**

This is the second independent measurement to show the same thing. S5 found hybrid and embedding
tied on validation Success@1 (92.0%, 23/25 both) after hybrid led dev by six requests. S6 now
finds them tied on validation cost after hybrid led dev by 29%. Two different metrics, same
pattern: **a large dev gain that validation does not reproduce.**

That is the signature of fitting the dev split, not of a better method. It does not prove hybrid
is no better — validation is 25 requests and cannot resolve a small true difference — but the
evidence for hybrid is now specifically absent twice, on the split that is supposed to arbitrate.

Note also that the embedding baseline *generalizes slightly better than it fit*: dev 0.1932 vs
validation 0.1833. Hybrid moves the other way, 0.1364 → 0.1833.

## Finding 2 — the cost function's review weight is load-bearing

No family's selection is stable across all three swept review costs:

| Family | 0.25 | 0.5 (selects) | 0.75 | Agree with selection |
|---|---|---|---|---|
| `embed` | 0.937 / 0.647 | 0.937 / 0.779 | 0.831 / 0.779 | 0.5 only |
| `embed_dimension_size_filter` | 0.819 / 0.649 | 0.756 / 0.692 | 0.756 / 0.692 | 0.5, 0.75 |
| `hybrid_dimension_size_filter` | 0.027 / 0.016 | 0.027 / 0.016 | 0.027 / 0.027 | 0.5, 0.25 |
| `hybrid_identity_filter` | 0.027 / 0.016 | 0.027 / 0.016 | 0.000 / 0.000 | 0.5, 0.25 |

The accept threshold is reasonably stable — it moves for only two families and never by much. The
**review floor is what moves**, which makes sense: the floor is exactly the knob that trades
review against abstention, and the review cost is exactly the price of that trade.

`hybrid_identity_filter` at review cost 0.75 collapses to 0.000/0.000, i.e. "never abstain, accept
everything" — when review is expensive enough, a baseline this poorly calibrated prefers guessing.

**The 0.5 weight is a declared design preference with no measured basis** ("one wrong match costs
about four review deferrals"). It was declared before the sweep, and the sweep confirms it
matters. These cut points should not be read as precise.

## Finding 3 — the optimum prefers review over abstention almost everywhere

Every family's selected review floor lands at or near the bottom of its grid, and the selected
outcome split is accept-heavy with a thin no-match tail (e.g. 67 / 14 / 7 for hybrid). The cost
function prefers showing a user candidates over silently returning nothing, which follows directly
from review (0.5) being cheaper than abstaining on an answerable request (1.0).

That is the intended behavior, but it means **the review band is doing real work and should be
reported as prominently as precision** — for the best family, 14 of 88 dev requests (16%) land in
review rather than getting an automatic answer.

## Relationship to the demo's finding

The demo (Checkpoint 6 slice) found that right and wrong matches do not separate cleanly on a
single score scale — a wrong lexical match at 0.574 outscored a right one at 0.401. S6 does not
contradict that and does not fix it. What the review band does is give the overlap region a
non-destructive destination: instead of forcing a wrong accept or a wrong abstention, an
ambiguous score defers. That is a mitigation, not a separation.

## What S7 inherits

1. **On validation, embedding and hybrid are indistinguishable** — 0.1833 cost, 92.0% Success@1,
   identical outcome splits. The plan's selection rule is "simplest method with the best
   validation tradeoff". Embedding is simpler, 12x faster (421 ms vs 4,904 ms), and ties on every
   validation measure taken. That is the currently-supported choice, and S7 should say so plainly
   rather than leading with hybrid's dev number.
2. **`hybrid_identity_filter` is not rescued by thresholding.** Its cost is worst on dev and
   validation at its own tuned cut points. As S5 found, this is an S2 extraction-quality problem,
   and S6 confirms no threshold fixes it.
3. **The cut points are approximate.** Report them with the sensitivity table, not as tuned
   constants.
4. **Test is still untouched.** S7 runs it once, after `frozen_config.json` is committed.

## Reproduction

```bash
cd dash
.venv/bin/python tune_threshold_v3.py   # rewrites evaluation_v3/threshold_selection.json
```

Full cost surface for the selecting run (0.5) is in `threshold_selection.json`, along with the
chosen pair at every swept review cost, the grids, the excluded request ids and the one-time
validation inspection.
