#!/usr/bin/env python3
"""Build candidate_pool.json: for every request in benchmark_requests.py,
gather a labeled-pending candidate pool from lexical retrieval,
synonym-assisted retrieval, the authored reference product(s), and any
authored hard negatives.

This pool is later reviewed end-to-end by label_review_ui.py -- everything
here is a *draft* (source + draft_label + draft_reason), never a final
decision. tfidf_baseline.py's pool-ranking experiment only ever scores
against reviewed decisions in label_review_decisions.json, not this file.

Usage:
    python3 build_candidate_pool.py
"""
import hashlib
import json
from pathlib import Path

import pandas as pd

import benchmark_config as cfg
from benchmark_requests import REQUEST_VERSION, REQUESTS
from parse_query import parse_shopping_line
from retrieval import fit_tfidf, lexical_search, synonym_assisted_search

HERE = Path(__file__).resolve().parent
FROZEN_CATALOG = HERE / "benchmark_catalog_frozen.csv"
OUT_PATH = HERE / "candidate_pool.json"
MANIFEST_PATH = HERE / "benchmark_manifest.json"


def _load_catalog() -> pd.DataFrame:
    return pd.read_csv(FROZEN_CATALOG, dtype={"product_id": str})


def _row_for(catalog_df, store_id, product_id):
    match = catalog_df[(catalog_df["store_id"] == store_id) & (catalog_df["product_id"] == product_id)]
    if match.empty:
        return None
    return match.iloc[0]


def draft_label(row, request: dict) -> tuple:
    """A rough, explicit-attribute-comparison guess at a label -- never
    trusted as final. Returns (label, reason). Every branch is a documented
    rule, per LABELING_GUIDELINES.md, so a reviewer can see why the draft
    says what it says (and override it)."""
    expected = request["expected"]
    structured = parse_shopping_line(request["text"])
    req_dimension = structured.get("dimension")
    substitutions = expected.get("allowed_substitutions", {})

    # row["pkg_dimension"] can be float NaN for a row with no parsed package
    # size at all (e.g. a variable-weight item) -- bool(nan) is True in
    # Python, so an unguarded truthy check here would misreport "unknown" as
    # "confirmed mismatch". pd.notna() treats it as the "unknown" it is.
    row_dimension = row["pkg_dimension"] if pd.notna(row["pkg_dimension"]) else None

    if req_dimension and row_dimension and row_dimension != req_dimension:
        if bool(row.get("dimension_review_flag")):
            return "Needs clarification", (
                f"dimension_review_flag is set (bare 'oz' on a likely-liquid product) -- "
                f"literal parse is {row_dimension!r} vs requested {req_dimension!r}, "
                "genuinely uncertain rather than clearly wrong"
            )
        return "Incorrect", f"pkg_dimension {row_dimension!r} != requested dimension {req_dimension!r}"

    brand = expected.get("brand")
    if brand and substitutions.get("brand") != "any":
        if brand.lower() not in str(row["raw_title"]).lower():
            return "Incorrect", f"expected brand {brand!r} not found in raw_title"

    variant = expected.get("variant")
    if variant and substitutions.get("flavor") != "any" and substitutions.get("variant") != "any":
        if variant.split(",")[0].strip().lower() not in str(row["raw_title"]).lower():
            return "Needs clarification", f"expected variant/flavor {variant!r} not confirmable from raw_title alone"

    return "Acceptable", "no explicit-attribute conflict found against expected fields"


def _candidate(store_id, product_id, source, score=None):
    return {"store_id": int(store_id), "product_id": str(product_id), "sources": [source],
            "scores": {source: score} if score is not None else {}}


def _merge(candidates: dict, store_id, product_id, source, score=None):
    key = (int(store_id), str(product_id))
    if key not in candidates:
        candidates[key] = _candidate(store_id, product_id, source, score)
    else:
        c = candidates[key]
        if source not in c["sources"]:
            c["sources"].append(source)
        if score is not None:
            c["scores"][source] = score


def _best_score(c: dict) -> float:
    return max(c["scores"].values()) if c["scores"] else 0.0


def _cap_pool(candidates: dict, max_pool_size: int = cfg.MAX_POOL_SIZE) -> dict:
    """Enforce the pool-size cap. references and hard_negatives are never
    trimmed (they're the deliberately-authored ground truth and known-wrong
    cases); only lexical/synonym-only candidates are, lowest score first,
    with a deterministic (store_id, product_id) tie-break -- never
    insertion/dict order."""
    protected = {k: v for k, v in candidates.items() if "reference" in v["sources"] or "hard_negative" in v["sources"]}
    trimmable = {k: v for k, v in candidates.items() if k not in protected}

    trimmable_sorted = sorted(trimmable.items(), key=lambda kv: (-_best_score(kv[1]), kv[0][0], kv[0][1]))
    room = max(max_pool_size - len(protected), 0)
    kept_trimmable = dict(trimmable_sorted[:room])

    return {**protected, **kept_trimmable}


def _pool_query_text(structured: dict, fallback_text: str) -> str:
    """The query text used to BUILD the candidate pool -- deliberately not
    the raw request text. A raw shopping-list line still carries quantity
    words ("a dozen", "3", "lb") that TF-IDF treats as ordinary content
    terms; the pilot audit caught this directly ("a dozen large eggs, ..."
    pulled in a "Dozen Roses" listing purely because "dozen" matched
    literally). attribute_filter_baseline -- the actual system under test,
    in retrieval.py -- still searches on the raw text, since that's an
    honest measurement of the baseline's own behavior; this function only
    affects how thoroughly the *labeling pool* is populated, which is a
    different concern from testing the baseline fairly."""
    product_type = (structured.get("product_type") or "").strip()
    modifiers = " ".join(structured.get("modifiers") or [])
    query = f"{modifiers} {product_type}".strip()
    return query or fallback_text


def build_pool_for_request(request: dict, catalog_df, vectorizer, matrix) -> dict:
    candidates = {}

    structured = parse_shopping_line(request["text"])
    query_text = _pool_query_text(structured, request["text"])

    for c in lexical_search(query_text, vectorizer, matrix, catalog_df, top_k=cfg.MAX_LEXICAL_CANDIDATES):
        _merge(candidates, c["store_id"], c["product_id"], "lexical", c["score"])

    for c in synonym_assisted_search(structured, catalog_df, top_k=cfg.MAX_SYNONYM_CANDIDATES):
        _merge(candidates, c["store_id"], c["product_id"], "synonym", c["score"])

    for store_id, product_id in request["hard_negative_product_ids"][: cfg.MAX_HARD_NEGATIVES]:
        _merge(candidates, store_id, product_id, "hard_negative")

    for store_id, product_id in request["reference_product_ids"]:
        _merge(candidates, store_id, product_id, "reference")

    final = _cap_pool(candidates)

    out_candidates = []
    for (store_id, product_id), c in sorted(final.items(), key=lambda kv: (-_best_score(kv[1]), kv[0][0], kv[0][1])):
        row = _row_for(catalog_df, store_id, product_id)
        if row is None:
            continue  # authored id not found in frozen catalog -- caught by validation, skip defensively
        label, reason = draft_label(row, request)
        out_candidates.append({
            "store_id": store_id,
            "product_id": product_id,
            "sources": sorted(c["sources"]),
            "scores": c["scores"],
            "draft_label": label,
            "draft_reason": reason,
        })

    return {"request_id": request["request_id"], "candidates": out_candidates}


def main():
    if not MANIFEST_PATH.exists():
        raise SystemExit(f"{MANIFEST_PATH.name} missing -- run freeze_catalog.py first")
    manifest = json.loads(MANIFEST_PATH.read_text())
    catalog_version = manifest.get("catalog_version")
    if not catalog_version:
        raise SystemExit("manifest has no catalog_version -- run freeze_catalog.py first")

    # Compared as raw file bytes -- the same way freeze_catalog.py computed
    # it -- not via retrieval.catalog_hash's pandas-round-tripped hash
    # (which fit_tfidf uses for its own, separate cache-staleness check):
    # those two hashes are computed differently and would never agree even
    # for byte-identical files, since a to_csv() round-trip can reformat
    # NaN/float representations.
    current_hash = hashlib.sha256(FROZEN_CATALOG.read_bytes()).hexdigest()
    if current_hash != catalog_version["sha256"]:
        raise SystemExit(
            f"benchmark_catalog_frozen.csv content hash {current_hash} does not match "
            f"manifest's recorded {catalog_version['sha256']} -- re-run freeze_catalog.py deliberately, "
            "this is not something to silently paper over"
        )

    catalog_df = _load_catalog()

    vectorizer, matrix = fit_tfidf(catalog_df)

    pools = [build_pool_for_request(r, catalog_df, vectorizer, matrix) for r in REQUESTS]
    OUT_PATH.write_text(json.dumps(pools, indent=2))

    sizes = [len(p["candidates"]) for p in pools]
    print(f"Built candidate pools for {len(pools)} requests (REQUEST_VERSION={REQUEST_VERSION})")
    print(f"  pool size: min={min(sizes)} max={max(sizes)} avg={sum(sizes)/len(sizes):.1f}")
    print(f"Wrote {OUT_PATH.name}")


if __name__ == "__main__":
    main()
