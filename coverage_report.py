#!/usr/bin/env python3
"""Checkpoint 1 coverage report: per-store product/category counts, missing
fields, and crawl-failure diagnostics across the five DashCartCompare MVP stores.

Reads the latest timestamped snapshot in runs/<store>_<id>/ for four stores
(scraped with the current scraper, which also writes a <output>.summary.json
alongside each run's items.csv), and DashMart's own accumulated CSV, scraped
with an older version of the scraper that predates per-run summaries -- that
gap is reported explicitly as "no crawl diagnostics available", not hidden or
backfilled.

Usage:
    python3 coverage_report.py
"""
import csv
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS_ROOT = HERE / "runs"

# (display name, runs/ subdirectory, store_id) for the four stores scraped via run_snapshot.py
RUN_STORES = [
    ("ALDI", "aldi_29631686", "29631686"),
    ("Ralphs", "ralphs_35802549", "35802549"),
    ("Vons", "vons_1742136", "1742136"),
    ("Sprouts", "sprouts_24325284", "24325284"),
]
DASHMART_CSV = HERE / "doordash_store_1042759_items.csv"
DASHMART_ID = "1042759"

REPORT_JSON = HERE / "coverage_report.json"
REPORT_MD = HERE / "coverage_report.md"


def latest_run_dir(store_dir: Path):
    runs = sorted(p for p in store_dir.iterdir() if p.is_dir())
    return runs[-1] if runs else None


def load_rows(csv_path: Path) -> list:
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def latest_snapshot_only(rows: list) -> tuple:
    """Select only the rows from the single most recent scrape run in an
    append-only CSV that accumulates rows from multiple runs over time
    (DashMart's legacy file). Returns (rows, snapshot_id).

    Deliberately NOT a dedupe-by-item_id-keep-last-occurrence: that approach
    was tried first and silently blended two different runs' inventories --
    a product dropped from the catalog between runs would still show up as
    "current" because it was the last row seen for that item_id, even though
    it only ever appeared in an older run. Filtering to one run's own
    scraped_at is the only way to answer "what does the store currently
    carry, per this scraper" rather than "everything ever observed"."""
    if not rows:
        return [], None
    latest_ts = max(r["scraped_at"] for r in rows)
    return [r for r in rows if r["scraped_at"] == latest_ts], latest_ts


def analyze(name: str, store_id: str, rows: list, summary: dict) -> dict:
    total = len(rows)
    ids = [r["item_id"] for r in rows]
    unique_ids = len(set(ids))
    missing_name = sum(1 for r in rows if not r.get("item_name", "").strip())
    missing_price = sum(1 for r in rows if not r.get("price_usd", "").strip())
    missing_unit_size = sum(1 for r in rows if not r.get("unit_size", "").strip())
    categories = Counter(r.get("category", "") for r in rows)

    prices = []
    for r in rows:
        try:
            prices.append(float(r["price_usd"]))
        except (ValueError, KeyError):
            pass

    return {
        "store": name,
        "store_id": store_id,
        "products_total": total,
        "unique_product_ids": unique_ids,
        "duplicate_ids": total - unique_ids,
        "missing_name": missing_name,
        "missing_price": missing_price,
        "missing_unit_size": missing_unit_size,
        "category_count": len(categories),
        "top_categories": categories.most_common(5),
        "price_range_usd": [round(min(prices), 2), round(max(prices), 2)] if prices else None,
        "crawl_diagnostics": summary,
    }


def collect_reports() -> list:
    reports = []
    for name, run_prefix, store_id in RUN_STORES:
        store_dir = RUNS_ROOT / run_prefix
        run_dir = latest_run_dir(store_dir) if store_dir.exists() else None
        if run_dir is None:
            reports.append({"store": name, "store_id": store_id, "error": "no snapshot found"})
            continue
        csv_path = run_dir / "items.csv"
        summary_path = run_dir / "items.summary.json"
        rows = load_rows(csv_path)
        summary = json.loads(summary_path.read_text()) if summary_path.exists() else None
        reports.append(analyze(name, store_id, rows, summary))

    if DASHMART_CSV.exists():
        rows, _snapshot_id = latest_snapshot_only(load_rows(DASHMART_CSV))
        reports.append(analyze("DashMart", DASHMART_ID, rows, None))
    else:
        reports.append({"store": "DashMart", "store_id": DASHMART_ID, "error": "no snapshot found"})
    return reports


def render_markdown(reports: list) -> str:
    lines = [
        "# DashCartCompare Checkpoint 1 -- Coverage Report",
        "",
        "One row per MVP store. \"Crawl\" reflects the scraper's own "
        "pass/fail accounting (see doordash_dashmart_scraper.py); \"n/a\" "
        "means the snapshot predates that instrumentation, not that the "
        "crawl was error-free.",
        "",
        "| Store | Products | Unique IDs | Duplicate IDs | Missing name | Missing price | Categories | Crawl |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in reports:
        if "error" in r:
            lines.append(f"| {r['store']} | - | - | - | - | - | - | {r['error']} |")
            continue
        d = r["crawl_diagnostics"]
        if d is None:
            crawl = "n/a"
        else:
            crawl = "COMPLETE" if d["complete"] else "INCOMPLETE"
            crawl += f" ({d['first_pass_failures']} first-pass fail, {d['still_failed']} still failed)"
        lines.append(
            f"| {r['store']} | {r['products_total']} | {r['unique_product_ids']} | "
            f"{r['duplicate_ids']} | {r['missing_name']} | {r['missing_price']} | "
            f"{r['category_count']} | {crawl} |"
        )

    lines += ["", "## Per-store detail", ""]
    for r in reports:
        if "error" in r:
            continue
        lines.append(f"### {r['store']} (store_id {r['store_id']})")
        if r["price_range_usd"]:
            lines.append(f"- Price range: ${r['price_range_usd'][0]:.2f} - ${r['price_range_usd'][1]:.2f}")
        else:
            lines.append("- Price range: n/a (no parseable prices)")
        pct = r["missing_unit_size"] / r["products_total"] if r["products_total"] else 0
        lines.append(f"- Missing unit_size: {r['missing_unit_size']} ({pct:.1%} of products)")
        top = ", ".join(f"{c} ({n})" for c, n in r["top_categories"])
        lines.append(f"- Top categories by count: {top}")
        if r["crawl_diagnostics"] is None:
            lines.append("- Crawl diagnostics: none recorded (scraped before per-run summaries were added)")
        else:
            d = r["crawl_diagnostics"]
            lines.append(
                f"- Crawl: {d['pages_discovered']} pages discovered, "
                f"{d['first_pass_failures']} failed on first pass "
                f"({d['recovered_on_retry']} recovered on retry, {d['still_failed']} still failed), "
                f"{d['discovery_failures']} discovery failures, "
                f"{d['pages_with_zero_items']} pages parsed with zero items, "
                f"{d['elapsed_seconds']}s elapsed at concurrency={d['settings']['concurrency']}"
            )
        lines.append("")
    return "\n".join(lines)


def main():
    reports = collect_reports()
    REPORT_JSON.write_text(json.dumps(reports, indent=2))
    md = render_markdown(reports)
    REPORT_MD.write_text(md)
    print(md)
    print(f"\nWrote {REPORT_JSON.name} and {REPORT_MD.name}")


if __name__ == "__main__":
    main()
