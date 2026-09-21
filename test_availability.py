"""Tests for build_availability.py (Checkpoint 5, B3).

The rule under test throughout: unknown is a third state. The failure this
guards against is an inference that would fabricate the majority of the signal,
since 49% of catalog rows carry no stock field at all.
"""
import pandas as pd
import pytest

import build_availability as ba


# --- classify: every observed value round-trips --------------------------------

def test_out_of_stock():
    got = ba.classify("Out of stock")
    assert got.state == ba.OUT_OF_STOCK
    assert not got.eligible


def test_many_in_stock_is_verified_without_a_count():
    got = ba.classify("Many in stock")
    assert got.state == ba.IN_STOCK
    assert got.eligible and got.verified
    assert got.remaining is None


def test_a_numeric_count_is_kept_not_folded_into_in_stock():
    """A basket needing 4 packages of something with 3 left is a real case."""
    got = ba.classify("In stock (3)")
    assert got.state == ba.IN_STOCK_LIMITED
    assert got.remaining == 3
    assert not got.remaining_is_lower_bound
    assert got.eligible and got.verified


def test_the_plus_form_is_a_lower_bound_not_an_exact_count():
    """'In stock (20+)' is the storefront's display cap. Reading it as exactly
    20 would invent a ceiling the data does not state."""
    got = ba.classify("In stock (20+)")
    assert got.remaining == 20
    assert got.remaining_is_lower_bound


@pytest.mark.parametrize("raw", [None, float("nan"), "", "   ", "nan", "None"])
def test_every_empty_form_is_unverified(raw):
    got = ba.classify(raw)
    assert got.state == ba.UNVERIFIED
    assert got.eligible          # eligible, but nothing is known
    assert not got.verified


def test_an_unrecognized_value_is_unverified_not_guessed():
    """A storefront string this code has not seen is not evidence of anything,
    and must not become eligible-verified or out-of-stock by accident."""
    got = ba.classify("Limited availability")
    assert got.state == ba.UNVERIFIED
    assert not got.verified
    assert got.raw == "Limited availability"     # carried so it surfaces in the manifest


def test_classification_is_case_insensitive():
    assert ba.classify("OUT OF STOCK").state == ba.OUT_OF_STOCK
    assert ba.classify("many in stock").state == ba.IN_STOCK


# --- the rule that must never break --------------------------------------------

def test_a_missing_stock_field_is_never_read_as_in_stock():
    """The single most important assertion in this file. 49% of rows are null;
    inferring in-stock would fabricate the majority of the signal."""
    for raw in (None, float("nan"), ""):
        assert ba.classify(raw).state != ba.IN_STOCK
        assert not ba.classify(raw).verified


def test_only_out_of_stock_is_ineligible():
    for raw in ("Many in stock", "In stock (1)", None, "something new"):
        assert ba.classify(raw).eligible, raw
    assert not ba.classify("Out of stock").eligible


# --- covers() -------------------------------------------------------------------

def test_a_known_count_cannot_cover_more_than_it_has():
    assert ba.classify("In stock (3)").covers(3)
    assert not ba.classify("In stock (3)").covers(4)


def test_an_unknown_count_does_not_deny_coverage():
    """covers() reports impossibility, not certainty -- absence of a published
    count is not evidence the shopper cannot buy four."""
    assert ba.classify(None).covers(4)
    assert ba.classify("Many in stock").covers(99)


def test_a_lower_bound_does_not_deny_coverage_above_the_cap():
    assert ba.classify("In stock (20+)").covers(25)


def test_out_of_stock_covers_nothing():
    assert not ba.classify("Out of stock").covers(1)


# --- lookup ---------------------------------------------------------------------

def test_a_missing_key_is_unverified_not_an_error():
    assert ba.lookup({}, 1, "p1").state == ba.UNVERIFIED


def test_lookup_keys_are_strings_on_both_sides():
    """The int64-vs-str dtype trap: a silent mismatch would turn the whole
    catalog unverified, which reads as a data problem rather than a bug."""
    table = {("1", "22646326037"): ba.Availability(ba.IN_STOCK)}
    assert ba.lookup(table, 1, 22646326037).state == ba.IN_STOCK


# --- basket-level labelling ------------------------------------------------------

def test_a_basket_with_any_unverified_line_is_unverified():
    got = ba.basket_availability([ba.Availability(ba.IN_STOCK),
                                  ba.Availability(ba.UNVERIFIED)])
    assert got["basket_state"] == "unverified"
    assert got["n_verified"] == 1 and got["n_unverified"] == 1


def test_a_fully_verified_basket_is_verified():
    got = ba.basket_availability([ba.Availability(ba.IN_STOCK),
                                  ba.Availability(ba.IN_STOCK_LIMITED, remaining=2)])
    assert got["basket_state"] == "verified"
    assert got["n_verified"] == 2


def test_an_out_of_stock_line_makes_the_basket_unverified_too():
    got = ba.basket_availability([ba.Availability(ba.IN_STOCK),
                                  ba.Availability(ba.OUT_OF_STOCK)])
    assert got["basket_state"] == "unverified"
    assert got["n_out_of_stock"] == 1


def test_an_empty_basket_is_not_verified():
    assert ba.basket_availability([])["basket_state"] == "unverified"


# --- the build, on a hand-made catalog -------------------------------------------

def _catalog():
    return pd.DataFrame([
        {"store_id": 1, "product_id": 111, "snapshot_id": "S1"},
        {"store_id": 1, "product_id": 222, "snapshot_id": "S1"},
        {"store_id": 1, "product_id": 999, "snapshot_id": "S1"},   # not in the snapshot
    ])


def test_build_joins_and_reports_the_failures(tmp_path, monkeypatch):
    snap = tmp_path / "runs" / "store_1" / "S1"
    snap.mkdir(parents=True)
    pd.DataFrame([{"item_id": 111, "stock_status": "Many in stock"},
                  {"item_id": 222, "stock_status": "Out of stock"}]
                 ).to_csv(snap / "items.csv", index=False)
    monkeypatch.setattr(ba, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(ba, "LEGACY_DASHMART_CSV", tmp_path / "nonexistent.csv")
    monkeypatch.setattr(ba, "HERE", tmp_path)

    out, manifest = ba.build(_catalog())
    by_pid = {str(r.product_id): r.state for r in out.itertuples()}
    assert by_pid == {"111": ba.IN_STOCK, "222": ba.OUT_OF_STOCK, "999": ba.UNVERIFIED}
    assert manifest["unjoined_rows"] == 1
    assert manifest["unjoined_rate"] == pytest.approx(1 / 3)


def test_an_unjoined_row_is_unverified_not_dropped(tmp_path, monkeypatch):
    """Dropping it would silently shrink a store's catalog and make that store
    look like it simply does not stock the item."""
    snap = tmp_path / "runs" / "store_1" / "S1"
    snap.mkdir(parents=True)
    pd.DataFrame([{"item_id": 111, "stock_status": "Many in stock"}]).to_csv(
        snap / "items.csv", index=False)
    monkeypatch.setattr(ba, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(ba, "LEGACY_DASHMART_CSV", tmp_path / "nonexistent.csv")
    monkeypatch.setattr(ba, "HERE", tmp_path)

    out, _ = ba.build(_catalog())
    assert len(out) == 3


# --- the real side-car, if it has been built ---------------------------------------

def test_the_built_sidecar_covers_every_catalog_row_exactly_once():
    if not ba.OUT_PATH.exists():
        pytest.skip("availability.csv not built")
    out = pd.read_csv(ba.OUT_PATH)
    catalog = pd.read_csv(ba.CATALOG_PATH, usecols=["store_id", "product_id"])
    assert len(out) == len(catalog)
    assert not out.duplicated(subset=["store_id", "product_id"]).any()


def test_the_sidecar_never_writes_back_into_the_frozen_catalog():
    """catalog_version must not move, or every Checkpoint 3 and 4 label goes
    stale. The side-car is a separate file and the catalog has no stock column."""
    catalog = pd.read_csv(ba.CATALOG_PATH, nrows=1)
    assert "stock_status" not in catalog.columns
    assert "state" not in catalog.columns
