# Price swing tracker — plan

Status: implementation plan only. Prepared 2026-09-28 on branch `price-mistake-finder`, cut from
`main` @ `eb5551e`. This is a standalone feature, not part of the DashCartCompare checkpoint
sequence. It does not read or write the frozen five-store catalog, `evaluation*/`, or the matcher.
Sub-checkpoints are **W1–W6**.

## What this is

Scrape a fixed set of stores repeatedly, keep every snapshot, and report products whose price moved
by a large amount between snapshots. The interval between snapshots is **not yet decided**. It is
chosen in W3, from measured crawl duration and rate-limit behaviour.

## Built so far (2026-09-28)

| file | what | plan step |
|---|---|---|
| `price_watch_config.py` | tracked stores, the $50 floor, swing thresholds, watch-crawl pacing (all provisional) | W1 |
| `price_watch.py` | loads snapshots, builds price history, detects swings, labels them, handles alert dedupe | W2, W5 |
| `price_watch_snapshot.py` | runs `--discover` and watch crawls, keeps `watch_pages.json`, stops on 403, sends macOS notifications for new dips | W1, alerts |
| `price_watch_app.py` | Streamlit report with Swings, Item history, Alerts sent and Crawl health tabs, launched with `.venv/bin/streamlit run price_watch_app.py` | report |
| `test_price_watch.py` | 14 tests on hand-built histories | |

The scraper change is a refactor with no change in behaviour: `item_row` and `CSV_FIELDNAMES` were
moved out of `main()` so the watch crawl writes the same CSV schema.

**First noise-floor reading.** Target's two snapshots were taken 44 minutes apart. 1,553 items
appear in both, and **0/1,553** changed price, so the detector found 0 swings on real data.

**Not done yet:**
- The first `--discover` crawl, which creates `watch_pages.json`. It waits for the 403 to clear.
- W3's interval choice.
- W4's launchd job.
- W6's hand review.

## Tracked stores

| store | DoorDash store ID | slug | categories at probe |
|---|---|---|---|
| Best Buy (9540 Mira Mesa Blvd) | 26060223 | `bestbuy` | 18 |
| Target (8001 Othello Ave) | 2833969 | `target` | 39 |

These two stores are the whole list. The 99 Ranch snapshot taken earlier on this branch was
deleted.

## Price scope: products at $50 and up

Swing tracking covers only products priced **≥ $50** (`WATCH_MIN_PRICE_CENTS = 5000`). The main
purpose is to cut the request count that triggered the 403s. Low-priced swings are also less worth
reporting.

**What it saves has to be counted in pages, not products.** DoorDash rate-limits requests, and one
page request returns every product on that page at every price. The filter therefore saves
requests only by skipping whole sub-category pages that hold no $50+ products. Measured on the
2026-09-28 snapshots:

| | products ≥ $50 | sub-category pages with any ≥ $50 product |
|---|---|---|
| Best Buy | 1,222/2,205 (55.4%) | 78/84 |
| Target | 761/11,504 (6.6%) | **93/324** |

For Target this cuts roughly 376 page requests to about 93 per crawl. For Best Buy it saves almost
nothing, but at 107 pages Best Buy was never the problem.

**Two-tier crawl:**

1. **Discovery crawl (infrequent).** A full crawl of both stores, as run on 2026-09-28. It rebuilds
   `price_watch/watch_pages.json`: every (category, sub-category) page that showed at least one
   ≥ $50 product, together with the sub-category lists, so watch crawls skip the 35 discovery
   requests too. It runs on a slow cadence, provisionally weekly.
2. **Watch crawl (on the interval).** Fetches only the pages in `watch_pages.json`. Every product on
   those pages is recorded, whatever its price.

**Rules that stop the filter from hiding swings:**

- An item's eligibility is judged on the **highest price observed** for it, not its current price.
  A TV that drops from $60 to $35 stays tracked, and it is exactly the swing we want.
- A page stays on the watch list once added, until a discovery crawl shows it has had no ≥ $50
  product for two discovery cycles in a row.
- **Known blind spot:** page membership comes from the first render batch, which holds 50–100
  products. A sub-category whose visible batch is all under $50 may still hold $50+ products further
  down. W3 measures this: for truncated pages, it compares DoorDash's `totalItemCount` with the
  number of products the page actually returned.

## Inputs and storage

- Snapshots come from the existing `run_snapshot.py` and are written to
  `runs/<slug>_<store_id>/<timestamp>/items.csv`. That is the layout `DATA_DICTIONARY.md` already
  documents: one directory per crawl, never modified after it is written.
- Baseline snapshots of both stores were taken on 2026-09-28. Their counts are recorded under
  "Baseline" below.

## Out of scope

- The five-store catalog, the benchmark, and any Checkpoint 5.1/6 work.
- Raising concurrency or lowering `--min-interval` below the tuned defaults. A tighter interval is
  bought by scraping less often, not by scraping faster.
- Alerts or notifications (email, push). The output is a report file. Alerts can come later once
  swing precision is known.
- UI.

Outputs go to **`price_watch/`**.

---

## W1 — Tracked-store config and snapshot runner

Add a `price_watch_config.py` holding `TRACKED_STORES` (name, slug, store ID) and
`WATCH_MIN_PRICE_CENTS`. Add a `price_watch_snapshot.py` with two modes:

- `--discover` runs the full crawl and rebuilds `watch_pages.json`.
- The default mode fetches only the watched pages, reusing the scraper's `fetch`, `Pacer` and
  `extract_items`, with no new extraction logic.

Stores run **sequentially**, never in parallel. It also appends one line per crawl to `price_watch/crawl_log.jsonl` with the
start time, duration, page failures, product count and COMPLETE/INCOMPLETE status.

**Pass criteria:** one invocation produces one new snapshot directory per store and one log line per
store. A store that fails is logged and does not stop the other store from running.

## W2 — Price history table

Join every snapshot of a store on `item_id` to build one history table: one row per (item,
snapshot), with `price_cents`, `original_price_cents`, `stock_status` and `observed_at`.

**The key assumption:** `item_id` is stable across snapshots of the same store. DashMart supports
this: 2,699 items matched by `item_id` between its 2026-09-08 and 2026-09-16 snapshots. W2 re-checks
it on the tracked stores by counting title changes under a fixed `item_id`.

**Absence is not a price change.** The crawler does not recover every product on every run, because
of per-category rendering truncation (see `doordash_scrape_findings.md`). An item missing from one
snapshot is recorded as `not_observed`, never as delisted and never as priced at zero.

**Pass criteria:** tests on hand-built snapshot fixtures cover these cases:
- an item present in every snapshot
- an item missing from a middle snapshot
- an item appearing for the first time
- a title change under the same `item_id`

## W3 — Noise floor and interval choice

This is measured, not assumed. Take a **second snapshot of each store on the same day** as the
baseline and diff the two:

- **Coverage churn:** items present in one run and absent from the other. Earlier Sprouts runs
  varied between 6,770 and 6,798 products within one day, so churn is expected.
- **Price differences with no real time elapsed:** these should be 0. Any nonzero count is scraper
  or storefront noise, and it is the floor every swing threshold has to clear.
- **Crawl duration per store:** the 99 Ranch crawl (205 pages) took 568 s.

The interval is then decided from three constraints:
1. It must be at least the total crawl time of both stores plus a cooldown.
2. It must stay under the frequency that triggered 429s during baseline and repeat runs.
3. It should match how often these stores actually change prices. That is unknown until W5 has
   data, so the first interval is provisional and is revisited after W5.

**Output:** `price_watch/W3_NOISE_AND_INTERVAL.md`, containing the measured churn, price-noise
count, crawl durations, and the chosen interval with its reasoning.

## W4 — Scheduling

Run `price_watch_snapshot.py` on the interval chosen in W3, using **launchd on this Mac**. Use a
user LaunchAgent with `StartInterval`, installed from a plist committed to the repo.

launchd does not run jobs while the Mac is asleep. A slot missed during sleep runs once on wake;
it is not replayed once per missed slot. The history therefore has irregular gaps, and W2/W5 must
treat snapshot spacing as variable, never as a fixed interval.

**Guardrails:**
- If a run is still going when the next one is due, the next run is skipped rather than started in
  parallel.
- A run that hits a hard 403 stops, logs the failure, and does not retry until the next scheduled
  slot.

## W5 — Swing detection

For each item, compare consecutive **observed** prices (skipping `not_observed` gaps) and flag a
**swing** when both of these hold:

- `|Δ| / previous ≥ SWING_REL_THRESHOLD`
- `|Δ| ≥ SWING_ABS_THRESHOLD_CENTS`

The absolute floor stops a $0.99 → $1.49 change (+51%) outranking a $1,299 → $999 television. Both
constants are declared with a sensitivity table, and their values are chosen after W3 has measured
the noise floor.

Each swing is labeled with how it can be explained:

| label | meaning |
|---|---|
| `sale_start` / `sale_end` | `original_price` appears or disappears alongside the change |
| `unexplained` | no `original_price` change accompanies it |
| `reverted` | the price returns to within `REVERT_TOLERANCE` of its earlier level on a later snapshot |

A short-lived unexplained swing that later reverts is the pattern most likely to be a pricing
error.

**Outputs:** `price_watch/swings.csv`, and `price_watch/SWINGS.md` listing the largest swings first
with before/after prices, timestamps and label.

**Pass criteria:** unit tests on hand-built histories cover each label and each threshold boundary.

## W6 — Hand review

Check the top 30 swings against the live product page. Label each one as `real` (the price did
move), `artifact` (the change came from a scraper or parse error) or `gone` (the page changed
again). Report precision per explanation label with numerator and denominator.

## Risks

1. **Different storefronts.** Best Buy and Target are DoorDash retail storefronts, not grocery.
   Their pages may render differently from the grocery stores the scraper was tuned on. The baseline
   crawl's zero-item page count is the first check.
2. **Rate limits over time.** One crawl is tolerated. A crawl every few hours for weeks may earn a
   long-lived block. The W1 crawl log should show a rising 429 rate before it becomes a hard block,
   and W4 backs off when it does.
3. **Sale prices on list pages.** Where a store does not publish `original_price`, every sale looks
   `unexplained`. Whether each store publishes it is checked on the baseline.

4. **Target coverage is capped at the first render batch.** See "Baseline" below. Without a fix,
   Target tracking follows whichever 50 products each category happens to show first.

## Baseline (2026-09-28)

Both baseline crawls finished COMPLETE with default settings (concurrency 6, min-interval 0.15 s).
All figures below are from the two snapshot directories.

| | Best Buy | Target |
|---|---|---|
| snapshot | `2026-09-29T054512Z` | `2026-09-29T055059Z` |
| pages crawled | 107 | 38 |
| first-pass failures / recovered | 5 / 5 | 0 / 0 |
| zero-item pages | 0 | 3 |
| crawl time | 346.5 s | 18.8 s |
| products | 2,205 | 1,605 |
| duplicate `item_id`s | 0 | 0 |
| categories / sub-categories seen | 17 / 84 | 35 / **0** |
| rows with `original_price` | 685/2,205 (31.1%) | 27/1,605 (1.7%) |
| median price | $59.99 | $8.19 |
| max price | $2,999.99 | $517.49 |
| rows ≥ $100 | 804 | 14 |

**Target is truncated.** 31 of its 35 categories returned **exactly 50** products, which is the
server-rendered batch size, and sub-category discovery found **no** sub-category links. The
decomposition workaround the scraper relies on (see `CLAUDE.md`, "Category pages under-render")
therefore does nothing for this storefront. The 1,605 products are a sample of Target's catalog,
not the catalog.

**W1b — done 2026-09-28.** The sub-categories are in the flight payload's `l2Categories` array.
They are not rendered as links, and that is why the regex missed them. `discover_subcategories`
now also reads them through `flight_subcategories`, which is covered by
`test_scraper_subcategories.py`. Details are in `doordash_scrape_findings.md`.

Re-crawl `2026-09-29T061806Z`:

| | truncated baseline | re-crawl |
|---|---|---|
| pages | 38 | 376 |
| products | 1,605 | **11,504** |
| crawl time | 18.8 s | 1,046 s (17.4 min) |
| status | COMPLETE | INCOMPLETE |

The re-crawl is INCOMPLETE because 11 of its 376 pages were still failing after the slow retry.
Those 11 are the Candy and Party Supplies category pages and 9 sub-category pages, and every one
returned **403**. The first pass had returned 429s; the retry pass got 403s, which means the IP was
being blocked rather than slowed down. Three pages parsed zero items: `men`, `women` and `kids`,
the three category slugs without a numeric ID. They appear to be landing pages.

Coverage against DoorDash's own `totalItemCount` is not measured yet. It needs one pass over the
35 category pages, deferred until the block clears. The one figure seen so far: Snacks reports
1,652 items.

**Implications for the interval (W3):**
- A full Target crawl is now about 376 requests and 17 minutes, and at that rate it reached a 403.
  One Best Buy crawl plus one Target crawl already sits at DoorDash's tolerance at the default
  settings.
- W3 has to measure the interval between clean crawls. It must not assume the old 429-only
  behaviour. It may also need a lower concurrency or a larger `--min-interval` for Target
  specifically.
- **W3's same-day rerun decides whether the capped set is stable.** If the top 50 per category
  reorders between runs, W2 will record most Target items as `not_observed` on most snapshots.
- **Target publishes almost no `original_price`** (1.7%). Nearly every Target swing will be
  labeled `unexplained`, so that label carries far less information for Target than for Best Buy.
  W6 reports the two stores separately.
- **Best Buy's price scale makes the absolute floor matter.** Its median item is $59.99 and 804
  rows are $100 or more.
