"""Shared retrieval primitives for Checkpoint 3: TF-IDF lexical search,
synonym-assisted search, and attribute_filter_baseline (the system under
test).

Every result is keyed by (store_id, product_id) -- item_id alone is not
globally unique across stores (see DATA_DICTIONARY.md) -- and every ranking
is broken by benchmark_config.tie_break_key so results are reproducible
across runs against the same frozen catalog.

attribute_filter_baseline deliberately only ever sees the raw request text,
parsed through parse_query.py exactly as a real system would at inference
time. It never receives the benchmark's hidden `expected` ground-truth
fields -- those exist purely to grade candidates in build_candidate_pool.py
and for human review, never to help the system being graded.
"""
import hashlib
import pickle
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import benchmark_config as cfg
from parse_query import parse_shopping_line

MODEL_CACHE_PATH = Path(__file__).resolve().parent / "tfidf_model.pkl"

# A small, explicit substitution table -- not embeddings, just words a
# shopper might reasonably use interchangeably with a catalog title/category
# term. SYNONYM_TABLE_VERSION in benchmark_config.py must be bumped whenever
# this changes meaningfully.
SYNONYMS = {
    "soda": {"pop", "soft drink"},
    "pop": {"soda", "soft drink"},
    "chips": {"crisps"},
    "cookies": {"biscuits"},
    "cilantro": {"coriander"},
    "yogurt": {"yoghurt"},
    "eggplant": {"aubergine"},
    "zucchini": {"courgette"},
    "arugula": {"rocket"},
    "candy": {"sweets"},
    "fries": {"chips"},
}


def catalog_hash(catalog_df) -> str:
    """Stable content hash of a catalog DataFrame's rows, used to detect a
    stale cached TF-IDF model or a manifest/catalog mismatch."""
    payload = catalog_df.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _catalog_text(catalog_df):
    return (
        catalog_df["raw_title"].fillna("")
        + " " + catalog_df["brand"].fillna("")
        + " " + catalog_df["variant"].fillna("")
    )


def fit_tfidf(catalog_df, cache_path: Path = MODEL_CACHE_PATH):
    """Fit a TF-IDF vectorizer once against the frozen catalog's raw_title (+
    brand/variant, once populated). Cached to disk keyed by the catalog's
    content hash -- a mismatched hash means the cache is stale and must be
    refit, but refitting only ever happens here, never inside
    lexical_search, which only ever transforms a query against this fitted
    model."""
    current_hash = catalog_hash(catalog_df)

    if cache_path.exists():
        with open(cache_path, "rb") as f:
            cached = pickle.load(f)
        if cached.get("catalog_hash") == current_hash:
            return cached["vectorizer"], cached["matrix"]

    vectorizer = TfidfVectorizer()
    matrix = vectorizer.fit_transform(_catalog_text(catalog_df))
    with open(cache_path, "wb") as f:
        pickle.dump({"catalog_hash": current_hash, "vectorizer": vectorizer, "matrix": matrix}, f)
    return vectorizer, matrix


def _ranked(catalog_df, scores) -> list:
    scored = [
        {
            "store_id": catalog_df.iloc[i]["store_id"],
            "product_id": catalog_df.iloc[i]["product_id"],
            "score": float(scores[i]),
            "row": i,
        }
        for i in range(len(catalog_df))
        if scores[i] > 0
    ]
    scored.sort(key=cfg.tie_break_key)
    return scored


def lexical_search(query_text, vectorizer, matrix, catalog_df, top_k):
    """TF-IDF cosine similarity. Transforms `query_text` only -- never
    refits the vectorizer (fit_tfidf does that once, up front)."""
    query_vec = vectorizer.transform([query_text])
    scores = cosine_similarity(query_vec, matrix)[0]
    return _ranked(catalog_df, scores)[:top_k]


def _expand_synonyms(word: str) -> set:
    return {word} | SYNONYMS.get(word, set())


def synonym_assisted_search(structured_request: dict, catalog_df, top_k):
    """Category + a small synonym table + package-dimension compatibility --
    the stand-in for "semantic" retrieval in a project with no embeddings
    source. Deliberately a different method than lexical_search, so the
    candidate pool isn't just TF-IDF's own top results scored against
    themselves."""
    product_type = (structured_request.get("product_type") or "").lower()
    expanded = set()
    for w in product_type.split():
        expanded |= _expand_synonyms(w)
    if not expanded:
        return []

    dimension = structured_request.get("dimension")

    scored = []
    for i in range(len(catalog_df)):
        row = catalog_df.iloc[i]
        title_words = set(str(row["raw_title"]).lower().split())
        category_words = set(str(row["raw_category"]).lower().split())
        overlap = expanded & (title_words | category_words)
        if not overlap:
            continue
        score = len(overlap) / len(expanded)
        if dimension and row["pkg_dimension"] and row["pkg_dimension"] != dimension:
            # Penalized, not hard-excluded -- this pool is meant to surface
            # plausible near-misses (useful as hard negatives), unlike
            # attribute_filter_baseline below which does hard-exclude.
            score *= 0.5
        scored.append({"store_id": row["store_id"], "product_id": row["product_id"], "score": score, "row": i})
    scored.sort(key=cfg.tie_break_key)
    return scored[:top_k]


def attribute_filter_baseline(request_text: str, catalog_df, vectorizer, matrix, top_k, min_similarity):
    """The system under test.

    Returns (ranked_results, response) where response is one of:
      "needs_clarification" -- the request's own parse flagged missing or
          ambiguous essentials (reuses parse_query.py's needs_review) --
          resolved before any retrieval is attempted.
      "no_acceptable_match"  -- every lexical candidate was filtered out by
          an explicit dimension mismatch, or the best surviving candidate's
          similarity is below min_similarity.
      "answerable"           -- ranked_results is a non-empty ranked list.
          Multiple tied top-scoring candidates are all valid alternatives,
          not a reason to abstain -- a score margin is never, on its own,
          grounds to return "no_acceptable_match" or "needs_clarification".
    """
    structured = parse_shopping_line(request_text)
    if structured["needs_review"]:
        return [], "needs_clarification"

    dimension = structured.get("dimension")
    candidates = lexical_search(request_text, vectorizer, matrix, catalog_df, top_k=max(top_k * 4, 20))

    survivors = [
        c for c in candidates
        if not (dimension and catalog_df.iloc[c["row"]]["pkg_dimension"] and catalog_df.iloc[c["row"]]["pkg_dimension"] != dimension)
    ]
    if not survivors:
        return [], "no_acceptable_match"

    survivors.sort(key=cfg.tie_break_key)
    top = survivors[:top_k]
    if top[0]["score"] < min_similarity:
        return [], "no_acceptable_match"

    return top, "answerable"
