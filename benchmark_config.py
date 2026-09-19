"""Single source of truth for every Checkpoint 3 benchmark tunable.

Nothing in retrieval.py / build_candidate_pool.py / build_benchmark.py /
tfidf_baseline.py should hardcode a quota, threshold, or seed that belongs
here -- benchmark_manifest.json is a direct dump of this module's constants,
so a report can always be traced back to the exact settings that produced it.
"""

# Candidate pool quotas (build_candidate_pool.py). Overflow is trimmed by the
# tie-break rule below, keeping the highest-priority candidates; underflow is
# never padded -- a pool with 8 real candidates stays at 8.
MAX_LEXICAL_CANDIDATES = 6
MAX_SYNONYM_CANDIDATES = 6
MAX_HARD_NEGATIVES = 3
MAX_POOL_SIZE = 15

# Deterministic ranking/tie-break for every retrieval function in
# retrieval.py: highest score first, then lowest (store_id, product_id) --
# never insertion order or dict/hash order, so two runs against the same
# frozen catalog always produce the same ranking.
def tie_break_key(scored_candidate: dict) -> tuple:
    """scored_candidate needs 'score', 'store_id', 'product_id'."""
    return (-scored_candidate["score"], scored_candidate["store_id"], scored_candidate["product_id"])


# Synonym table version -- bump whenever SYNONYMS (below, or wherever
# retrieval.py defines it) changes meaningfully, so old candidate pools/
# manifests can be told apart from ones built under a different table.
SYNONYM_TABLE_VERSION = "v1"

# Random seed for any sampling done while authoring benchmark_requests.py
# (picking reference products, hard negatives) and for build_benchmark.py's
# split assignment among non-pilot paraphrase groups.
RANDOM_SEED = 20260916

# Minimum cosine similarity for attribute_filter_baseline to return
# "answerable" rather than "no_acceptable_match". This is the one threshold
# in the project; it is chosen using the dev split only (tfidf_baseline.py),
# then locked before validation/test are ever scored against it.
MIN_SIMILARITY = 0.65  # frozen by tune_threshold.py (Checkpoint E6) -- see evaluation/threshold_selection.json for the dev-only selection that set this

# Target overall split ratios by request count (build_benchmark.py). The 50
# pilot requests are pinned to dev unconditionally and count toward this
# ratio; only the remaining (non-pilot) paraphrase groups are actually free
# to be assigned to validation/test.
SPLIT_RATIOS = {"dev": 0.6, "validation": 0.2, "test": 0.2}
