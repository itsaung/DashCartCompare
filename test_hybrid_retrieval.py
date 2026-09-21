"""Tests for hybrid_retrieval.py.

Every RRF expectation below is computed by hand from the formula
1/(k + rank), not read off a run. With RRF_K = 60 the arithmetic is small
enough to check on paper, which is the point.
"""
import numpy as np
import pandas as pd
import pytest

import checkpoint4_config as c4
import hybrid_retrieval as hr


def _cand(product_id, score=1.0, store_id="s1", row=0):
    return {"store_id": store_id, "product_id": product_id, "score": score, "row": row}


def _catalog(rows):
    return pd.DataFrame(rows)


def _row(store_id, product_id, title, dimension=None):
    return {"store_id": store_id, "product_id": product_id, "raw_title": title,
            "raw_category": "Grocery", "pkg_dimension": dimension,
            "pkg_canonical_unit": None, "pkg_canonical_total": None, "pkg_count": 1.0}


# --- RRF arithmetic ---------------------------------------------------------

def test_rrf_score_is_one_over_k_plus_rank():
    """A candidate ranked 1 by a single retriever scores exactly 1/(60+1)."""
    out = hr.reciprocal_rank_fusion([[_cand("p1")]])
    assert out[0]["score"] == pytest.approx(1.0 / 61)


def test_rrf_sums_contributions_across_retrievers():
    """Ranked 1 by one and 2 by the other: 1/61 + 1/62."""
    out = hr.reciprocal_rank_fusion([[_cand("p1")], [_cand("p9"), _cand("p1")]])
    p1 = next(c for c in out if c["product_id"] == "p1")
    assert p1["score"] == pytest.approx(1.0 / 61 + 1.0 / 62)


def test_consistent_middling_beats_one_strong_one_absent():
    """The behavior RRF is chosen for: a candidate both retrievers like
    moderately outranks one that only a single retriever ranks first.

    List A: solo, x1, x2, x3, both   -> solo rank 1, both rank 5
    List B: y1, y2, y3, y4, both     -> both rank 5, solo absent

    both = 1/65 + 1/65 = 0.030769;  solo = 1/61 = 0.016393
    """
    a_list = [_cand("solo")] + [_cand(f"x{i}") for i in range(1, 4)] + [_cand("both")]
    b_list = [_cand(f"y{i}") for i in range(1, 5)] + [_cand("both")]
    out = hr.reciprocal_rank_fusion([a_list, b_list])

    both = next(c for c in out if c["product_id"] == "both")
    solo = next(c for c in out if c["product_id"] == "solo")
    assert both["score"] == pytest.approx(2.0 / 65)
    assert solo["score"] == pytest.approx(1.0 / 61)
    assert both["score"] > solo["score"]
    assert out[0]["product_id"] == "both"


def test_rank_1_in_both_beats_rank_1_in_one():
    out = hr.reciprocal_rank_fusion([[_cand("p1")], [_cand("p1")]])
    assert out[0]["score"] == pytest.approx(2.0 / 61)


def test_candidate_in_only_one_list_is_kept():
    """Not dropped -- a candidate one retriever misses entirely can still
    surface, which is half the reason to fuse at all."""
    out = hr.reciprocal_rank_fusion([[_cand("p1")], [_cand("p2")]])
    assert {c["product_id"] for c in out} == {"p1", "p2"}


def test_fusion_replaces_the_retriever_score():
    """The surviving 'score' must be the RRF score, not a leftover cosine --
    otherwise a downstream threshold would be comparing the wrong quantity."""
    out = hr.reciprocal_rank_fusion([[_cand("p1", score=0.97)]])
    assert out[0]["score"] == pytest.approx(1.0 / 61)
    assert out[0]["score"] != pytest.approx(0.97)


def test_ties_break_on_store_then_product_id():
    out = hr.reciprocal_rank_fusion([[_cand("p3", store_id="s2"), _cand("p1", store_id="s1")],
                                     [_cand("p1", store_id="s1"), _cand("p3", store_id="s2")]])
    # Both earn 1/61 + 1/62, so the tie-break decides.
    assert [(c["store_id"], c["product_id"]) for c in out] == [("s1", "p1"), ("s2", "p3")]


def test_top_k_truncates_after_fusion():
    lists = [[_cand(f"p{i}") for i in range(10)]]
    assert len(hr.reciprocal_rank_fusion(lists, top_k=3)) == 3


def test_empty_inputs_fuse_to_empty():
    assert hr.reciprocal_rank_fusion([[], []]) == []


def test_k_is_configurable_and_defaults_to_config():
    out = hr.reciprocal_rank_fusion([[_cand("p1")]], k=9)
    assert out[0]["score"] == pytest.approx(1.0 / 10)
    assert c4.RRF_K == 60


def test_larger_k_compresses_rank_differences():
    """Sanity check on what k does: a bigger k shrinks the gap between rank 1
    and rank 2, which is why it is a declared convention rather than a free
    knob to tune."""
    small = hr.reciprocal_rank_fusion([[_cand("a"), _cand("b")]], k=1)
    large = hr.reciprocal_rank_fusion([[_cand("a"), _cand("b")]], k=1000)
    small_gap = small[0]["score"] - small[1]["score"]
    large_gap = large[0]["score"] - large[1]["score"]
    assert large_gap < small_gap


# --- gate stack -------------------------------------------------------------

def test_gates_apply_in_declared_order_and_drop_a_dimension_conflict():
    catalog = _catalog([_row("s1", "p1", "milk", dimension="weight")])
    structured = {"dimension": "volume"}
    survivors, review = hr._apply_gates("1 gallon whole milk", structured,
                                        [_cand("p1", row=0)], catalog)
    assert survivors == []
    assert review is False


def test_gates_keep_an_unknown_dimension():
    catalog = _catalog([_row("s1", "p1", "milk", dimension=None)])
    survivors, _ = hr._apply_gates("1 gallon whole milk", {"dimension": "volume"},
                                   [_cand("p1", row=0)], catalog)
    assert len(survivors) == 1


def test_identity_gate_raises_review_for_an_unconfirmable_exact_request():
    catalog = _catalog([_row("s1", "p1", "Mystery Oat Milk")])
    survivors, review = hr._apply_gates(
        "0.5 gal Oatly Original Oat Milk", {"dimension": None}, [_cand("p1", row=0)],
        catalog, identity_lookup={}, brand_lexicon={}, mode="exact")
    assert survivors == []
    assert review is True


def test_identity_gate_is_skipped_when_no_lookup_is_given():
    """hybrid_dimension_size_filter must not silently acquire an identity gate
    -- that is what makes it comparable to v2 and S4."""
    catalog = _catalog([_row("s1", "p1", "Mystery Oat Milk")])
    survivors, review = hr._apply_gates("0.5 gal Oatly Original Oat Milk", {"dimension": None},
                                        [_cand("p1", row=0)], catalog)
    assert len(survivors) == 1
    assert review is False


# --- response branches ------------------------------------------------------

def test_ambiguous_request_is_gated_before_any_retrieval():
    catalog = _catalog([_row("s1", "p1", "chips")])
    out, resp = hr.run_hybrid_baseline("2 bags of chips", catalog, None, None, None, 5)
    assert (out, resp) == ([], "needs_clarification")


def test_hybrid_within_pool_gates_an_ambiguous_request():
    catalog = _catalog([_row("s1", "p1", "chips")])
    out, resp = hr.run_hybrid_within_pool("2 bags of chips", [("s1", "p1")], catalog,
                                          None, None, None, {})
    assert (out, resp) == ([], "needs_clarification")


def test_hybrid_within_pool_empty_pool_is_no_match():
    catalog = _catalog([_row("s1", "p1", "milk")])
    out, resp = hr.run_hybrid_within_pool("1 gallon whole milk", [], catalog,
                                          None, None, None, {})
    assert (out, resp) == ([], "no_acceptable_match")
