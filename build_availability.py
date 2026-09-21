#!/usr/bin/env python3
"""Checkpoint 5, B3: join stock status back onto the frozen catalog.

`benchmark_catalog_frozen.csv` and `normalized_catalog.csv` carry no
availability column -- normalization dropped it -- so PROJECT_PLAN.md's
Checkpoint 5 requirements ("exclude explicitly out-of-stock items", "label
unknown availability as unverified") have nothing to read. The raw snapshots
each catalog row came from do carry `stock_status`, and this recovers it.

Output is a SIDE-CAR (`evaluation_v4/availability.csv`), never a write back
into the frozen catalog: `catalog_version` must not move, or every Checkpoint 3
and Checkpoint 4 label goes stale. Same discipline as
`evaluation_v3/catalog_identity.csv`.

THE STANDING RULE APPLIES: unknown is a third state. Roughly half of all rows
carry no stock field at all, so inferring "in stock" from a missing value would
fabricate the majority of the signal. Those rows are eligible but UNVERIFIED,
and a basket built from them says so.

Four eligibility states, not two:

    out_of_stock          excluded from a basket, and named in the explanation
    in_stock              eligible, verified, quantity not stated
    in_stock_limited      eligible, verified, with a known remaining count --
                          kept distinct because a basket needing 4 packages of
                          something with 3 left is a real case the engine
                          should be able to see
    unverified            eligible, but nothing is known

Usage:
    .venv/bin/python build_availability.py
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
CATALOG_PATH = HERE / "benchmark_catalog_frozen.csv"
RUNS_DIR = HERE / "runs"
LEGACY_DASHMART_CSV = HERE / "doordash_dashmart_1042759_items.csv"
OUT_DIR = HERE / "evaluation_v4"
OUT_PATH = OUT_DIR / "availability.csv"
MANIFEST_PATH = OUT_DIR / "availability_manifest.json"

OUT_OF_STOCK = "out_of_stock"
IN_STOCK = "in_stock"
IN_STOCK_LIMITED = "in_stock_limited"
UNVERIFIED = "unverified"

ELIGIBLE_STATES = {IN_STOCK, IN_STOCK_LIMITED, UNVERIFIED}
VERIFIED_STATES = {IN_STOCK, IN_STOCK_LIMITED}

# "In stock (3)", "In stock (20+)". The "+" form means "at least 20" -- the
# storefront caps the number it will show -- so the count is a LOWER BOUND and
# is flagged as one rather than being read as exactly 20.
_IN_STOCK_N_RE = re.compile(r"^in stock\s*\((\d+)(\+?)\)$", re.I)


@dataclass(frozen=True)
class Availability:
    state: str
    remaining: int | None = None
    remaining_is_lower_bound: bool = False
    raw: str | None = None

    @property
    def eligible(self) -> bool:
        return self.state in ELIGIBLE_STATES

    @property
    def verified(self) -> bool:
        return self.state in VERIFIED_STATES

    def covers(self, packages: int) -> bool:
        """Whether this row can supply `packages` units.

        True when the remaining count is unknown -- that is not a claim that it
        can, it is the absence of a claim that it cannot, which is the only
        honest reading of a field the storefront did not publish. A caller that
        needs certainty must check `verified` as well.
        """
        if self.state == OUT_OF_STOCK:
            return False
        if self.remaining is None:
            return True
        if self.remaining_is_lower_bound:
            # "In stock (20+)" is the storefront's display cap, not a count.
            # Asking for 25 of a "20+" row is not known to be impossible, and
            # this function reports impossibility, not certainty.
            return True
        return packages <= self.remaining


def classify(raw) -> Availability:
    """One `stock_status` cell -> an Availability. Null/blank -> unverified."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return Availability(UNVERIFIED)
    text = str(raw).strip()
    if not text or text.lower() in {"nan", "none"}:
        return Availability(UNVERIFIED)

    lowered = text.lower()
    if lowered == "out of stock":
        return Availability(OUT_OF_STOCK, raw=text)
    if lowered == "many in stock":
        return Availability(IN_STOCK, raw=text)

    m = _IN_STOCK_N_RE.match(text)
    if m:
        return Availability(IN_STOCK_LIMITED, remaining=int(m.group(1)),
                            remaining_is_lower_bound=bool(m.group(2)), raw=text)

    # An unrecognized value is UNVERIFIED, never eligible-verified and never
    # out-of-stock: a storefront string this code has not seen is not evidence
    # of anything. The raw text is carried so a new form shows up in the
    # manifest instead of disappearing.
    return Availability(UNVERIFIED, raw=text)


def snapshot_sources(catalog_df) -> dict:
    """{snapshot_id: path} for every snapshot the catalog actually draws on.

    Resolved from the catalog rather than by globbing `runs/`: there are 11
    snapshot directories on disk but only 5 that the frozen catalog was built
    from, and joining a row against a different run of the same store would be
    reading availability from the wrong moment.
    """
    sources = {}
    for snapshot_id in sorted(catalog_df["snapshot_id"].dropna().unique()):
        matches = sorted(RUNS_DIR.glob(f"*/{snapshot_id}/items.csv"))
        if matches:
            sources[snapshot_id] = matches[0]
        elif LEGACY_DASHMART_CSV.exists():
            # DashMart predates the runs/ layout and has no snapshot directory;
            # its rows come from the legacy top-level CSV.
            sources[snapshot_id] = LEGACY_DASHMART_CSV
    return sources


def build(catalog_df) -> tuple[pd.DataFrame, dict]:
    sources = snapshot_sources(catalog_df)
    missing = sorted(set(catalog_df["snapshot_id"].dropna().unique()) - set(sources))

    status_by_key = {}
    per_snapshot = {}
    for snapshot_id, path in sources.items():
        snap = pd.read_csv(path)
        n_dupes = int(snap["item_id"].duplicated().sum())
        for row in snap.itertuples():
            status_by_key[(snapshot_id, str(row.item_id))] = getattr(row, "stock_status", None)
        per_snapshot[snapshot_id] = {"source": str(path.relative_to(HERE)),
                                     "rows": len(snap), "duplicate_item_ids": n_dupes}

    records, unjoined, raw_counts = [], 0, {}
    for row in catalog_df.itertuples():
        key = (row.snapshot_id, str(row.product_id))
        if key in status_by_key:
            availability = classify(status_by_key[key])
        else:
            unjoined += 1
            availability = Availability(UNVERIFIED)
        raw_counts[availability.raw or "<null>"] = raw_counts.get(availability.raw or "<null>", 0) + 1
        records.append({
            "store_id": row.store_id,
            "product_id": row.product_id,
            "snapshot_id": row.snapshot_id,
            "state": availability.state,
            "remaining": availability.remaining,
            "remaining_is_lower_bound": availability.remaining_is_lower_bound,
            "raw_stock_status": availability.raw,
        })

    out = pd.DataFrame.from_records(records)
    by_state = out["state"].value_counts().to_dict()
    manifest = {
        "catalog_rows": int(len(catalog_df)),
        "snapshots_used": per_snapshot,
        "snapshot_ids_without_a_source": missing,
        "unjoined_rows": unjoined,
        "unjoined_rate": unjoined / len(catalog_df) if len(catalog_df) else None,
        "state_counts": {k: int(v) for k, v in by_state.items()},
        "state_rates": {k: int(v) / len(catalog_df) for k, v in by_state.items()},
        "raw_value_counts": dict(sorted(raw_counts.items(), key=lambda kv: -kv[1])),
        "by_store": {
            str(store): {k: int(v) for k, v in grp["state"].value_counts().items()}
            for store, grp in out.groupby("store_id")
        },
        "note": ("A row that failed to join is UNVERIFIED, not dropped and not "
                 "assumed in stock. unjoined_rate is reported rather than "
                 "swallowed so a broken join shows up as a number."),
    }
    return out, manifest


def load(path: Path = OUT_PATH) -> dict:
    """{(store_id, product_id): Availability}, both keys as str.

    Str keys for the same reason retrieval._identity_lookup uses them: the
    catalog carries product_id as int64 and a CSV reads it back as str, and a
    silent dtype mismatch here would make every lookup miss and turn the whole
    catalog 'unverified' -- which reads as a data problem rather than as the
    bug it is.
    """
    df = pd.read_csv(path)
    out = {}
    for row in df.itertuples():
        remaining = None if pd.isna(row.remaining) else int(row.remaining)
        raw = None if pd.isna(row.raw_stock_status) else str(row.raw_stock_status)
        out[(str(row.store_id), str(row.product_id))] = Availability(
            state=row.state, remaining=remaining,
            remaining_is_lower_bound=bool(row.remaining_is_lower_bound), raw=raw)
    return out


def lookup(availability_by_key: dict, store_id, product_id) -> Availability:
    """A missing key is UNVERIFIED, never an error and never assumed in stock."""
    return availability_by_key.get((str(store_id), str(product_id)), Availability(UNVERIFIED))


def basket_availability(states) -> dict:
    """Basket-level label. PROJECT_PLAN.md requires unknown availability to be
    labeled unverified; a basket whose lines are mostly unverified must not
    present a clean total, so the label lives at the basket level and not only
    per line."""
    states = list(states)
    n_verified = sum(1 for s in states if s.verified)
    n_unverified = sum(1 for s in states if s.state == UNVERIFIED)
    n_out = sum(1 for s in states if s.state == OUT_OF_STOCK)
    return {
        "n_lines": len(states),
        "n_verified": n_verified,
        "n_unverified": n_unverified,
        "n_out_of_stock": n_out,
        # Any unverified line makes the basket unverified. Not a majority vote:
        # one unpriceable-with-confidence line is enough to make the total a
        # best effort rather than a fact.
        "basket_state": "verified" if states and n_unverified == 0 and n_out == 0 else "unverified",
    }


def main():
    catalog_df = pd.read_csv(CATALOG_PATH)
    out, manifest = build(catalog_df)
    OUT_DIR.mkdir(exist_ok=True)
    out.to_csv(OUT_PATH, index=False)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"Wrote {OUT_PATH} ({len(out)} rows)")
    total = len(out)
    for state, n in sorted(manifest["state_counts"].items(), key=lambda kv: -kv[1]):
        print(f"  {state:18} {n:>6}  {n / total:6.1%}")
    print(f"  unjoined rows      {manifest['unjoined_rows']:>6}  "
          f"{manifest['unjoined_rate']:6.1%}")
    if manifest["snapshot_ids_without_a_source"]:
        print(f"  NO SOURCE for snapshots: {manifest['snapshot_ids_without_a_source']}")
    print(f"Wrote {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
