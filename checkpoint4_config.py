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

# --- S6: thresholds (set by tune_threshold_v3.py, dev only) -----------------

# Deliberately None until S6 runs. tfidf_baseline.py's existing convention is
# that a thresholded baseline RAISES rather than guessing a floor, and the same
# applies here.
ACCEPT_THRESHOLD = None
REVIEW_FLOOR = None
