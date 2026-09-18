#!/usr/bin/env python3
"""Apply "Claude labels the rest" -- a deliberate, disclosed deviation from
the Checkpoint 3 plan's original "every label is human-reviewed" design.

After starting the full manual review, the user found reviewing all 574
pilot candidate pairs impractical and asked Claude to take over. Rather than
silently doing that (which would make the benchmark fully self-graded --
Claude building the pools, drafting labels, AND being the only "reviewer" --
exactly the circular-verification failure this project hit and fixed once
before, see project memory on Checkpoint 2's manual_review.py redesign),
the agreed compromise is:

  - The user reviews a stratified random sample of the pool directly in
    label_review_ui.py (an independent check that survives in the benchmark
    manifest).
  - Every other candidate is labeled here, by an improved, explicit
    attribute-comparison rule set -- catching the numeric-size bug that the
    user's own spot-check caught in build_candidate_pool.py's rougher draft
    heuristic (which never compared package sizes at all).
  - Every decision this script writes is stamped reviewed_by="claude_auto"
    (vs "human" for ones written via the UI or recorded from the user's
    earlier chat review), so build_benchmark.py and the benchmark docs can
    honestly report the split rather than overstate independent review.

Usage:
    python3 claude_auto_label.py --sample-fraction 0.17
"""
import argparse
import json
import random
from pathlib import Path

import pandas as pd

import benchmark_config as cfg
from benchmark_requests import REQUEST_VERSION, REQUESTS
from label_review_ui import LABELING_GUIDELINE_VERSION, current_catalog_sha256, save_decisions_atomic
from normalize import parse_package_size
from parse_query import parse_shopping_line

HERE = Path(__file__).resolve().parent
CANDIDATE_POOL_PATH = HERE / "candidate_pool.json"
DECISIONS_PATH = HERE / "label_review_decisions.json"
CATALOG_PATH = HERE / "benchmark_catalog_frozen.csv"

SIZE_MISMATCH_TOLERANCE = 0.03  # relative difference beyond which two same-dimension sizes count as different

# The user's own decisions, made in chat while trying the UI before asking
# Claude to take over the rest -- these are genuine independent human
# judgments and are recorded as such (reviewed_by="human"), not overwritten
# by the automated labeler below.
HUMAN_REVIEWED_FROM_CHAT = [
    # (request_id, store_id, product_id, label)
    ("r001", 24325284, "16915213943", "Incorrect"),   # Sprouts French Vanilla Light Roast (10 oz) -- wrong brand+size
    ("r001", 35802549, "30994838145", "Incorrect"),   # Kroger Medium Roast French Vanilla (11 oz) -- wrong brand+size
    ("r001", 29631686, "1000038340833004", "Incorrect"),  # Barissimo Caramel (12 oz) -- wrong flavor
    ("r003", 29631686, "1000013692600004", "Incorrect"),  # Spreadable Butter with Canola Oil (15 oz) -- wrong size/form
    ("r003", 29631686, "1000030409614281", "Incorrect"),  # Salted Butter Quarters (16 oz) -- wrong salt content
    ("r003", 29631686, "1000030409614305", "Acceptable"),  # Unsalted Butter (16 oz) -- exact match (the reference)
    ("r003", 29631686, "40919724364", "Acceptable"),  # Sweet Cream Unsalted Butter (16 oz) -- descriptor, not a conflict
    ("r004", 1042759, "8776479873", "Incorrect"),  # Oatly Barista Edition (32 fl oz) -- wrong variant+size
]


def _decision_key(request_id, store_id, product_id) -> str:
    return f"{request_id}|{store_id}|{product_id}"


def _load_catalog_by_key() -> dict:
    by_key = {}
    for row in pd.read_csv(CATALOG_PATH, dtype={"product_id": str}).to_dict("records"):
        by_key[(int(row["store_id"]), row["product_id"])] = row
    return by_key


# Supplementary flavor/variant words for the specific product domains the
# 50 pilot requests cover (coffee, butter, milk/milk-alternatives, apples,
# chips, cereal, orange juice, ice cream) -- these are real, observed
# sibling-product distinguishers in the frozen catalog (e.g. Barissimo's
# other 12 oz ground coffee flavors besides French Vanilla), not an
# arbitrary general-purpose flavor list. Needed because the authored-variant
# vocabulary alone only covers the ~20 variant values this benchmark's own
# requests happened to specify, which undercounts real confirmable conflicts
# (e.g. nothing requests "Caramel" coffee, so without this list a Caramel
# candidate against a French-Vanilla request would default to "unconfirmable"
# instead of the confirmed conflict it actually is).
_SUPPLEMENTARY_VARIANTS = {
    "caramel", "breakfast blend", "apple crisp", "hazelnut", "dark roast", "medium roast", "light roast",
    "salted", "sweet cream", "spreadable",
    "barista edition", "full fat",
    "gala", "fuji", "pink lady", "cosmic crisp", "granny smith",
    "barbecue", "sour cream", "jalapeno", "salt & vinegar", "flamin hot", "chile limon",
    "cherry garcia", "half baked", "strawberry cheesecake",
    "no pulp", "pulp free", "high pulp", "with pineapple",
    "skim", "non-fat", "nonfat", "low fat",
    "strawberry", "blueberry", "black cherry", "raspberry",
}


def _known_variant_vocabulary() -> dict:
    """variant phrase (lowercased, first comma-segment) -> request_id it
    came from (or "(supplementary)"). Built from every authored request's
    own `expected.variant`, plus _SUPPLEMENTARY_VARIANTS above -- a
    principled (not arbitrary) vocabulary for detecting "title confirms a
    different named variant" versus "title just doesn't say.\""""
    vocab = {}
    for r in REQUESTS:
        variant = r["expected"].get("variant")
        if not variant:
            continue
        phrase = variant.split(",")[0].strip().lower()
        if len(phrase) > 2:
            vocab.setdefault(phrase, r["request_id"])
    for phrase in _SUPPLEMENTARY_VARIANTS:
        vocab.setdefault(phrase, "(supplementary)")
    return vocab


KNOWN_VARIANTS = _known_variant_vocabulary()

# Filler words that survive parse_query.py's modifier extraction but carry
# no product-identity signal -- excluded from the product-type sanity check
# below so they never count as "a matching token" or get blamed for a
# mismatch. Notably includes words that can leak into `product_type` from a
# malformed comma clause (see the pilot audit's "Dozen Roses" finding: the
# request text "a dozen large eggs, any brand is fine" left "any brand is
# fine" stuck onto product_type after the comma-form parse gave up).
_PRODUCT_TYPE_STOPWORDS = {
    "any", "is", "are", "the", "a", "an", "of", "for", "with", "please",
    "brand", "fine", "doesn't", "matter", "one",
    # Generic descriptors that carry no product-identity signal on their
    # own -- "flavored"/"flavor" describes almost any packaged food, so it
    # must not count as a token match on its own (a comma clause like
    # "any flavor" can otherwise leak this in exactly the way "brand"/
    # "fine" leak in from "any brand is fine" -- see the pilot audit's
    # corn-snacks-labeled-as-yogurt finding).
    "flavored", "flavor", "flavors",
}


def _product_type_tokens(product_type: str) -> set:
    tokens = set()
    for word in (product_type or "").lower().split():
        cleaned = word.strip(".,!?;:()")
        if len(cleaned) > 2 and cleaned not in _PRODUCT_TYPE_STOPWORDS:
            tokens.add(cleaned)
    return tokens


def auto_label(row: dict, request: dict) -> tuple:
    """Improved explicit-attribute-comparison labeler: adds numeric package-
    size comparison (missing from build_candidate_pool.py's draft_label --
    the exact gap the human spot-check caught on the "Spreadable Butter,
    15 oz vs 16 oz" and "Oatly Barista Edition, 32 fl oz vs 0.5 gal" cases),
    a known-variant-vocabulary check for confirmed (not just unconfirmable)
    flavor/variant conflicts, and a basic product-type sanity check (the
    pilot audit caught corn snacks labeled Acceptable against a yogurt
    request, and candy against a chips request -- nothing in `expected`
    states the product type explicitly, so without this check a candidate
    that fails on every *other* axis could still slip through as
    Acceptable just because brand/variant/size happen not to apply)."""
    expected = request["expected"]
    structured = parse_shopping_line(request["text"])
    req_dimension = structured.get("dimension")
    substitutions = expected.get("allowed_substitutions", {})
    title = str(row["raw_title"])
    title_lower = title.lower()

    product_type_tokens = _product_type_tokens(structured.get("product_type"))
    if product_type_tokens and not any(tok in title_lower for tok in product_type_tokens):
        return "Incorrect", (
            f"none of the request's product-type words {sorted(product_type_tokens)!r} "
            f"appear anywhere in raw_title -- likely a different product entirely"
        )

    row_dimension = row["pkg_dimension"] if pd.notna(row.get("pkg_dimension")) else None

    if req_dimension and row_dimension and row_dimension != req_dimension:
        if bool(row.get("dimension_review_flag")):
            return "Needs clarification", (
                f"dimension_review_flag set -- literal dimension {row_dimension!r} vs requested "
                f"{req_dimension!r} is genuinely uncertain, not clearly wrong"
            )
        return "Incorrect", f"pkg_dimension {row_dimension!r} != requested dimension {req_dimension!r}"

    expected_size = expected.get("size")
    if expected_size and substitutions.get("size") != "any":
        parsed_expected = parse_package_size(expected_size)
        parsed_row = parse_package_size(str(row.get("raw_size") or ""))
        if (
            not parsed_expected["unresolved"] and not parsed_row["unresolved"]
            and parsed_expected["dimension"] == parsed_row["dimension"]
            and parsed_expected["canonical_total"] and parsed_row["canonical_total"]
        ):
            rel_diff = abs(parsed_row["canonical_total"] - parsed_expected["canonical_total"]) / parsed_expected["canonical_total"]
            if rel_diff > SIZE_MISMATCH_TOLERANCE:
                return "Incorrect", (
                    f"size mismatch: expected {expected_size!r} "
                    f"({parsed_expected['canonical_total']:.2f} {parsed_expected['canonical_unit']}), "
                    f"candidate is {row.get('raw_size')!r} "
                    f"({parsed_row['canonical_total']:.2f} {parsed_row['canonical_unit']})"
                )

    brand = expected.get("brand")
    if brand and substitutions.get("brand") != "any":
        if brand.lower() not in title_lower:
            return "Incorrect", f"expected brand {brand!r} not found in raw_title"

    variant = expected.get("variant")
    if variant and substitutions.get("flavor") != "any" and substitutions.get("variant") != "any":
        primary_variant = variant.split(",")[0].strip().lower()
        if primary_variant not in title_lower:
            conflicting = [
                v for v, owner in KNOWN_VARIANTS.items()
                if v != primary_variant and v in title_lower
            ]
            if conflicting:
                return "Incorrect", f"title confirms a different named variant ({conflicting[0]!r}), not {variant!r}"
            return "Needs clarification", f"expected variant {variant!r} not confirmable from raw_title alone"

    return "Acceptable", "no explicit-attribute conflict found (dimension, size, brand, variant all checked)"


def stratified_sample(pools: list, already_decided: set, fraction: float, seed: int) -> set:
    """Pick a subset of (request_id, store_id, product_id) keys for human
    review, proportionally per request (so every request gets at least one
    sampled item where possible), deterministic given `seed`."""
    rng = random.Random(seed)
    sample = set()
    for pool in pools:
        remaining = [
            (pool["request_id"], c["store_id"], c["product_id"])
            for c in pool["candidates"]
            if (pool["request_id"], c["store_id"], c["product_id"]) not in already_decided
        ]
        if not remaining:
            continue
        n = max(1, round(len(remaining) * fraction))
        n = min(n, len(remaining))
        sample.update(rng.sample(remaining, n))
    return sample


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-fraction", type=float, default=0.17)
    args = parser.parse_args()

    pools = json.loads(CANDIDATE_POOL_PATH.read_text())
    catalog_by_key = _load_catalog_by_key()
    requests_by_id = {r["request_id"]: r for r in REQUESTS}

    decisions = json.loads(DECISIONS_PATH.read_text()) if DECISIONS_PATH.exists() else {}

    # Any pre-existing decision without a reviewed_by tag was written by an
    # older version of label_review_ui.py's /api/decide (before that field
    # existed) -- it's a genuine decision the user made by clicking in the
    # UI, so it's backfilled as "human", never silently dropped or
    # re-labeled.
    for d in decisions.values():
        d.setdefault("reviewed_by", "human")

    already_decided = set()
    for request_id, store_id, product_id, label in HUMAN_REVIEWED_FROM_CHAT:
        key = _decision_key(request_id, store_id, product_id)
        decisions[key] = {
            "request_id": request_id, "store_id": store_id, "product_id": product_id,
            "reviewer_label": label,
            "catalog_version_sha256": current_catalog_sha256(),
            "request_version": REQUEST_VERSION,
            "labeling_guideline_version": LABELING_GUIDELINE_VERSION,
            "reviewed_by": "human",
            "revealed": False, "draft_label": None, "agreed_with_draft": None,
        }
        already_decided.add((request_id, store_id, product_id))
    for key, d in decisions.items():
        already_decided.add((d["request_id"], d["store_id"], d["product_id"]))

    sample = stratified_sample(pools, already_decided, args.sample_fraction, cfg.RANDOM_SEED)

    auto_labeled = 0
    for pool in pools:
        request = requests_by_id[pool["request_id"]]
        for c in pool["candidates"]:
            triple = (pool["request_id"], c["store_id"], c["product_id"])
            if triple in already_decided or triple in sample:
                continue  # already human-decided, or reserved for the human sample
            row = catalog_by_key.get((c["store_id"], c["product_id"]))
            if row is None:
                continue
            label, reason = auto_label(row, request)
            key = _decision_key(*triple)
            decisions[key] = {
                "request_id": triple[0], "store_id": triple[1], "product_id": triple[2],
                "reviewer_label": label,
                "catalog_version_sha256": current_catalog_sha256(),
                "request_version": REQUEST_VERSION,
                "labeling_guideline_version": LABELING_GUIDELINE_VERSION,
                "reviewed_by": "claude_auto",
                "reviewed_by_reason": reason,
                "revealed": False, "draft_label": None, "agreed_with_draft": None,
            }
            auto_labeled += 1

    save_decisions_atomic(decisions)

    total_candidates = sum(len(p["candidates"]) for p in pools)
    print(f"total candidates: {total_candidates}")
    print(f"human-reviewed (chat, already recorded): {len(HUMAN_REVIEWED_FROM_CHAT)}")
    print(f"reserved for human review in the UI (sample): {len(sample)}")
    print(f"claude_auto labeled: {auto_labeled}")
    print(f"decisions.json total entries: {len(decisions)}")


if __name__ == "__main__":
    main()
