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

import benchmark_config as cfg
from retrieval import attribute_filter_baseline, lexical_search

BASELINE_NAMES = ("tfidf", "tfidf_dimension_filter", "tfidf_dimension_filter_threshold")


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
