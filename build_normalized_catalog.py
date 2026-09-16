#!/usr/bin/env python3
"""Build one reproducible normalized catalog table across all five stores.

This is Checkpoint 2's actual dataset deliverable: parsing functions
(normalize.py, parse_query.py) are necessary but not sufficient -- the plan
calls for a normalized artifact downstream steps (labeling, matching) can
load directly, with explicit identity/provenance, rather than every
consumer re-deriving normalization for itself.

Not a source of truth -- a build artifact from the run folders + DashMart's
CSV. Regenerate by re-running this script whenever a newer snapshot
supersedes an old one.

Usage:
    python3 build_normalized_catalog.py
"""
import csv
import re
from pathlib import Path

from coverage_report import DASHMART_CSV, DASHMART_ID, RUN_STORES, RUNS_ROOT, latest_run_dir, latest_snapshot_only
from normalize import parse_package_size

OUT_PATH = Path(__file__).resolve().parent / "normalized_catalog.csv"

FIELDNAMES = [
    "store_id", "store_name", "snapshot_id", "product_id",
    "raw_title", "raw_category", "raw_size",
    "price_cents",
    "brand", "variant",
    "pkg_dimension", "pkg_count", "pkg_amount_per_pack", "pkg_unit",
    "pkg_canonical_unit", "pkg_canonical_total",
    "parsing_status", "parsing_reason",
    "dimension_review_flag", "dimension_review_reason",
]

# normalize.py's rule "bare oz is always weight" is a deliberate
# simplification of the *string* "oz" -- it has no idea what the product
# actually is. But a beverage recorded with bare "oz" (rather than "fl oz")
# gets parsed as a weight, and a flexible-mode request in fluid ounces would
# never match it: the dimensions just don't line up. This module (which
# does see the product's title/category, unlike normalize.py) flags that
# specific situation for human review. It does NOT reinterpret the value as
# volume -- that would be a different kind of silent guess, just as wrong
# as leaving it unflagged.
_LIQUID_CATEGORIES = {"Drinks", "Alcohol"}

# A much smaller keyword list than a first pass tried, and checked only as
# the *head noun* of the title (the last content word, or immediately
# followed by a container word), not "appears anywhere". Checked against
# this project's real data: a plain "does this word appear anywhere"
# version flagged 340 "milk" hits, the overwhelming majority of them "Milk
# Chocolate" / "Whole Milk Yogurt" / "Whole Milk Ricotta Cheese" -- the word
# describing an ingredient, not the product being a drinkable liquid. Even
# with the head-noun restriction, "coffee" (ground coffee beans), "water"
# (tuna packed in water), "soda" (baking soda), "tea" (green tea shampoo),
# "wine" (cooking wine, wine vinegar), and "cocktail" (fruit cocktail) all
# stayed dominated by false positives and were dropped entirely -- real
# beverages using those words are already caught by the category check
# above. Only kept what actually cleaned up: milk, juice, broth, smoothie.
_LIQUID_HEAD_NOUNS = {"milk", "juice", "broth", "smoothie", "kombucha"}
_CONTAINER_FOLLOWERS = {"bottle", "bottles", "carton", "cartons", "jug", "jugs", "can", "cans"}
_TRAILING_SIZE_RE = re.compile(r"\([^)]*\)\s*$")
# "Dry"/"powder(ed)" milk is a real, common, genuinely solid product
# ("Instant Dry Milk", "Dry Whole Milk Powder") -- excluded explicitly
# rather than relying on the head-noun check alone to catch it.
_DRY_QUALIFIERS = {"dry", "powder", "powdered"}


def _looks_like_liquid(raw_title: str, raw_category: str) -> bool:
    if raw_category in _LIQUID_CATEGORIES:
        return True
    title_wo_size = _TRAILING_SIZE_RE.sub("", raw_title).strip()
    words = title_wo_size.lower().split()
    if set(words) & _DRY_QUALIFIERS:
        return False
    for i, word in enumerate(words):
        if word in _LIQUID_HEAD_NOUNS:
            if i == len(words) - 1 or words[i + 1] in _CONTAINER_FOLLOWERS:
                return True
    return False


def price_to_cents(price_usd: str):
    """Integer cents, per the plan's target schema (avoids float rounding
    drift when summing basket totals later). None -- not 0 -- when the
    source gave no price at all; 0 cents would falsely say "free"."""
    if not price_usd or not price_usd.strip():
        return None
    try:
        return round(float(price_usd) * 100)
    except ValueError:
        return None


def build_row(store_name: str, store_id: str, snapshot_id: str, row: dict) -> dict:
    parsed = parse_package_size(row.get("unit_size", ""))
    if not parsed["unresolved"]:
        status = "resolved"
    elif parsed["variable_weight"]:
        status = "variable_weight"
    else:
        status = "unresolved"

    raw_title = row.get("item_name", "")
    raw_category = row.get("category", "")
    dimension_flag = False
    dimension_reason = None
    if parsed["dimension"] == "weight" and parsed["unit"] == "oz" and _looks_like_liquid(raw_title, raw_category):
        dimension_flag = True
        dimension_reason = (
            "bare 'oz' on a likely-liquid product -- parsed as weight per the "
            "documented literal rule, but this may actually be a beverage "
            "sold in fluid ounces; not auto-converted, needs human review"
        )

    return {
        "store_id": store_id,
        "store_name": store_name,
        "snapshot_id": snapshot_id,
        "product_id": row.get("item_id", ""),
        "raw_title": raw_title,
        "raw_category": raw_category,
        "raw_size": row.get("unit_size", ""),
        "price_cents": price_to_cents(row.get("price_usd", "")),
        # Not yet extracted from raw_title -- explicitly unknown rather than
        # guessed. Filling these in is a later task (Checkpoint 4, matching),
        # not required to get identity/provenance/size right here.
        "brand": None,
        "variant": None,
        "pkg_dimension": parsed["dimension"],
        "pkg_count": parsed["pack_count"],
        "pkg_amount_per_pack": parsed["amount_per_pack"],
        "pkg_unit": parsed["unit"],
        "pkg_canonical_unit": parsed["canonical_unit"],
        "pkg_canonical_total": parsed["canonical_total"],
        "parsing_status": status,
        "parsing_reason": parsed["reason"],
        "dimension_review_flag": dimension_flag,
        "dimension_review_reason": dimension_reason,
    }


def main():
    rows_out = []

    for name, run_prefix, store_id in RUN_STORES:
        store_dir = RUNS_ROOT / run_prefix
        run_dir = latest_run_dir(store_dir) if store_dir.exists() else None
        if run_dir is None:
            continue
        snapshot_id = run_dir.name
        with open(run_dir / "items.csv", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows_out.append(build_row(name, store_id, snapshot_id, row))

    if DASHMART_CSV.exists():
        with open(DASHMART_CSV, newline="", encoding="utf-8") as f:
            all_rows = list(csv.DictReader(f))
        dashmart_rows, snapshot_id = latest_snapshot_only(all_rows)
        for row in dashmart_rows:
            rows_out.append(build_row("DashMart", DASHMART_ID, snapshot_id, row))

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows_out)

    print(f"Wrote {len(rows_out)} rows to {OUT_PATH.name}")
    counts = {}
    for r in rows_out:
        counts[r["parsing_status"]] = counts.get(r["parsing_status"], 0) + 1
    for status, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {status}: {n} ({n / len(rows_out):.1%})")


if __name__ == "__main__":
    main()
