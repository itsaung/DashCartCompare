# Checkpoint 5, B1.5 — the container-word parser fix, and what it changes

Measured 2026-09-21, after Checkpoint 4 closed. `evaluation/`, `evaluation_v2/` and
`evaluation_v3/` are untouched; this file records the delta rather than rewriting a frozen report.

## What was broken

`parse_shopping_line` discarded the size a shopper stated whenever the line used an
`a <size> <container> of <product>` phrasing. The line parsed as a bare count of 1:

| request | before | after |
|---|---|---|
| `a 67.6 fl oz bottle of Coke soda` | `count`, 1 ct | `volume`, 67.6 fl oz |
| `a 24 oz loaf of Bimbo Large White Bread` | `count`, 1 ct | `weight`, 24 oz |
| `a 12 fl oz x 12 ct pack of Diet Coke Diet Cola Soda` | `count`, 1 ct | `volume`, 144 fl oz |
| `a 12 fl oz x 12 ct case of La Croix Razz-Cranberry Sparkling Water` | `count`, 1 ct | `volume`, 144 fl oz |
| `3 boxes of 12 oz pasta` | `needs_review` | `weight`, 36 oz (3 × 12) |

With the dimension reading `count`, `filter_by_dimension` dropped every volume or weight candidate
before size matching was ever reached, so the matcher abstained.

**4 of the 150 benchmark requests state a size the old parser discarded. All four are dev.**

## Why it was fixed before B2 rather than in B4

In Checkpoint 4 this bug caused an *abstention* — the matcher returned nothing, which is visible
and safe. A basket engine fed `1 ct` when the shopper said `67.6 fl oz` computes a confident
**wrong package count and a wrong price**. The failure mode changes from silence to a plausible
lie, so the fix moved ahead of the engine that would consume it.

## Measured effect on the frozen matcher

`embed_dimension_size_filter` at its frozen cut points (accept 0.75552 / review floor 0.691613),
re-run on those four requests only:

| request | before | after | top-1 after | conservative label |
|---|---|---|---|---|
| r017 | abstain | **automatic match** | Coke Cola Soda Bottle (67.6 fl oz) | Acceptable |
| r021 | abstain | **automatic match** | Bimbo Large White Bread (24 oz) | Acceptable |
| r142 | abstain | **automatic match** | Diet Coke Diet Cola Soda (12 fl oz x 12 ct) | Acceptable |
| r151 | abstain | **automatic match** | La Croix Razz-Cranberry Sparkling Water Cans (12 fl oz x 12 ct) | Acceptable |

All four resolve to the exactly-named product. Consequent dev-split movement:

| | Checkpoint 4 (frozen) | with the parser fix |
|---|---|---|
| automatic / review / abstain | 65 / 12 / 13 | 69 / 12 / 9 |
| automatic-match rate | 72.2% (65/90) | 76.7% (69/90) |
| abstention rate | 14.4% (13/90) | 10.0% (9/90) |
| automatic-match precision, conservative | 96.9% (63/65) | 97.1% (67/69) |

**Validation and test do not move** — all four affected requests are in dev. The Checkpoint 4
headline (100.0%, 17/17 on test) is unaffected, and nothing in `frozen_config.json` changes.

## Disclosure: Checkpoint 4's reproduction claim is now version-dependent

`evaluation_v3/SEMANTIC_RESULTS.md` states that a fresh run reproduces its predictions. That
remains true **at the code SHA recorded in `frozen_config.json`** (`237b021fa6`). It is no longer
true at `HEAD`, because these four requests now parse differently and the matcher consequently
matches them. The frozen artifacts were not regenerated, deliberately: rewriting a published
report to absorb a later fix is exactly the move that makes a frozen benchmark meaningless.

Read the Checkpoint 4 numbers as what that configuration measured, and this file as the one
known, measured divergence from it.

## Reproduction

```bash
cd dash
.venv/bin/python -m pytest test_parse_query.py -q
```

`parser_fix_delta.json` carries the per-request before/after outcomes, scores and labels.
