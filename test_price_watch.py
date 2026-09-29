"""price_watch: history, swing detection, alert dedupe, watch-list upkeep.

Histories are hand-built; every expected number is written out, not derived
from the code under test.
"""
import csv

import pytest

import price_watch as pw
from doordash_dashmart_scraper import CSV_FIELDNAMES
from price_watch_snapshot import dip_message, update_watch_pages


def snap(tmp_path, ts, rows):
    d = tmp_path / "runs" / "target_2833969" / ts
    d.mkdir(parents=True)
    with open(d / "items.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        w.writeheader()
        for item_id, price, orig in rows:
            w.writerow({"scraped_at": ts, "item_id": item_id, "item_name": f"item {item_id}", "price_usd": price, "original_price_usd": orig})


def swings_for(tmp_path, snapshots):
    for ts, rows in snapshots:
        snap(tmp_path, ts, rows)
    history = pw.build_history(pw.load_snapshots(tmp_path / "runs" / "target_2833969"))
    return pw.detect_swings(history, "Target")


def test_dip_over_both_thresholds(tmp_path):
    # $100 -> $70: -30%, -$30. Clears 20% and $10.
    [s] = swings_for(tmp_path, [("t1", [("a", "100.00", "")]), ("t2", [("a", "70.00", "")])])
    assert (s["direction"], s["before_cents"], s["after_cents"], s["delta_cents"]) == ("dip", 10000, 7000, -3000)
    assert s["delta_rel"] == pytest.approx(-0.30)
    assert s["label"] == "unexplained" and s["reverted_at"] is None


def test_relative_floor_alone_is_not_enough(tmp_path):
    # $600 -> $500 is -$100 but only -16.7%.
    assert swings_for(tmp_path, [("t1", [("a", "600.00", "")]), ("t2", [("a", "500.00", "")])]) == []


def test_absolute_floor_alone_is_not_enough():
    # Any eligible item (>= $50) that moves 20% moves >= $10, so the $10 floor
    # only bites below $50 -- tested on the threshold function directly.
    # $30 -> $38 is +26.7% but +$8; $30 -> $40 is +33.3% and +$10.
    assert not pw.is_swing(3000, 3800)
    assert pw.is_swing(3000, 4000)


def test_eligibility_uses_highest_observed_price(tmp_path):
    # $60 -> $35 falls below $50 but the $60 observation keeps it tracked.
    [s] = swings_for(tmp_path, [("t1", [("a", "60.00", "")]), ("t2", [("a", "35.00", "")])])
    assert s["after_cents"] == 3500
    # $45 -> $30 never reached $50: not tracked.
    assert swings_for(tmp_path / "x", [("t1", [("b", "45.00", "")]), ("t2", [("b", "30.00", "")])]) == []


def test_absence_is_not_a_change(tmp_path):
    # Missing from t2; t1 -> t3 compared directly, and unchanged, so no swing.
    got = swings_for(tmp_path, [("t1", [("a", "80.00", "")]), ("t2", [("z", "99.00", "")]), ("t3", [("a", "80.00", "")])])
    assert got == []


def test_gap_then_change_compares_across_gap(tmp_path):
    [s] = swings_for(tmp_path, [("t1", [("a", "80.00", "")]), ("t2", []), ("t3", [("a", "40.00", "")])])
    assert (s["before_at"], s["after_at"]) == ("t1", "t3")


def test_sale_labels(tmp_path):
    got = swings_for(
        tmp_path,
        [("t1", [("a", "100.00", "")]), ("t2", [("a", "70.00", "100.00")]), ("t3", [("a", "100.00", "")])],
    )
    assert [(s["direction"], s["label"]) for s in got] == [("dip", "sale_start"), ("rise", "sale_end")]


def test_revert_detected(tmp_path):
    # $200 -> $20 -> $198: back within 5% of $200.
    got = swings_for(
        tmp_path,
        [("t1", [("a", "200.00", "")]), ("t2", [("a", "20.00", "")]), ("t3", [("a", "198.00", "")])],
    )
    dip = next(s for s in got if s["direction"] == "dip")
    assert dip["reverted_at"] == "t3"


def test_new_dips_only_latest_snapshot_and_not_repeated():
    s1 = {"store": "Target", "item_id": "a", "snapshot_id": "t2", "direction": "dip"}
    s2 = {"store": "Target", "item_id": "b", "snapshot_id": "t3", "direction": "dip"}
    s3 = {"store": "Target", "item_id": "c", "snapshot_id": "t3", "direction": "rise"}
    assert pw.new_dips([s1, s2, s3], {"Target": "t3"}, set()) == [s2]
    assert pw.new_dips([s1, s2, s3], {"Target": "t3"}, {"Target:b:t3"}) == []


def test_alert_roundtrip(tmp_path):
    path = tmp_path / "alerts.jsonl"
    s = {"store": "Best Buy", "item_id": "9", "snapshot_id": "t5", "direction": "dip"}
    pw.record_alerts([s], path)
    assert pw.load_alerted(path) == {"Best Buy:9:t5"}


def test_watch_pages_keeps_pages_with_expensive_item():
    page_items = {("snacks-758", "chips-765"): ["a", "b"], ("electronics-27441", None): ["c"], ("toys-8821", "lego-1"): []}
    prices = {"a": 499, "b": 899, "c": 12999}
    assert pw.watch_pages(page_items, prices) == [("electronics-27441", None)]


def test_watch_page_dropped_only_after_two_cold_discoveries():
    state = {"Target": [{"category": "toys-8821", "subcat": "lego-1", "misses": 0}]}
    cold = {("toys-8821", "lego-1"): ["a"]}
    state = update_watch_pages(state, "Target", cold, {"a": 999})
    assert state["Target"][0]["misses"] == 1
    state = update_watch_pages(state, "Target", cold, {"a": 999})
    assert state["Target"] == []


def test_watch_page_not_charged_a_miss_when_not_crawled():
    # A page absent from this discovery (e.g. its fetch failed) keeps its count.
    state = {"Target": [{"category": "toys-8821", "subcat": "lego-1", "misses": 1}]}
    state = update_watch_pages(state, "Target", {}, {})
    assert state["Target"][0]["misses"] == 1


def test_dip_message_names_biggest_drop():
    dips = [
        {"store": "Target", "item_name": "Lamp", "before_cents": 6000, "after_cents": 4500, "delta_rel": -0.25},
        {"store": "Best Buy", "item_name": "TV", "before_cents": 99999, "after_cents": 49999, "delta_rel": -0.50},
    ]
    title, body = dip_message(dips)
    assert title == "2 price dips"
    assert body == "Biggest: Best Buy: TV $999.99 -> $499.99 (-50%)"
