"""Price history and swing detection over runs/<slug>_<store_id>/<ts>/items.csv.

Pure functions, no network. `price_watch_snapshot.py` writes snapshots and
calls `new_dips`; `price_watch_app.py` renders `detect_swings`.

Two rules from PRICE_MISTAKE_FINDER_PLAN.md shape everything here:

- Absence is not a price change. A crawl does not see every item every time,
  so an item missing from a snapshot is simply not observed; consecutive
  comparisons skip over the gap rather than treating it as a drop to zero.
- Eligibility is judged on the highest price ever observed for an item, so an
  item that falls below WATCH_MIN_PRICE_CENTS is still tracked -- that fall is
  the event being looked for.
"""
import csv
import json
from pathlib import Path

import price_watch_config as cfg


def to_cents(usd: str) -> int | None:
    if not usd:
        return None
    try:
        return round(float(usd) * 100)
    except ValueError:
        return None


def store_dir(slug: str, store_id: str, runs_root: Path = cfg.RUNS_ROOT) -> Path:
    return runs_root / f"{slug}_{store_id}"


def load_snapshots(sdir: Path) -> list:
    """[(snapshot_id, observed_at, {item_id: row})] oldest first. A snapshot
    directory without items.csv (a crawl that died before writing) is skipped."""
    out = []
    if not sdir.exists():
        return out
    for d in sorted(p for p in sdir.iterdir() if p.is_dir()):
        path = d / "items.csv"
        if not path.exists():
            continue
        with open(path, newline="") as f:
            rows = {r["item_id"]: r for r in csv.DictReader(f) if r.get("item_id")}
        observed_at = next(iter(rows.values()))["scraped_at"] if rows else d.name
        out.append((d.name, observed_at, rows))
    return out


def build_history(snapshots: list) -> dict:
    """{item_id: [observation, ...]} in snapshot order, observed snapshots only."""
    history = {}
    for snap_id, observed_at, rows in snapshots:
        for item_id, r in rows.items():
            price = to_cents(r.get("price_usd", ""))
            if price is None:
                continue
            history.setdefault(item_id, []).append(
                {
                    "snapshot_id": snap_id,
                    "observed_at": observed_at,
                    "price_cents": price,
                    "original_cents": to_cents(r.get("original_price_usd", "")),
                    "item_name": r.get("item_name", ""),
                    "category": r.get("category", ""),
                    "subcategory": r.get("subcategory", ""),
                    "stock_status": r.get("stock_status", ""),
                    "image_url": r.get("image_url", ""),
                }
            )
    return history


def is_swing(prev: int, new: int, rel=cfg.SWING_REL_THRESHOLD, abs_cents=cfg.SWING_ABS_THRESHOLD_CENTS) -> bool:
    delta = abs(new - prev)
    return prev > 0 and delta >= abs_cents and delta / prev >= rel


def swing_label(before: dict, after: dict) -> str:
    """How the change can be explained from what the listing itself shows."""
    was_sale, now_sale = before["original_cents"] is not None, after["original_cents"] is not None
    if now_sale and not was_sale:
        return "sale_start"
    if was_sale and not now_sale:
        return "sale_end"
    return "unexplained"


def detect_swings(
    history: dict,
    store: str,
    min_price=cfg.WATCH_MIN_PRICE_CENTS,
    rel=cfg.SWING_REL_THRESHOLD,
    abs_cents=cfg.SWING_ABS_THRESHOLD_CENTS,
    revert_tol=cfg.REVERT_TOLERANCE,
) -> list:
    swings = []
    for item_id, obs in history.items():
        if max(o["price_cents"] for o in obs) < min_price:
            continue
        for i in range(1, len(obs)):
            before, after = obs[i - 1], obs[i]
            prev, new = before["price_cents"], after["price_cents"]
            if not is_swing(prev, new, rel, abs_cents):
                continue
            reverted_at = next(
                (o["observed_at"] for o in obs[i + 1 :] if abs(o["price_cents"] - prev) <= revert_tol * prev),
                None,
            )
            swings.append(
                {
                    "store": store,
                    "item_id": item_id,
                    "item_name": after["item_name"],
                    "category": after["category"],
                    "subcategory": after["subcategory"],
                    "direction": "dip" if new < prev else "rise",
                    "before_cents": prev,
                    "after_cents": new,
                    "delta_cents": new - prev,
                    "delta_rel": (new - prev) / prev,
                    "before_at": before["observed_at"],
                    "after_at": after["observed_at"],
                    "snapshot_id": after["snapshot_id"],
                    "label": swing_label(before, after),
                    "original_cents": after["original_cents"],
                    "reverted_at": reverted_at,
                    "image_url": after["image_url"],
                }
            )
    swings.sort(key=lambda s: s["delta_rel"])
    return swings


def all_swings(runs_root: Path = cfg.RUNS_ROOT) -> tuple:
    """(swings across every tracked store, {store: [snapshot_ids]})."""
    swings, snaps = [], {}
    for name, slug, store_id in cfg.TRACKED_STORES:
        snapshots = load_snapshots(store_dir(slug, store_id, runs_root))
        snaps[name] = [(s[0], s[1], len(s[2])) for s in snapshots]
        swings.extend(detect_swings(build_history(snapshots), name))
    swings.sort(key=lambda s: s["delta_rel"])
    return swings, snaps


def alert_key(swing: dict) -> str:
    return f"{swing['store']}:{swing['item_id']}:{swing['snapshot_id']}"


def new_dips(swings: list, latest_snapshot: dict, already_alerted: set) -> list:
    """Dips that landed in each store's latest snapshot and have not been
    alerted before. `latest_snapshot` maps store -> snapshot_id."""
    return [
        s
        for s in swings
        if s["direction"] == "dip"
        and latest_snapshot.get(s["store"]) == s["snapshot_id"]
        and alert_key(s) not in already_alerted
    ]


def load_alerted(path: Path = cfg.ALERTS_PATH) -> set:
    if not path.exists():
        return set()
    with open(path) as f:
        return {json.loads(line)["key"] for line in f if line.strip()}


def record_alerts(dips: list, path: Path = cfg.ALERTS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        for s in dips:
            f.write(json.dumps({"key": alert_key(s), **s}) + "\n")


def watch_pages(page_items: dict, prices: dict, min_price=cfg.WATCH_MIN_PRICE_CENTS) -> list:
    """Pages that showed at least one item at or above min_price.

    `page_items` maps (category_slug, subcat_slug_or_None) -> [item_id];
    `prices` maps item_id -> highest observed price in cents.
    """
    keep = [page for page, ids in page_items.items() if any(prices.get(i, 0) >= min_price for i in ids)]
    return sorted(keep, key=lambda p: (p[0], p[1] or ""))


def fmt_usd(cents: int | None) -> str:
    return "" if cents is None else f"${cents / 100:,.2f}"
