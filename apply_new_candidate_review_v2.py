#!/usr/bin/env python3
"""Checkpoint 3.1: adjudicate the candidates evaluation_v2/run_experiments_v2.py's
full-catalog search returned that weren't already judged by v1 (neither the
original 1,658-pair pool nor v1's own 153 additional judgments), and write
evaluation_v2/additional_judgments.json.

Reuses apply_new_candidate_review.py's adjudicate_new_candidate() directly
(the same function, already fixed twice by external review -- see its own
module docstring) rather than writing a third copy of this logic.

Usage:
    python3 apply_new_candidate_review_v2.py
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from apply_new_candidate_review import LABELING_GUIDELINE_VERSION, _load_catalog_by_key, adjudicate_new_candidate
from benchmark_requests import REQUEST_VERSION

HERE = Path(__file__).resolve().parent
V1_DIR = HERE / "evaluation"
OUT_DIR = HERE / "evaluation_v2"
NEW_CANDIDATES_PATH = OUT_DIR / "new_candidates_to_review.json"
REQUESTS_PATH = V1_DIR / "benchmark_requests.json"
MANIFEST_PATH = HERE / "benchmark_manifest.json"

REVIEWED_BY = "claude_new_candidate_review_v2"


def main():
    if not NEW_CANDIDATES_PATH.exists():
        raise SystemExit(f"{NEW_CANDIDATES_PATH.name} missing -- run run_experiments_v2.py first")

    new_candidates = json.loads(NEW_CANDIDATES_PATH.read_text())
    requests = {r["request_id"]: r for r in json.loads(REQUESTS_PATH.read_text())}
    manifest = json.loads(MANIFEST_PATH.read_text())
    catalog_sha = manifest["catalog_version"]["sha256"]
    catalog_by_key = _load_catalog_by_key()

    judgments = {}
    label_counts = {"Acceptable": 0, "Incorrect": 0, "Needs clarification": 0}

    for c in new_candidates:
        request = requests[c["request_id"]]
        row = catalog_by_key[(c["store_id"], c["product_id"])]
        label, reason = adjudicate_new_candidate(request, row)
        label_counts[label] += 1

        key = f"{c['request_id']}|{c['store_id']}|{c['product_id']}"
        request_hash = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        judgments[key] = {
            "request_id": c["request_id"],
            "store_id": c["store_id"],
            "product_id": c["product_id"],
            "reviewer_label": label,
            "conservative_label": label,
            "is_best_guess": False,
            "label_quality": "text_rule_based",
            "reviewed_by": REVIEWED_BY,
            "reviewed_by_reason": reason,
            "source": "run_experiments_v2.py full-catalog search (tfidf_dimension_size_filter), "
                      "not in the original candidate pool or v1's additional judgments",
            "request_version": REQUEST_VERSION,
            "labeling_guideline_version": LABELING_GUIDELINE_VERSION,
            "catalog_version_sha256": catalog_sha,
            "request_content_sha256": request_hash,
            "reviewed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ"),
        }

    (OUT_DIR / "additional_judgments.json").write_text(json.dumps(judgments, indent=2))

    print(f"Adjudicated {len(new_candidates)} new candidates: {label_counts}")
    print(f"Wrote {OUT_DIR / 'additional_judgments.json'}")


if __name__ == "__main__":
    main()
