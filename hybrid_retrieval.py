"""Checkpoint 4, S5: hybrid retrieval — lexical and embedding, fused by rank.

The hypothesis S4 handed this step, stated before running it: TF-IDF wins
exact-mode requests (they carry brand and size tokens it matches literally)
and embeddings win flexible-mode requests (which have no such anchor). On dev,
exact was 90.7% for both retrievers while flexible was 76.5% lexical against
82.4% embedding. If those strengths are complementary rather than redundant,
fusing the two rankings should beat both. If they are redundant, it will not,
and that is a reportable result rather than a failure.

Fusion is reciprocal rank fusion:

    score(d) = sum over retrievers of  1 / (RRF_K + rank_r(d))

using RANKS only, never the underlying similarity values. That choice is
load-bearing: a TF-IDF cosine and an embedding cosine live on different
scales, so any weighted blend of the two scores would need both a calibration
constant and a weight, and both would be free parameters tuned on dev. RRF has
no free weight. RRF_K and the per-retriever depth are declared in
checkpoint4_config.py before this module ran for the first time.

Two named baselines, not one:

  hybrid_dimension_size_filter  -- the same gate stack as v2's
                                   tfidf_dimension_size_filter and S4's
                                   embed_dimension_size_filter. This is the
                                   only three-way comparison in the project
                                   where the retriever is the sole variable.
  hybrid_identity_filter        -- adds S3's brand/variant identity gate. The
                                   full stack, and the one CHECKPOINT_4_PLAN.md
                                   S5 names.

The plan named only the second. The first is added because without it there is
no clean way to attribute a change to the retriever rather than to the extra
gate -- S4's whole comparison rests on holding the stack constant, and dropping
that here would break the chain.
"""

from __future__ import annotations

import numpy as np

import benchmark_config as cfg
import checkpoint4_config as c4
import embedding_retrieval as er
import retrieval
from parse_query import parse_shopping_line
from product_identity import extract_request_identity

HYBRID_BASELINE_NAME = "hybrid_dimension_size_filter"
HYBRID_IDENTITY_BASELINE_NAME = "hybrid_identity_filter"


def _pair_key(candidate: dict) -> tuple:
    return (str(candidate["store_id"]), str(candidate["product_id"]))


def reciprocal_rank_fusion(ranked_lists: list, k: int = None, top_k: int = None) -> list:
    """Fuse several ranked candidate lists into one.

    Each input is a list of candidate dicts already in rank order (rank 1
    first). A candidate present in only one list is kept -- it simply earns a
    contribution from that list alone, which is RRF's intended behavior and
    the reason a candidate one retriever misses entirely can still surface.

    The fused score replaces the retriever score. Ties break on
    cfg.tie_break_key exactly as everywhere else in the project, so two runs
    over the same frozen catalog always produce the same order.
    """
    k = c4.RRF_K if k is None else k

    fused: dict[tuple, dict] = {}
    for ranked in ranked_lists:
        for rank, candidate in enumerate(ranked, start=1):
            key = _pair_key(candidate)
            entry = fused.get(key)
            if entry is None:
                entry = dict(candidate)
                entry["rrf_score"] = 0.0
                entry["retriever_scores"] = {}
                fused[key] = entry
            entry["rrf_score"] += 1.0 / (k + rank)

    out = []
    for entry in fused.values():
        entry["score"] = entry.pop("rrf_score")
        entry.pop("retriever_scores", None)
        out.append(entry)

    out.sort(key=cfg.tie_break_key)
    return out[:top_k] if top_k else out


def hybrid_search(request_text: str, catalog_df, vectorizer, matrix, embeddings,
                  top_k: int, model=None, depth: int = None) -> list:
    """Union of the two retrievers' top-`depth`, fused by rank."""
    depth = c4.HYBRID_RETRIEVER_DEPTH if depth is None else depth
    lexical = retrieval.lexical_search(request_text, vectorizer, matrix, catalog_df, top_k=depth)
    semantic = er.embedding_search(request_text, embeddings, catalog_df, depth, model)
    return reciprocal_rank_fusion([lexical, semantic], top_k=top_k)


def _apply_gates(request_text: str, structured: dict, candidates: list, catalog_df,
                 identity_lookup=None, brand_lexicon=None, mode: str = None):
    """The constraint stack, in one fixed order: dimension -> package size ->
    identity. Retrieve then constrain, the order PROJECT_PLAN.md's Checkpoint 4
    specifies. Returns (survivors, needs_review)."""
    survivors = retrieval.filter_by_dimension(candidates, catalog_df, structured.get("dimension"))
    survivors = retrieval.filter_by_package_size(survivors, catalog_df, request_text, structured)

    needs_review = False
    if identity_lookup is not None:
        request_identity = extract_request_identity(request_text, brand_lexicon or {})
        survivors, needs_review = retrieval.filter_by_identity(
            survivors, catalog_df, identity_lookup, request_identity, mode)
    return survivors, needs_review


def run_hybrid_baseline(request_text: str, catalog_df, vectorizer, matrix, embeddings,
                        top_k, min_similarity: float = 0.0, model=None):
    """`hybrid_dimension_size_filter`: fusion plus v2's gate stack.

    Same three response branches as every other baseline in the project.
    Note that min_similarity here is compared against an RRF score, which is
    not on the same scale as either retriever's cosine -- S6 derives a floor
    for this family separately rather than inheriting one.
    """
    structured = parse_shopping_line(request_text)
    if structured["needs_review"]:
        return [], "needs_clarification"

    candidates = hybrid_search(request_text, catalog_df, vectorizer, matrix, embeddings,
                               top_k=max(top_k * 4, 20), model=model)
    survivors, _ = _apply_gates(request_text, structured, candidates, catalog_df)
    if not survivors:
        return [], "no_acceptable_match"

    survivors.sort(key=cfg.tie_break_key)
    top = survivors[:top_k]
    if top[0]["score"] < min_similarity:
        return [], "no_acceptable_match"
    return top, "answerable"


def run_hybrid_identity_baseline(request_text: str, catalog_df, vectorizer, matrix, embeddings,
                                 top_k, min_similarity: float = 0.0, model=None,
                                 identity_lookup=None, brand_lexicon=None, mode="flexible"):
    """`hybrid_identity_filter`: fusion plus the full stack including S3's
    identity gate.

    Exact-mode requests still never fall through to a substitute: an
    unconfirmable identity returns needs_clarification at any threshold.
    """
    structured = parse_shopping_line(request_text)
    if structured["needs_review"]:
        return [], "needs_clarification"

    candidates = hybrid_search(request_text, catalog_df, vectorizer, matrix, embeddings,
                               top_k=max(top_k * 4, 20), model=model)
    survivors, needs_review = _apply_gates(
        request_text, structured, candidates, catalog_df,
        identity_lookup=identity_lookup, brand_lexicon=brand_lexicon, mode=mode)

    if not survivors:
        return [], "needs_clarification" if needs_review else "no_acceptable_match"

    survivors.sort(key=cfg.tie_break_key)
    top = survivors[:top_k]
    if top[0]["score"] < min_similarity:
        return [], "no_acceptable_match"
    return top, "answerable"


# --- pool-ranking variants (Experiment A) -----------------------------------

def _fuse_within_pool(request_text: str, pool_pairs: list, catalog_df, vectorizer, matrix,
                      embeddings, catalog_index: dict, model=None) -> list:
    """Rank exactly the frozen pool by fusing each retriever's ranking OF THAT
    POOL -- not by fusing full-catalog rankings and then intersecting, which
    would give a candidate's rank a dependency on catalog rows outside the
    pool."""
    rows, present = [], []
    for store_id, product_id in pool_pairs:
        row = catalog_index.get((store_id, str(product_id)))
        if row is not None:
            rows.append(row)
            present.append({"store_id": store_id, "product_id": product_id, "row": row})
    if not rows:
        return []

    query_vec = vectorizer.transform([request_text])
    lex_scores = (matrix[rows] @ query_vec.T).toarray().ravel()

    emb_query = er.encode_query(request_text, model)
    emb_scores = embeddings[rows] @ emb_query

    lexical = sorted(
        [{**p, "score": float(s)} for p, s in zip(present, lex_scores)],
        key=cfg.tie_break_key)
    semantic = sorted(
        [{**p, "score": float(s)} for p, s in zip(present, emb_scores)],
        key=cfg.tie_break_key)
    return reciprocal_rank_fusion([lexical, semantic])


def run_hybrid_within_pool(request_text: str, pool_pairs: list, catalog_df, vectorizer, matrix,
                           embeddings, catalog_index: dict, top_k=5, model=None):
    structured = parse_shopping_line(request_text)
    if structured["needs_review"]:
        return [], "needs_clarification"

    scored = _fuse_within_pool(request_text, pool_pairs, catalog_df, vectorizer, matrix,
                               embeddings, catalog_index, model)
    survivors, _ = _apply_gates(request_text, structured, scored, catalog_df)
    if not survivors:
        return [], "no_acceptable_match"
    survivors.sort(key=cfg.tie_break_key)
    return survivors[:top_k], "answerable"


def run_hybrid_identity_within_pool(request_text: str, pool_pairs: list, catalog_df, vectorizer,
                                    matrix, embeddings, catalog_index: dict, top_k=5, model=None,
                                    identity_lookup=None, brand_lexicon=None, mode="flexible"):
    structured = parse_shopping_line(request_text)
    if structured["needs_review"]:
        return [], "needs_clarification"

    scored = _fuse_within_pool(request_text, pool_pairs, catalog_df, vectorizer, matrix,
                               embeddings, catalog_index, model)
    survivors, needs_review = _apply_gates(
        request_text, structured, scored, catalog_df,
        identity_lookup=identity_lookup, brand_lexicon=brand_lexicon, mode=mode)
    if not survivors:
        return [], "needs_clarification" if needs_review else "no_acceptable_match"
    survivors.sort(key=cfg.tie_break_key)
    return survivors[:top_k], "answerable"
