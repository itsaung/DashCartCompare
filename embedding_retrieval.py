"""Checkpoint 4, S4: embedding retrieval and the two embedding baselines.

Mirrors retrieval.py's conventions deliberately, so the only thing that
differs between a lexical baseline and its embedding counterpart is the
retriever -- same prefilter depth, same tie-break, same three response
branches, same "score > 0 to be ranked" rule. If the two produce different
metrics, that difference is the retriever and not an incidental plumbing
choice.

Two named baselines:
  embed                        -- raw embedding ranking, no gate, no filters.
                                  The direct counterpart of v1's `tfidf`.
  embed_dimension_size_filter  -- the same gates as v2's
                                  tfidf_dimension_size_filter. The direct
                                  counterpart of the current best baseline,
                                  differing only in the retriever.

Neither applies a threshold. S6 tunes one on dev; until then these run at a
0.0 floor, the same shape run_experiments_v2.py used.

The query encoder is loaded once and reused. Embedding scores are NOT
comparable to TF-IDF scores -- the two similarity scales differ, so only the
metrics are comparable, never the raw numbers.
"""

from __future__ import annotations

import numpy as np

import benchmark_config as cfg
import embed_catalog
import retrieval
from parse_query import parse_shopping_line

EMBED_BASELINE_NAME = "embed"
EMBED_FILTER_BASELINE_NAME = "embed_dimension_size_filter"

_MODEL = None


def get_model():
    """Loaded lazily and cached: a module-level import must not pull ~90MB of
    weights into memory for a test that never encodes anything."""
    global _MODEL
    if _MODEL is None:
        _MODEL = embed_catalog._load_model()
    return _MODEL


def encode_query(text: str, model=None) -> np.ndarray:
    model = model or get_model()
    vec = model.encode([text], normalize_embeddings=True, convert_to_numpy=True)[0]
    return np.asarray(vec, dtype=np.float32)


# How many top-scoring rows to materialize before ranking. See _ranked_top.
_PREFILTER_ROWS = 2000


def _unwrap(value):
    """numpy scalar -> Python scalar, so predictions.jsonl stays serializable."""
    return value.item() if hasattr(value, "item") else value


def _ranked_top(catalog_df, scores: np.ndarray, top_k: int) -> list:
    """retrieval._ranked's output, computed without materializing the whole
    catalog.

    Why this exists rather than calling retrieval._ranked directly: TF-IDF
    cosine is sparse, so `score > 0` discards most rows and _ranked stays
    cheap. Embedding cosine is dense -- measured, 30,875 of 31,398 rows
    (98.3%) score positive against a real query -- so _ranked builds and
    sorts a 31k-element list of dicts on every single query, which measured
    at 4,165 ms. That is the retrieval path's entire cost, and it is an
    artifact of the ranking helper, not of the similarity computation
    (the dot product itself is ~6 ms).

    So: argpartition to the top _PREFILTER_ROWS by score, then apply exactly
    the same `score > 0` rule and cfg.tie_break_key sort to those.

    Equivalence caveat, stated rather than assumed: this returns the same
    top_k as a full sort unless more than (_PREFILTER_ROWS - top_k) rows
    share the boundary score, in which case which tied rows survive could
    differ. With _PREFILTER_ROWS at 2000 against top_k <= 20 that needs a
    ~1980-row exact-score tie. Verified equal to retrieval._ranked's top_k on
    real queries (see test_embedding_retrieval.py).
    """
    n = len(catalog_df)
    take = min(_PREFILTER_ROWS, n)
    idx = np.argpartition(-scores, take - 1)[:take] if take < n else np.arange(n)
    # _unwrap: indexing with a numpy index yields numpy scalars, which json
    # cannot serialize. retrieval._ranked never hit this because its callers
    # index with Python ints; argpartition hands back int64.
    scored = [
        {
            "store_id": _unwrap(catalog_df.iloc[int(i)]["store_id"]),
            "product_id": _unwrap(catalog_df.iloc[int(i)]["product_id"]),
            "score": float(scores[i]),
            "row": int(i),
        }
        for i in idx
        if scores[i] > 0
    ]
    scored.sort(key=cfg.tie_break_key)
    return scored[:top_k]


def embedding_search(query_text: str, embeddings: np.ndarray, catalog_df, top_k: int,
                     model=None) -> list:
    """Cosine similarity over the cached catalog matrix.

    Both sides are L2-normalized (embed_catalog guarantees it for the matrix),
    so cosine is a plain dot product. Same `score > 0` rule and same
    cfg.tie_break_key as the lexical path -- see _ranked_top for why the sort
    is done there rather than in retrieval._ranked.
    """
    query_vec = encode_query(query_text, model)
    scores = embeddings @ query_vec
    return _ranked_top(catalog_df, scores, top_k)


def run_embed_baseline(request_text: str, embeddings, catalog_df, top_k,
                       min_similarity: float = 0.0, model=None):
    """`embed`: raw ranking, no parser gate and no attribute filters.

    The counterpart of v1's `tfidf`, including its weakness -- it returns
    something for essentially every request, answerable or not.
    """
    results = embedding_search(request_text, embeddings, catalog_df, top_k, model)
    if not results:
        return [], "no_acceptable_match"
    if results[0]["score"] < min_similarity:
        return [], "no_acceptable_match"
    return results, "answerable"


def run_embed_filter_baseline(request_text: str, embeddings, catalog_df, top_k,
                              min_similarity: float = 0.0, model=None):
    """`embed_dimension_size_filter`: the v2 gate stack on embedding retrieval.

    Same three response branches and same prefilter depth
    (max(top_k * 4, 20)) as attribute_and_size_filter_baseline, so depth is
    not a confound when the two are compared.
    """
    structured = parse_shopping_line(request_text)
    if structured["needs_review"]:
        return [], "needs_clarification"

    candidates = embedding_search(
        request_text, embeddings, catalog_df, max(top_k * 4, 20), model)
    survivors = retrieval.filter_by_dimension(candidates, catalog_df, structured.get("dimension"))
    survivors = retrieval.filter_by_package_size(survivors, catalog_df, request_text, structured)
    if not survivors:
        return [], "no_acceptable_match"

    survivors.sort(key=cfg.tie_break_key)
    top = survivors[:top_k]
    if top[0]["score"] < min_similarity:
        return [], "no_acceptable_match"
    return top, "answerable"


def _score_within_pool(request_text: str, pool_pairs: list, embeddings, catalog_df,
                       catalog_index: dict, model=None) -> list:
    """Score exactly the candidates already in a request's frozen pool.

    Experiment A: ranking within the labeled pool, so Pool Recall@5 has a
    denominator that doesn't depend on what full-catalog search happened to
    surface.
    """
    query_vec = encode_query(request_text, model)
    scored = []
    for store_id, product_id in pool_pairs:
        row = catalog_index.get((store_id, str(product_id)))
        if row is None:
            continue
        scored.append({
            "store_id": store_id,
            "product_id": product_id,
            "score": float(embeddings[row] @ query_vec),
            "row": row,
        })
    scored.sort(key=cfg.tie_break_key)
    return scored


def run_embed_within_pool(request_text: str, pool_pairs: list, embeddings, catalog_df,
                          catalog_index: dict, top_k=5, model=None):
    scored = _score_within_pool(request_text, pool_pairs, embeddings, catalog_df,
                                catalog_index, model)
    if not scored:
        return [], "no_acceptable_match"
    return scored[:top_k], "answerable"


def run_embed_filter_within_pool(request_text: str, pool_pairs: list, embeddings, catalog_df,
                                 catalog_index: dict, top_k=5, model=None):
    structured = parse_shopping_line(request_text)
    if structured["needs_review"]:
        return [], "needs_clarification"

    scored = _score_within_pool(request_text, pool_pairs, embeddings, catalog_df,
                                catalog_index, model)
    survivors = retrieval.filter_by_dimension(scored, catalog_df, structured.get("dimension"))
    survivors = retrieval.filter_by_package_size(survivors, catalog_df, request_text, structured)
    if not survivors:
        return [], "no_acceptable_match"
    survivors.sort(key=cfg.tie_break_key)
    return survivors[:top_k], "answerable"
