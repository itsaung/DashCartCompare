"""Tests for retrieval.py: hand-calculated TF-IDF/cosine fixtures (not just
"looks plausible" checks) plus attribute_filter_baseline's three response
branches."""
import pandas as pd
import pytest

from retrieval import attribute_filter_baseline, fit_tfidf, lexical_search, synonym_assisted_search


def _catalog(rows):
    return pd.DataFrame(rows)


def _row(store_id, product_id, title, category="Grocery", brand=None, variant=None, dimension=None):
    return {
        "store_id": store_id, "product_id": product_id,
        "raw_title": title, "raw_category": category,
        "brand": brand, "variant": variant, "pkg_dimension": dimension,
    }


# --- lexical_search / fit_tfidf ---------------------------------------------

def test_lexical_search_hand_calculated_cosine(tmp_path):
    # 2-doc corpus, vocabulary {apple, juice, orange}. With sklearn's default
    # smooth idf (ln((1+n)/(1+df))+1, n=2): idf(apple)=idf(orange)=1+ln(1.5)
    # =1.405465, idf(juice)=1.0 (appears in both docs). Query == doc0's term
    # set exactly, so cosine(query, doc0) = 1.0 exactly; cosine(query, doc1)
    # only shares "juice", whose L2-normalized weight is
    # 1/sqrt(1.405465**2 + 1**2) = 0.579716, squared = 0.335990.
    catalog = _catalog([
        _row("s1", "p1", "apple juice"),
        _row("s1", "p2", "orange juice"),
    ])
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")
    results = lexical_search("apple juice", vectorizer, matrix, catalog, top_k=5)

    assert [r["product_id"] for r in results] == ["p1", "p2"]
    assert results[0]["score"] == pytest.approx(1.0, abs=1e-6)
    assert results[1]["score"] == pytest.approx(0.335990, abs=1e-3)


def test_lexical_search_excludes_zero_score_and_ties_break_deterministically(tmp_path):
    catalog = _catalog([
        _row("s2", "p1", "apple juice"),
        _row("s1", "p1", "apple juice"),  # identical text, different store -- tie
        _row("s1", "p2", "frozen pizza"),  # no shared terms -> score 0, excluded
    ])
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")
    results = lexical_search("apple juice", vectorizer, matrix, catalog, top_k=5)

    assert [(r["store_id"], r["product_id"]) for r in results] == [("s1", "p1"), ("s2", "p1")]


def test_fit_tfidf_cache_reused_when_catalog_unchanged(tmp_path):
    catalog = _catalog([_row("s1", "p1", "apple juice")])
    cache_path = tmp_path / "model.pkl"
    v1, _ = fit_tfidf(catalog, cache_path=cache_path)
    v2, _ = fit_tfidf(catalog, cache_path=cache_path)
    assert v1.vocabulary_ == v2.vocabulary_


def test_fit_tfidf_refits_on_catalog_change(tmp_path):
    cache_path = tmp_path / "model.pkl"
    catalog_a = _catalog([_row("s1", "p1", "apple juice")])
    fit_tfidf(catalog_a, cache_path=cache_path)
    catalog_b = _catalog([_row("s1", "p1", "apple juice"), _row("s1", "p2", "grape soda")])
    _, matrix = fit_tfidf(catalog_b, cache_path=cache_path)
    assert matrix.shape[0] == 2


# --- synonym_assisted_search -------------------------------------------------

def test_synonym_assisted_search_matches_via_synonym_table():
    catalog = _catalog([_row("s1", "p1", "Cola Soda 12 pack", category="Drinks")])
    structured = {"product_type": "pop", "dimension": None}
    results = synonym_assisted_search(structured, catalog, top_k=5)
    assert [r["product_id"] for r in results] == ["p1"]


def test_synonym_assisted_search_penalizes_dimension_mismatch():
    catalog = _catalog([_row("s1", "p1", "milk chocolate bar", category="Snacks", dimension="weight")])
    structured = {"product_type": "milk chocolate", "dimension": "volume"}
    results = synonym_assisted_search(structured, catalog, top_k=5)
    assert results[0]["score"] == pytest.approx(0.5)


def test_synonym_assisted_search_no_overlap_returns_empty():
    catalog = _catalog([_row("s1", "p1", "frozen pizza", category="Frozen")])
    structured = {"product_type": "milk", "dimension": None}
    assert synonym_assisted_search(structured, catalog, top_k=5) == []


# --- attribute_filter_baseline: three response branches ----------------------

def test_baseline_needs_clarification_for_unparseable_request(tmp_path):
    catalog = _catalog([_row("s1", "p1", "whole milk", dimension="volume")])
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")
    results, response = attribute_filter_baseline(
        "some milk", catalog, vectorizer, matrix, top_k=5, min_similarity=0.0,
    )
    assert response == "needs_clarification"
    assert results == []


def test_baseline_no_acceptable_match_on_explicit_dimension_conflict(tmp_path):
    # "1 gal milk" parses cleanly (dimension=volume) but the only catalog
    # row sharing the word "milk" is a solid weight-sold item -- an explicit
    # constraint violation, filtered out entirely rather than ranked low.
    catalog = _catalog([_row("s1", "p1", "milk chocolate bar", dimension="weight")])
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")
    results, response = attribute_filter_baseline(
        "1 gal milk", catalog, vectorizer, matrix, top_k=5, min_similarity=0.0,
    )
    assert response == "no_acceptable_match"
    assert results == []


def test_baseline_no_acceptable_match_below_min_similarity_floor(tmp_path):
    catalog = _catalog([_row("s1", "p1", "totally unrelated frozen pizza", dimension="weight")])
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")
    results, response = attribute_filter_baseline(
        "3 apples", catalog, vectorizer, matrix, top_k=5, min_similarity=0.9,
    )
    assert response == "no_acceptable_match"
    assert results == []


def test_baseline_answerable_with_tied_candidates_both_returned(tmp_path):
    catalog = _catalog([
        _row("s1", "p1", "gala apples", dimension="count"),
        _row("s2", "p1", "gala apples", dimension="count"),
    ])
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")
    results, response = attribute_filter_baseline(
        "3 apples", catalog, vectorizer, matrix, top_k=5, min_similarity=0.0,
    )
    assert response == "answerable"
    assert len(results) == 2
    assert results[0]["score"] == pytest.approx(results[1]["score"])
    # deterministic tie-break: lower store_id first
    assert [r["store_id"] for r in results] == ["s1", "s2"]
