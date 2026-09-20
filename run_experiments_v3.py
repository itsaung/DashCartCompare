#!/usr/bin/env python3
"""Checkpoint 4, S4: run E4's two experiments for the two embedding baselines
(`embed`, `embed_dimension_size_filter`) into evaluation_v3/.

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
from run_experiments import _catalog_index, _load_catalog, find_new_candidates

HERE = Path(__file__).resolve().parent
CANDIDATE_POOL_PATH = HERE / "candidate_pool.json"
V1_DIR = HERE / "evaluation"
V2_DIR = HERE / "evaluation_v2"
REQUESTS_PATH = V1_DIR / "benchmark_requests.json"
PAIRS_PATH = V1_DIR / "benchmark_pairs.jsonl"
OUT_DIR = HERE / "evaluation_v3"

FULL_CATALOG_TOP_K = 5

BASELINES = [
    (er.EMBED_BASELINE_NAME, er.run_embed_baseline, er.run_embed_within_pool),
    (er.EMBED_FILTER_BASELINE_NAME, er.run_embed_filter_baseline, er.run_embed_filter_within_pool),
]


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


def run_pool_experiment(requests, pools_by_request, embeddings, catalog_df, catalog_index,
                        name, pool_fn, model) -> list:
    records = []
    for r in requests:
        pool = pools_by_request.get(r["request_id"], [])
        pool_pairs = [(c["store_id"], str(c["product_id"])) for c in pool]
        results, response = pool_fn(r["text"], pool_pairs, embeddings, catalog_df,
                                    catalog_index, model=model)
        records.append({"request_id": r["request_id"], "baseline": name,
                        "experiment": "pool", "results": results, "response": response})
    return records


def run_full_catalog_experiment(requests, embeddings, catalog_df, name, full_fn, model,
                                top_k=FULL_CATALOG_TOP_K) -> list:
    records = []
    for r in requests:
        start = time.perf_counter()
        results, response = full_fn(r["text"], embeddings, catalog_df, top_k, model=model)
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

    all_records = []
    for name, full_fn, pool_fn in BASELINES:
        pool_records = run_pool_experiment(requests, pools_by_request, embeddings, catalog_df,
                                           catalog_index, name, pool_fn, model)
        full_records = run_full_catalog_experiment(requests, embeddings, catalog_df, name,
                                                   full_fn, model)
        all_records.extend(pool_records + full_records)
        print(f"{name}: {len(pool_records)} pool, {len(full_records)} full-catalog")

    OUT_DIR.mkdir(exist_ok=True)
    with open(OUT_DIR / "predictions.jsonl", "w") as f:
        for rec in all_records:
            f.write(json.dumps(rec) + "\n")

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

    print(f"\nWrote {OUT_DIR / 'predictions.jsonl'} ({len(all_records)} records)")
    print(f"New candidates needing review: {len(new_candidates)}")
    print(f"Latency: cold start {cold_ms:.0f} ms, warm median {median:.1f} ms, p95 {p95:.1f} ms")


if __name__ == "__main__":
    main()
