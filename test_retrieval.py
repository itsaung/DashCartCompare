"""Tests for retrieval.py: hand-calculated TF-IDF/cosine fixtures (not just
"looks plausible" checks) plus attribute_filter_baseline's three response
branches."""
import pandas as pd
import pytest

from retrieval import (
    _requested_canonical_total, attribute_filter_baseline, filter_by_package_size, fit_tfidf,
    lexical_search, synonym_assisted_search,
)


def _catalog(rows):
    return pd.DataFrame(rows)


def _row(store_id, product_id, title, category="Grocery", brand=None, variant=None, dimension=None):
    return {
        "store_id": store_id, "product_id": product_id,
        "raw_title": title, "raw_category": category,
        "brand": brand, "variant": variant, "pkg_dimension": dimension,
    }


def _size_row(store_id, product_id, title, pkg_canonical_unit=None, pkg_canonical_total=None, pkg_count=1.0):
    return {
        "store_id": store_id, "product_id": product_id, "raw_title": title,
        "pkg_canonical_unit": pkg_canonical_unit, "pkg_canonical_total": pkg_canonical_total,
        "pkg_count": pkg_count,
    }


def _cand(row_index, store_id="s1", product_id="p1"):
    return {"row": row_index, "store_id": store_id, "product_id": product_id, "score": 1.0}


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


def test_fit_tfidf_refits_when_text_construction_version_changes(tmp_path, monkeypatch):
    # A code change to _catalog_text's field construction must invalidate
    # an on-disk cache even though the catalog content hash is unchanged --
    # this is what TEXT_CONSTRUCTION_VERSION is for.
    import retrieval

    cache_path = tmp_path / "model.pkl"
    catalog = _catalog([_row("s1", "p1", "apple juice")])
    v1, _ = fit_tfidf(catalog, cache_path=cache_path)

    monkeypatch.setattr(retrieval, "TEXT_CONSTRUCTION_VERSION", "v2-changed")
    with open(cache_path, "rb") as f:
        import pickle
        cached_before = pickle.load(f)
    v2, _ = fit_tfidf(catalog, cache_path=cache_path)
    with open(cache_path, "rb") as f:
        import pickle
        cached_after = pickle.load(f)
    assert cached_before["cache_key"] != cached_after["cache_key"]


def test_fit_tfidf_refits_when_vectorizer_params_change(tmp_path):
    from sklearn.feature_extraction.text import TfidfVectorizer

    import retrieval

    cache_path = tmp_path / "model.pkl"
    catalog = _catalog([_row("s1", "p1", "apple juice")])
    fit_tfidf(catalog, cache_path=cache_path)

    key_with_defaults = retrieval._cache_key(catalog)
    original = TfidfVectorizer
    try:
        class _DifferentParams(TfidfVectorizer):
            def __init__(self):
                super().__init__(lowercase=False)
        retrieval.TfidfVectorizer = _DifferentParams
        key_with_different_params = retrieval._cache_key(catalog)
    finally:
        retrieval.TfidfVectorizer = original

    assert key_with_defaults != key_with_different_params


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


# --- _requested_canonical_total ------------------------------------------------

def test_requested_canonical_total_extracts_a_multipack_phrase_as_the_full_total():
    structured = {"canonical_unit": "fl oz", "canonical_quantity": 12.0}  # what parse_shopping_line alone gives
    unit, total = _requested_canonical_total("12 fl oz x 12 ct Diet Coke Diet Cola Soda", structured)
    assert unit == "fl oz"
    assert total == 144.0


def test_requested_canonical_total_finds_the_multipack_phrase_mid_sentence():
    structured = {"canonical_unit": "fl oz", "canonical_quantity": 12.0}
    unit, total = _requested_canonical_total("a 12 fl oz x 12 ct pack of Diet Coke Diet Cola Soda", structured)
    assert total == 144.0


def test_requested_canonical_total_falls_back_to_parse_shopping_line_for_a_plain_request():
    structured = {"canonical_unit": "oz", "canonical_quantity": 5.3}
    unit, total = _requested_canonical_total("5.3 oz cottage cheese", structured)
    assert unit == "oz"
    assert total == 5.3


def test_requested_canonical_total_unresolvable_returns_none_none():
    structured = {"canonical_unit": None, "canonical_quantity": None}
    assert _requested_canonical_total("some milk", structured) == (None, None)


# --- filter_by_package_size ---------------------------------------------------

def test_filter_by_package_size_drops_a_confirmed_different_size():
    # Regression fixture for the dominant real failure mode from
    # BASELINE_RESULTS.md: a 16 oz candidate scoring highly against a
    # 5.3 oz request purely on brand/lexical overlap.
    catalog = _catalog([_size_row("s1", "p1", "cottage cheese", "oz", 16.0, 1.0)])
    structured = {"canonical_unit": "oz", "canonical_quantity": 5.3}
    survivors = filter_by_package_size([_cand(0)], catalog, "5.3 oz cottage cheese", structured)
    assert survivors == []


def test_filter_by_package_size_keeps_an_exact_match():
    catalog = _catalog([_size_row("s1", "p1", "cottage cheese", "oz", 5.3, 1.0)])
    structured = {"canonical_unit": "oz", "canonical_quantity": 5.3}
    survivors = filter_by_package_size([_cand(0)], catalog, "5.3 oz cottage cheese", structured)
    assert len(survivors) == 1


def test_filter_by_package_size_allows_genuine_cross_unit_rounding():
    # 2 L request vs a candidate whose canonical total (from a "67.6 fl oz"
    # printed label) is 67.628 fl oz after conversion -- ordinary rounding,
    # not a distinct size.
    catalog = _catalog([_size_row("s1", "p1", "soda", "fl oz", 67.6, 1.0)])
    structured = {"canonical_unit": "fl oz", "canonical_quantity": 67.628}
    survivors = filter_by_package_size([_cand(0)], catalog, "2 L soda", structured)
    assert len(survivors) == 1


def test_filter_by_package_size_compares_total_not_per_pack_for_a_multipack():
    # "12 fl oz x 12 ct Diet Coke" -- parse_shopping_line's own
    # canonical_quantity only captures the per-can size (12), dropping the
    # "x 12 ct" multiplier, but _requested_canonical_total re-parses the
    # multipack phrase directly out of the raw text via
    # normalize.parse_package_size, giving the correct 144 fl oz total --
    # matched against the row's own 144 fl oz total, a true total-vs-total
    # comparison.
    catalog = _catalog([_size_row("s1", "p1", "Diet Coke (12 fl oz x 12 ct)", "fl oz", 144.0, 12.0)])
    structured = {"canonical_unit": "fl oz", "canonical_quantity": 12.0}  # what parse_shopping_line alone would give
    survivors = filter_by_package_size(
        [_cand(0)], catalog, "12 fl oz x 12 ct Diet Coke Diet Cola Soda", structured,
    )
    assert len(survivors) == 1


def test_filter_by_package_size_rejects_a_multipack_whose_total_is_wrong():
    # Same multipack phrase, but the candidate is actually a 24-can case
    # (288 fl oz total) -- must be rejected now that both sides compare
    # totals.
    catalog = _catalog([_size_row("s1", "p1", "Diet Coke (12 fl oz x 24 ct)", "fl oz", 288.0, 24.0)])
    structured = {"canonical_unit": "fl oz", "canonical_quantity": 12.0}
    survivors = filter_by_package_size(
        [_cand(0)], catalog, "12 fl oz x 12 ct Diet Coke Diet Cola Soda", structured,
    )
    assert survivors == []


def test_filter_by_package_size_rejects_a_multi_cup_pack_for_a_single_cup_request():
    # Regression test for the exact inconsistency this fix resolves: a
    # "5.3 oz cottage cheese" request (no multipack phrase at all) must be
    # judged against the CANDIDATE'S total, so a "5.3 oz x 2 ct" (10.6 oz
    # total) pack is correctly rejected -- previously it wrongly passed by
    # comparing against the candidate's per-pack amount (5.3), which
    # matched the request's number by coincidence.
    catalog = _catalog([_size_row("s1", "p1", "Daisy Cottage Cheese (5.3 oz x 2 ct)", "oz", 10.6, 2.0)])
    structured = {"canonical_unit": "oz", "canonical_quantity": 5.3}
    survivors = filter_by_package_size([_cand(0)], catalog, "5.3 oz cottage cheese", structured)
    assert survivors == []


def test_filter_by_package_size_unresolved_request_never_filters():
    catalog = _catalog([_size_row("s1", "p1", "cottage cheese", "oz", 16.0, 1.0)])
    structured = {"canonical_unit": None, "canonical_quantity": None}
    survivors = filter_by_package_size([_cand(0)], catalog, "some cottage cheese", structured)
    assert len(survivors) == 1


def test_filter_by_package_size_unresolved_row_never_filters():
    # A variable-weight item (e.g. produce priced by the pound) has no
    # fixed canonical total -- unknown, not a confirmed mismatch.
    catalog = _catalog([_size_row("s1", "p1", "bananas", pkg_canonical_unit=None, pkg_canonical_total=None)])
    structured = {"canonical_unit": "ct", "canonical_quantity": 3.0}
    survivors = filter_by_package_size([_cand(0)], catalog, "3 bananas", structured)
    assert len(survivors) == 1


def test_filter_by_package_size_defers_a_different_dimension_to_filter_by_dimension():
    # A "ct" row against an "oz" request is a dimension mismatch, not a
    # size mismatch -- this function leaves it for filter_by_dimension.
    catalog = _catalog([_size_row("s1", "p1", "eggs", "ct", 12.0, 1.0)])
    structured = {"canonical_unit": "oz", "canonical_quantity": 16.0}
    survivors = filter_by_package_size([_cand(0)], catalog, "16 oz eggs", structured)
    assert len(survivors) == 1


def test_filter_by_package_size_close_but_distinct_size_is_still_dropped():
    # 20% oversize (10 oz requested vs 12 oz candidate) -- BASELINE_RESULTS.md's
    # r105 pattern: close enough to score highly, still a real mismatch.
    catalog = _catalog([_size_row("s1", "p1", "frozen broccoli", "oz", 12.0, 1.0)])
    structured = {"canonical_unit": "oz", "canonical_quantity": 10.0}
    survivors = filter_by_package_size([_cand(0)], catalog, "10 oz frozen broccoli", structured)
    assert survivors == []


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


def test_baseline_missing_row_dimension_is_not_treated_as_a_confirmed_mismatch(tmp_path):
    # Regression test: pkg_dimension is NaN for a row with no parsed
    # package size (e.g. variable-weight produce). bool(nan) is True in
    # Python, so an unguarded truthy check on it would wrongly filter this
    # candidate out as a "confirmed" dimension conflict, when the truth is
    # simply unknown and should not exclude it.
    catalog = _catalog([_row("s1", "p1", "whole milk gallon jug")])
    catalog.loc[0, "pkg_dimension"] = float("nan")
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")
    results, response = attribute_filter_baseline(
        "1 gal whole milk", catalog, vectorizer, matrix, top_k=5, min_similarity=0.0,
    )
    assert response == "answerable"
    assert len(results) == 1


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


# --- attribute_and_size_filter_baseline: the new, non-v1 baseline ------------

def _full_row(store_id, product_id, title, dimension=None, pkg_canonical_unit=None,
              pkg_canonical_total=None, pkg_count=1.0):
    return {
        "store_id": store_id, "product_id": product_id, "raw_title": title,
        "raw_category": "Grocery", "brand": None, "variant": None,
        "pkg_dimension": dimension, "pkg_canonical_unit": pkg_canonical_unit,
        "pkg_canonical_total": pkg_canonical_total, "pkg_count": pkg_count,
    }


def test_size_baseline_rejects_a_same_dimension_wrong_size_candidate_that_dimension_alone_would_keep(tmp_path):
    # The exact r078-shaped scenario from BASELINE_RESULTS.md: a 16 oz
    # candidate is same-dimension ("weight") as a 5.3 oz request, so
    # attribute_filter_baseline's own dimension filter lets it through --
    # attribute_and_size_filter_baseline must not.
    from retrieval import attribute_and_size_filter_baseline

    catalog = _catalog([
        _full_row("s1", "p1", "good culture cottage cheese", dimension="weight",
                   pkg_canonical_unit="oz", pkg_canonical_total=16.0, pkg_count=1.0),
    ])
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")

    dimension_only_results, dimension_only_response = attribute_filter_baseline(
        "5.3 oz good culture cottage cheese", catalog, vectorizer, matrix, top_k=5, min_similarity=0.0,
    )
    assert dimension_only_response == "answerable"  # confirms the wrong-size candidate WOULD survive dimension alone

    results, response = attribute_and_size_filter_baseline(
        "5.3 oz good culture cottage cheese", catalog, vectorizer, matrix, top_k=5, min_similarity=0.0,
    )
    assert response == "no_acceptable_match"
    assert results == []


def test_size_baseline_keeps_a_correctly_sized_candidate(tmp_path):
    from retrieval import attribute_and_size_filter_baseline

    catalog = _catalog([
        _full_row("s1", "p1", "good culture cottage cheese", dimension="weight",
                   pkg_canonical_unit="oz", pkg_canonical_total=5.3, pkg_count=1.0),
    ])
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")
    results, response = attribute_and_size_filter_baseline(
        "5.3 oz good culture cottage cheese", catalog, vectorizer, matrix, top_k=5, min_similarity=0.0,
    )
    assert response == "answerable"
    assert len(results) == 1


def test_size_baseline_still_needs_clarification_for_unparseable_request(tmp_path):
    from retrieval import attribute_and_size_filter_baseline

    catalog = _catalog([_full_row("s1", "p1", "whole milk", dimension="volume")])
    vectorizer, matrix = fit_tfidf(catalog, cache_path=tmp_path / "model.pkl")
    results, response = attribute_and_size_filter_baseline(
        "some milk", catalog, vectorizer, matrix, top_k=5, min_similarity=0.0,
    )
    assert response == "needs_clarification"
    assert results == []
