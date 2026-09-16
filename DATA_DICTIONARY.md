# Data Dictionary — DoorDash catalog snapshots

Scope: the raw scraped catalog data collected in Checkpoint 1, before any
normalization. This describes the data as `doordash_dashmart_scraper.py`
produces it today, not the target normalized schema in the project plan
(store ID / product type / package count / etc. as separate structured
fields) — that mapping is Checkpoint 2's job, not this document's.

## File layout

```
dash/runs/<store_slug>_<store_id>/<timestamp>/items.csv
dash/runs/<store_slug>_<store_id>/<timestamp>/items.summary.json        (if the run had any pages to report on)
dash/runs/<store_slug>_<store_id>/<timestamp>/items.failed_pages.json   (only if something failed or parsed empty)
```

`<timestamp>` is UTC, `YYYY-MM-DDTHHMMSSZ`. Each timestamped directory is one
full crawl of one store and is never modified after being written — a new
crawl gets a new directory, it does not overwrite or append to an old one.

**Exception:** `dash/doordash_store_1042759_items.csv` (DashMart) predates
this per-run-directory convention. It is a single file that multiple scrape
runs have appended to over time (via `append_csv`), so it contains rows from
more than one `scraped_at` date. Anything reading it as "the current
catalog" must filter to rows matching the single most recent `scraped_at`
value (see `coverage_report.py`'s `latest_snapshot_only`) — **not** dedupe by
`item_id` keeping the last occurrence across the whole file. That
alternative was tried first and is wrong: a product dropped from the store
between two runs would still show up as "current" because it was the last
row ever seen for that `item_id`, even though it only existed in an older
run (this file has exactly two runs, and the difference is 304 products).
It also has no `.summary.json` — that instrumentation didn't exist yet when
most of its rows were collected.

## Store identity — not a column

**`store_id` and store name are not columns in `items.csv`.** They're
implied by which file you're reading: the `runs/<slug>_<store_id>/` directory
name, or which of the five known CSVs you loaded. This is a known gap
against the project plan's target schema, which wants store ID and store
name as explicit columns (so a downstream step can concatenate all five
stores' rows into one table and still know which store each row came from
without tracking file provenance separately). Left as-is for Checkpoint 1
since it doesn't block coverage analysis; adding those two columns is a
small, natural part of Checkpoint 2's normalization pass rather than
something to bolt on here.

## `items.csv` columns

| Column | Type | Description | Notes |
|---|---|---|---|
| `scraped_at` | ISO 8601 UTC timestamp | When this row was written | Same for every row in one run |
| `category` | string | Top-level category display name (e.g. "Snacks") | Title-cased from the URL slug |
| `subcategory` | string | Sub-category chip display name, or empty | Empty for rows found directly on a category page rather than a sub-category page |
| `item_id` | string | DoorDash's item identifier | **Not globally unique across stores** — see store-identity note above. ID *length* varies within a single store (11 vs. 16 digits observed) since DoorDash's catalog blends items from different backend systems; this is expected, not a parsing artifact |
| `item_name` | string | Product title as DoorDash displays it | Not brand/variant/size decomposed — that's Checkpoint 2 |
| `expires_soon` | "yes" or "" | Whether the listing was flagged expiring soon | |
| `best_by` | string or "" | Best-by date if DoorDash surfaced one | Sparse — only present in some list-card badges, not the full catalog |
| `price` | string | Display price, e.g. `"$4.29"` | Human-formatted, not for arithmetic |
| `price_usd` | string | Price as a decimal string, e.g. `"4.29"` | Use this for calculations; parse with `float()`. Empty only if DoorDash's own listing omitted a price entirely |
| `original_price` / `original_price_usd` | string | Pre-discount price, if the item is on sale | Empty when not on sale |
| `discount` | string | Discount badge text, e.g. `"20% off"` | Empty if none |
| `unit_size` | string | Free-text package size, e.g. `"12 oz"`, `"4.8 oz × 8 ct"` | **Not yet split** into count/amount/unit — single free-text field. Missing on 2–10% of rows per store (see coverage report); DoorDash simply doesn't always expose it |
| `unit_price` | string | Price per unit, e.g. `"$0.36/oz"`, when DoorDash/the scraper could derive one | Sparser than `unit_size` |
| `stock_status` | string | e.g. `"In stock (20+)"`, `"Out of stock"` | Derived from a stock badge; empty if DoorDash didn't show one |
| `recently_sold` | string | e.g. `"500+ recently sold"` | Only ever populated via `--details` (product-page fetch), empty otherwise |
| `snap` | "yes" or "" | SNAP/EBT eligibility flag | |
| `rating` | string | Average star rating | Empty if the item has no ratings yet |
| `rating_count` | string | Number of ratings, as DoorDash displays it (e.g. `"1.2k"`) | Free text, not a clean integer |
| `image_url` | string | Product image URL | |

## `items.summary.json`

One object per run, written next to `items.csv`.

| Field | Description |
|---|---|
| `store_id`, `name` | Store identifier and display name |
| `scraped_at` | Run timestamp |
| `settings` | `concurrency`, `min_interval`, `paginate`, `details` — the CLI settings the run used |
| `elapsed_seconds` | Total wall-clock time for the run |
| `pages_discovered` | Category + sub-category pages found and crawled |
| `first_pass_failures` | Pages that failed at least once before any retry |
| `recovered_on_retry` | Of those, how many succeeded on the single slow retry pass |
| `still_failed` | Pages that failed even after the retry — these did not make it into `items.csv` |
| `discovery_failures` | Categories whose sub-category list itself failed to load — their sub-category pages were never even attempted |
| `pages_with_zero_items` | Pages that returned HTTP success but parsed no items — could be a genuinely empty sub-category, or a parser/page-shape mismatch; not distinguished |
| `products_saved` | Row count in this run's `items.csv` |
| `complete` | `true` only if `still_failed == 0` and `discovery_failures == 0`. **Does not mean the full catalog was recovered** — see the SSR-truncation caveat in the scraper's module docstring; this flag is scoped to "every discovered page was fetched," not "every product on the site was found" |

## `items.failed_pages.json`

Only written when there's something to show. Three lists:

- `first_pass_failures` — every page that failed on its first attempt, **even if a later retry fixed it**. Each entry has `category`, `subcat`, `url`, and `attempts`: a list of every individual attempt (`n`, `status`, `error`, `elapsed`, `size`), not just the last one.
- `still_failed` — pages that never succeeded, in the same shape. These are missing from `items.csv` entirely.
- `discovery_failures` / `zero_item_pages` — see the summary fields above; same per-page detail.

## Known limitations (Checkpoint 1 scope)

- No explicit `store_id`/`store_name` columns (see above).
- `unit_size` is unparsed free text; distinguishing "12 oz" from "4.8 oz × 8 ct" (pack count vs. total quantity) is Checkpoint 2 work, not done here.
- Coverage is bounded by what DoorDash's category/sub-category pages server-render — a "COMPLETE" crawl (per `items.summary.json`) means every discovered page was fetched, not that every product the store actually carries was found. Some individual sub-categories still exceed a single page's render batch (documented in `doordash_scrape_findings.md`); that gap is not currently measured or reported per-store.
- DashMart's snapshot has no crawl diagnostics (predates `items.summary.json`) and is deduped from an append-only multi-run file rather than being one clean single-run snapshot like the other four stores.
