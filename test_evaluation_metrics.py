"""Tests for evaluation_metrics.py: hand-calculated fixtures for every
metric's denominator, the conservative bounds, abstention/confusion-table
counts, and pool-recall N/A behavior -- per Checkpoint E5's explicit pass
criterion ("hand-calculated fixtures verify denominators, uncertainty
bounds, abstention and N/A behavior")."""
import evaluation_metrics as em


def _lookup(entries):
    """entries: {(request_id, store_id, product_id): (conservative, practical, is_best_guess)}"""
    return {
        (rid, sid, pid): {"conservative": c, "practical": p, "is_best_guess": g}
        for (rid, sid, pid), (c, p, g) in entries.items()
    }


def _res(store_id, product_id):
    return {"store_id": store_id, "product_id": product_id}


def _record(request_id, response, results=None):
    return {"request_id": request_id, "response": response, "results": results or []}


# --- success_at_1 -------------------------------------------------------------

def test_success_at_1_hand_calculated():
    lookup = _lookup({
        ("r1", 1, "p1"): ("Acceptable", "Acceptable", False),
        ("r2", 1, "p2"): ("Incorrect", "Incorrect", False),
    })
    records = [
        _record("r1", "answerable", [_res(1, "p1")]),
        _record("r2", "answerable", [_res(1, "p2")]),
    ]
    out = em.success_at_1(records, lookup, "practical")
    assert out == {"successes": 1, "n": 2, "rate": 0.5}


def test_success_at_1_abstention_counts_as_zero_but_stays_in_n():
    records = [_record("r1", "no_acceptable_match", [])]
    out = em.success_at_1(records, {}, "practical")
    assert out == {"successes": 0, "n": 1, "rate": 0.0}


def test_success_at_1_empty_n_is_none_rate_not_zero_division():
    out = em.success_at_1([], {}, "practical")
    assert out == {"successes": 0, "n": 0, "rate": None}


# --- hit_at_5 -----------------------------------------------------------------

def test_hit_at_5_hand_calculated_hit_in_fifth_slot():
    lookup = _lookup({("r1", 1, "p5"): ("Acceptable", "Acceptable", False)})
    results = [_res(1, f"p{i}") for i in range(1, 5)] + [_res(1, "p5")]
    records = [_record("r1", "answerable", results)]
    out = em.hit_at_5(records, lookup, "practical")
    assert out == {"hits": 1, "n": 1, "rate": 1.0}


def test_hit_at_5_ignores_a_sixth_result():
    lookup = _lookup({("r1", 1, "p6"): ("Acceptable", "Acceptable", False)})
    results = [_res(1, f"p{i}") for i in range(1, 6)] + [_res(1, "p6")]
    records = [_record("r1", "answerable", results)]
    out = em.hit_at_5(records, lookup, "practical")
    assert out == {"hits": 0, "n": 1, "rate": 0.0}


# --- mrr_at_5 -------------------------------------------------------------------

def test_mrr_at_5_hand_calculated():
    lookup = _lookup({
        ("r1", 1, "p1"): ("Acceptable", "Acceptable", False),  # rank 1 -> 1.0
        ("r2", 1, "p3"): ("Acceptable", "Acceptable", False),  # rank 3 -> 1/3
    })
    records = [
        _record("r1", "answerable", [_res(1, "p1")]),
        _record("r2", "answerable", [_res(1, "px"), _res(1, "py"), _res(1, "p3")]),
    ]
    out = em.mrr_at_5(records, lookup, "practical")
    assert out["n"] == 2
    assert out["sum_reciprocal_rank"] == 1.0 + 1 / 3
    assert out["mrr"] == (1.0 + 1 / 3) / 2


def test_mrr_at_5_no_acceptable_result_contributes_zero():
    lookup = _lookup({("r1", 1, "p1"): ("Incorrect", "Incorrect", False)})
    records = [_record("r1", "answerable", [_res(1, "p1")])]
    out = em.mrr_at_5(records, lookup, "practical")
    assert out == {"sum_reciprocal_rank": 0.0, "n": 1, "mrr": 0.0}


# --- pool_recall_at_5 -----------------------------------------------------------

def test_pool_recall_hand_calculated_two_of_three_positives_in_top5():
    lookup = _lookup({
        ("r1", 1, "pos1"): ("Acceptable", "Acceptable", False),
        ("r1", 1, "pos2"): ("Acceptable", "Acceptable", False),
        ("r1", 1, "pos3"): ("Acceptable", "Acceptable", False),
        ("r1", 1, "neg1"): ("Incorrect", "Incorrect", False),
    })
    full_pool = {"r1": [(1, "pos1"), (1, "pos2"), (1, "pos3"), (1, "neg1")]}
    # top-5 ranked results include pos1, pos2 but not pos3
    pool_records = [{"request_id": "r1", "results": [_res(1, "pos1"), _res(1, "pos2"), _res(1, "neg1")]}]
    out = em.pool_recall_at_5(pool_records, full_pool, lookup, "practical")
    assert out["n_pools_with_positive"] == 1
    assert out["n_zero_positive_pools"] == 0
    assert out["mean_recall"] == 2 / 3


def test_pool_recall_zero_positive_pool_is_na_not_zero():
    lookup = _lookup({("r1", 1, "neg1"): ("Incorrect", "Incorrect", False)})
    full_pool = {"r1": [(1, "neg1")]}
    pool_records = [{"request_id": "r1", "results": [_res(1, "neg1")]}]
    out = em.pool_recall_at_5(pool_records, full_pool, lookup, "practical")
    assert out["mean_recall"] is None  # N/A, not folded into a 0
    assert out["n_zero_positive_pools"] == 1
    assert out["n_pools_with_positive"] == 0


def test_pool_recall_denominator_uses_full_pool_not_filtered_results():
    # A dimension-filter baseline's `results` can drop a pool member the
    # gate excluded -- the denominator must still count it if it's a known
    # positive, so recall isn't inflated by shrinking the denominator.
    lookup = _lookup({
        ("r1", 1, "pos1"): ("Acceptable", "Acceptable", False),
        ("r1", 1, "pos2"): ("Acceptable", "Acceptable", False),
    })
    full_pool = {"r1": [(1, "pos1"), (1, "pos2")]}
    pool_records = [{"request_id": "r1", "results": [_res(1, "pos1")]}]  # pos2 filtered out upstream
    out = em.pool_recall_at_5(pool_records, full_pool, lookup, "practical")
    assert out["mean_recall"] == 0.5  # 1 of 2 known positives retrieved, not 1 of 1


def test_pool_recall_request_missing_from_pool_records_counts_as_zero_retrieved():
    lookup = _lookup({("r1", 1, "pos1"): ("Acceptable", "Acceptable", False)})
    full_pool = {"r1": [(1, "pos1")]}
    out = em.pool_recall_at_5([], full_pool, lookup, "practical")  # no pool_records at all for r1
    assert out["mean_recall"] == 0.0


# --- confusion_table / abstention metrics ---------------------------------------

def test_confusion_table_hand_calculated():
    answerability = {"r1": "answerable", "r2": "needs_clarification", "r3": "answerable"}
    records = [
        _record("r1", "answerable"),
        _record("r2", "needs_clarification"),
        _record("r3", "no_acceptable_match"),  # answerable ground truth, but abstained
    ]
    table = em.confusion_table(records, answerability)
    assert table["answerable"]["answerable"] == 1
    assert table["answerable"]["no_acceptable_match"] == 1
    assert table["needs_clarification"]["needs_clarification"] == 1
    assert table["no_acceptable_match"] == {"answerable": 0, "needs_clarification": 0, "no_acceptable_match": 0}


def test_return_coverage_hand_calculated():
    records = [_record("r1", "answerable"), _record("r2", "no_acceptable_match"), _record("r3", "answerable")]
    out = em.return_coverage(records)
    assert out == {"returned": 2, "n": 3, "rate": 2 / 3}


def test_returned_match_accuracy_only_denominates_over_returned_requests():
    lookup = _lookup({("r1", 1, "p1"): ("Acceptable", "Acceptable", False)})
    records = [
        _record("r1", "answerable", [_res(1, "p1")]),  # returned, correct
        _record("r2", "no_acceptable_match", []),       # abstained -- excluded from n
    ]
    out = em.returned_match_accuracy(records, lookup, "practical")
    assert out == {"correct": 1, "n": 1, "rate": 1.0}


def test_false_return_rate_on_unanswerable_hand_calculated():
    answerability = {"r1": "needs_clarification", "r2": "no_acceptable_match", "r3": "answerable"}
    records = [
        _record("r1", "answerable", [_res(1, "p1")]),  # false return
        _record("r2", "no_acceptable_match"),           # correctly abstained
        _record("r3", "answerable", [_res(1, "p1")]),  # answerable -- excluded from this denominator
    ]
    out = em.false_return_rate(records, answerability)
    assert out == {"false_returns": 1, "n": 2, "rate": 0.5}


def test_false_abstention_rate_hand_calculated():
    answerability = {"r1": "answerable", "r2": "answerable", "r3": "needs_clarification"}
    records = [
        _record("r1", "no_acceptable_match"),  # false abstention
        _record("r2", "answerable", [_res(1, "p1")]),
        _record("r3", "needs_clarification"),  # excluded -- not answerable ground truth
    ]
    out = em.false_abstention_rate(records, answerability)
    assert out == {"abstentions": 1, "n": 2, "rate": 0.5}


# --- conservative bounds ---------------------------------------------------------

def test_success_at_1_bounds_confirmed_correct_incorrect_and_unresolved():
    lookup = _lookup({
        ("r1", 1, "p1"): ("Acceptable", "Acceptable", False),               # confirmed correct
        ("r2", 1, "p2"): ("Needs clarification", "Incorrect", True),        # best guess, practical says Incorrect too -> confirmed incorrect
        ("r3", 1, "p3"): ("Needs clarification", "Acceptable", True),       # best guess, practical Acceptable -> unresolved
        ("r4", 1, "p4"): ("Incorrect", "Incorrect", False),                 # confirmed incorrect
    })
    records = [
        _record("r1", "answerable", [_res(1, "p1")]),
        _record("r2", "answerable", [_res(1, "p2")]),
        _record("r3", "answerable", [_res(1, "p3")]),
        _record("r4", "answerable", [_res(1, "p4")]),
    ]
    out = em.success_at_1_bounds(records, lookup)
    assert out["n"] == 4
    assert out["confirmed_correct"] == 1
    assert out["confirmed_incorrect"] == 2
    assert out["unresolved"] == 1
    assert out["lower_bound_rate"] == 1 / 4  # unresolved treated as nonpositive
    assert out["upper_bound_rate"] == 2 / 4  # unresolved treated as potentially acceptable


def test_success_at_1_bounds_abstention_excluded_from_correct_or_incorrect_but_counts_in_n():
    records = [_record("r1", "no_acceptable_match", [])]
    out = em.success_at_1_bounds(records, {})
    assert out["n"] == 1
    assert out["confirmed_correct"] == 0
    assert out["confirmed_incorrect"] == 0
    assert out["unresolved"] == 0
    assert out["lower_bound_rate"] == 0.0
    assert out["upper_bound_rate"] == 0.0


# --- guessed_label_exposure -------------------------------------------------------

def test_guessed_label_exposure_counts_only_scored_top1_predictions():
    lookup = _lookup({
        ("r1", 1, "p1"): ("Needs clarification", "Acceptable", True),  # guessed, touches top-1
        ("r2", 1, "p2"): ("Acceptable", "Acceptable", False),           # not a guess
    })
    records = [
        _record("r1", "answerable", [_res(1, "p1")]),
        _record("r2", "answerable", [_res(1, "p2")]),
        _record("r3", "no_acceptable_match", []),  # abstained -- not "scored"
    ]
    out = em.guessed_label_exposure(records, lookup)
    assert out == {"scored_top1_predictions": 2, "touching_a_guessed_label": 1}


# --- label_lookup merge behavior (pool pairs take priority over additional) ------

def test_load_label_lookup_merges_pool_and_additional_without_pool_pairs_overridden(tmp_path):
    pairs_path = tmp_path / "benchmark_pairs.jsonl"
    pairs_path.write_text(
        '{"request_id": "r1", "store_id": 1, "product_id": "p1", '
        '"reviewer_label": "Acceptable", "conservative_label": "Acceptable", "is_best_guess": false}\n'
    )
    additional_path = tmp_path / "additional_judgments.json"
    additional_path.write_text(
        '{"r1|1|p1": {"request_id": "r1", "store_id": 1, "product_id": "p1", '
        '"reviewer_label": "Incorrect", "conservative_label": "Incorrect", "is_best_guess": false}, '
        '"r2|1|p2": {"request_id": "r2", "store_id": 1, "product_id": "p2", '
        '"reviewer_label": "Incorrect", "conservative_label": "Incorrect", "is_best_guess": false}}'
    )
    lookup = em.load_label_lookup(pairs_path, additional_path)
    # pool pairs' own label must win over an additional_judgments entry for the same key
    assert lookup[("r1", 1, "p1")]["practical"] == "Acceptable"
    assert lookup[("r2", 1, "p2")]["practical"] == "Incorrect"
