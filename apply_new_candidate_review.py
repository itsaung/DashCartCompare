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
from claude_auto_label import KNOWN_VARIANTS, _product_type_tokens, auto_label
from normalize import parse_package_size
from parse_query import parse_shopping_line

# Product-type words that are false friends across genuinely different
# product families in this catalog -- the bare word is technically present
# and "matches" a title, but names a different kind of product entirely.
# Found via a real false positive: "a bag of chips" (no other qualifier)
# matched "Ghirardelli Premium Milk Chocolate Baking Chips" -- the exact
# same failure class the original 2026-09-18 audit already corrected for
# other candidates in this same request's original pool (r048/r049), now
# reappearing in a newly-discovered candidate outside that pool. A match
# here is a CONFIRMED conflict, not mere unconfirmability, so it asserts
# Incorrect -- the same treatment the original audit gave the other
# baking-chips candidates on this exact request.
_FALSE_FRIEND_PHRASES = {
    "chips": ["chocolate chips", "baking chips", "morsels"],
}

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


def _variant_not_shadowed_by_a_more_specific_known_variant(request: dict, title_lower: str) -> bool:
    """auto_label()'s own variant-conflict check only runs when the
    expected variant phrase is NOT found in the title at all
    (`if primary_variant not in title_lower`) -- so when the expected
    phrase is itself a substring of a different, more specific KNOWN_VARIANTS
    phrase that's actually in the title (e.g. expected "large" vs a title
    that says "extra large"), that substring match satisfies the check
    before the conflict-detection code ever runs, and the real conflict is
    never caught. This checks for exactly that shadowing, independent of
    auto_label's own control flow. True = no such shadowing found."""
    expected = request["expected"]
    variant = expected.get("variant")
    substitutions = expected.get("allowed_substitutions", {})
    if not variant or substitutions.get("flavor") == "any" or substitutions.get("variant") == "any":
        return True
    primary = variant.split(",")[0].strip().lower()
    if not primary:
        return True
    for known in KNOWN_VARIANTS:
        if known != primary and primary in known and known in title_lower:
            return False
    return True


def _no_false_friend_product_type_conflict(request: dict, title_lower: str) -> bool:
    """See _FALSE_FRIEND_PHRASES. True = no conflicting phrase found."""
    structured = parse_shopping_line(request["text"])
    tokens = _product_type_tokens(structured.get("product_type"))
    for token in tokens:
        for phrase in _FALSE_FRIEND_PHRASES.get(token, []):
            if phrase in title_lower:
                return False
    return True


# Only applied when the expected/candidate sizes were printed in DIFFERENT
# raw units (a genuine metric<->imperial conversion, e.g. "2 L" printed
# against a candidate labeled "67.6 fl oz") -- never as a same-unit fudge
# factor. The guideline's own examples (2 L/67.6 fl oz: 0.04% off; 946 ml/
# 32 fl oz: 0.006% off) are both far inside this; it exists only to absorb
# real label-rounding on a genuine unit conversion, not to blur distinct
# printed sizes.
_UNIT_CONVERSION_ROUNDING_TOLERANCE = 0.01  # relative


def _size_confirmed_without_arbitrary_tolerance(request: dict, candidate: dict) -> bool:
    """auto_label() allows a 3% relative-size tolerance (SIZE_MISMATCH_TOLERANCE)
    that LABELING_GUIDELINES.md v2 explicitly rejects: "Distinct printed
    sizes are distinct packages... not an arbitrary three-percent size
    tolerance." Found via a real false positive: "15 oz cereal" matched a
    "15.4 oz" candidate (2.7% off -- inside auto_label's 3% tolerance, but
    both sizes are printed in the SAME unit, "oz", so there is no unit-
    conversion excuse for the difference; "15 oz" and "15.4 oz" are simply
    distinct printed sizes. This re-checks: exact match (up to floating-
    point precision) when both sizes share a raw printed unit; only a tight
    tolerance for genuine cross-unit rounding when they don't (see
    _UNIT_CONVERSION_ROUNDING_TOLERANCE). True = no conflict found (either
    no expected size, or the sizes pass one of those two checks)."""
    expected = request["expected"]
    size = expected.get("size")
    substitutions = expected.get("allowed_substitutions", {})
    if not size or substitutions.get("size") == "any":
        return True
    parsed_expected = parse_package_size(size)
    parsed_candidate = parse_package_size(str(candidate.get("raw_size") or ""))
    if (
        parsed_expected["unresolved"] or parsed_candidate["unresolved"]
        or parsed_expected["dimension"] != parsed_candidate["dimension"]
        or not parsed_expected["canonical_total"] or not parsed_candidate["canonical_total"]
    ):
        return True  # can't compare -- not this check's job to flag unresolvable sizes

    if parsed_expected["unit"] == parsed_candidate["unit"]:
        return abs(parsed_candidate["canonical_total"] - parsed_expected["canonical_total"]) < 1e-6

    rel_diff = abs(parsed_candidate["canonical_total"] - parsed_expected["canonical_total"]) / parsed_expected["canonical_total"]
    return rel_diff <= _UNIT_CONVERSION_ROUNDING_TOLERANCE


def _load_catalog_by_key() -> dict:
    by_key = {}
    for row in pd.read_csv(FROZEN_CATALOG, dtype={"product_id": str}).to_dict("records"):
        by_key[(int(row["store_id"]), row["product_id"])] = row
    return by_key


def adjudicate_new_candidate(request: dict, row) -> tuple:
    """Returns (label, reason). Starts from auto_label()'s own verdict, then
    applies four additional checks written against real false positives
    found while reviewing these 153 pairs (see module docstring). Each
    check only ever runs when auto_label said Acceptable, and each
    distinguishes a CONFIRMED conflict (a specific different value is
    actually present in raw_title, or two sizes both parse and genuinely
    differ) -- which asserts Incorrect, matching auto_label's own
    convention for the same situation -- from mere unconfirmability (the
    core product-type words are simply absent, which could mean many
    things), which downgrades to Needs clarification instead."""
    label, reason = auto_label(row, request)
    title_lower = str(row["raw_title"]).lower()

    if label == "Acceptable" and not _core_product_type_confirmed(request, title_lower):
        label = "Needs clarification"
        reason = (
            "auto_label found no attribute conflict, but the core product-type words "
            "(excluding brand/variant, matched whole-word) are not confirmable in raw_title "
            f"-- original auto_label reason: {reason!r}"
        )
    elif label == "Acceptable" and not _variant_not_shadowed_by_a_more_specific_known_variant(request, title_lower):
        # A CONFIRMED conflict, not mere unconfirmability -- raw_title
        # names a specific, different, more-specific known variant
        # (e.g. "extra large" present when "large" was requested).
        # Matches auto_label's own convention for this exact situation
        # ("title confirms a different named variant" -> Incorrect).
        label = "Incorrect"
        reason = (
            "raw_title confirms a different, more specific known variant phrase than the one "
            f"requested (a substring-shadowed conflict) -- original auto_label reason: {reason!r}"
        )
    elif label == "Acceptable" and not _no_false_friend_product_type_conflict(request, title_lower):
        # Also a confirmed conflict: raw_title names a specific
        # different product family (e.g. "chocolate chips" when a
        # generic "chips" snack was requested), not just an
        # unconfirmable word.
        label = "Incorrect"
        reason = (
            "raw_title contains a known false-friend phrase for this product-type word "
            f"(different product family, same word) -- original auto_label reason: {reason!r}"
        )
    elif label == "Acceptable" and not _size_confirmed_without_arbitrary_tolerance(request, row):
        # Also a confirmed conflict: both sizes parsed successfully and
        # differ beyond genuine unit-conversion rounding -- "Distinct
        # printed sizes are distinct packages" (LABELING_GUIDELINES.md
        # v2). Matches auto_label's own convention for a size mismatch
        # beyond its own (looser) tolerance -> Incorrect, not Needs
        # clarification.
        label = "Incorrect"
        reason = (
            "auto_label's size match relied on its 3% tolerance band rather than unit-"
            f"equivalent equality -- distinct printed sizes are distinct packages -- original auto_label reason: {reason!r}"
        )

    return label, reason


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
