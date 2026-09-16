import csv

from build_normalized_catalog import DASHMART_ID, OUT_PATH, RUN_STORES


def _rows():
    with open(OUT_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_all_five_stores_present():
    rows = _rows()
    store_ids = {r["store_id"] for r in rows}
    expected = {store_id for _name, _prefix, store_id in RUN_STORES} | {DASHMART_ID}
    assert store_ids == expected


def test_no_duplicate_product_within_a_store_snapshot():
    rows = _rows()
    seen = set()
    for r in rows:
        key = (r["store_id"], r["snapshot_id"], r["product_id"])
        assert key not in seen, f"duplicate product row: {key}"
        seen.add(key)


def test_price_cents_is_integer_valued_when_present():
    rows = _rows()
    checked = 0
    for r in rows:
        if r["price_cents"]:
            int(r["price_cents"])  # raises if not a clean integer string
            checked += 1
    assert checked > 1000


def test_dashmart_uses_single_snapshot_not_merged_history():
    # Regression: this used to silently merge two scrape runs via a
    # keep-last-occurrence dedupe, producing 3,326 "current" products when
    # the actual latest run only had 3,022.
    rows = [r for r in _rows() if r["store_id"] == DASHMART_ID]
    assert len(rows) == len({r["product_id"] for r in rows})
    snapshot_ids = {r["snapshot_id"] for r in rows}
    assert len(snapshot_ids) == 1, f"expected one DashMart snapshot, got {snapshot_ids}"


def test_unresolved_and_variable_weight_rows_have_no_fabricated_size():
    rows = _rows()
    for r in rows:
        if r["parsing_status"] in ("unresolved", "variable_weight"):
            assert r["pkg_canonical_total"] == ""
            assert r["parsing_reason"] != ""


def test_brand_and_variant_are_explicitly_unknown_not_guessed():
    rows = _rows()
    assert all(r["brand"] == "" for r in rows[:200])
    assert all(r["variant"] == "" for r in rows[:200])


def test_bare_oz_liquids_are_flagged_not_reinterpreted():
    # Regression from code review: bare "oz" on a beverage parses as WEIGHT
    # per normalize.py's literal rule, which would silently reject it from
    # a volume-based basket comparison. The fix flags this for review; it
    # must NOT change pkg_dimension/pkg_canonical_unit to "fix" it, since
    # that would just be a different silent guess.
    rows = _rows()
    flagged = [r for r in rows if r["dimension_review_flag"] == "True"]
    assert len(flagged) > 0
    for r in flagged:
        assert r["pkg_dimension"] == "weight"
        assert r["pkg_unit"] == "oz"
        assert r["dimension_review_reason"]

    titles = {r["raw_title"] for r in flagged}
    assert any("Ripple" in t and "Milk" in t for t in titles)
    assert any("Modelo" in t for t in titles)
    assert any("FocusAid" in t for t in titles)


def test_dimension_review_flag_is_false_for_ordinary_weight_items():
    from build_normalized_catalog import _LIQUID_CATEGORIES, _LIQUID_HEAD_NOUNS

    rows = _rows()
    # A product that's obviously solid -- not in a liquid category, and none
    # of the module's own liquid head-noun keywords appear anywhere in the
    # title (a looser check than the real head-noun-position logic, so
    # it only excludes titles the function couldn't possibly flag) --
    # must not be flagged. Uses the module's actual constants rather than a
    # hand-copied word list, so this test can't drift out of sync with the
    # real vocabulary the way an earlier version of it did.
    solid_oz_rows = [
        r for r in rows
        if r["pkg_dimension"] == "weight" and r["pkg_unit"] == "oz"
        and r["raw_category"] not in _LIQUID_CATEGORIES
        and not (set(r["raw_title"].lower().split()) & _LIQUID_HEAD_NOUNS)
    ]
    assert solid_oz_rows
    assert all(r["dimension_review_flag"] == "False" for r in solid_oz_rows)
