#!/usr/bin/env python3
"""Checkpoint 3 evaluation, Checkpoint E4: run the two experiments the plan
calls for and write evaluation/predictions.jsonl.

Experiment A -- ranking within the prepared pool: for every request, score
every candidate already in candidate_pool.json (never a full-catalog top-k
intersected with the pool -- that would confound pool ranking with
retrieval). Authored references and hard negatives stay in this pool; this
experiment reports ranking among supplied candidates, not independent
discovery.

Experiment B -- end-to-end full-catalog search: for every request, search
all 31,398 rows and take the top 5, with no injected references and no
restriction to the labeled pool.

Both experiments run for baselines "tfidf" and "tfidf_dimension_filter"
only. "tfidf_dimension_filter_threshold" is not run here: its candidate set
is, by construction, tfidf_dimension_filter's own pre-threshold set with a
not-yet-tuned cutoff applied afterward (Checkpoint E6) -- so
tfidf_dimension_filter's results already cover what the plan calls
"collect results before threshold rejection as well" for the filtered
variant, and running a third pass would only re-score the same candidates.

After Experiment B, this script collects the union of each baseline's
top-5 full-catalog results per request and diffs it against
evaluation/benchmark_pairs.jsonl (Checkpoint E1's labeled pairs). Any
(request_id, store_id, product_id) triple that the full-catalog search
returned but that was never in the original candidate pool -- so it has no
label -- is written to evaluation/new_candidates_to_review.json, stripped
of model identity/score/rank per the plan ("reviewers should see
request/product details without model identity, score, or rank"). This
script does not itself perform that review -- see apply_new_candidate_review.py.

Usage:
    python3 run_experiments.py
"""
import json
from pathlib import Path

import pandas as pd

from tfidf_baseline import POOL_BASELINE_NAMES, run_baseline, run_baseline_within_pool

HERE = Path(__file__).resolve().parent
FROZEN_CATALOG = HERE / "benchmark_catalog_frozen.csv"
CANDIDATE_POOL_PATH = HERE / "candidate_pool.json"
OUT_DIR = HERE / "evaluation"
REQUESTS_PATH = OUT_DIR / "benchmark_requests.json"
PAIRS_PATH = OUT_DIR / "benchmark_pairs.jsonl"

FULL_CATALOG_TOP_K = 5


def _load_catalog() -> pd.DataFrame:
    return pd.read_csv(FROZEN_CATALOG, dtype={"product_id": str})


def _catalog_index(catalog_df) -> dict:
    return {
        (int(row.store_id), str(row.product_id)): i
        for i, row in enumerate(catalog_df.itertuples())
    }


def _load_labeled_pairs() -> set:
    pairs = set()
    with open(PAIRS_PATH) as f:
        for line in f:
            row = json.loads(line)
            pairs.add((row["request_id"], row["store_id"], row["product_id"]))
    return pairs


def run_pool_experiment(requests, pools_by_request, catalog_df, vectorizer, matrix, catalog_index) -> list:
    records = []
    for r in requests:
        pool = pools_by_request.get(r["request_id"], [])
        pool_pairs = [(c["store_id"], str(c["product_id"])) for c in pool]
        for name in POOL_BASELINE_NAMES:
            out = run_baseline_within_pool(name, r["text"], pool_pairs, catalog_df, vectorizer, matrix, catalog_index)
            records.append({
                "request_id": r["request_id"], "baseline": name, "experiment": "pool",
                **out,
            })
    return records


def run_full_catalog_experiment(requests, catalog_df, vectorizer, matrix, top_k=FULL_CATALOG_TOP_K) -> list:
    records = []
    for r in requests:
        for name in POOL_BASELINE_NAMES:
            out = run_baseline(name, r["text"], catalog_df, vectorizer, matrix, top_k=top_k)
            records.append({
                "request_id": r["request_id"], "baseline": name, "experiment": "full_catalog",
                **out,
            })
    return records


def find_new_candidates(full_catalog_records, labeled_pairs, catalog_df, catalog_index) -> list:
    """The union of every full-catalog top-5 result across both baselines,
    minus anything already labeled in the current pool. Deduplicated by
    (request_id, store_id, product_id) -- a pair returned by both baselines
    for the same request appears once."""
    seen = set()
    new_candidates = []
    for rec in full_catalog_records:
        for res in rec["results"]:
            key = (rec["request_id"], res["store_id"], str(res["product_id"]))
            if key in labeled_pairs or key in seen:
                continue
            seen.add(key)
            row = catalog_df.iloc[catalog_index[(res["store_id"], str(res["product_id"]))]]
            new_candidates.append({
                "request_id": key[0],
                "store_id": key[1],
                "product_id": key[2],
                "raw_title": row.get("raw_title"),
                "raw_category": row.get("raw_category"),
                "brand": row.get("brand") if pd.notna(row.get("brand")) else None,
                "variant": row.get("variant") if pd.notna(row.get("variant")) else None,
                "raw_size": row.get("raw_size") if pd.notna(row.get("raw_size")) else None,
                "pkg_dimension": row.get("pkg_dimension") if pd.notna(row.get("pkg_dimension")) else None,
                # deliberately no baseline name, score, or rank -- the plan
                # requires reviewers judge blind to which model/score
                # surfaced a candidate.
            })
    new_candidates.sort(key=lambda c: (c["request_id"], c["store_id"], c["product_id"]))
    return new_candidates


def main():
    if not REQUESTS_PATH.exists() or not PAIRS_PATH.exists():
        raise SystemExit(f"{REQUESTS_PATH.name}/{PAIRS_PATH.name} missing -- run build_benchmark.py first (E1)")
    if not CANDIDATE_POOL_PATH.exists():
        raise SystemExit(f"{CANDIDATE_POOL_PATH.name} missing -- run build_candidate_pool.py first")

    requests = json.loads(REQUESTS_PATH.read_text())
    pool = json.loads(CANDIDATE_POOL_PATH.read_text())
    pools_by_request = {p["request_id"]: p["candidates"] for p in pool}
    labeled_pairs = _load_labeled_pairs()

    catalog_df = _load_catalog()
    catalog_index = _catalog_index(catalog_df)

    from retrieval import fit_tfidf
    vectorizer, matrix = fit_tfidf(catalog_df)

    pool_records = run_pool_experiment(requests, pools_by_request, catalog_df, vectorizer, matrix, catalog_index)
    full_records = run_full_catalog_experiment(requests, catalog_df, vectorizer, matrix)

    with open(OUT_DIR / "predictions.jsonl", "w") as f:
        for rec in pool_records + full_records:
            f.write(json.dumps(rec) + "\n")

    new_candidates = find_new_candidates(full_records, labeled_pairs, catalog_df, catalog_index)
    (OUT_DIR / "new_candidates_to_review.json").write_text(json.dumps(new_candidates, indent=2))

    print(f"Ran {len(requests)} requests x {len(POOL_BASELINE_NAMES)} baselines: "
          f"{len(pool_records)} pool records, {len(full_records)} full-catalog records")
    print(f"Wrote {OUT_DIR / 'predictions.jsonl'}")
    print(f"New candidates needing review (full-catalog top-{FULL_CATALOG_TOP_K}, not in the current pool): "
          f"{len(new_candidates)}")
    print(f"Wrote {OUT_DIR / 'new_candidates_to_review.json'}")


if __name__ == "__main__":
    main()
