"""Tests for run_experiments.py: new-candidate discovery (union of
full-catalog top-5s minus the labeled pool, deduplicated, model identity/
score/rank stripped) and the pool-vs-full-catalog experiment split. Small
hand-built fixtures, not the real 150-request run."""
import pandas as pd

import run_experiments as re_


def _catalog(rows):
    return pd.DataFrame(rows)


def _row(store_id, product_id, title="milk", brand=None, variant=None, dimension=None,
         category="Grocery", size=None):
    return {"store_id": store_id, "product_id": product_id, "raw_title": title,
            "raw_category": category, "brand": brand, "variant": variant,
            "pkg_dimension": dimension, "raw_size": size}


def _full_catalog_record(request_id, baseline, results):
    return {"request_id": request_id, "baseline": baseline, "experiment": "full_catalog", "results": results}


def _result(store_id, product_id, score=0.5):
    return {"store_id": store_id, "product_id": product_id, "score": score}


# --- find_new_candidates -----------------------------------------------------

def test_new_candidate_not_in_labeled_pairs_is_reported():
    catalog = _catalog([_row(1, "p1", title="whole milk")])
    index = re_._catalog_index(catalog)
    records = [_full_catalog_record("r1", "tfidf", [_result(1, "p1")])]
    new = re_.find_new_candidates(records, labeled_pairs=set(), catalog_df=catalog, catalog_index=index)
    assert len(new) == 1
    assert new[0]["request_id"] == "r1"
    assert new[0]["store_id"] == 1
    assert new[0]["product_id"] == "p1"
    assert new[0]["raw_title"] == "whole milk"


def test_already_labeled_candidate_is_not_reported():
    catalog = _catalog([_row(1, "p1")])
    index = re_._catalog_index(catalog)
    records = [_full_catalog_record("r1", "tfidf", [_result(1, "p1")])]
    labeled = {("r1", 1, "p1")}
    new = re_.find_new_candidates(records, labeled, catalog, index)
    assert new == []


def test_candidate_returned_by_both_baselines_is_deduplicated():
    catalog = _catalog([_row(1, "p1")])
    index = re_._catalog_index(catalog)
    records = [
        _full_catalog_record("r1", "tfidf", [_result(1, "p1")]),
        _full_catalog_record("r1", "tfidf_dimension_filter", [_result(1, "p1")]),
    ]
    new = re_.find_new_candidates(records, set(), catalog, index)
    assert len(new) == 1


def test_new_candidate_export_never_includes_model_identity_score_or_rank():
    catalog = _catalog([_row(1, "p1")])
    index = re_._catalog_index(catalog)
    records = [_full_catalog_record("r1", "tfidf_dimension_filter", [_result(1, "p1", score=0.987)])]
    new = re_.find_new_candidates(records, set(), catalog, index)
    keys = set(new[0].keys())
    assert "score" not in keys
    assert "baseline" not in keys
    assert "rank" not in keys


def test_new_candidates_sorted_deterministically():
    catalog = _catalog([_row(1, "pB"), _row(1, "pA"), _row(2, "pA")])
    index = re_._catalog_index(catalog)
    records = [_full_catalog_record("r1", "tfidf", [_result(2, "pA"), _result(1, "pB"), _result(1, "pA")])]
    new = re_.find_new_candidates(records, set(), catalog, index)
    assert [(c["request_id"], c["store_id"], c["product_id"]) for c in new] == [
        ("r1", 1, "pA"), ("r1", 1, "pB"), ("r1", 2, "pA"),
    ]


# --- pool vs full-catalog experiment separation -------------------------------

def test_pool_experiment_never_scores_outside_the_requests_pool(tmp_path, monkeypatch):
    from retrieval import fit_tfidf

    catalog = _catalog([_row(1, "p1", title="apple juice"), _row(1, "p2", title="apple juice fresh")])
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")
    index = re_._catalog_index(catalog)

    requests = [{"request_id": "r1", "text": "apple juice"}]
    pools_by_request = {"r1": [{"store_id": 1, "product_id": "p1"}]}  # p2 deliberately excluded

    records = re_.run_pool_experiment(requests, pools_by_request, catalog, vectorizer, matrix, index)
    for rec in records:
        assert {r["product_id"] for r in rec["results"]} <= {"p1"}


def test_full_catalog_experiment_can_return_products_outside_the_pool(tmp_path):
    from retrieval import fit_tfidf

    catalog = _catalog([_row(1, "p1", title="apple juice"), _row(1, "p2", title="apple juice fresh")])
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")

    requests = [{"request_id": "r1", "text": "apple juice"}]
    records = re_.run_full_catalog_experiment(requests, catalog, vectorizer, matrix, top_k=5)
    all_ids = {r["product_id"] for rec in records for r in rec["results"]}
    assert "p2" in all_ids  # never restricted to a labeled pool
