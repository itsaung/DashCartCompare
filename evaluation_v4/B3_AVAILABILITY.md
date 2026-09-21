# Checkpoint 5, B3 — availability and eligibility

Built 2026-09-21 from the 5 snapshots the frozen catalog was actually assembled from. The frozen
catalog is not modified: availability lives in a side-car, `evaluation_v4/availability.csv`, keyed
`(store_id, product_id)`, so `catalog_version` does not move and no Checkpoint 3 or 4 label goes
stale. Same discipline as `evaluation_v3/catalog_identity.csv`.

## Four states, not two

| state | meaning | in a basket |
|---|---|---|
| `out_of_stock` | the storefront said so | **excluded**, and named in the explanation |
| `in_stock` | `Many in stock` | eligible, verified |
| `in_stock_limited` | `In stock (N)` — a remaining count | eligible, verified, count carried |
| `unverified` | no stock field, or a value this code has not seen | eligible, **nothing is known** |

`In stock (20+)` is recorded as a **lower bound**, not as exactly 20 — it is the storefront's
display cap. An unrecognized value maps to `unverified` and its raw text is carried into the
manifest, so a new storefront form surfaces as a number rather than disappearing into a bucket.

## Result, 31,398 catalog rows

| state | rows | share |
|---|---|---|
| `unverified` | 15,388 | **49.0%** |
| `in_stock` | 13,060 | 41.6% |
| `in_stock_limited` | 2,750 | 8.8% |
| `out_of_stock` | 200 | 0.6% |
| *(of which, failed to join at all)* | *248* | *0.8%* |

**Roughly half the catalog has no availability signal at all.** "Exclude explicitly out-of-stock
items" therefore removes 0.6% of rows, and is a far weaker guarantee than it sounds. The engine
must not let a confident-looking basket total imply verified availability.

## Correction to the plan's figures

`CHECKPOINT_5_PLAN.md` B3 recorded 54.6% null across "all 11 snapshot files (77,126 rows)" and four
distinct non-null values. Both numbers were computed over every snapshot directory on disk, which
is the wrong population twice over: there are 11 snapshot directories but the frozen catalog draws
on only **5** of them, and that glob missed DashMart entirely, whose rows come from the legacy
top-level `doordash_dashmart_1042759_items.csv` and have no `runs/` directory.

Against the 5 real sources: **49.0% unverified**, and the value space includes `In stock (20+)`,
a fifth form the earlier count did not see. The join is resolved from each catalog row's own
`snapshot_id` rather than by globbing, so a row is never read against a different run of the same
store.

## Finding — verification rate is a storefront artifact, not a stock difference

| store | rows | verified | unverified | out of stock |
|---|---|---|---|---|
| DashMart | 3,022 | **89%** | 8% | 74 |
| Ralphs | 9,267 | 55% | 45% | 3 |
| Vons | 9,002 | 44% | 55% | 32 |
| Sprouts | 6,770 | 41% | 58% | 25 |
| ALDI | 3,337 | **37%** | 61% | 66 |

DashMart publishes a numeric count for almost every product (2,700 of 3,022 are
`in_stock_limited`); the other four storefronts publish `Many in stock` or nothing. **DashMart is
not better stocked — it is more talkative.**

This matters for B5. Two stores can hold the same basket and one will look far better verified
purely because of what its storefront chose to render. A comparison that ranked or filtered on
verification, or that presented "89% verified" next to "37% verified" without explaining why,
would be reporting a UI difference as a supply difference. Availability verification is reported
per store **with this caveat attached**, and is never an input to ranking.

It also compounds the catalog-size bias already recorded as Risk 1: DashMart has the smallest
catalog *and* the most verbose stock data.

## The 248 unjoined rows

All 248 are DashMart. Its catalog slice has 3,022 rows while the legacy CSV has 3,163, and 248
catalog rows do not appear in that file by `item_id` — the legacy CSV is a different capture from
the one the catalog was built from. They are recorded as `unverified`, never dropped: dropping them
would silently shrink DashMart's catalog and make it look as though it does not stock those items.

## Basket-level labelling

`basket_availability` labels a whole basket, not only its lines. **Any** unverified or out-of-stock
line makes the basket unverified — not a majority vote, because one line that cannot be confirmed
is enough to make the total a best effort rather than a fact. With 49% of rows unverified, most
real baskets will carry this label, which is the honest outcome rather than a defect to tune away.

## Reproduction

```bash
cd dash
.venv/bin/python build_availability.py      # -> availability.csv + availability_manifest.json
.venv/bin/python -m pytest test_availability.py -q
```

A fresh build reproduces `availability.csv` byte-for-byte; checked, not assumed.
