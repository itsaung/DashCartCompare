#!/usr/bin/env python3
"""Sample products from the normalized catalog for manual verification
against the plan's Checkpoint 1 pass criterion (20 products per store,
checked against source data).

Generation and review are deliberately separate steps. `generate()` only
ever creates rows in the "unreviewed" state -- it never assigns "OK" on
anyone's behalf, and it never overwrites a decision a reviewer already
recorded. Recording an actual decision (that a human, or an independent
fetch of the live product page, checked this row) is done with
`record_decision()`, which is the only thing allowed to change a row's
status. Rerunning generation is safe: the sample draw is seeded, so the
same rows come back, and existing decisions for those rows are kept as-is.

`source_url` on each row is the live DoorDash product-page URL for that
item, so "verified" means someone (or something) actually compared this
row's raw_title/price_cents/raw_size against that independent source --
not just re-read the same normalized_catalog.csv value back at itself.

Usage:
    python3 manual_review.py                              # generate/refresh unreviewed rows, render MANUAL_REVIEW.md
    python3 manual_review.py --record STORE PRODUCT_ID DECISION [NOTES]
        # DECISION is one of: verified, discrepancy
"""
import csv
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "normalized_catalog.csv"
DECISIONS_PATH = HERE / "manual_review_decisions.json"
OUT_PATH = HERE / "MANUAL_REVIEW.md"
PER_STORE = 20
SEED = 20260916


def _key(store: str, product_id: str) -> str:
    return f"{store}|{product_id}"


def _source_url(store_id: str, product_id: str) -> str:
    return (
        f"https://www.doordash.com/convenience/store/{store_id}"
        f"?origin_page=item&product_id={product_id}&store_id={store_id}"
    )


def load_decisions() -> dict:
    if DECISIONS_PATH.exists():
        return json.loads(DECISIONS_PATH.read_text())
    return {}


def save_decisions(decisions: dict) -> None:
    DECISIONS_PATH.write_text(json.dumps(decisions, indent=2, sort_keys=True))


def sample_rows() -> list:
    rows = list(csv.DictReader(open(CATALOG, newline="", encoding="utf-8")))
    by_store = {}
    for r in rows:
        by_store.setdefault(r["store_name"], []).append(r)
    rng = random.Random(SEED)
    sampled = []
    for store in sorted(by_store):
        pool = by_store[store]
        sampled.extend(rng.sample(pool, min(PER_STORE, len(pool))))
    return sampled


def generate() -> tuple:
    """Ensure every currently-sampled row has a decisions entry, creating
    new ones as "unreviewed" and leaving existing decisions untouched.
    Returns (sampled_rows, decisions)."""
    rows = sample_rows()
    decisions = load_decisions()
    for r in rows:
        key = _key(r["store_name"], r["product_id"])
        if key not in decisions:
            decisions[key] = {
                "decision": "unreviewed",
                "notes": "",
                "source_url": _source_url(r["store_id"], r["product_id"]),
                "expected": {},
                "reviewed_at": None,
            }
    save_decisions(decisions)
    return rows, decisions


def record_decision(store: str, product_id: str, decision: str, notes: str = "", expected: dict = None) -> None:
    if decision not in ("verified", "discrepancy", "unreviewed"):
        raise ValueError(f"decision must be verified/discrepancy/unreviewed, got {decision!r}")
    decisions = load_decisions()
    key = _key(store, product_id)
    if key not in decisions:
        raise KeyError(f"{key} is not in the current sample -- run generate() first")
    decisions[key]["decision"] = decision
    decisions[key]["notes"] = notes
    if expected is not None:
        decisions[key]["expected"] = expected
    decisions[key]["reviewed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    save_decisions(decisions)


def render(rows: list, decisions: dict) -> str:
    counts = {"verified": 0, "discrepancy": 0, "unreviewed": 0}
    lines = [
        "# Manual Review — Checkpoint 1/2 sample verification",
        "",
        f"{PER_STORE} products per store, sampled with a fixed seed ({SEED}) from "
        "`normalized_catalog.csv`. Rows start as `unreviewed` and only change when "
        "`record_decision()` is actually called -- this file does not manufacture "
        "\"OK\" for rows nobody has checked. `source_url` is the live DoorDash "
        "product page, checked independently of this project's own stored data, "
        "not just re-reading the CSV back at itself.",
        "",
        "| Store | Product ID | Title | Price | Size | Status | Notes |",
        "|---|---|---|---:|---|---|---|",
    ]
    for r in rows:
        key = _key(r["store_name"], r["product_id"])
        d = decisions.get(key, {"decision": "unreviewed", "notes": ""})
        counts[d["decision"]] = counts.get(d["decision"], 0) + 1
        price = f"${int(r['price_cents']) / 100:.2f}" if r["price_cents"] else "(none)"
        lines.append(
            f"| {r['store_name']} | {r['product_id']} | {r['raw_title'][:50]} | "
            f"{price} | {r['raw_size'] or '(none)'} | {d['decision']} | {d['notes']} |"
        )
    lines += [
        "",
        f"## Status: {counts.get('verified', 0)} verified, {counts.get('discrepancy', 0)} discrepancy, "
        f"{counts.get('unreviewed', 0)} unreviewed (of {len(rows)})",
        "",
        "Discrepancies, if any, are recorded with their `expected` values in "
        f"`{DECISIONS_PATH.name}` (source of truth for review state; this file is "
        "a rendered view of it).",
    ]
    return "\n".join(lines)


def main():
    if "--record" in sys.argv:
        i = sys.argv.index("--record")
        args = sys.argv[i + 1 :]
        if len(args) < 3:
            print("usage: manual_review.py --record STORE PRODUCT_ID DECISION [NOTES]")
            sys.exit(1)
        store, product_id, decision = args[0], args[1], args[2]
        notes = args[3] if len(args) > 3 else ""
        record_decision(store, product_id, decision, notes)
        print(f"Recorded {decision!r} for {store}/{product_id}")

    rows, decisions = generate()
    OUT_PATH.write_text(render(rows, decisions))
    print(f"{len(rows)} rows sampled; wrote {OUT_PATH.name}")


if __name__ == "__main__":
    main()
