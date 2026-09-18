"""Tests for build_candidate_pool.py: multi-source retention, overflow
trimming that protects reference/hard_negative candidates, deterministic
tie-breaking, and the draft-label heuristic's explicit rules."""
import pandas as pd
import pytest

import benchmark_config as cfg
from build_candidate_pool import _cap_pool, _merge, _pool_query_text, draft_label
from parse_query import parse_shopping_line


def _row(store_id=1, product_id="p1", title="whole milk", dimension="volume",
         dimension_review_flag=False):
    return pd.Series({
        "store_id": store_id, "product_id": product_id, "raw_title": title,
        "pkg_dimension": dimension, "dimension_review_flag": dimension_review_flag,
    })


def _request(text="1 gal whole milk", brand=None, variant=None, substitutions=None):
    return {
        "text": text,
        "expected": {"brand": brand, "variant": variant, "allowed_substitutions": substitutions or {}},
    }


# --- _merge: multi-source retention ------------------------------------------

def test_merge_retains_all_sources_for_same_candidate():
    candidates = {}
    _merge(candidates, 1, "p1", "lexical", score=0.8)
    _merge(candidates, 1, "p1", "synonym", score=0.5)
    c = candidates[(1, "p1")]
    assert sorted(c["sources"]) == ["lexical", "synonym"]
    assert c["scores"] == {"lexical": 0.8, "synonym": 0.5}


def test_merge_does_not_duplicate_source():
    candidates = {}
    _merge(candidates, 1, "p1", "reference")
    _merge(candidates, 1, "p1", "reference")
    assert candidates[(1, "p1")]["sources"] == ["reference"]


# --- _cap_pool: overflow trimming + protection -------------------------------

def test_cap_pool_never_trims_reference_or_hard_negative():
    candidates = {}
    for i in range(20):
        _merge(candidates, 1, f"filler{i}", "lexical", score=1.0 - i * 0.01)
    _merge(candidates, 1, "ref1", "reference")
    _merge(candidates, 1, "neg1", "hard_negative")

    capped = _cap_pool(candidates, max_pool_size=5)

    assert (1, "ref1") in capped
    assert (1, "neg1") in capped
    assert len(capped) == 5  # 2 protected + 3 highest-scoring fillers


def test_cap_pool_trims_lowest_score_first_with_deterministic_tie_break():
    candidates = {}
    _merge(candidates, 2, "p1", "lexical", score=0.5)  # tie on score with next
    _merge(candidates, 1, "p1", "lexical", score=0.5)  # same score, lower store_id -- kept first
    _merge(candidates, 1, "p2", "lexical", score=0.9)  # highest score

    capped = _cap_pool(candidates, max_pool_size=2)

    assert set(capped.keys()) == {(1, "p2"), (1, "p1")}


def test_cap_pool_no_padding_below_cap():
    candidates = {}
    _merge(candidates, 1, "p1", "lexical", score=0.9)
    capped = _cap_pool(candidates, max_pool_size=15)
    assert len(capped) == 1


# --- draft_label: explicit rules ---------------------------------------------

def test_draft_label_dimension_mismatch_is_incorrect():
    row = _row(dimension="weight")
    label, reason = draft_label(row, _request("1 gal whole milk"))
    assert label == "Incorrect"
    assert "dimension" in reason


def test_draft_label_dimension_mismatch_with_review_flag_is_needs_clarification():
    # A dimension_review_flag=True candidate must NOT be auto-Incorrect just
    # because the literal parsed dimension disagrees -- this is exactly the
    # case the flag exists for (see build_normalized_catalog.py).
    row = _row(dimension="weight", dimension_review_flag=True, title="milk 12 oz bottle")
    label, reason = draft_label(row, _request("1 gal whole milk"))
    assert label == "Needs clarification"


def test_draft_label_brand_mismatch_is_incorrect():
    row = _row(title="Silk Almond Milk", dimension="volume")
    label, reason = draft_label(row, _request("64 fl oz Friendly Farms Almond Milk", brand="Friendly Farms"))
    assert label == "Incorrect"
    assert "brand" in reason


def test_draft_label_brand_mismatch_not_flagged_when_substitution_allowed():
    row = _row(title="Silk Almond Milk", dimension="volume")
    label, reason = draft_label(
        row, _request("64 fl oz almond milk", brand="Friendly Farms", substitutions={"brand": "any"})
    )
    assert label == "Acceptable"


# --- _pool_query_text: strips quantity words that pollute lexical search --

def test_pool_query_text_drops_quantity_word_that_collides_with_products():
    # Pilot audit: "a dozen large eggs, ..." literally matched "Dozen
    # Roses" via lexical search because the raw text (with "dozen" in it)
    # was used as the TF-IDF query. The cleaned query must not contain it.
    structured = parse_shopping_line("a dozen large eggs, any brand is fine")
    query = _pool_query_text(structured, "a dozen large eggs, any brand is fine")
    assert "dozen" not in query.lower()
    assert "eggs" in query.lower()


def test_pool_query_text_falls_back_to_raw_text_when_product_type_empty():
    structured = {"product_type": None, "modifiers": []}
    assert _pool_query_text(structured, "some milk") == "some milk"


def test_draft_label_defaults_to_acceptable_with_no_conflict():
    row = _row(title="Friendly Farms Whole Milk", dimension="volume")
    label, reason = draft_label(row, _request("1 gal whole milk"))
    assert label == "Acceptable"


def test_draft_label_missing_dimension_is_not_treated_as_a_mismatch():
    # A variable-weight row has pkg_dimension == NaN in the real catalog.
    # bool(float('nan')) is True in Python, so an unguarded truthy check
    # would misreport "unknown" as "confirmed mismatch" -- this must not
    # auto-Incorrect a candidate just because its dimension is unrecorded.
    row = _row(title="Boneless Chicken Breast", dimension=float("nan"))
    label, reason = draft_label(row, _request("2 lb chicken breast"))
    assert label != "Incorrect"
