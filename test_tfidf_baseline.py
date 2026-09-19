"""Tests for tfidf_baseline.py: the three named Checkpoint E3 baselines,
hidden-field independence, deterministic ties/empty queries, and the
threshold baseline's refusal to run with an unset MIN_SIMILARITY."""
import pandas as pd
import pytest

import benchmark_config as cfg
import tfidf_baseline as tb
from retrieval import fit_tfidf


def _catalog(rows):
    return pd.DataFrame(rows)


def _row(store_id, product_id, title, dimension=None):
    return {"store_id": store_id, "product_id": product_id, "raw_title": title,
            "brand": None, "variant": None, "pkg_dimension": dimension}


def _fit(rows, tmp_path):
    catalog = _catalog(rows)
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")
    return catalog, vectorizer, matrix


# --- baseline 1: tfidf (no gate, no filter, no threshold) -------------------

def test_tfidf_baseline_ranks_by_cosine_no_gate(tmp_path):
    catalog, vectorizer, matrix = _fit([_row(1, "p1", "apple juice"), _row(1, "p2", "orange juice")], tmp_path)
    out = tb.run_baseline("tfidf", "apple juice", catalog, vectorizer, matrix, top_k=5)
    assert out["response"] == "answerable"
    assert [r["product_id"] for r in out["results"]] == ["p1", "p2"]
    assert out["config"] == {"name": "tfidf", "dimension_filter": False, "min_similarity": None}


def test_tfidf_baseline_does_not_apply_the_parser_clarification_gate(tmp_path):
    # "some milk" needs_review under parse_query.py -- baseline 2/3 would
    # abstain for this; baseline 1 has no such concept and just ranks.
    catalog, vectorizer, matrix = _fit([_row(1, "p1", "some milk substitute")], tmp_path)
    out = tb.run_baseline("tfidf", "some milk", catalog, vectorizer, matrix, top_k=5)
    assert out["response"] == "answerable"


def test_tfidf_baseline_empty_query_returns_no_acceptable_match(tmp_path):
    catalog, vectorizer, matrix = _fit([_row(1, "p1", "apple juice")], tmp_path)
    out = tb.run_baseline("tfidf", "", catalog, vectorizer, matrix, top_k=5)
    assert out["response"] == "no_acceptable_match"
    assert out["results"] == []


# --- baseline 2: tfidf_dimension_filter (floor 0.0) --------------------------

def test_dimension_filter_baseline_floor_is_zero_not_none(tmp_path):
    catalog, vectorizer, matrix = _fit([_row(1, "p1", "whole milk", dimension="volume")], tmp_path)
    out = tb.run_baseline("tfidf_dimension_filter", "1 gal whole milk", catalog, vectorizer, matrix, top_k=5)
    assert out["config"]["min_similarity"] == 0.0
    assert out["response"] == "answerable"


def test_dimension_filter_baseline_respects_needs_clarification(tmp_path):
    catalog, vectorizer, matrix = _fit([_row(1, "p1", "some milk substitute")], tmp_path)
    out = tb.run_baseline("tfidf_dimension_filter", "some milk", catalog, vectorizer, matrix, top_k=5)
    assert out["response"] == "needs_clarification"
    assert out["results"] == []


def test_dimension_filter_baseline_missing_dimension_is_not_a_confirmed_mismatch(tmp_path):
    # Regression test for the NaN-truthiness bug: a row with an unknown
    # (NaN) pkg_dimension must survive the filter, not be treated as an
    # automatic mismatch against a request that does specify a dimension.
    catalog = _catalog([_row(1, "p1", "whole milk gallon jug")])  # dimension left as None -> NaN in a real df
    catalog.loc[0, "pkg_dimension"] = float("nan")
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")
    out = tb.run_baseline("tfidf_dimension_filter", "1 gal whole milk", catalog, vectorizer, matrix, top_k=5)
    assert out["response"] == "answerable"
    assert len(out["results"]) == 1


# --- baseline 3: tfidf_dimension_filter_threshold ----------------------------

def test_threshold_baseline_raises_when_min_similarity_unset(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MIN_SIMILARITY", None)
    catalog, vectorizer, matrix = _fit([_row(1, "p1", "whole milk", dimension="volume")], tmp_path)
    with pytest.raises(RuntimeError, match="MIN_SIMILARITY is unset"):
        tb.run_baseline("tfidf_dimension_filter_threshold", "1 gal whole milk", catalog, vectorizer, matrix)


def test_threshold_baseline_runs_once_min_similarity_is_set(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "MIN_SIMILARITY", 0.5)
    catalog, vectorizer, matrix = _fit([_row(1, "p1", "whole milk", dimension="volume")], tmp_path)
    out = tb.run_baseline("tfidf_dimension_filter_threshold", "1 gal whole milk", catalog, vectorizer, matrix)
    assert out["config"]["min_similarity"] == 0.5
    assert out["response"] == "answerable"


# --- unknown baseline name ----------------------------------------------------

def test_unknown_baseline_name_raises(tmp_path):
    catalog, vectorizer, matrix = _fit([_row(1, "p1", "whole milk")], tmp_path)
    with pytest.raises(ValueError, match="unknown baseline"):
        tb.run_baseline("embeddings", "milk", catalog, vectorizer, matrix)


# --- hidden-field independence: only request_text can ever reach the matcher -

def test_run_baseline_signature_has_no_hidden_label_parameter():
    import inspect
    params = set(inspect.signature(tb.run_baseline).parameters)
    assert params == {"name", "request_text", "catalog_df", "vectorizer", "matrix", "top_k"}


@pytest.mark.parametrize("name", ["tfidf", "tfidf_dimension_filter"])
def test_predictions_identical_regardless_of_a_requests_hidden_fields(tmp_path, name):
    # Two "requests" that would carry wildly different expected/reference
    # fields in benchmark_requests.py but share the same text must produce
    # byte-identical predictions -- there is no code path for the hidden
    # fields to influence the outcome, since run_baseline never receives them.
    catalog, vectorizer, matrix = _fit([_row(1, "p1", "whole milk", dimension="volume")], tmp_path)
    request_a = {"text": "1 gal whole milk", "expected": {"brand": "Acme"}, "reference_product_ids": [[1, "p1"]]}
    request_b = {"text": "1 gal whole milk", "expected": {"brand": "Other"}, "reference_product_ids": [[9, "ghost"]]}
    out_a = tb.run_baseline(name, request_a["text"], catalog, vectorizer, matrix)
    out_b = tb.run_baseline(name, request_b["text"], catalog, vectorizer, matrix)
    assert out_a["results"] == out_b["results"]
    assert out_a["response"] == out_b["response"]


# --- deterministic ties -------------------------------------------------------

def test_tied_scores_break_deterministically_across_repeated_calls(tmp_path):
    catalog, vectorizer, matrix = _fit(
        [_row(2, "p1", "gala apples", dimension="count"), _row(1, "p1", "gala apples", dimension="count")],
        tmp_path,
    )
    out1 = tb.run_baseline("tfidf_dimension_filter", "3 apples", catalog, vectorizer, matrix, top_k=5)
    out2 = tb.run_baseline("tfidf_dimension_filter", "3 apples", catalog, vectorizer, matrix, top_k=5)
    assert out1["results"] == out2["results"]
    assert [r["store_id"] for r in out1["results"]] == [1, 2]  # lower store_id first
