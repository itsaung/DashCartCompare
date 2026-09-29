#!/usr/bin/env python3
"""Snapshot the tracked stores, then alert on new price dips.

    .venv/bin/python price_watch_snapshot.py --discover   # full crawl, rebuilds watch_pages.json
    .venv/bin/python price_watch_snapshot.py              # watch crawl: only pages in watch_pages.json
    .venv/bin/python price_watch_snapshot.py --store Target --no-notify

Each store gets a new runs/<slug>_<store_id>/<ts>/ directory holding items.csv
(same schema as the scraper) and pages.json (which page each item came from).
Stores run one after the other, never in parallel.

Rate limiting: the first 403 on a store stops that store's crawl at once --
a 403 here is a block, not a rate limit, and retrying into it is how a block
gets longer (see doordash_scrape_findings.md, 2026-09-28). 429s get the
scraper's usual backoff plus one slow sequential retry pass.
"""
import argparse
import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from threading import Event, Lock

import requests

import price_watch as pw
import price_watch_config as cfg
from doordash_dashmart_scraper import (
    BASE_HEADERS,
    CSV_FIELDNAMES,
    Pacer,
    append_csv,
    category_display_name,
    discover_categories,
    extract_flight,
    extract_items,
    fetch,
    flight_subcategories,
    item_row,
    merge_item,
)


def page_url(store_id: str, cat: str, sub: str | None) -> str:
    base = f"https://www.doordash.com/convenience/store/{store_id}/category/{cat}"
    return f"{base}/sub-category/{sub}" if sub else base


def fetch_page(session, store_id, cat, sub, pacer):
    """(items, subcat_slugs, failure_log_or_None) for one page. Sub-category
    slugs come back too, so discovery does not fetch each category page twice."""
    resp, log = fetch(session, page_url(store_id, cat, sub), pacer)
    if resp is None or resp.status_code >= 400:
        return [], [], {"category": cat, "subcat": sub, **log}
    combined = extract_flight(resp.text)
    items = extract_items(combined, category_display_name(cat), category_display_name(sub) if sub else "")
    subs = []
    if not sub:
        found = set(re.findall(r"sub-category/([a-zA-Z0-9%\-]+)", resp.text))
        subs = sorted(found | flight_subcategories(combined, cat))
    return items, subs, None


def crawl(store_id: str, pages: list, discover: bool) -> dict:
    """Fetch `pages` [(cat, sub_or_None)]. In discover mode, category pages
    also queue their sub-category pages. Stops on the first 403."""
    session = requests.Session()
    session.headers.update(BASE_HEADERS)
    pacer = Pacer(min_interval=cfg.WATCH_MIN_INTERVAL)
    blocked = Event()
    lock = Lock()
    item_map, page_items, failures = {}, {}, []

    def run(page):
        if blocked.is_set():
            with lock:
                failures.append({"category": page[0], "subcat": page[1], "status": "skipped_after_403"})
            return []
        items, subs, err = fetch_page(session, store_id, page[0], page[1], pacer)
        with lock:
            if err:
                failures.append(err)
                if err.get("status") == 403:
                    blocked.set()
            page_items[page] = sorted({it["item_id"] for it in items})
            for it in items:
                if it["item_id"] in item_map:
                    merge_item(item_map[it["item_id"]], it)
                else:
                    item_map[it["item_id"]] = it
        return [(page[0], s) for s in subs] if discover else []

    with ThreadPoolExecutor(max_workers=cfg.WATCH_CONCURRENCY) as pool:
        pending = {pool.submit(run, p) for p in pages}
        while pending:
            fut = next(as_completed(pending))
            pending.remove(fut)
            for child in fut.result():
                pending.add(pool.submit(run, child))

    first_pass = len(failures)
    if failures and not blocked.is_set():
        queue = [(e["category"], e["subcat"]) for e in failures]
        failures.clear()
        while queue:
            page = queue.pop(0)
            time.sleep(2)
            queue.extend(run(page))  # a recovered category page still yields its sub-categories
    return {
        "item_map": item_map,
        "page_items": page_items,
        "first_pass_failures": first_pass,
        "failures": failures,
        "blocked": blocked.is_set(),
    }


def load_watch_pages() -> dict:
    if not cfg.WATCH_PAGES_PATH.exists():
        return {}
    return json.loads(cfg.WATCH_PAGES_PATH.read_text())


def update_watch_pages(state: dict, store: str, page_items: dict, max_prices: dict) -> dict:
    """Pages with a >= $50 item are (re)added with misses=0. A previously
    watched page without one gets misses+1 and is dropped at 2 -- two discovery
    cycles in a row, per the plan -- so one noisy crawl cannot drop a page."""
    hot = {tuple(p) for p in pw.watch_pages(page_items, max_prices)}
    entries = {(e["category"], e["subcat"]): e for e in state.get(store, [])}
    for page in hot:
        entries[page] = {"category": page[0], "subcat": page[1], "misses": 0}
    for page, e in list(entries.items()):
        if page not in hot and page in page_items:
            e["misses"] = e.get("misses", 0) + 1
            if e["misses"] >= 2:
                del entries[page]
    state[store] = sorted(entries.values(), key=lambda e: (e["category"], e["subcat"] or ""))
    return state


def write_snapshot(slug, store_id, name, mode, result, started, ts) -> dict:
    run_dir = pw.store_dir(slug, store_id) / ts
    run_dir.mkdir(parents=True, exist_ok=True)
    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = sorted((item_row(it, scraped_at) for it in result["item_map"].values()), key=lambda r: (r["category"], r["item_name"]))
    append_csv(run_dir / "items.csv", rows, CSV_FIELDNAMES)
    pages = [{"category": c, "subcat": s, "item_ids": ids} for (c, s), ids in result["page_items"].items()]
    (run_dir / "pages.json").write_text(json.dumps({"mode": mode, "pages": pages}, indent=1))
    status = "BLOCKED" if result["blocked"] else ("INCOMPLETE" if result["failures"] else "COMPLETE")
    entry = {
        "store": name,
        "store_id": store_id,
        "snapshot_id": ts,
        "mode": mode,
        "status": status,
        "started_at": started,
        "scraped_at": scraped_at,
        "elapsed_seconds": round(time.monotonic() - result["t0"], 1),
        "pages_fetched": len(result["page_items"]),
        "first_pass_failures": result["first_pass_failures"],
        "still_failed": len(result["failures"]),
        "failure_statuses": sorted({str(f.get("status")) for f in result["failures"]}),
        "items": len(rows),
    }
    (run_dir / "items.summary.json").write_text(json.dumps(entry, indent=1))
    cfg.CRAWL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg.CRAWL_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def notify(title: str, message: str) -> None:
    """macOS Notification Center via osascript; quotes stripped rather than escaped."""
    clean = lambda s: s.replace('"', "'").replace("\\", "")
    script = f'display notification "{clean(message)}" with title "{clean(title)}" sound name "Glass"'
    subprocess.run(["osascript", "-e", script], check=False)


def dip_message(dips: list) -> tuple:
    top = min(dips, key=lambda s: s["delta_rel"])
    line = (
        f"{top['store']}: {top['item_name'][:60]} "
        f"{pw.fmt_usd(top['before_cents'])} -> {pw.fmt_usd(top['after_cents'])} ({top['delta_rel']:+.0%})"
    )
    if len(dips) == 1:
        return "Price dip", line
    return f"{len(dips)} price dips", f"Biggest: {line}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--discover", action="store_true", help="full crawl; rebuild watch_pages.json")
    ap.add_argument("--store", help="only this tracked store (display name)")
    ap.add_argument("--no-notify", action="store_true")
    args = ap.parse_args()

    stores = [s for s in cfg.TRACKED_STORES if not args.store or s[0] == args.store]
    if not stores:
        raise SystemExit(f"unknown store {args.store!r}")
    state = load_watch_pages()
    mode = "discover" if args.discover else "watch"
    latest = {}

    for name, slug, store_id in stores:
        started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        if args.discover:
            session = requests.Session()
            session.headers.update(BASE_HEADERS)
            pages = [(c, None) for c in discover_categories(session, store_id, Pacer(cfg.WATCH_MIN_INTERVAL))]
        else:
            pages = [(e["category"], e["subcat"]) for e in state.get(name, [])]
            if not pages:
                print(f"{name}: no watch pages yet -- run with --discover first")
                continue
        print(f"{name}: {mode} crawl of {len(pages)} {'categories' if args.discover else 'pages'}...")
        t0 = time.monotonic()
        result = crawl(store_id, pages, args.discover)
        result["t0"] = t0
        entry = write_snapshot(slug, store_id, name, mode, result, started, ts)
        latest[name] = ts
        print(f"  {entry['status']}: {entry['items']} items from {entry['pages_fetched']} pages in {entry['elapsed_seconds']}s")

        if args.discover and not result["blocked"]:
            history = pw.build_history(pw.load_snapshots(pw.store_dir(slug, store_id)))
            max_prices = {i: max(o["price_cents"] for o in obs) for i, obs in history.items()}
            state = update_watch_pages(state, name, result["page_items"], max_prices)
            cfg.WATCH_PAGES_PATH.write_text(json.dumps(state, indent=1))
            print(f"  watch list: {len(state[name])} pages")
        if result["blocked"]:
            print("  403 received -- stopped; watch list left unchanged")
            if not args.no_notify:
                notify("Price watch blocked", f"{name}: DoorDash returned 403; crawl stopped early.")

    swings, _ = pw.all_swings()
    dips = pw.new_dips(swings, latest, pw.load_alerted())
    print(f"{len(dips)} new dips")
    if dips:
        pw.record_alerts(dips)
        if not args.no_notify:
            notify(*dip_message(dips))


if __name__ == "__main__":
    main()
