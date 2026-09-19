"""Tests for tune_threshold.py: the dev_cost function's three buckets
(hand-calculated per Checkpoint E6's own cost table), the tie-break rule,
and freeze_min_similarity's in-place edit. Small fixtures, not the real
150-request run."""
import tune_threshold as tt


def _lookup(entries):
    return {
        (rid, sid, pid): {"conservative": c, "practical": p, "is_best_guess": g}
        for (rid, sid, pid), (c, p, g) in entries.items()
    }


def _rec(request_id, response, results=None):
    return {"request_id": request_id, "response": response, "results": results or []}


def _res(store_id, product_id, score=0.5):
    return {"store_id": store_id, "product_id": product_id, "score": score}


# --- dev_cost: the three buckets, hand-calculated -----------------------------

def test_cost_0_appropriate_acceptable_return():
    lookup = _lookup({("r1", 1, "p1"): ("Acceptable", "Acceptable", False)})
    rec = _rec("r1", "answerable", [_res(1, "p1")])
    assert tt.dev_cost(rec, "answerable", lookup) == 0


def test_cost_0_correct_abstention_on_unanswerable():
    rec = _rec("r1", "no_acceptable_match", [])
    assert tt.dev_cost(rec, "no_acceptable_match", lookup={}) == 0


def test_cost_1_false_abstention_on_answerable():
    rec = _rec("r1", "no_acceptable_match", [])
    assert tt.dev_cost(rec, "answerable", lookup={}) == 1


def test_cost_2_incorrect_return():
    lookup = _lookup({("r1", 1, "p1"): ("Incorrect", "Incorrect", False)})
    rec = _rec("r1", "answerable", [_res(1, "p1")])
    assert tt.dev_cost(rec, "answerable", lookup) == 2


def test_cost_2_return_on_unanswerable_regardless_of_candidate_quality():
    # Even a "conservative Acceptable" candidate is still a policy error
    # when the request itself needed clarification or had no match.
    lookup = _lookup({("r1", 1, "p1"): ("Acceptable", "Acceptable", False)})
    rec = _rec("r1", "answerable", [_res(1, "p1")])
    assert tt.dev_cost(rec, "needs_clarification", lookup) == 2
    assert tt.dev_cost(rec, "no_acceptable_match", lookup) == 2


def test_cost_2_unresolved_best_guess_top1_under_conservative_labels():
    lookup = _lookup({("r1", 1, "p1"): ("Needs clarification", "Acceptable", True)})
    rec = _rec("r1", "answerable", [_res(1, "p1")])
    assert tt.dev_cost(rec, "answerable", lookup) == 2


def test_dev_cost_raises_on_a_genuinely_unjudged_top1():
    rec = _rec("r1", "answerable", [_res(1, "p1")])
    try:
        tt.dev_cost(rec, "answerable", lookup={})
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError for an unjudged top-1")


# --- excluded_request_ids -----------------------------------------------------

def test_excluded_request_ids_matches_the_unresolved_no_match_audit_entries(monkeypatch):
    monkeypatch.setattr(tt, "NO_MATCH_AUDIT", {
        "r1": {"confidence": "confirmed"},
        "r2": {"confidence": "confirmed by construction"},
        "r3": {"confidence": "pattern-consistent, not independently re-searched"},
    })
    assert tt.excluded_request_ids() == ["r3"]


# --- cost_curve_point / best_threshold ----------------------------------------

def test_cost_curve_point_averages_correctly():
    lookup = _lookup({("r1", 1, "p1"): ("Acceptable", "Acceptable", False)})
    dev_records = {
        "r1": {"request_id": "r1", "response": "answerable",
               "results": [_res(1, "p1", score=0.9)],
               "config": {"name": "tfidf_dimension_filter", "min_similarity": 0.0}},
        "r2": {"request_id": "r2", "response": "no_acceptable_match", "results": [],
               "config": {"name": "tfidf_dimension_filter", "min_similarity": 0.0}},
    }
    true_answerability = {"r1": "answerable", "r2": "no_acceptable_match"}
    point = tt.cost_curve_point(0.5, dev_records, true_answerability, lookup, ["r1", "r2"])
    assert point["n"] == 2
    assert point["cost_0_count"] == 2  # r1 acceptable return, r2 correct abstention
    assert point["avg_cost"] == 0.0
    assert point["confirmed_correct_returns"] == 1


def test_cost_curve_point_raising_threshold_can_convert_an_incorrect_return_to_an_abstention():
    lookup = _lookup({("r1", 1, "p1"): ("Incorrect", "Incorrect", False)})
    dev_records = {
        "r1": {"request_id": "r1", "response": "answerable",
               "results": [_res(1, "p1", score=0.3)],
               "config": {"name": "tfidf_dimension_filter", "min_similarity": 0.0}},
    }
    true_answerability = {"r1": "answerable"}
    low = tt.cost_curve_point(0.1, dev_records, true_answerability, lookup, ["r1"])
    high = tt.cost_curve_point(0.5, dev_records, true_answerability, lookup, ["r1"])
    assert low["cost_2_count"] == 1   # returned, wrong -> cost 2
    assert high["cost_1_count"] == 1  # threshold rejects it -> abstains -> cost 1 (an improvement)


def test_best_threshold_picks_lowest_avg_cost():
    curve = [
        {"threshold": 0.0, "avg_cost": 1.0, "confirmed_correct_returns": 5},
        {"threshold": 0.1, "avg_cost": 0.5, "confirmed_correct_returns": 3},
        {"threshold": 0.2, "avg_cost": 0.8, "confirmed_correct_returns": 9},
    ]
    assert tt.best_threshold(curve)["threshold"] == 0.1


def test_best_threshold_ties_break_by_greater_confirmed_correct_returns():
    curve = [
        {"threshold": 0.0, "avg_cost": 0.5, "confirmed_correct_returns": 3},
        {"threshold": 0.1, "avg_cost": 0.5, "confirmed_correct_returns": 7},
    ]
    assert tt.best_threshold(curve)["threshold"] == 0.1


def test_best_threshold_ties_break_by_lower_threshold_last():
    curve = [
        {"threshold": 0.2, "avg_cost": 0.5, "confirmed_correct_returns": 4},
        {"threshold": 0.1, "avg_cost": 0.5, "confirmed_correct_returns": 4},
    ]
    assert tt.best_threshold(curve)["threshold"] == 0.1


# --- freeze_min_similarity -----------------------------------------------------

def test_freeze_min_similarity_edits_in_place(tmp_path, monkeypatch):
    config_path = tmp_path / "benchmark_config.py"
    config_path.write_text("FOO = 1\nMIN_SIMILARITY = None  # old comment\nBAR = 2\n")
    monkeypatch.setattr(tt, "CONFIG_PATH", config_path)
    tt.freeze_min_similarity(0.35)
    text = config_path.read_text()
    assert "MIN_SIMILARITY = 0.35" in text
    assert "FOO = 1" in text and "BAR = 2" in text  # surrounding lines untouched


def test_freeze_min_similarity_raises_if_constant_not_found(tmp_path, monkeypatch):
    config_path = tmp_path / "benchmark_config.py"
    config_path.write_text("FOO = 1\n")
    monkeypatch.setattr(tt, "CONFIG_PATH", config_path)
    try:
        tt.freeze_min_similarity(0.35)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError when MIN_SIMILARITY is missing")
