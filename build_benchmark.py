#!/usr/bin/env python3
"""Checkpoint 3 evaluation, Checkpoint E1: validate every input the
benchmark depends on and export evaluation-ready records.

This script never regenerates requests, overwrites label_review_decisions.json,
refits normalization, or scrapes -- it only reads the already-frozen catalog,
already-authored requests, already-built candidate pool, and already-reviewed
decisions, checks that they are mutually consistent, and -- only if every
check passes -- writes three files under evaluation/:

  benchmark_pairs.jsonl    -- one JSON object per (request_id, store_id,
                               product_id) pair currently in the candidate
                               pool, carrying both label views (practical
                               reviewer_label and the conservative view),
                               evidence quality, and the versions the
                               decision was made under. This is for grading
                               predictions later -- never fed to the matcher.
  benchmark_requests.json  -- the full REQUESTS records (including `expected`
                               and reference/hard-negative ids), for
                               denominators, split grouping, and analysis.
                               The matcher under test (retrieval.py's
                               attribute_filter_baseline) only ever receives
                               a request's raw `text`, regardless of what
                               this file contains.
  validation_report.json   -- always written, pass or fail: every check run,
                               its result, and a request-level answerability
                               audit (see below).

If any check fails, the two data files are NOT written (a stale/inconsistent
benchmark must not silently look frozen); validation_report.json still is,
so the failure is visible.

Usage:
    python3 build_benchmark.py
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from benchmark_requests import REQUEST_VERSION, REQUESTS

HERE = Path(__file__).resolve().parent
FROZEN_CATALOG = HERE / "benchmark_catalog_frozen.csv"
CANDIDATE_POOL_PATH = HERE / "candidate_pool.json"
DECISIONS_PATH = HERE / "label_review_decisions.json"
MANIFEST_PATH = HERE / "benchmark_manifest.json"
OUT_DIR = HERE / "evaluation"

# Kept in sync by hand with the "Version: vN" line at the top of
# LABELING_GUIDELINES.md and LABELING_GUIDELINE_VERSION in label_review_ui.py.
LABELING_GUIDELINE_VERSION = "v2"

VALID_LABELS = {"Acceptable", "Needs clarification", "Incorrect"}

# The original pilot's request ids, exactly as authored in the first
# `REQUESTS = [...]` block of benchmark_requests.py (before the two
# `REQUESTS += [...]` extensions added the other 104 requests). IDs have
# gaps -- r002, r005, r043, r044 were never used -- so this is the actual
# pilot membership by id, not a numeric range like "r001".."r050".
PILOT_REQUEST_IDS = frozenset([
    "r001", "r003", "r004", "r006", "r007", "r008", "r009", "r010", "r011",
    "r012", "r013", "r014", "r015", "r016", "r017", "r018", "r019", "r020",
    "r021", "r022", "r023", "r024", "r025", "r026", "r027", "r028", "r029",
    "r030", "r031", "r032", "r033", "r034", "r035", "r036", "r037", "r038",
    "r039", "r040", "r041", "r042", "r045", "r046", "r047", "r048", "r049",
    "r050",
])

# Request-level answerability audit for the 11 "no_acceptable_match"
# requests (Checkpoint E1's "check the 11 no-match assertions with targeted
# catalog searches" step). Each entry records what was actually checked
# against the full 31,398-row frozen catalog (not just the request's small
# candidate pool) and the resulting confidence. This is deliberately kept in
# code, not silently asserted, so a future re-check can see exactly what
# search was run and challenge it.
NO_MATCH_AUDIT = {
    "r039": {
        "confidence": "confirmed",
        "method": "full-catalog title search for 'unsalted'+'butter'",
        "finding": "Only 8 oz/16 oz dairy butter and one unrelated 12 oz "
                   "macadamia NUT butter exist; no 12 oz unsalted dairy "
                   "butter. Recorded in the 2026-09-18 label audit.",
    },
    "r051": {
        "confidence": "confirmed",
        "method": "full-catalog raw_size search over all 171 "
                   "'chicken'+'breast' rows",
        "finding": "No row has raw_size == '2 lb' (32 oz); fixed packages "
                   "cluster at 1 lb, 16-29 oz, or are sold 'by pound' "
                   "(variable weight, excluded per policy).",
    },
    "r052": {
        "confidence": "pattern-consistent, not independently re-searched",
        "method": "none beyond the candidate pool",
        "finding": "Bananas are sold by bunch or 'each' with per-pound "
                   "pricing, never as a fixed 3-count package; consistent "
                   "with r051's confirmed pattern but not itself searched.",
    },
    "r053": {
        "confidence": "confirmed by construction",
        "method": "none needed",
        "finding": "'1 lb' of a liquid (oat milk) is a dimension mismatch "
                   "by definition -- no catalog search can produce a weight "
                   "match for a beverage.",
    },
    "r054": {
        "confidence": "pattern-consistent, not independently re-searched",
        "method": "none beyond the candidate pool",
        "finding": "5 gal (640 fl oz) is far outside any observed retail "
                   "milk packaging (largest seen is under 1 gal); plausible "
                   "by inspection but not exhaustively searched.",
    },
    "r129": {
        "confidence": "pattern-consistent, not independently re-searched",
        "method": "none beyond the candidate pool",
        "finding": "Salmon fillets are sold by weight/pack, not as a fixed "
                   "'2 fillets' unit; consistent with r051's confirmed "
                   "pattern but not itself searched.",
    },
    "r130": {
        "confidence": "pattern-consistent, not independently re-searched",
        "method": "full-catalog raw_size search over all 133 "
                   "'turkey'+'breast' rows (shared with r051's check)",
        "finding": "No fixed '3-breast' unit; deli turkey is sold by "
                   "weight/ct or 'by pound'.",
    },
    "r131": {
        "confidence": "confirmed by construction",
        "method": "none needed",
        "finding": "100 ct of individually-wrapped granola bars is far "
                   "outside any observed multipack count (largest seen is "
                   "18 ct); not a catalog-search question.",
    },
    "r132": {
        "confidence": "confirmed by construction",
        "method": "none needed",
        "finding": "'1 lb' of sparkling water is a dimension mismatch by "
                   "definition (weight requested for a liquid).",
    },
    "r133": {
        "confidence": "confirmed by construction",
        "method": "none needed",
        "finding": "10 gal of sparkling water is far outside any observed "
                   "retail beverage packaging.",
    },
    "r154": {
        "confidence": "confirmed by construction",
        "method": "none needed",
        "finding": "Same product/count as r131 (paraphrase), same finding.",
    },
}


def _sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_json(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def _load_catalog() -> pd.DataFrame:
    return pd.read_csv(FROZEN_CATALOG, dtype={"product_id": str})


def _decision_key(request_id, store_id, product_id) -> str:
    return f"{request_id}|{store_id}|{product_id}"


def _request_content_hashes() -> dict:
    return {r["request_id"]: _sha256_json(r) for r in REQUESTS}


def validate(catalog_df, pool, decisions, manifest) -> dict:
    """Run every Checkpoint E1 check. Returns a report dict with a top-level
    `pass` bool and per-check detail; never raises -- callers decide what to
    do with a failing report."""
    errors = []
    warnings = []
    checks = {}

    def record(name, ok, count, examples=None):
        checks[name] = {
            "status": "pass" if ok else "fail",
            "count": count,
            "examples": (examples or [])[:10],
        }
        if not ok:
            errors.append(name)

    # -- manifest self-consistency -------------------------------------
    actual_catalog_sha = _sha256_bytes(FROZEN_CATALOG)
    manifest_catalog_sha = manifest.get("catalog_version", {}).get("sha256")
    record("manifest_catalog_hash_matches_file",
           actual_catalog_sha == manifest_catalog_sha, 0 if actual_catalog_sha == manifest_catalog_sha else 1,
           [] if actual_catalog_sha == manifest_catalog_sha else [{"expected": manifest_catalog_sha, "actual": actual_catalog_sha}])

    actual_decisions_sha = _sha256_bytes(DECISIONS_PATH)
    manifest_decisions_sha = manifest.get("current_decisions_sha256")
    record("manifest_decisions_hash_matches_file",
           actual_decisions_sha == manifest_decisions_sha, 0 if actual_decisions_sha == manifest_decisions_sha else 1,
           [] if actual_decisions_sha == manifest_decisions_sha else [{"expected": manifest_decisions_sha, "actual": actual_decisions_sha}])

    # -- request ids ------------------------------------------------------
    request_ids = [r["request_id"] for r in REQUESTS]
    dupe_request_ids = sorted({rid for rid in request_ids if request_ids.count(rid) > 1})
    record("no_duplicate_request_ids", not dupe_request_ids, len(dupe_request_ids), dupe_request_ids)

    missing_pilot_ids = sorted(PILOT_REQUEST_IDS - set(request_ids))
    record("pilot_ids_present_in_requests", not missing_pilot_ids, len(missing_pilot_ids), missing_pilot_ids)

    # -- catalog identity ---------------------------------------------------
    dupe_catalog = catalog_df[catalog_df.duplicated(subset=["store_id", "product_id"], keep=False)]
    dupe_catalog_examples = [
        {"store_id": int(r.store_id), "product_id": r.product_id}
        for r in dupe_catalog.itertuples()
    ]
    record("no_duplicate_catalog_identities", dupe_catalog.empty, len(dupe_catalog), dupe_catalog_examples)

    catalog_ids = set(zip(catalog_df["store_id"], catalog_df["product_id"].astype(str)))

    # -- per-pair checks ------------------------------------------------
    req_hash = _request_content_hashes()
    pool_by_req = {p["request_id"]: p["candidates"] for p in pool}

    missing_products = []
    missing_decisions = []
    dup_pairs = []
    invalid_labels = []
    version_mismatches = []
    guesses_without_conservative = []
    pool_keys = set()

    for p in pool:
        rid = p["request_id"]
        seen = set()
        for c in p["candidates"]:
            key = (int(c["store_id"]), str(c["product_id"]))
            dkey = _decision_key(rid, key[0], key[1])
            pool_keys.add(dkey)

            if key in seen:
                dup_pairs.append(dkey)
            seen.add(key)

            if key not in catalog_ids:
                missing_products.append(dkey)

            dec = decisions.get(dkey)
            if dec is None:
                missing_decisions.append(dkey)
                continue

            if dec.get("reviewer_label") not in VALID_LABELS:
                invalid_labels.append({"key": dkey, "label": dec.get("reviewer_label")})

            if dec.get("catalog_version_sha256") != manifest_catalog_sha:
                version_mismatches.append({"key": dkey, "field": "catalog_version_sha256"})
            if dec.get("request_version") != REQUEST_VERSION:
                version_mismatches.append({"key": dkey, "field": "request_version"})
            if dec.get("labeling_guideline_version") != LABELING_GUIDELINE_VERSION:
                version_mismatches.append({"key": dkey, "field": "labeling_guideline_version"})
            if dec.get("request_content_sha256") != req_hash.get(rid):
                version_mismatches.append({"key": dkey, "field": "request_content_sha256"})

            if dec.get("is_best_guess") and not dec.get("conservative_label"):
                guesses_without_conservative.append(dkey)

    record("every_pair_product_in_catalog", not missing_products, len(missing_products), missing_products)
    record("every_pair_has_a_decision", not missing_decisions, len(missing_decisions), missing_decisions)
    record("no_duplicate_pairs_within_a_pool", not dup_pairs, len(dup_pairs), dup_pairs)
    record("all_reviewer_labels_valid", not invalid_labels, len(invalid_labels), invalid_labels)
    record("no_version_or_hash_mismatches", not version_mismatches, len(version_mismatches), version_mismatches)
    record("guessed_labels_carry_conservative_interpretation",
           not guesses_without_conservative, len(guesses_without_conservative), guesses_without_conservative)

    # Decisions outside the current pool are not an error -- they're
    # historical provenance (earlier pool memberships) that label_audit
    # already preserves separately -- but the count is reported so it's
    # never silently invisible.
    obsolete_decisions = sorted(k for k in decisions if k not in pool_keys)
    checks["decisions_outside_current_pool"] = {
        "status": "info",
        "count": len(obsolete_decisions),
        "examples": obsolete_decisions[:10],
    }

    # -- paraphrase-group label conflicts -----------------------------------
    group_of = {r["request_id"]: r["paraphrase_group"] for r in REQUESTS}
    group_members = {}
    for rid, g in group_of.items():
        group_members.setdefault(g, []).append(rid)

    conflicts = []
    for g, rids in group_members.items():
        if len(rids) < 2:
            continue
        label_by_product = {}
        for rid in rids:
            for c in pool_by_req.get(rid, []):
                key = (int(c["store_id"]), str(c["product_id"]))
                dec = decisions.get(_decision_key(rid, key[0], key[1]))
                if dec is None:
                    continue
                label_by_product.setdefault(key, set()).add(dec.get("reviewer_label"))
        for key, labels in label_by_product.items():
            if len(labels) > 1:
                conflicts.append({"group": g, "store_id": key[0], "product_id": key[1], "labels": sorted(labels)})
    record("no_paraphrase_group_label_conflicts", not conflicts, len(conflicts), conflicts)

    # -- request-level answerability audit -----------------------------
    pilot_groups = {group_of[rid] for rid in PILOT_REQUEST_IDS if rid in group_of}
    non_pilot_overlap = sorted(
        rid for rid in group_of
        if rid not in PILOT_REQUEST_IDS and group_of[rid] in pilot_groups
    )
    record("pilot_groups_disjoint_from_non_pilot_requests", not non_pilot_overlap, len(non_pilot_overlap), non_pilot_overlap)

    no_match_ids = sorted(r["request_id"] for r in REQUESTS if r["answerability"] == "no_acceptable_match")
    unaudited_no_match = sorted(rid for rid in no_match_ids if rid not in NO_MATCH_AUDIT)
    record("every_no_match_request_has_an_audit_entry", not unaudited_no_match, len(unaudited_no_match), unaudited_no_match)

    answerable_without_positive = []
    for r in REQUESTS:
        if r["answerability"] != "answerable":
            continue
        has_positive = any(
            decisions.get(_decision_key(r["request_id"], c["store_id"], c["product_id"]), {}).get("reviewer_label") == "Acceptable"
            for c in pool_by_req.get(r["request_id"], [])
        )
        if not has_positive:
            answerable_without_positive.append(r["request_id"])
    checks["answerable_requests_with_no_known_positive_in_pool"] = {
        "status": "info" if not answerable_without_positive else "warn",
        "count": len(answerable_without_positive),
        "examples": answerable_without_positive[:10],
    }
    if answerable_without_positive:
        warnings.append("answerable_requests_with_no_known_positive_in_pool")

    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ"),
        "catalog_version_sha256": manifest_catalog_sha,
        "request_version": REQUEST_VERSION,
        "labeling_guideline_version": LABELING_GUIDELINE_VERSION,
        "requests_total": len(REQUESTS),
        "pilot_requests_total": len(PILOT_REQUEST_IDS),
        "pairs_total": sum(len(p["candidates"]) for p in pool),
        "checks": checks,
        "request_level_answerability_audit": {
            "no_acceptable_match_requests": no_match_ids,
            "audit": NO_MATCH_AUDIT,
        },
        "errors": errors,
        "warnings": warnings,
        "pass": not errors,
    }
    return report


def export_pairs(pool, decisions) -> list:
    rows = []
    for p in pool:
        rid = p["request_id"]
        for c in p["candidates"]:
            store_id, product_id = int(c["store_id"]), str(c["product_id"])
            dec = decisions[_decision_key(rid, store_id, product_id)]
            reviewer_label = dec["reviewer_label"]
            rows.append({
                "request_id": rid,
                "store_id": store_id,
                "product_id": product_id,
                "reviewer_label": reviewer_label,
                "conservative_label": dec.get("conservative_label", reviewer_label),
                "is_best_guess": bool(dec.get("is_best_guess", False)),
                "label_quality": dec.get("label_quality"),
                "reviewed_by": dec.get("reviewed_by"),
                "request_version": dec.get("request_version"),
                "labeling_guideline_version": dec.get("labeling_guideline_version"),
                "catalog_version_sha256": dec.get("catalog_version_sha256"),
            })
    return rows


def export_requests() -> list:
    return [
        {**r, "is_pilot": r["request_id"] in PILOT_REQUEST_IDS}
        for r in REQUESTS
    ]


def main():
    if not MANIFEST_PATH.exists():
        raise SystemExit(f"{MANIFEST_PATH.name} missing -- run freeze_catalog.py first")
    if not CANDIDATE_POOL_PATH.exists():
        raise SystemExit(f"{CANDIDATE_POOL_PATH.name} missing -- run build_candidate_pool.py first")

    manifest = json.loads(MANIFEST_PATH.read_text())
    pool = json.loads(CANDIDATE_POOL_PATH.read_text())
    decisions = json.loads(DECISIONS_PATH.read_text())
    catalog_df = _load_catalog()

    report = validate(catalog_df, pool, decisions, manifest)

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "validation_report.json").write_text(json.dumps(report, indent=2))

    if not report["pass"]:
        print(f"Validation FAILED: {report['errors']}")
        print(f"See {OUT_DIR / 'validation_report.json'}")
        raise SystemExit(1)

    pairs = export_pairs(pool, decisions)
    with open(OUT_DIR / "benchmark_pairs.jsonl", "w") as f:
        for row in pairs:
            f.write(json.dumps(row) + "\n")

    requests_out = export_requests()
    (OUT_DIR / "benchmark_requests.json").write_text(json.dumps(requests_out, indent=2))

    print(f"Validation passed ({len(report['checks'])} checks).")
    if report["warnings"]:
        print(f"Warnings: {report['warnings']}")
    print(f"Wrote {len(pairs)} pairs -> {OUT_DIR / 'benchmark_pairs.jsonl'}")
    print(f"Wrote {len(requests_out)} requests -> {OUT_DIR / 'benchmark_requests.json'}")
    print(f"Wrote {OUT_DIR / 'validation_report.json'}")


if __name__ == "__main__":
    main()
