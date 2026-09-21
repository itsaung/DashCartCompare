"""Checkpoint 4's own constants, declared before the runs that use them.

Separate from benchmark_config.py on purpose. benchmark_config.MIN_SIMILARITY
is frozen at 0.65 for v1's `tfidf_dimension_filter_threshold`, on a TF-IDF
cosine scale that means nothing to an embedding score or an RRF score. Reusing
it would be a category error, and overwriting it would break v1's
reproduction. Checkpoint 4's cut points live here instead.

Everything in this file is declared BEFORE the sub-checkpoint that consumes it
runs, so nothing here can be a value chosen after seeing a result. Where a
value is a convention rather than a measurement, it says so.
"""

# --- S5: hybrid fusion ------------------------------------------------------

# Depth taken from EACH retriever before fusion. Declared before S5's first
# run, not swept. Deep enough that a candidate ranked mid-list by one retriever
# and highly by the other still survives to be fused.
HYBRID_RETRIEVER_DEPTH = 50

# Reciprocal rank fusion constant. 60 is the value from the original RRF paper
# (Cormack, Clarke & Buettcher 2009) and is used here as a convention, not as a
# tuned optimum -- it was not swept against any split.
#
# RRF rather than a weighted score blend, deliberately: a TF-IDF cosine and an
# embedding cosine are not on a common scale, so a weighted blend would need a
# calibration constant AND a weight, both of which would be free parameters
# tuned on dev. RRF uses only ranks, so it has no free weight at all.
RRF_K = 60

# --- S6: thresholds, frozen 2026-09-21 by tune_threshold_v3.py --------------

# Per baseline family, because the three score scales are not comparable: a
# TF-IDF cosine tops out near 1.0, an embedding cosine sits in a narrow high
# band, and an RRF score is ~0.03 for a top result by construction. There is no
# single threshold that means the same thing to all of them, which is also why
# benchmark_config.MIN_SIMILARITY (0.65) is untouched.
#
# Selected on DEV ONLY, by the cost function declared in tune_threshold_v3.py's
# docstring (0 correct / 0.5 review / 1 abstain / 2 wrong), excluding the two
# dev no_acceptable_match requests whose own E1 answerability audit was
# unverified (r052, r129). validation_avg_cost below is a one-time
# informational read at the dev-chosen pair -- it never fed back into selection.
#
# review_costs_agreeing lists which of the swept review costs (0.25/0.5/0.75)
# pick this same pair. None of the four families agree across all three, so the
# 0.5 choice IS load-bearing -- and it is a declared design preference with no
# measured basis. Do not read these cut points as precise.
CUT_POINTS = {
    "embed": {
        "accept_threshold": 0.93703,
        "review_floor": 0.77859,
        "dev_avg_cost": 0.2841,
        "validation_avg_cost": 0.3167,
        "dev_outcomes": {'accept': 33, 'review': 40, 'no_match': 15},
        "review_costs_agreeing": [0.5],
    },
    "embed_dimension_size_filter": {
        "accept_threshold": 0.75552,
        "review_floor": 0.691613,
        "dev_avg_cost": 0.1932,
        "validation_avg_cost": 0.1833,
        "dev_outcomes": {'accept': 65, 'review': 12, 'no_match': 11},
        "review_costs_agreeing": [0.5, 0.75],
    },
    "hybrid_dimension_size_filter": {
        "accept_threshold": 0.027424,
        "review_floor": 0.015625,
        "dev_avg_cost": 0.1364,
        "validation_avg_cost": 0.1833,
        "dev_outcomes": {'accept': 67, 'review': 14, 'no_match': 7},
        "review_costs_agreeing": [0.5, 0.25],
    },
    "hybrid_identity_filter": {
        "accept_threshold": 0.027424,
        "review_floor": 0.015625,
        "dev_avg_cost": 0.233,
        "validation_avg_cost": 0.2833,
        "dev_outcomes": {'accept': 58, 'review': 15, 'no_match': 15},
        "review_costs_agreeing": [0.5, 0.25],
    },
}


def cut_points_for(baseline_name):
    """(accept_threshold, review_floor) for a baseline family.

    Raises for an unknown family rather than falling back to a default --
    tfidf_baseline.py's convention, and the reason a thresholded baseline
    cannot silently run on a guessed floor.
    """
    if baseline_name not in CUT_POINTS:
        raise KeyError(
            "no S6 cut points for %r; known families: %s"
            % (baseline_name, sorted(CUT_POINTS)))
    entry = CUT_POINTS[baseline_name]
    return entry["accept_threshold"], entry["review_floor"]


# Kept as None deliberately: there is no single project-wide threshold, and a
# module-level constant here would invite exactly that mistake.
ACCEPT_THRESHOLD = None
REVIEW_FLOOR = None
