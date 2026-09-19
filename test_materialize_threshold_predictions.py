"""Tests for materialize_threshold_predictions.py's pure derivation step."""
from materialize_threshold_predictions import THRESHOLD_BASELINE_NAME, derive_threshold_predictions


def _record(request_id, response="answerable", results=None, experiment="full_catalog"):
    return {
        "request_id": request_id, "experiment": experiment, "baseline": "tfidf_dimension_filter",
        "config": {"name": "tfidf_dimension_filter", "dimension_filter": True, "min_similarity": 0.0},
        "results": results or [], "response": response, "elapsed_ms": 1.0,
    }


def _res(store_id, product_id, score):
    return {"store_id": store_id, "product_id": product_id, "score": score}


def test_derives_the_threshold_baseline_name():
    out = derive_threshold_predictions([_record("r1", results=[_res(1, "p1", 0.9)])], min_similarity=0.5)
    assert out[0]["baseline"] == THRESHOLD_BASELINE_NAME == "tfidf_dimension_filter_threshold"


def test_rejects_below_threshold():
    out = derive_threshold_predictions([_record("r1", results=[_res(1, "p1", 0.2)])], min_similarity=0.5)
    assert out[0]["response"] == "no_acceptable_match"
    assert out[0]["results"] == []


def test_survives_above_threshold():
    out = derive_threshold_predictions([_record("r1", results=[_res(1, "p1", 0.9)])], min_similarity=0.5)
    assert out[0]["response"] == "answerable"
    assert out[0]["results"] == [_res(1, "p1", 0.9)]


def test_preserves_experiment_and_request_id():
    out = derive_threshold_predictions([_record("r1", experiment="pool", results=[_res(1, "p1", 0.9)])], 0.5)
    assert out[0]["request_id"] == "r1"
    assert out[0]["experiment"] == "pool"


def test_empty_input_produces_empty_output():
    assert derive_threshold_predictions([], min_similarity=0.5) == []
