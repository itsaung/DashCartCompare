#!/usr/bin/env python3
"""Checkpoint 3 evaluation, Checkpoint E4 (continued): review the candidates
run_experiments.py's full-catalog search returned that were never in the
original labeled pool (evaluation/new_candidates_to_review.json), and write
evaluation/additional_judgments.json -- kept separate from
label_review_decisions.json per the plan ("do not change the original pool
experiment by appending them there").

Reuses claude_auto_label.py's auto_label() rather than reimplementing
attribute comparison here: it already has the product-type sanity check,
known-variant-vocabulary conflict detection, and numeric package-size
tolerance that build_candidate_pool.py's simpler draft_label() lacks -- an
earlier version of this script used a hand-rolled comparison missing the
product-type check and mislabeled a Friendly Farms *oat* milk as Acceptable
against a Friendly Farms *almond* milk request (brand/size matched, variant
"Original" matched, but nothing checked the base product noun at all).
auto_label() is the same function claude_auto_label.py used for the main
1658-pair audit, so this reuses one already-exercised rule set rather than
inventing a second, weaker one for these 153 pairs.

This is AI adjudication from frozen catalog text, not independent human
review or live verification -- same caveat as every other automated label
in this project.

Usage:
    python3 apply_new_candidate_review.py
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from benchmark_requests import REQUEST_VERSION
from build_benchmark import LABELING_GUIDELINE_VERSION
from claude_auto_label import _product_type_tokens, auto_label
from parse_query import parse_shopping_line

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "evaluation"
NEW_CANDIDATES_PATH = OUT_DIR / "new_candidates_to_review.json"
REQUESTS_PATH = OUT_DIR / "benchmark_requests.json"
MANIFEST_PATH = HERE / "benchmark_manifest.json"
FROZEN_CATALOG = HERE / "benchmark_catalog_frozen.csv"

REVIEWED_BY = "claude_new_candidate_review"


def _core_product_type_confirmed(request: dict, title_lower: str) -> bool:
    """A stricter product-type check than claude_auto_label.py's own, whose
    check has two weaknesses that let a real mismatch slip through
    Acceptable: (1) plain substring containment -- "milk" is a substring of
    "oatmilk" -- and (2) requiring only ANY token to match, so generic words
    like the brand name or "original" alone satisfy it even when the actual
    differentiating noun doesn't match at all. Concretely: "64 fl oz
    Friendly Farms Almond Milk Original" was passing auto_label()'s check
    against a Friendly Farms *oat* milk, because "friendly"/"farms"/
    "original" all substring-match even though "almond" does not.

    This check instead: (a) drops tokens already covered by `expected`'s
    own brand/variant (those are separately, correctly checked by
    auto_label already) to isolate the tokens that actually carry
    product-identity signal, then (b) requires ALL of the remaining tokens
    to match as whole words, not any single one. A failure here downgrades
    an Acceptable to Needs clarification rather than asserting Incorrect
    off a second heuristic that could itself have false negatives."""
    structured = parse_shopping_line(request["text"])
    tokens = _product_type_tokens(structured.get("product_type"))
    if not tokens:
        return True

    expected = request["expected"]
    covered = set((expected.get("brand") or "").lower().split())
    variant = (expected.get("variant") or "").split(",")[0]
    covered |= set(variant.lower().split())
    core_tokens = tokens - covered
    if not core_tokens:
        return True

    return all(re.search(rf"\b{re.escape(tok)}\b", title_lower) for tok in core_tokens)


def _load_catalog_by_key() -> dict:
    by_key = {}
    for row in pd.read_csv(FROZEN_CATALOG, dtype={"product_id": str}).to_dict("records"):
        by_key[(int(row["store_id"]), row["product_id"])] = row
    return by_key


def main():
    if not NEW_CANDIDATES_PATH.exists():
        raise SystemExit(f"{NEW_CANDIDATES_PATH.name} missing -- run run_experiments.py first")

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
        label, reason = auto_label(row, request)

        if label == "Acceptable" and not _core_product_type_confirmed(request, str(row["raw_title"]).lower()):
            label = "Needs clarification"
            reason = (
                "auto_label found no attribute conflict, but the core product-type words "
                "(excluding brand/variant, matched whole-word) are not confirmable in raw_title "
                f"-- original auto_label reason: {reason!r}"
            )

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
            "source": "run_experiments.py full-catalog search, not in the original candidate pool",
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
