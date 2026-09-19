"""Tests for run_experiments_v2.py's thin wiring around the already-tested
run_size_baseline / run_size_baseline_within_pool functions."""
import pandas as pd

import run_experiments_v2 as re2
from retrieval import fit_tfidf
from tfidf_baseline import SIZE_BASELINE_NAME


def _catalog(rows):
    return pd.DataFrame(rows)


def _row(store_id, product_id, title, pkg_canonical_unit=None, pkg_canonical_total=None, pkg_count=1.0):
    return {"store_id": store_id, "product_id": product_id, "raw_title": title,
            "brand": None, "variant": None, "pkg_dimension": None,
            "pkg_canonical_unit": pkg_canonical_unit, "pkg_canonical_total": pkg_canonical_total,
            "pkg_count": pkg_count}


def test_full_catalog_experiment_tags_the_size_baseline_and_experiment(tmp_path):
    catalog = _catalog([_row(1, "p1", "apple juice")])
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")
    requests = [{"request_id": "r1", "text": "apple juice"}]
    records = re2.run_full_catalog_experiment(requests, catalog, vectorizer, matrix, top_k=5)
    assert len(records) == 1
    assert records[0]["baseline"] == SIZE_BASELINE_NAME
    assert records[0]["experiment"] == "full_catalog"
    assert records[0]["request_id"] == "r1"


def test_pool_experiment_tags_the_size_baseline_and_experiment(tmp_path):
    catalog = _catalog([_row(1, "p1", "apple juice")])
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")
    requests = [{"request_id": "r1", "text": "apple juice"}]
    catalog_index = {(1, "p1"): 0}
    pools_by_request = {"r1": [{"store_id": 1, "product_id": "p1"}]}
    records = re2.run_pool_experiment(requests, pools_by_request, catalog, vectorizer, matrix, catalog_index)
    assert len(records) == 1
    assert records[0]["baseline"] == SIZE_BASELINE_NAME
    assert records[0]["experiment"] == "pool"


def test_already_labeled_pairs_union_of_pairs_and_additional_judgments(tmp_path, monkeypatch):
    pairs_path = tmp_path / "benchmark_pairs.jsonl"
    pairs_path.write_text('{"request_id": "r1", "store_id": 1, "product_id": "p1"}\n')
    additional_path = tmp_path / "additional_judgments.json"
    additional_path.write_text('{"r2|1|p2": {"request_id": "r2", "store_id": 1, "product_id": "p2"}}')
    monkeypatch.setattr(re2, "PAIRS_PATH", pairs_path)
    monkeypatch.setattr(re2, "ADDITIONAL_JUDGMENTS_PATH", additional_path)
    pairs = re2._load_already_labeled_pairs()
    assert pairs == {("r1", 1, "p1"), ("r2", 1, "p2")}
