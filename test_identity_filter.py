"""Tests for Checkpoint 4 S3: retrieval.filter_by_identity and
identity_filter_baseline.

Hand-built fixtures. Every assertion is on matcher behavior -- no test here
asserts a metric value, per CHECKPOINT_4_PLAN.md S3.
"""
import pandas as pd
import pytest

from retrieval import _identity_lookup, filter_by_identity


def _catalog(rows):
    return pd.DataFrame(rows)


def _row(store_id, product_id, title):
    return {"store_id": store_id, "product_id": product_id, "raw_title": title}


def _identity(store_id, product_id, brand, variant=""):
    return {"store_id": store_id, "product_id": product_id,
            "brand": brand, "variant_tokens": variant}


def _cand(row_index, store_id="s1", product_id="p1", score=1.0):
    return {"row": row_index, "store_id": store_id, "product_id": product_id, "score": score}


def _setup(brand, variant=""):
    catalog = _catalog([_row("s1", "p1", "Oatly Original Oat Milk")])
    lookup = _identity_lookup(pd.DataFrame([_identity("s1", "p1", brand, variant)]))
    return catalog, lookup


# --- exact mode -------------------------------------------------------------

def test_exact_brand_match_is_retained():
    catalog, lookup = _setup("Oatly")
    survivors, review = filter_by_identity(
        [_cand(0)], catalog, lookup, {"brand": "Oatly", "variant_tokens": frozenset()}, "exact")
    assert len(survivors) == 1
    assert review is False


def test_exact_brand_conflict_is_dropped():
    catalog, lookup = _setup("Oatly")
    survivors, review = filter_by_identity(
        [_cand(0)], catalog, lookup, {"brand": "Califia Farms", "variant_tokens": frozenset()}, "exact")
    assert survivors == []
    # A confirmed conflict is a rejection, not a review case.
    assert review is False


def test_exact_brand_match_is_case_insensitive():
    catalog, lookup = _setup("Oatly")
    survivors, _ = filter_by_identity(
        [_cand(0)], catalog, lookup, {"brand": "OATLY", "variant_tokens": frozenset()}, "exact")
    assert len(survivors) == 1


def test_exact_with_unknown_candidate_brand_raises_review_and_returns_nothing():
    """PROJECT_PLAN.md Checkpoint 4: "If key identity attributes are missing,
    request review." Unknown must not be treated as a match."""
    catalog, lookup = _setup(None)
    survivors, review = filter_by_identity(
        [_cand(0)], catalog, lookup, {"brand": "Oatly", "variant_tokens": frozenset()}, "exact")
    assert survivors == []
    assert review is True


def test_exact_with_no_requested_brand_raises_review():
    catalog, lookup = _setup("Oatly")
    survivors, review = filter_by_identity(
        [_cand(0)], catalog, lookup, {"brand": None, "variant_tokens": frozenset()}, "exact")
    assert survivors == []
    assert review is True


def test_exact_brand_match_but_variant_conflict_is_dropped():
    catalog, lookup = _setup("Oatly", "chocolate")
    survivors, review = filter_by_identity(
        [_cand(0)], catalog, lookup,
        {"brand": "Oatly", "variant_tokens": frozenset({"vanilla"})}, "exact")
    assert survivors == []
    assert review is False


def test_exact_variant_unknown_on_candidate_is_not_a_conflict():
    """An empty variant set is unknown, not a contradiction -- the brand still
    confirms, so the candidate survives."""
    catalog, lookup = _setup("Oatly", "")
    survivors, _ = filter_by_identity(
        [_cand(0)], catalog, lookup,
        {"brand": "Oatly", "variant_tokens": frozenset({"vanilla"})}, "exact")
    assert len(survivors) == 1


# --- flexible mode ----------------------------------------------------------

def test_flexible_allows_a_different_brand_when_none_requested():
    catalog, lookup = _setup("Friendly Farms")
    survivors, review = filter_by_identity(
        [_cand(0)], catalog, lookup, {"brand": None, "variant_tokens": frozenset()}, "flexible")
    assert len(survivors) == 1
    assert review is False


def test_flexible_enforces_a_brand_the_request_does_state():
    catalog, lookup = _setup("Friendly Farms")
    survivors, _ = filter_by_identity(
        [_cand(0)], catalog, lookup, {"brand": "Oatly", "variant_tokens": frozenset()}, "flexible")
    assert survivors == []


def test_flexible_with_unknown_candidate_brand_does_not_raise_review():
    """Unlike exact mode, flexible mode has no identity requirement to fail --
    an unknown brand is simply not a conflict."""
    catalog, lookup = _setup(None)
    survivors, review = filter_by_identity(
        [_cand(0)], catalog, lookup, {"brand": None, "variant_tokens": frozenset()}, "flexible")
    assert len(survivors) == 1
    assert review is False


def test_flexible_still_drops_a_variant_conflict():
    catalog, lookup = _setup("Friendly Farms", "whole")
    survivors, _ = filter_by_identity(
        [_cand(0)], catalog, lookup,
        {"brand": None, "variant_tokens": frozenset({"2%"})}, "flexible")
    assert survivors == []


# --- lookup robustness ------------------------------------------------------

def test_lookup_matches_across_int_and_str_product_ids():
    """The catalog carries product_id as int64 and the side-car CSV reads it
    back as str. A dtype mismatch here would miss every lookup and read as a
    coverage collapse rather than as a bug."""
    catalog = _catalog([{"store_id": 1742136, "product_id": 12345,
                         "raw_title": "Lucerne Whole Milk"}])
    lookup = _identity_lookup(pd.DataFrame([
        {"store_id": "1742136", "product_id": "12345",
         "brand": "Lucerne", "variant_tokens": "whole"}]))
    survivors, review = filter_by_identity(
        [_cand(0, store_id=1742136, product_id=12345)], catalog, lookup,
        {"brand": "Lucerne", "variant_tokens": frozenset({"whole"})}, "exact")
    assert len(survivors) == 1
    assert review is False


def test_candidate_missing_from_identity_table_is_review_in_exact_mode():
    catalog = _catalog([_row("s1", "p1", "Mystery Product")])
    survivors, review = filter_by_identity(
        [_cand(0)], catalog, {}, {"brand": "Oatly", "variant_tokens": frozenset()}, "exact")
    assert survivors == []
    assert review is True


def test_nan_brand_from_csv_is_treated_as_unknown():
    catalog = _catalog([_row("s1", "p1", "Mystery Product")])
    lookup = _identity_lookup(pd.DataFrame([
        {"store_id": "s1", "product_id": "p1", "brand": float("nan"), "variant_tokens": ""}]))
    survivors, review = filter_by_identity(
        [_cand(0)], catalog, lookup, {"brand": "Oatly", "variant_tokens": frozenset()}, "exact")
    assert survivors == []
    assert review is True


def test_multiple_candidates_partition_correctly():
    catalog = _catalog([
        _row("s1", "p1", "Oatly Original Oat Milk"),
        _row("s1", "p2", "Califia Farms Oat Milk"),
        _row("s1", "p3", "Unknown Oat Milk"),
    ])
    lookup = _identity_lookup(pd.DataFrame([
        _identity("s1", "p1", "Oatly"),
        _identity("s1", "p2", "Califia Farms"),
        _identity("s1", "p3", None),
    ]))
    cands = [_cand(0, product_id="p1"), _cand(1, product_id="p2"), _cand(2, product_id="p3")]
    survivors, review = filter_by_identity(
        cands, catalog, lookup, {"brand": "Oatly", "variant_tokens": frozenset()}, "exact")

    assert [c["product_id"] for c in survivors] == ["p1"]
    # p3's unknown brand still raises review even though p1 confirmed.
    assert review is True
