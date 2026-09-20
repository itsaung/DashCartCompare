#!/usr/bin/env python3
"""Checkpoint 3.1: run E4's two experiments for the new numeric-package-size
baseline (tfidf_dimension_size_filter, from retrieval.py's
attribute_and_size_filter_baseline / filter_by_package_size) and write
evaluation_v2/predictions.jsonl -- kept in a separate directory from
evaluation/ so Checkpoint 3's v1 predictions.jsonl (and everything
BASELINE_RESULTS.md's reproduction section documents) stays untouched.

Same two experiments as run_experiments.py, same catalog/requests/pool/
splits (frozen already, reused as-is -- E1/E2 do not need re-running for a
new baseline), just one baseline instead of two. "Already labeled" for the
new-candidate diff is the UNION of v1's benchmark_pairs.jsonl AND v1's
additional_judgments.json (the 153 pairs Checkpoint E4 already got judged
outside the original pool) -- a candidate this baseline surfaces that one
of those already covers must not be re-flagged as new.

Usage:
    python3 run_experiments_v2.py
"""
import json
from pathlib import Path

from run_experiments import _catalog_index, _load_catalog, find_new_candidates
from tfidf_baseline import SIZE_BASELINE_NAME, run_size_baseline, run_size_baseline_within_pool

HERE = Path(__file__).resolve().parent
CANDIDATE_POOL_PATH = HERE / "candidate_pool.json"
V1_DIR = HERE / "evaluation"
REQUESTS_PATH = V1_DIR / "benchmark_requests.json"
PAIRS_PATH = V1_DIR / "benchmark_pairs.jsonl"
ADDITIONAL_JUDGMENTS_PATH = V1_DIR / "additional_judgments.json"
OUT_DIR = HERE / "evaluation_v2"

FULL_CATALOG_TOP_K = 5


def _load_already_labeled_pairs() -> set:
    pairs = set()
    with open(PAIRS_PATH) as f:
        for line in f:
            row = json.loads(line)
            pairs.add((row["request_id"], row["store_id"], row["product_id"]))
    if ADDITIONAL_JUDGMENTS_PATH.exists():
        for row in json.loads(ADDITIONAL_JUDGMENTS_PATH.read_text()).values():
            pairs.add((row["request_id"], row["store_id"], row["product_id"]))
    return pairs


def run_pool_experiment(requests, pools_by_request, catalog_df, vectorizer, matrix, catalog_index) -> list:
    records = []
    for r in requests:
        pool = pools_by_request.get(r["request_id"], [])
        pool_pairs = [(c["store_id"], str(c["product_id"])) for c in pool]
        out = run_size_baseline_within_pool(r["text"], pool_pairs, catalog_df, vectorizer, matrix, catalog_index)
        records.append({"request_id": r["request_id"], "baseline": SIZE_BASELINE_NAME, "experiment": "pool", **out})
    return records


def run_full_catalog_experiment(requests, catalog_df, vectorizer, matrix, top_k=FULL_CATALOG_TOP_K) -> list:
    records = []
    for r in requests:
        out = run_size_baseline(r["text"], catalog_df, vectorizer, matrix, top_k=top_k)
        records.append({"request_id": r["request_id"], "baseline": SIZE_BASELINE_NAME, "experiment": "full_catalog", **out})
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

    from retrieval import fit_tfidf
    vectorizer, matrix = fit_tfidf(catalog_df)

    pool_records = run_pool_experiment(requests, pools_by_request, catalog_df, vectorizer, matrix, catalog_index)
    full_records = run_full_catalog_experiment(requests, catalog_df, vectorizer, matrix)

    OUT_DIR.mkdir(exist_ok=True)
    with open(OUT_DIR / "predictions.jsonl", "w") as f:
        for rec in pool_records + full_records:
            f.write(json.dumps(rec) + "\n")

    new_candidates = find_new_candidates(full_records, already_labeled, catalog_df, catalog_index)
    (OUT_DIR / "new_candidates_to_review.json").write_text(json.dumps(new_candidates, indent=2))

    print(f"Ran {len(requests)} requests x 1 baseline ({SIZE_BASELINE_NAME}): "
          f"{len(pool_records)} pool records, {len(full_records)} full-catalog records")
    print(f"Wrote {OUT_DIR / 'predictions.jsonl'}")
    print(f"New candidates needing review (not already judged by v1's pool or additional judgments): "
          f"{len(new_candidates)}")
    print(f"Wrote {OUT_DIR / 'new_candidates_to_review.json'}")


if __name__ == "__main__":
    main()
