#!/usr/bin/env python3
"""Checkpoint 3 evaluation, Checkpoint E7 prep: materialize
tfidf_dimension_filter_threshold's own predictions into
evaluation/predictions.jsonl, now that Checkpoint E6 has frozen
benchmark_config.MIN_SIMILARITY.

Checkpoint E4 deliberately never ran a third baseline pass -- the
threshold baseline's candidate set is, by construction, identical to
tfidf_dimension_filter's own pre-threshold set, so its predictions are
fully derivable from what's already on disk via tfidf_baseline.apply_threshold
(no retrieval re-run). This script does exactly that derivation, for both
the pool and full_catalog experiments, and appends the results to
predictions.jsonl so evaluation_metrics.py's baseline loop (which just
groups by whatever `baseline` values are present in the file) picks up a
genuine third baseline automatically -- Checkpoint E7 needs all three
side by side.

Idempotent: re-running drops any previously-materialized
tfidf_dimension_filter_threshold rows before regenerating, so it can be
re-run safely if MIN_SIMILARITY is ever re-tuned.

Usage:
    python3 materialize_threshold_predictions.py
"""
import json
from pathlib import Path

import benchmark_config as cfg
from tfidf_baseline import apply_threshold

HERE = Path(__file__).resolve().parent
PREDICTIONS_PATH = HERE / "evaluation" / "predictions.jsonl"

THRESHOLD_BASELINE_NAME = "tfidf_dimension_filter_threshold"


def derive_threshold_predictions(records: list, min_similarity: float) -> list:
    """records: tfidf_dimension_filter prediction rows (any mix of pool/
    full_catalog experiments). Returns the derived threshold-baseline rows,
    each carrying the same request_id/experiment, `baseline` renamed, and
    apply_threshold's own config/response/results changes."""
    derived = []
    for rec in records:
        out = apply_threshold(rec, min_similarity)
        derived.append({**out, "baseline": THRESHOLD_BASELINE_NAME})
    return derived


def main():
    if cfg.MIN_SIMILARITY is None:
        raise SystemExit("benchmark_config.MIN_SIMILARITY is unset -- run tune_threshold.py first (Checkpoint E6)")

    all_records = [json.loads(line) for line in open(PREDICTIONS_PATH)]
    source_records = [r for r in all_records if r["baseline"] == "tfidf_dimension_filter"]
    kept_records = [r for r in all_records if r["baseline"] != THRESHOLD_BASELINE_NAME]

    derived = derive_threshold_predictions(source_records, cfg.MIN_SIMILARITY)

    with open(PREDICTIONS_PATH, "w") as f:
        for rec in kept_records + derived:
            f.write(json.dumps(rec) + "\n")

    print(f"Derived {len(derived)} {THRESHOLD_BASELINE_NAME!r} predictions "
          f"at MIN_SIMILARITY={cfg.MIN_SIMILARITY} from {len(source_records)} source records")
    print(f"Wrote {PREDICTIONS_PATH}")


if __name__ == "__main__":
    main()
