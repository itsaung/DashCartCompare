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


def _size_row(store_id, product_id, title, dimension=None, pkg_canonical_unit=None,
              pkg_canonical_total=None, pkg_count=1.0):
    return {"store_id": store_id, "product_id": product_id, "raw_title": title,
            "brand": None, "variant": None, "pkg_dimension": dimension,
            "pkg_canonical_unit": pkg_canonical_unit, "pkg_canonical_total": pkg_canonical_total,
            "pkg_count": pkg_count}


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


# --- run_baseline_within_pool: Checkpoint E4 Experiment A --------------------

def _catalog_index(catalog):
    return {(row.store_id, row.product_id): i for i, row in enumerate(catalog.itertuples())}


def test_pool_baseline_scores_every_pool_candidate_including_zero_score(tmp_path):
    catalog, vectorizer, matrix = _fit(
        [_row(1, "p1", "apple juice"), _row(1, "p2", "frozen pizza"), _row(1, "p3", "grape soda")],
        tmp_path,
    )
    index = _catalog_index(catalog)
    pool = [(1, "p1"), (1, "p2")]  # p3 deliberately excluded -- not in this request's pool
    out = tb.run_baseline_within_pool("tfidf", "apple juice", pool, catalog, vectorizer, matrix, index)
    ids = {r["product_id"] for r in out["results"]}
    assert ids == {"p1", "p2"}  # p3 never appears -- pool ranking never reaches outside the pool
    zero_score = [r for r in out["results"] if r["product_id"] == "p2"][0]
    assert zero_score["score"] == 0.0  # unrelated pool member still scored and returned, not dropped


def test_pool_baseline_never_returns_a_pair_outside_the_pool(tmp_path):
    catalog, vectorizer, matrix = _fit(
        [_row(1, "p1", "apple juice"), _row(1, "p2", "apple juice concentrate")], tmp_path,
    )
    index = _catalog_index(catalog)
    pool = [(1, "p1")]  # p2 scores highly too but isn't in the pool
    out = tb.run_baseline_within_pool("tfidf", "apple juice", pool, catalog, vectorizer, matrix, index)
    assert {r["product_id"] for r in out["results"]} == {"p1"}


def test_pool_baseline_dimension_filter_applies_needs_clarification_gate(tmp_path):
    catalog, vectorizer, matrix = _fit([_row(1, "p1", "some milk substitute")], tmp_path)
    index = _catalog_index(catalog)
    out = tb.run_baseline_within_pool(
        "tfidf_dimension_filter", "some milk", [(1, "p1")], catalog, vectorizer, matrix, index,
    )
    assert out["response"] == "needs_clarification"
    assert out["results"] == []


def test_pool_baseline_missing_dimension_not_treated_as_confirmed_mismatch(tmp_path):
    catalog = _catalog([_row(1, "p1", "whole milk gallon jug")])
    catalog.loc[0, "pkg_dimension"] = float("nan")
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")
    index = _catalog_index(catalog)
    out = tb.run_baseline_within_pool(
        "tfidf_dimension_filter", "1 gal whole milk", [(1, "p1")], catalog, vectorizer, matrix, index,
    )
    assert out["response"] == "answerable"
    assert len(out["results"]) == 1


# --- apply_threshold: derive baseline 3 from baseline 2's pre-threshold record

def _dimension_filter_record(response="answerable", results=None):
    return {
        "config": {"name": "tfidf_dimension_filter", "dimension_filter": True, "min_similarity": 0.0},
        "results": results or [],
        "response": response,
    }


def test_apply_threshold_survives_above_the_floor():
    rec = _dimension_filter_record(results=[{"store_id": 1, "product_id": "p1", "score": 0.6}])
    out = tb.apply_threshold(rec, min_similarity=0.5)
    assert out["response"] == "answerable"
    assert out["results"] == rec["results"]
    assert out["config"]["min_similarity"] == 0.5
    assert out["config"]["name"] == "tfidf_dimension_filter_threshold"


def test_apply_threshold_rejects_below_the_floor():
    rec = _dimension_filter_record(results=[{"store_id": 1, "product_id": "p1", "score": 0.3}])
    out = tb.apply_threshold(rec, min_similarity=0.5)
    assert out["response"] == "no_acceptable_match"
    assert out["results"] == []


def test_apply_threshold_leaves_an_already_abstained_record_alone():
    rec = _dimension_filter_record(response="needs_clarification", results=[])
    out = tb.apply_threshold(rec, min_similarity=0.5)
    assert out["response"] == "needs_clarification"
    assert out["results"] == []


def test_apply_threshold_rejects_a_record_from_the_wrong_baseline():
    rec = {"config": {"name": "tfidf"}, "results": [], "response": "answerable"}
    with pytest.raises(ValueError, match="only derives from tfidf_dimension_filter"):
        tb.apply_threshold(rec, min_similarity=0.5)


def test_pool_baseline_rejects_the_threshold_baseline_name(tmp_path):
    catalog, vectorizer, matrix = _fit([_row(1, "p1", "milk")], tmp_path)
    index = _catalog_index(catalog)
    with pytest.raises(ValueError, match="unknown pool baseline"):
        tb.run_baseline_within_pool(
            "tfidf_dimension_filter_threshold", "milk", [(1, "p1")], catalog, vectorizer, matrix, index,
        )


# --- run_size_baseline / run_size_baseline_within_pool (v2, not a v1 baseline) -

def test_size_baseline_rejects_a_wrong_size_candidate_that_dimension_alone_keeps(tmp_path):
    catalog = _catalog([_size_row(1, "p1", "good culture cottage cheese", dimension="weight",
                                   pkg_canonical_unit="oz", pkg_canonical_total=16.0, pkg_count=1.0)])
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")
    out = tb.run_size_baseline("5.3 oz good culture cottage cheese", catalog, vectorizer, matrix, top_k=5)
    assert out["response"] == "no_acceptable_match"
    assert out["results"] == []
    assert out["config"]["name"] == tb.SIZE_BASELINE_NAME


def test_size_baseline_keeps_a_correctly_sized_candidate(tmp_path):
    catalog = _catalog([_size_row(1, "p1", "good culture cottage cheese", dimension="weight",
                                   pkg_canonical_unit="oz", pkg_canonical_total=5.3, pkg_count=1.0)])
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")
    out = tb.run_size_baseline("5.3 oz good culture cottage cheese", catalog, vectorizer, matrix, top_k=5)
    assert out["response"] == "answerable"
    assert len(out["results"]) == 1


def test_size_baseline_within_pool_matches_full_catalog_behavior(tmp_path):
    catalog = _catalog([
        _size_row(1, "p1", "good culture cottage cheese", dimension="weight",
                  pkg_canonical_unit="oz", pkg_canonical_total=16.0, pkg_count=1.0),
        _size_row(1, "p2", "good culture cottage cheese", dimension="weight",
                  pkg_canonical_unit="oz", pkg_canonical_total=5.3, pkg_count=1.0),
    ])
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")
    index = _catalog_index(catalog)
    out = tb.run_size_baseline_within_pool(
        "5.3 oz good culture cottage cheese", [(1, "p1"), (1, "p2")], catalog, vectorizer, matrix, index,
    )
    assert out["response"] == "answerable"
    assert [r["product_id"] for r in out["results"]] == ["p2"]  # p1 (16 oz) filtered out, p2 (5.3 oz) kept


def test_size_baseline_within_pool_needs_clarification_for_unparseable_request(tmp_path):
    catalog = _catalog([_size_row(1, "p1", "some milk substitute")])
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")
    index = _catalog_index(catalog)
    out = tb.run_size_baseline_within_pool("some milk", [(1, "p1")], catalog, vectorizer, matrix, index)
    assert out["response"] == "needs_clarification"
    assert out["results"] == []
