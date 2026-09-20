"""Tests for embedding_retrieval.py.

A fake encoder stands in for the real model: what these check is ranking,
tie-break, the response branches and the gate stack -- not sentence-transformers'
own behavior. Scores are hand-chosen so the expected order is computed by hand,
not read off a run.
"""
import numpy as np
import pandas as pd
import pytest

import embedding_retrieval as er


class _FakeModel:
    """Encodes by lookup, so a test can state exactly what score each catalog
    row gets against the query."""

    max_seq_length = 256

    def __init__(self, query_vec):
        self.query_vec = np.asarray(query_vec, dtype=np.float32)
        self.calls = 0

    def encode(self, texts, **kwargs):
        self.calls += 1
        return np.vstack([self.query_vec for _ in texts])


def _catalog(rows):
    return pd.DataFrame(rows)


def _row(store_id, product_id, title, dimension=None):
    return {"store_id": store_id, "product_id": product_id, "raw_title": title,
            "raw_category": "Grocery", "pkg_dimension": dimension,
            "pkg_canonical_unit": None, "pkg_canonical_total": None, "pkg_count": 1.0}


# A 2-dimensional embedding space: the query is (1, 0), so a row's score is
# simply its first coordinate.
QUERY = [1.0, 0.0]


def _embeddings(first_coords):
    return np.array([[c, 0.0] for c in first_coords], dtype=np.float32)


# --- ranking ----------------------------------------------------------------

def test_ranks_by_descending_score():
    catalog = _catalog([_row("s1", "p1", "a"), _row("s1", "p2", "b"), _row("s1", "p3", "c")])
    emb = _embeddings([0.2, 0.9, 0.5])
    out = er.embedding_search("q", emb, catalog, top_k=3, model=_FakeModel(QUERY))
    assert [c["product_id"] for c in out] == ["p2", "p3", "p1"]
    assert out[0]["score"] == pytest.approx(0.9)


def test_top_k_truncates():
    catalog = _catalog([_row("s1", f"p{i}", "t") for i in range(5)])
    emb = _embeddings([0.1, 0.2, 0.3, 0.4, 0.5])
    assert len(er.embedding_search("q", emb, catalog, top_k=2, model=_FakeModel(QUERY))) == 2


def test_ties_break_on_store_then_product_id():
    """Same deterministic rule the lexical path uses, so two runs over the
    same frozen catalog always rank identically."""
    catalog = _catalog([_row("s2", "p9", "t"), _row("s1", "p3", "t"), _row("s1", "p1", "t")])
    emb = _embeddings([0.5, 0.5, 0.5])
    out = er.embedding_search("q", emb, catalog, top_k=3, model=_FakeModel(QUERY))
    assert [(c["store_id"], c["product_id"]) for c in out] == [("s1", "p1"), ("s1", "p3"), ("s2", "p9")]


def test_zero_and_negative_scores_are_not_ranked():
    """retrieval._ranked keeps only score > 0. Cosine over normalized vectors
    can go negative, and a negative-similarity row is not a candidate."""
    catalog = _catalog([_row("s1", "p1", "a"), _row("s1", "p2", "b"), _row("s1", "p3", "c")])
    emb = _embeddings([0.0, -0.4, 0.3])
    out = er.embedding_search("q", emb, catalog, top_k=5, model=_FakeModel(QUERY))
    assert [c["product_id"] for c in out] == ["p3"]


def test_row_index_points_back_at_the_catalog_row():
    catalog = _catalog([_row("s1", "p1", "a"), _row("s1", "p2", "b")])
    emb = _embeddings([0.1, 0.8])
    out = er.embedding_search("q", emb, catalog, top_k=1, model=_FakeModel(QUERY))
    assert catalog.iloc[out[0]["row"]]["product_id"] == "p2"


# --- embed baseline ---------------------------------------------------------

def test_embed_baseline_returns_answerable():
    catalog = _catalog([_row("s1", "p1", "a")])
    out, resp = er.run_embed_baseline("q", _embeddings([0.7]), catalog, 5, model=_FakeModel(QUERY))
    assert resp == "answerable"
    assert len(out) == 1


def test_embed_baseline_has_no_parser_gate():
    """Unlike the filtered baselines, `embed` answers even an ambiguous
    request -- that is the weakness it exists to demonstrate, matching v1's
    `tfidf`."""
    catalog = _catalog([_row("s1", "p1", "chips")])
    out, resp = er.run_embed_baseline("2 bags of chips", _embeddings([0.6]), catalog, 5,
                                      model=_FakeModel(QUERY))
    assert resp == "answerable"


def test_embed_baseline_no_positive_scores_is_no_match():
    catalog = _catalog([_row("s1", "p1", "a")])
    out, resp = er.run_embed_baseline("q", _embeddings([0.0]), catalog, 5, model=_FakeModel(QUERY))
    assert (out, resp) == ([], "no_acceptable_match")


def test_embed_baseline_respects_a_min_similarity_floor():
    catalog = _catalog([_row("s1", "p1", "a")])
    out, resp = er.run_embed_baseline("q", _embeddings([0.4]), catalog, 5,
                                      min_similarity=0.5, model=_FakeModel(QUERY))
    assert (out, resp) == ([], "no_acceptable_match")


# --- embed + filter baseline ------------------------------------------------

def test_filter_baseline_gates_an_ambiguous_request():
    catalog = _catalog([_row("s1", "p1", "chips")])
    out, resp = er.run_embed_filter_baseline("2 bags of chips", _embeddings([0.9]), catalog, 5,
                                             model=_FakeModel(QUERY))
    assert (out, resp) == ([], "needs_clarification")


def test_filter_baseline_drops_a_dimension_conflict():
    # Request is a volume; the only candidate is a known weight.
    catalog = _catalog([_row("s1", "p1", "milk", dimension="weight")])
    out, resp = er.run_embed_filter_baseline("1 gallon whole milk", _embeddings([0.9]), catalog, 5,
                                             model=_FakeModel(QUERY))
    assert (out, resp) == ([], "no_acceptable_match")


def test_filter_baseline_keeps_an_unknown_dimension():
    """Unknown is not a confirmed mismatch -- the same rule
    filter_by_dimension follows for the lexical path."""
    catalog = _catalog([_row("s1", "p1", "milk", dimension=None)])
    out, resp = er.run_embed_filter_baseline("1 gallon whole milk", _embeddings([0.9]), catalog, 5,
                                             model=_FakeModel(QUERY))
    assert resp == "answerable"
    assert len(out) == 1


# --- pool scoring -----------------------------------------------------------

def test_within_pool_scores_only_pool_members():
    catalog = _catalog([_row("s1", "p1", "a"), _row("s1", "p2", "b"), _row("s1", "p3", "c")])
    emb = _embeddings([0.9, 0.2, 0.8])
    index = {("s1", "p1"): 0, ("s1", "p2"): 1, ("s1", "p3"): 2}
    out, resp = er.run_embed_within_pool("q", [("s1", "p1"), ("s1", "p2")], emb, catalog,
                                         index, model=_FakeModel(QUERY))
    # p3 scores higher than p2 but is not in the pool, so it must not appear.
    assert [c["product_id"] for c in out] == ["p1", "p2"]
    assert resp == "answerable"


def test_within_pool_skips_a_pair_missing_from_the_catalog():
    catalog = _catalog([_row("s1", "p1", "a")])
    emb = _embeddings([0.9])
    out, _ = er.run_embed_within_pool("q", [("s1", "p1"), ("s1", "ghost")], emb, catalog,
                                      {("s1", "p1"): 0}, model=_FakeModel(QUERY))
    assert [c["product_id"] for c in out] == ["p1"]


def test_within_pool_empty_pool_is_no_match():
    catalog = _catalog([_row("s1", "p1", "a")])
    out, resp = er.run_embed_within_pool("q", [], _embeddings([0.9]), catalog, {},
                                         model=_FakeModel(QUERY))
    assert (out, resp) == ([], "no_acceptable_match")


# --- prefilter equivalence --------------------------------------------------

def test_prefilter_matches_a_full_sort_on_a_synthetic_catalog():
    """_ranked_top must return exactly what retrieval._ranked would, for any
    catalog smaller than the prefilter window -- the window is a performance
    shortcut, never a semantic change."""
    import retrieval

    rng = np.random.default_rng(0)
    n = 500
    catalog = _catalog([_row("s1", f"p{i:04d}", "t") for i in range(n)])
    scores = rng.random(n).astype(np.float32)

    full = retrieval._ranked(catalog, scores)[:20]
    fast = er._ranked_top(catalog, scores, 20)
    assert [(c["store_id"], c["product_id"]) for c in full] == \
           [(c["store_id"], c["product_id"]) for c in fast]


def test_prefilter_applies_when_the_catalog_exceeds_the_window(monkeypatch):
    """With the window set below the catalog size, the top_k must still be the
    true global top_k."""
    import retrieval

    monkeypatch.setattr(er, "_PREFILTER_ROWS", 50)
    rng = np.random.default_rng(7)
    n = 400
    catalog = _catalog([_row("s1", f"p{i:04d}", "t") for i in range(n)])
    scores = rng.random(n).astype(np.float32)

    full = retrieval._ranked(catalog, scores)[:10]
    fast = er._ranked_top(catalog, scores, 10)
    assert [c["product_id"] for c in full] == [c["product_id"] for c in fast]


def test_prefilter_still_drops_non_positive_scores():
    catalog = _catalog([_row("s1", "p1", "a"), _row("s1", "p2", "b")])
    out = er._ranked_top(catalog, np.array([-0.5, 0.0], dtype=np.float32), 5)
    assert out == []
