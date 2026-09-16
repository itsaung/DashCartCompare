# DashCartCompare Checkpoint 1 -- Coverage Report

One row per MVP store. "Crawl" reflects the scraper's own pass/fail accounting (see doordash_dashmart_scraper.py); "n/a" means the snapshot predates that instrumentation, not that the crawl was error-free.

| Store | Products | Unique IDs | Duplicate IDs | Missing name | Missing price | Categories | Crawl |
|---|---:|---:|---:|---:|---:|---:|---|
| ALDI | 3337 | 3337 | 0 | 0 | 0 | 22 | COMPLETE (8 first-pass fail, 0 still failed) |
| Ralphs | 9267 | 9267 | 0 | 0 | 0 | 22 | COMPLETE (14 first-pass fail, 0 still failed) |
| Vons | 9002 | 9002 | 0 | 0 | 0 | 22 | COMPLETE (16 first-pass fail, 0 still failed) |
| Sprouts | 6770 | 6770 | 0 | 0 | 0 | 28 | COMPLETE (22 first-pass fail, 0 still failed) |
| DashMart | 3022 | 3022 | 0 | 0 | 0 | 22 | n/a |

## Per-store detail

### ALDI (store_id 29631686)
- Price range: $0.18 - $57.99
- Missing unit_size: 339 (10.2% of products)
- Top categories by count: Pantry (716), Snacks (490), Household (407), Drinks (323), Frozen (250)
- Crawl: 214 pages discovered, 8 failed on first pass (8 recovered on retry, 0 still failed), 0 discovery failures, 0 pages parsed with zero items, 418.4s elapsed at concurrency=3

### Ralphs (store_id 35802549)
- Price range: $0.17 - $105.79
- Missing unit_size: 611 (6.6% of products)
- Top categories by count: Pantry (1431), Household (968), Personal Care (889), Drinks (713), Snacks (650)
- Crawl: 263 pages discovered, 14 failed on first pass (14 recovered on retry, 0 still failed), 0 discovery failures, 0 pages parsed with zero items, 787.0s elapsed at concurrency=3

### Vons (store_id 1742136)
- Price range: $0.10 - $381.49
- Missing unit_size: 499 (5.5% of products)
- Top categories by count: Pantry (1439), Personal Care (879), Household (821), Drinks (717), Snacks (650)
- Crawl: 262 pages discovered, 16 failed on first pass (16 recovered on retry, 0 still failed), 0 discovery failures, 0 pages parsed with zero items, 789.2s elapsed at concurrency=3

### Sprouts (store_id 24325284)
- Price range: $0.30 - $94.69
- Missing unit_size: 139 (2.1% of products)
- Top categories by count: Pantry (1213), Snacks (607), Drinks (566), Personal Care (548), Dairy & Eggs (413)
- Crawl: 325 pages discovered, 22 failed on first pass (22 recovered on retry, 0 still failed), 0 discovery failures, 0 pages parsed with zero items, 1129.3s elapsed at concurrency=3

### DashMart (store_id 1042759)
- Price range: $0.47 - $100.00
- Missing unit_size: 242 (8.0% of products)
- Top categories by count: Pantry (520), Snacks (391), Drinks (350), Frozen (284), Household (258)
- Crawl diagnostics: none recorded (scraped before per-run summaries were added)
