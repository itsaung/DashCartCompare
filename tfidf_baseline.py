#!/usr/bin/env python3
"""Checkpoint 3 evaluation, Checkpoint E3: define the three small baselines
that E4/E5/E6 score, as thin named wrappers around retrieval.py's existing
primitives -- no new matching logic, per the plan's explicit "do not add
embeddings or gold-intent constraints merely to improve the reported
baseline."

  tfidf                             -- raw lexical_search: cosine ranking
                                        against catalog titles, no parser
                                        clarification gate, no dimension
                                        filter, no confidence threshold.
  tfidf_dimension_filter            -- attribute_filter_baseline with
                                        min_similarity=0.0. The parser
                                        clarification gate and dimension
                                        filter stay active; nothing is
                                        rejected on score alone, so this
                                        measures the current guardrails in
                                        isolation from any threshold.
  tfidf_dimension_filter_threshold  -- the same matcher with
                                        benchmark_config.MIN_SIMILARITY,
                                        which only Checkpoint E6 sets, by
                                        tuning on the dev split alone.
                                        Calling this baseline before E6 has
                                        run raises rather than guessing a
                                        floor -- there is deliberately no
                                        default here.

run_baseline() is the single entry point E4 calls at scale: it takes only
`request_text` and the catalog/model (exactly what attribute_filter_baseline
itself accepts), so it is structurally impossible for a request's hidden
`expected`/reference/hard-negative fields to reach it or influence a
prediction -- there is no parameter for them to travel through.

Usage (smoke demo against the real frozen catalog + a few dev requests):
    python3 tfidf_baseline.py
"""
import time

from sklearn.metrics.pairwise import cosine_similarity

import benchmark_config as cfg
from parse_query import parse_shopping_line
from retrieval import attribute_filter_baseline, filter_by_dimension, lexical_search

BASELINE_NAMES = ("tfidf", "tfidf_dimension_filter", "tfidf_dimension_filter_threshold")

# Only these two are meaningful as a pool-ranking experiment (Checkpoint E4,
# Experiment A). tfidf_dimension_filter_threshold's candidate set is, by
# construction, a subset of tfidf_dimension_filter's -- same ranking, same
# candidates, filtered afterward by a threshold that doesn't exist yet -- so
# it contributes nothing new to a pool ranking and isn't run separately here.
POOL_BASELINE_NAMES = ("tfidf", "tfidf_dimension_filter")


def _tfidf_only(request_text, catalog_df, vectorizer, matrix, top_k):
    ranked = lexical_search(request_text, vectorizer, matrix, catalog_df, top_k=top_k)
    response = "answerable" if ranked else "no_acceptable_match"
    return ranked, response


def run_baseline(name: str, request_text: str, catalog_df, vectorizer, matrix, top_k: int = 5) -> dict:
    """Score one query against one named baseline. Returns a dict with the
    exact model configuration used, the ranked results (each carrying its
    own score), the response status, and elapsed time -- written out before
    any label is ever consulted, per the plan."""
    if name not in BASELINE_NAMES:
        raise ValueError(f"unknown baseline {name!r}; must be one of {BASELINE_NAMES}")

    started = time.perf_counter()

    if name == "tfidf":
        ranked, response = _tfidf_only(request_text, catalog_df, vectorizer, matrix, top_k)
        config = {"name": name, "dimension_filter": False, "min_similarity": None}

    elif name == "tfidf_dimension_filter":
        ranked, response = attribute_filter_baseline(
            request_text, catalog_df, vectorizer, matrix, top_k=top_k, min_similarity=0.0,
        )
        config = {"name": name, "dimension_filter": True, "min_similarity": 0.0}

    else:  # tfidf_dimension_filter_threshold
        if cfg.MIN_SIMILARITY is None:
            raise RuntimeError(
                "benchmark_config.MIN_SIMILARITY is unset -- tfidf_dimension_filter_threshold "
                "cannot run until Checkpoint E6 tunes it on the dev split. Use "
                "tfidf_dimension_filter (floor 0.0) until then; this deliberately does not "
                "fall back to a guessed value."
            )
        ranked, response = attribute_filter_baseline(
            request_text, catalog_df, vectorizer, matrix, top_k=top_k, min_similarity=cfg.MIN_SIMILARITY,
        )
        config = {"name": name, "dimension_filter": True, "min_similarity": cfg.MIN_SIMILARITY}

    elapsed_ms = (time.perf_counter() - started) * 1000

    return {
        "config": config,
        "results": [
            {"store_id": int(r["store_id"]), "product_id": str(r["product_id"]), "score": float(r["score"])}
            for r in ranked
        ],
        "response": response,
        "elapsed_ms": elapsed_ms,
    }


def run_baseline_within_pool(name: str, request_text: str, pool_pairs: list, catalog_df, vectorizer, matrix,
                              catalog_index: dict) -> dict:
    """Checkpoint E4, Experiment A: score every candidate in a request's own
    fixed pool (`pool_pairs`, a list of (store_id, product_id)) -- never a
    full-catalog top-k intersected with the pool, which would confound pool
    ranking with retrieval, per the plan. Uses the SAME catalog-fitted
    vectorizer/matrix as the full-catalog baselines (never refit per
    request): the pool's rows are sliced out of the already-fitted matrix
    by `catalog_index`, a {(store_id, product_id): row} lookup built once
    over the whole catalog.

    Unlike run_baseline, this scores and returns EVERY pool candidate
    (including zero-score ones) rather than a top-k -- the point of pool
    ranking is to see where the known-labeled candidates land, not to
    simulate retrieval depth."""
    if name not in POOL_BASELINE_NAMES:
        raise ValueError(f"unknown pool baseline {name!r}; must be one of {POOL_BASELINE_NAMES}")

    started = time.perf_counter()

    rows = [catalog_index[pair] for pair in pool_pairs]
    query_vec = vectorizer.transform([request_text])
    scores = cosine_similarity(query_vec, matrix[rows])[0] if rows else []

    scored = [
        {"store_id": int(sid), "product_id": str(pid), "score": float(scores[i]), "row": rows[i]}
        for i, (sid, pid) in enumerate(pool_pairs)
    ]
    scored.sort(key=cfg.tie_break_key)

    if name == "tfidf":
        response = "answerable" if scored else "no_acceptable_match"
        results = scored
        config = {"name": name, "dimension_filter": False, "min_similarity": None, "experiment": "pool"}
    else:  # tfidf_dimension_filter
        structured = parse_shopping_line(request_text)
        if structured["needs_review"]:
            response, results = "needs_clarification", []
        else:
            survivors = filter_by_dimension(scored, catalog_df, structured.get("dimension"))
            response, results = ("answerable", survivors) if survivors else ("no_acceptable_match", [])
        config = {"name": name, "dimension_filter": True, "min_similarity": 0.0, "experiment": "pool"}

    elapsed_ms = (time.perf_counter() - started) * 1000

    return {
        "config": config,
        "results": [
            {"store_id": r["store_id"], "product_id": r["product_id"], "score": r["score"]}
            for r in results
        ],
        "response": response,
        "elapsed_ms": elapsed_ms,
    }


def apply_threshold(record: dict, min_similarity: float) -> dict:
    """Derive what tfidf_dimension_filter_threshold would have returned at
    `min_similarity`, from an already-computed tfidf_dimension_filter record
    (config min_similarity=0.0, i.e. pre-threshold) -- without re-running
    retrieval, since the candidate set and ranking are byte-identical; only
    the threshold cutoff differs. This is what Checkpoint E6's grid search
    sweeps over (cheaply, over already-written predictions), and what
    Checkpoint E7 uses to materialize the frozen threshold baseline's own
    results for the final report."""
    if record["config"]["name"] != "tfidf_dimension_filter":
        raise ValueError(
            f"apply_threshold only derives from tfidf_dimension_filter records, got "
            f"{record['config']['name']!r}"
        )

    config = {**record["config"], "name": "tfidf_dimension_filter_threshold", "min_similarity": min_similarity}

    if record["response"] != "answerable" or not record["results"]:
        return {**record, "config": config}

    if record["results"][0]["score"] < min_similarity:
        return {**record, "config": config, "response": "no_acceptable_match", "results": []}

    return {**record, "config": config}


def main():
    import json
    from pathlib import Path

    import pandas as pd

    from retrieval import fit_tfidf

    here = Path(__file__).resolve().parent
    catalog_df = pd.read_csv(here / "benchmark_catalog_frozen.csv", dtype={"product_id": str})
    vectorizer, matrix = fit_tfidf(catalog_df)

    requests = json.loads((here / "evaluation" / "benchmark_requests.json").read_text())
    splits = json.loads((here / "evaluation" / "splits.json").read_text())["request_split"]
    sample = [r for r in requests if splits.get(r["request_id"]) == "dev"][:3]

    for r in sample:
        print(f"\n=== {r['request_id']}: {r['text']!r} ===")
        for name in ("tfidf", "tfidf_dimension_filter"):
            out = run_baseline(name, r["text"], catalog_df, vectorizer, matrix, top_k=3)
            print(f"  {name}: response={out['response']} elapsed_ms={out['elapsed_ms']:.2f} "
                  f"top={out['results'][:3]}")
        print("  tfidf_dimension_filter_threshold: skipped (MIN_SIMILARITY unset until Checkpoint E6)")


if __name__ == "__main__":
    main()
