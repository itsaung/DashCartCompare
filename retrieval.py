"""Shared retrieval primitives for Checkpoint 3: TF-IDF lexical search,
synonym-assisted search, and attribute_filter_baseline (the system under
test).

Every result is keyed by (store_id, product_id) -- item_id alone is not
globally unique across stores (see DATA_DICTIONARY.md) -- and every ranking
is broken by benchmark_config.tie_break_key so results are reproducible
across runs against the same frozen catalog.

attribute_filter_baseline deliberately only ever sees the raw request text,
parsed through parse_query.py exactly as a real system would at inference
time. It never receives the benchmark's hidden `expected` ground-truth
fields -- those exist purely to grade candidates in build_candidate_pool.py
and for human review, never to help the system being graded.
"""
import hashlib
import pickle
import re
import sklearn
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import benchmark_config as cfg
from normalize import parse_package_size
from parse_query import parse_shopping_line
from product_identity import extract_request_identity, variants_conflict

MODEL_CACHE_PATH = Path(__file__).resolve().parent / "tfidf_model.pkl"

# Bumped whenever _catalog_text's field construction changes meaningfully --
# part of the fit_tfidf cache key (see _cache_key) so a code change that
# doesn't touch the catalog content still invalidates a stale cache.
TEXT_CONSTRUCTION_VERSION = "v1"  # raw_title + brand + variant

# A small, explicit substitution table -- not embeddings, just words a
# shopper might reasonably use interchangeably with a catalog title/category
# term. SYNONYM_TABLE_VERSION in benchmark_config.py must be bumped whenever
# this changes meaningfully.
SYNONYMS = {
    "soda": {"pop", "soft drink"},
    "pop": {"soda", "soft drink"},
    "chips": {"crisps"},
    "cookies": {"biscuits"},
    "cilantro": {"coriander"},
    "yogurt": {"yoghurt"},
    "eggplant": {"aubergine"},
    "zucchini": {"courgette"},
    "arugula": {"rocket"},
    "candy": {"sweets"},
    "fries": {"chips"},
}


def catalog_hash(catalog_df) -> str:
    """Stable content hash of a catalog DataFrame's rows, used to detect a
    stale cached TF-IDF model or a manifest/catalog mismatch."""
    payload = catalog_df.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _catalog_text(catalog_df):
    return (
        catalog_df["raw_title"].fillna("")
        + " " + catalog_df["brand"].fillna("")
        + " " + catalog_df["variant"].fillna("")
    )


def _cache_key(catalog_df) -> dict:
    """Everything a stale TF-IDF cache could silently disagree with the
    current run on -- not just catalog content. A code change to
    TfidfVectorizer's hyperparameters, an sklearn/pandas upgrade, or a
    _catalog_text field-construction change must all invalidate the cache
    on their own, even if the catalog rows are byte-identical."""
    return {
        "catalog_hash": catalog_hash(catalog_df),
        "row_order": list(zip(catalog_df["store_id"], catalog_df["product_id"].astype(str))),
        "vectorizer_params": TfidfVectorizer().get_params(),
        "text_construction_version": TEXT_CONSTRUCTION_VERSION,
        "sklearn_version": sklearn.__version__,
        "pandas_version": pd.__version__,
    }


def fit_tfidf(catalog_df, cache_path: Path = MODEL_CACHE_PATH):
    """Fit a TF-IDF vectorizer once against the frozen catalog's raw_title (+
    brand/variant, once populated). Cached to disk keyed by _cache_key -- a
    mismatched key means the cache is stale and must be refit, but
    refitting only ever happens here, never inside lexical_search, which
    only ever transforms a query against this fitted model."""
    current_key = _cache_key(catalog_df)

    if cache_path.exists():
        with open(cache_path, "rb") as f:
            cached = pickle.load(f)
        if cached.get("cache_key") == current_key:
            return cached["vectorizer"], cached["matrix"]

    vectorizer = TfidfVectorizer()
    matrix = vectorizer.fit_transform(_catalog_text(catalog_df))
    with open(cache_path, "wb") as f:
        pickle.dump({"cache_key": current_key, "vectorizer": vectorizer, "matrix": matrix}, f)
    return vectorizer, matrix


def _unwrap(value):
    """numpy scalar -> Python scalar.

    store_id is an int64 column, so catalog_df.iloc[i]["store_id"] yields a
    numpy int64, which json.dump refuses. That has always been true here; it
    only surfaced once a caller wrote these dicts straight to JSON. Values are
    unchanged, only their Python type, so nothing downstream shifts.
    """
    return value.item() if hasattr(value, "item") else value


def _ranked(catalog_df, scores) -> list:
    scored = [
        {
            "store_id": _unwrap(catalog_df.iloc[i]["store_id"]),
            "product_id": _unwrap(catalog_df.iloc[i]["product_id"]),
            "score": float(scores[i]),
            "row": int(i),
        }
        for i in range(len(catalog_df))
        if scores[i] > 0
    ]
    scored.sort(key=cfg.tie_break_key)
    return scored


def lexical_search(query_text, vectorizer, matrix, catalog_df, top_k):
    """TF-IDF cosine similarity. Transforms `query_text` only -- never
    refits the vectorizer (fit_tfidf does that once, up front)."""
    query_vec = vectorizer.transform([query_text])
    scores = cosine_similarity(query_vec, matrix)[0]
    return _ranked(catalog_df, scores)[:top_k]


def _expand_synonyms(word: str) -> set:
    return {word} | SYNONYMS.get(word, set())


def synonym_assisted_search(structured_request: dict, catalog_df, top_k):
    """Category + a small synonym table + package-dimension compatibility --
    the stand-in for "semantic" retrieval in a project with no embeddings
    source. Deliberately a different method than lexical_search, so the
    candidate pool isn't just TF-IDF's own top results scored against
    themselves."""
    product_type = (structured_request.get("product_type") or "").lower()
    expanded = set()
    for w in product_type.split():
        expanded |= _expand_synonyms(w)
    if not expanded:
        return []

    dimension = structured_request.get("dimension")

    scored = []
    for i in range(len(catalog_df)):
        row = catalog_df.iloc[i]
        title_words = set(str(row["raw_title"]).lower().split())
        category_words = set(str(row["raw_category"]).lower().split())
        overlap = expanded & (title_words | category_words)
        if not overlap:
            continue
        score = len(overlap) / len(expanded)
        if dimension and row["pkg_dimension"] and row["pkg_dimension"] != dimension:
            # Penalized, not hard-excluded -- this pool is meant to surface
            # plausible near-misses (useful as hard negatives), unlike
            # attribute_filter_baseline below which does hard-exclude.
            score *= 0.5
        scored.append({"store_id": row["store_id"], "product_id": row["product_id"], "score": score, "row": i})
    scored.sort(key=cfg.tie_break_key)
    return scored[:top_k]


def filter_by_dimension(candidates: list, catalog_df, dimension) -> list:
    """Drop only candidates whose row has a KNOWN, conflicting pkg_dimension.
    row_dimension can be NaN for a row with no parsed package size at all
    (e.g. a variable-weight item) -- bool(nan) is True in Python, so an
    unguarded truthy check here would misreport "unknown" as "confirmed
    mismatch" and wrongly filter the candidate out. pd.notna() treats a
    missing dimension as the "unknown, don't filter" case it actually is.
    Shared by attribute_filter_baseline and tfidf_baseline.py's pool-ranking
    experiment so there is exactly one place this rule is written."""
    if not dimension:
        return list(candidates)
    survivors = []
    for c in candidates:
        row_dimension = catalog_df.iloc[c["row"]]["pkg_dimension"]
        if pd.notna(row_dimension) and row_dimension != dimension:
            continue
        survivors.append(c)
    return survivors


# Relative tolerance for comparing a request's requested canonical total
# against a catalog row's canonical total. Both values are already
# expressed in the same canonical unit by the time they reach this
# comparison, so a genuine cross-unit label-rounding difference (e.g. "2 L"
# printed against a candidate labeled "67.6 fl oz", ~0.04% apart) and an
# identical-unit exact match (0% apart) both pass trivially; a materially
# different printed size (e.g. "15 oz" vs "15.4 oz", ~2.7% apart) does not.
# This is deliberately NOT claude_auto_label.py's 3% SIZE_MISMATCH_TOLERANCE
# -- LABELING_GUIDELINES.md v2 explicitly rejects that as arbitrary, and a
# 2026-09-19 audit found real false positives it let through (see
# apply_new_candidate_review.py's identically-named-and-reasoned constant).
PACKAGE_SIZE_ROUNDING_TOLERANCE = 0.01  # relative

# Matches a "<amount> <unit> x <count> [ct-word]" multipack phrase inside
# free request text (e.g. the "12 fl oz x 12 ct" in "a 12 fl oz x 12 ct
# pack of Diet Coke..."), narrow enough to feed straight into
# normalize.parse_package_size() -- which expects exactly this shape (it's
# built to parse a catalog row's own raw_size string) and, unlike
# parse_shopping_line, already knows how to compute a multipack's TOTAL.
_MULTIPACK_PHRASE_RE = re.compile(
    r"[\d./]+\s*(?:fl\s?oz|fluid\s?ounces?|floz|oz|ounces?|lbs?|pounds?|g|grams?|kg|"
    r"gal|gallons?|qt|quarts?|pt|pints?|ml|l|liters?|ct|count|ea|each)\s*[x×]\s*"
    r"\d+\s*(?:ct|count|pk|pack|ea|each)?",
    re.I,
)


def _requested_canonical_total(request_text: str, structured: dict):
    """Returns (canonical_unit, canonical_total) for the FULL amount the
    shopper is asking for. parse_shopping_line's own canonical_quantity
    silently drops a trailing "x N ct" multipack multiplier in free text
    (e.g. "12 fl oz x 12 ct Diet Coke" parses to 12, the per-can size, not
    144, the total) -- when such a phrase is found in the raw text, this
    re-parses just that phrase with normalize.parse_package_size(), the
    same, more capable parser already used for the catalog's own raw_size
    strings and for a request's authored `expected.size` in
    claude_auto_label.py's auto_label(). That keeps this function and the
    labeling logic judging "total" consistently, instead of this function
    comparing a per-pack amount that the labeling side never did (the
    inconsistency a "5.3 oz" request matched against a "5.3 oz x 2 ct",
    10.6 oz total candidate exposed: auto_label correctly rejects it by
    total; the old per-pack comparison here wrongly accepted it).
    Falls back to parse_shopping_line's own canonical_quantity/unit --
    already a correct total for anything that ISN'T a multipack phrase --
    when no such phrase is found. Returns (None, None) if neither
    resolves."""
    m = _MULTIPACK_PHRASE_RE.search(request_text)
    if m:
        parsed = parse_package_size(m.group(0))
        if not parsed["unresolved"] and parsed["canonical_total"]:
            return parsed["canonical_unit"], parsed["canonical_total"]

    unit = structured.get("canonical_unit")
    qty = structured.get("canonical_quantity")
    if not unit or qty is None:
        return None, None
    return unit, qty


def filter_by_package_size(candidates: list, catalog_df, request_text: str, structured: dict) -> list:
    """Drop only candidates whose row has a KNOWN, conflicting total
    package amount -- the numeric sibling of filter_by_dimension, which
    only checks weight/volume/count category and has nothing to say about
    "5.3 oz" vs "16 oz" both being "weight" (the dominant failure mode
    found in Checkpoint 3's E7 baseline analysis, e.g. r078: a 16 oz
    candidate scored 0.977 against a request for 5.3 oz).

    Compares the shopper's requested canonical TOTAL (see
    _requested_canonical_total, which is multipack-phrase-aware) against
    each row's own canonical total, `pkg_canonical_total` -- both are the
    same "how much is in the package" quantity, so this is always a
    total-vs-total comparison, never a per-pack one. A request whose own
    amount can't be resolved, or a row whose package size is unknown/
    unresolved (variable-weight produce, missing data), is never filtered
    -- the same "unknown means don't filter" rule as filter_by_dimension,
    not a confirmed mismatch."""
    canonical_unit, canonical_total = _requested_canonical_total(request_text, structured)
    if not canonical_unit or canonical_total is None:
        return list(candidates)

    survivors = []
    for c in candidates:
        row = catalog_df.iloc[c["row"]]
        row_unit = row.get("pkg_canonical_unit")
        row_total = row.get("pkg_canonical_total")
        if pd.isna(row_unit) or pd.isna(row_total) or row_unit != canonical_unit:
            # Unknown package size, or a different canonical unit entirely
            # (a dimension mismatch -- filter_by_dimension's concern, not
            # this function's) -- never filtered here.
            survivors.append(c)
            continue
        rel_diff = abs(row_total - canonical_total) / canonical_total
        if rel_diff <= PACKAGE_SIZE_ROUNDING_TOLERANCE:
            survivors.append(c)
    return survivors


def attribute_filter_baseline(request_text: str, catalog_df, vectorizer, matrix, top_k, min_similarity):
    """The system under test.

    Returns (ranked_results, response) where response is one of:
      "needs_clarification" -- the request's own parse flagged missing or
          ambiguous essentials (reuses parse_query.py's needs_review) --
          resolved before any retrieval is attempted.
      "no_acceptable_match"  -- every lexical candidate was filtered out by
          an explicit dimension mismatch, or the best surviving candidate's
          similarity is below min_similarity.
      "answerable"           -- ranked_results is a non-empty ranked list.
          Multiple tied top-scoring candidates are all valid alternatives,
          not a reason to abstain -- a score margin is never, on its own,
          grounds to return "no_acceptable_match" or "needs_clarification".
    """
    structured = parse_shopping_line(request_text)
    if structured["needs_review"]:
        return [], "needs_clarification"

    dimension = structured.get("dimension")
    candidates = lexical_search(request_text, vectorizer, matrix, catalog_df, top_k=max(top_k * 4, 20))
    survivors = filter_by_dimension(candidates, catalog_df, dimension)
    if not survivors:
        return [], "no_acceptable_match"

    survivors.sort(key=cfg.tie_break_key)
    top = survivors[:top_k]
    if top[0]["score"] < min_similarity:
        return [], "no_acceptable_match"

    return top, "answerable"


def attribute_and_size_filter_baseline(request_text: str, catalog_df, vectorizer, matrix, top_k, min_similarity):
    """A NEW baseline, not a modification of attribute_filter_baseline --
    Checkpoint 3's v1 baselines (tfidf, tfidf_dimension_filter,
    tfidf_dimension_filter_threshold) stay byte-for-byte immutable per the
    plan ("Keep baseline v1 results immutable when a later model is
    evaluated"), so BASELINE_RESULTS.md's published numbers remain
    reproducible from a clean checkout indefinitely.

    Adds filter_by_package_size on top of attribute_filter_baseline's own
    dimension filter -- the evidence-justified next step from
    BASELINE_RESULTS.md's own E7 conclusion: 9 of 14 representative
    failures there were a candidate with the right dimension (weight,
    volume, or count) but the wrong actual number (e.g. 16 oz returned
    for a 5.3 oz request). Same three response branches as
    attribute_filter_baseline, same tie-break, same top_k prefilter depth
    -- only the extra filter differs."""
    structured = parse_shopping_line(request_text)
    if structured["needs_review"]:
        return [], "needs_clarification"

    dimension = structured.get("dimension")
    candidates = lexical_search(request_text, vectorizer, matrix, catalog_df, top_k=max(top_k * 4, 20))
    survivors = filter_by_dimension(candidates, catalog_df, dimension)
    survivors = filter_by_package_size(survivors, catalog_df, request_text, structured)
    if not survivors:
        return [], "no_acceptable_match"

    survivors.sort(key=cfg.tie_break_key)
    top = survivors[:top_k]
    if top[0]["score"] < min_similarity:
        return [], "no_acceptable_match"

    return top, "answerable"


# --- Checkpoint 4, S3: exact-mode identity ----------------------------------

def _identity_lookup(identity_df) -> dict:
    """{(store_id, product_id): row} with both keys as str, because the
    catalog carries product_id as int64 and the side-car CSV reads it back as
    str -- a silent dtype mismatch here would make every lookup miss and turn
    every candidate into "brand unknown", which reads as a coverage collapse
    rather than as the bug it is."""
    out = {}
    for row in identity_df.itertuples():
        out[(str(row.store_id), str(row.product_id))] = row
    return out


def filter_by_identity(candidates: list, catalog_df, identity_lookup: dict,
                       request_identity: dict, mode: str):
    """Brand/variant identity gate. Returns (survivors, needs_review).

    Follows filter_by_dimension's rule exactly: only a CONFIRMED conflict
    drops a candidate. Unknown on either side is a third state -- it neither
    drops the candidate nor accepts it, it raises needs_review, because
    PROJECT_PLAN.md's Checkpoint 4 requires that a missing identity attribute
    request review rather than be guessed past ("If key identity attributes
    are missing, request review").

    exact mode:   brand must match and variant must not conflict.
    flexible mode: brand is only enforced when the request states one; a
                   variant conflict still drops the candidate.

    Package-size identity, the third leg of exact mode, is deliberately NOT
    handled here -- filter_by_package_size already does it, unchanged, and
    duplicating the rule would give it two places to drift.
    """
    requested_brand = (request_identity or {}).get("brand")
    requested_variant = (request_identity or {}).get("variant_tokens") or frozenset()

    survivors = []
    needs_review = False

    for c in candidates:
        row = catalog_df.iloc[c["row"]]
        ident = identity_lookup.get((str(row["store_id"]), str(row["product_id"])))
        cand_brand = getattr(ident, "brand", None) if ident is not None else None
        if isinstance(cand_brand, float):  # NaN from the CSV
            cand_brand = None
        raw_variant = getattr(ident, "variant_tokens", "") if ident is not None else ""
        cand_variant = frozenset(str(raw_variant).split()) if isinstance(raw_variant, str) else frozenset()

        if variants_conflict(requested_variant, cand_variant):
            continue

        if mode == "exact":
            if not requested_brand or cand_brand is None:
                # Unknown identity: cannot confirm, must not guess.
                needs_review = True
                continue
            if cand_brand.casefold() != requested_brand.casefold():
                continue
        else:
            if requested_brand and cand_brand is not None:
                if cand_brand.casefold() != requested_brand.casefold():
                    continue

        survivors.append(c)

    return survivors, needs_review


def identity_filter_baseline(request_text: str, catalog_df, vectorizer, matrix, top_k,
                             min_similarity, identity_lookup: dict, brand_lexicon: dict,
                             mode: str):
    """A NEW baseline on top of attribute_and_size_filter_baseline, not a
    modification of it -- v1's and v2's baselines stay byte-identical, the
    same rule Checkpoint 3.1 followed.

    Exact-mode requests never fall through to a substitute: if the identity
    gate cannot confirm a candidate, the response is needs_clarification or
    no_acceptable_match, at any threshold including 0.0.
    """
    structured = parse_shopping_line(request_text)
    if structured["needs_review"]:
        return [], "needs_clarification"

    dimension = structured.get("dimension")
    candidates = lexical_search(request_text, vectorizer, matrix, catalog_df, top_k=max(top_k * 4, 20))
    survivors = filter_by_dimension(candidates, catalog_df, dimension)
    survivors = filter_by_package_size(survivors, catalog_df, request_text, structured)

    request_identity = extract_request_identity(request_text, brand_lexicon)
    survivors, needs_review = filter_by_identity(
        survivors, catalog_df, identity_lookup, request_identity, mode
    )

    if not survivors:
        # An exact request whose identity could not be confirmed is a review
        # case, not a "no such product" case -- the distinction matters for
        # the false-abstention rate.
        return [], "needs_clarification" if needs_review else "no_acceptable_match"

    survivors.sort(key=cfg.tie_break_key)
    top = survivors[:top_k]
    if top[0]["score"] < min_similarity:
        return [], "no_acceptable_match"

    return top, "answerable"
