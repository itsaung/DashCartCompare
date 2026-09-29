"""Constants for the price swing tracker (PRICE_MISTAKE_FINDER_PLAN.md).

Every threshold here is PROVISIONAL: chosen before any multi-snapshot history
existed for the tracked stores. W3 measures the same-day noise floor and W5
revisits these against it. Change them here, nowhere else.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS_ROOT = HERE / "runs"
WATCH_DIR = HERE / "price_watch"
WATCH_PAGES_PATH = WATCH_DIR / "watch_pages.json"
CRAWL_LOG_PATH = WATCH_DIR / "crawl_log.jsonl"
ALERTS_PATH = WATCH_DIR / "alerts.jsonl"

# (display name, runs/ directory slug, DoorDash store ID)
TRACKED_STORES = [
    ("Best Buy", "bestbuy", "26060223"),
    ("Target", "target", "2833969"),
]

# Only items whose HIGHEST observed price reaches this are tracked, so an item
# that falls from $60 to $35 stays in scope. $50 chosen by the user to cut
# Target's page count (93 of 324 sub-category pages hold a >= $50 item).
WATCH_MIN_PRICE_CENTS = 5000

# A swing needs BOTH: the relative floor alone lets a $0.99 -> $1.49 move
# (+51%) rank with a TV, the absolute floor alone flags every 1% move on a
# $1,999 laptop. 20% / $10 are round starting values, not fitted to data.
SWING_REL_THRESHOLD = 0.20
SWING_ABS_THRESHOLD_CENTS = 1000

# A swing is "reverted" when a later observation is back within this fraction
# of the pre-swing price. Short-lived unexplained reverted swings are the
# likeliest pricing errors.
REVERT_TOLERANCE = 0.05

# Watch crawls run gentler than the scraper's defaults (6 / 0.15 s), which
# reached a 403 on Target's 376-page crawl on 2026-09-28.
WATCH_CONCURRENCY = 3
WATCH_MIN_INTERVAL = 0.5
