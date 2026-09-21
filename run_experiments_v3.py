#!/usr/bin/env python3
"""Checkpoint 4, S4+S5: run E4's two experiments for the embedding and hybrid
baselines (`embed`, `embed_dimension_size_filter`, `hybrid_dimension_size_filter`,
`hybrid_identity_filter`) into evaluation_v3/.

Same shape as run_experiments_v2.py: same frozen catalog, requests, candidate
pool and splits, reused as-is (E1/E2 do not re-run for a new baseline).
evaluation/ and evaluation_v2/ are read-only inputs here.

"Already labeled" for the new-candidate diff is the UNION of v1's
benchmark_pairs.jsonl, v1's additional_judgments.json (153 pairs) and v2's
additional_judgments.json (94 pairs) -- a candidate these baselines surface
that any earlier round already judged must not be re-flagged as new.

Usage:
    .venv/bin/python run_experiments_v3.py
"""
import json
import time
from pathlib import Path

import numpy as np

import embed_catalog
import embedding_retrieval as er
import hybrid_retrieval as hr
import pandas as pd
from product_identity import build_brand_lexicon
from retrieval import _identity_lookup, fit_tfidf
from run_experiments import _catalog_index, _load_catalog, find_new_candidates

HERE = Path(__file__).resolve().parent
CANDIDATE_POOL_PATH = HERE / "candidate_pool.json"
V1_DIR = HERE / "evaluation"
V2_DIR = HERE / "evaluation_v2"
REQUESTS_PATH = V1_DIR / "benchmark_requests.json"
PAIRS_PATH = V1_DIR / "benchmark_pairs.jsonl"
OUT_DIR = HERE / "evaluation_v3"

FULL_CATALOG_TOP_K = 5

IDENTITY_PATH = HERE / "evaluation_v3" / "catalog_identity.csv"

# Each entry: (name, full_catalog_fn, pool_fn). The functions take different
# arguments, so ctx below carries everything any of them needs and each
# adapter picks what it uses -- rather than forcing one signature on all four
# and having unused parameters drift out of sync.
BASELINES = [
    er.EMBED_BASELINE_NAME,
    er.EMBED_FILTER_BASELINE_NAME,
    hr.HYBRID_BASELINE_NAME,
    hr.HYBRID_IDENTITY_BASELINE_NAME,
]


def _full_catalog_call(name, text, ctx, top_k, mode):
    if name == er.EMBED_BASELINE_NAME:
        return er.run_embed_baseline(text, ctx["embeddings"], ctx["catalog"], top_k,
                                     model=ctx["model"])
    if name == er.EMBED_FILTER_BASELINE_NAME:
        return er.run_embed_filter_baseline(text, ctx["embeddings"], ctx["catalog"], top_k,
                                            model=ctx["model"])
    if name == hr.HYBRID_BASELINE_NAME:
        return hr.run_hybrid_baseline(text, ctx["catalog"], ctx["vectorizer"], ctx["matrix"],
                                      ctx["embeddings"], top_k, model=ctx["model"])
    return hr.run_hybrid_identity_baseline(
        text, ctx["catalog"], ctx["vectorizer"], ctx["matrix"], ctx["embeddings"], top_k,
        model=ctx["model"], identity_lookup=ctx["identity_lookup"],
        brand_lexicon=ctx["brand_lexicon"], mode=mode)


def _pool_call(name, text, pool_pairs, ctx, mode):
    if name == er.EMBED_BASELINE_NAME:
        return er.run_embed_within_pool(text, pool_pairs, ctx["embeddings"], ctx["catalog"],
                                        ctx["catalog_index"], model=ctx["model"])
    if name == er.EMBED_FILTER_BASELINE_NAME:
        return er.run_embed_filter_within_pool(text, pool_pairs, ctx["embeddings"], ctx["catalog"],
                                               ctx["catalog_index"], model=ctx["model"])
    if name == hr.HYBRID_BASELINE_NAME:
        return hr.run_hybrid_within_pool(text, pool_pairs, ctx["catalog"], ctx["vectorizer"],
                                         ctx["matrix"], ctx["embeddings"], ctx["catalog_index"],
                                         model=ctx["model"])
    return hr.run_hybrid_identity_within_pool(
        text, pool_pairs, ctx["catalog"], ctx["vectorizer"], ctx["matrix"], ctx["embeddings"],
        ctx["catalog_index"], model=ctx["model"], identity_lookup=ctx["identity_lookup"],
        brand_lexicon=ctx["brand_lexicon"], mode=mode)


def _load_already_labeled_pairs() -> set:
    pairs = set()
    with open(PAIRS_PATH) as f:
        for line in f:
            row = json.loads(line)
            pairs.add((row["request_id"], row["store_id"], row["product_id"]))
    for path in (V1_DIR / "additional_judgments.json", V2_DIR / "additional_judgments.json"):
        if path.exists():
            for row in json.loads(path.read_text()).values():
                pairs.add((row["request_id"], row["store_id"], row["product_id"]))
    return pairs


def run_pool_experiment(requests, pools_by_request, ctx, name) -> list:
    records = []
    for r in requests:
        pool = pools_by_request.get(r["request_id"], [])
        pool_pairs = [(c["store_id"], str(c["product_id"])) for c in pool]
        results, response = _pool_call(name, r["text"], pool_pairs, ctx, r["matching_mode"])
        records.append({"request_id": r["request_id"], "baseline": name,
                        "experiment": "pool", "results": results, "response": response})
    return records


def run_full_catalog_experiment(requests, ctx, name, top_k=FULL_CATALOG_TOP_K) -> list:
    records = []
    for r in requests:
        start = time.perf_counter()
        results, response = _full_catalog_call(name, r["text"], ctx, top_k, r["matching_mode"])
        elapsed_ms = (time.perf_counter() - start) * 1000
        records.append({"request_id": r["request_id"], "baseline": name,
                        "experiment": "full_catalog", "results": results,
                        "response": response, "elapsed_ms": elapsed_ms})
    return records


def main():
    if not REQUESTS_PATH.exists() or not PAIRS_PATH.exists():
        raise SystemExit(f"{REQUESTS_PATH} missing -- v1's Checkpoint E1 outputs must exist first")
    if not CANDIDATE_POOL_PATH.exists():
        raise SystemExit(f"{CANDIDATE_POOL_PATH.name} missing")

    requests = json.loads(REQUESTS_PATH.read_text())
    pool = json.loads(CANDIDATE_POOL_PATH.read_text())
    pools_by_request = {p["request_id"]: p["candidates"] for p in pool}
    already_labeled = _load_already_labeled_pairs()

    print(f"loading catalog and fitting retrievers...", flush=True)
    catalog_df = _load_catalog()
    catalog_index = _catalog_index(catalog_df)

    # load_or_build refuses a stale cache on its own (catalog hash, row order,
    # model revision, package versions), so this either reuses S1's matrix or
    # recomputes it -- never silently uses one that disagrees with the catalog.
    cold_start = time.perf_counter()
    embeddings = embed_catalog.load_or_build(catalog_df)
    model = er.get_model()
    cold_ms = (time.perf_counter() - cold_start) * 1000

    if embeddings.shape[0] != len(catalog_df):
        raise SystemExit(f"embedding rows {embeddings.shape[0]} != catalog rows {len(catalog_df)}")

    vectorizer, matrix = fit_tfidf(catalog_df)
    ctx = {
        "catalog": catalog_df,
        "catalog_index": catalog_index,
        "embeddings": embeddings,
        "model": model,
        "vectorizer": vectorizer,
        "matrix": matrix,
        "identity_lookup": _identity_lookup(pd.read_csv(IDENTITY_PATH)),
        "brand_lexicon": build_brand_lexicon(catalog_df),
    }

    OUT_DIR.mkdir(exist_ok=True)
    predictions_path = OUT_DIR / "predictions.jsonl"

    # Written per baseline rather than all at the end. This run is ~25 minutes
    # and has twice now lost everything to a serialization error raised on the
    # final dump; a completed baseline should survive a later one failing.
    all_records = []
    with open(predictions_path, "w") as out:
        for name in BASELINES:
            started = time.perf_counter()
            pool_records = run_pool_experiment(requests, pools_by_request, ctx, name)
            full_records = run_full_catalog_experiment(requests, ctx, name)
            for rec in pool_records + full_records:
                out.write(json.dumps(rec) + "\n")
            out.flush()
            all_records.extend(pool_records + full_records)
            print(f"{name}: {len(pool_records)} pool, {len(full_records)} full-catalog "
                  f"({time.perf_counter() - started:.0f}s)", flush=True)

    full_only = [r for r in all_records if r["experiment"] == "full_catalog"]
    new_candidates = find_new_candidates(full_only, already_labeled, catalog_df, catalog_index)
    (OUT_DIR / "new_candidates_to_review.json").write_text(json.dumps(new_candidates, indent=2))

    lat = sorted(r["elapsed_ms"] for r in full_only)
    median = lat[len(lat) // 2]
    p95 = lat[int(0.95 * len(lat)) - 1]
    (OUT_DIR / "latency.json").write_text(json.dumps({
        "cold_start_ms": cold_ms,
        "full_catalog_median_ms": median,
        "full_catalog_p95_ms": p95,
        "n_queries": len(lat),
        "note": "cold start = cached-matrix load plus model load. Warm query "
                "times are per full-catalog search, both embedding baselines pooled.",
    }, indent=2) + "\n")

    print(f"\nWrote {predictions_path} ({len(all_records)} records)")
    print(f"New candidates needing review: {len(new_candidates)}")
    print(f"Latency: cold start {cold_ms:.0f} ms, warm median {median:.1f} ms, p95 {p95:.1f} ms")


if __name__ == "__main__":
    main()
