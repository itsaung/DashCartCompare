"""Tests for tune_threshold_v3.py.

Every cost below is hand-calculated from the declared table, not read off a
run. The plan requires coverage of each branch including the new 0.5 review
outcome and the degenerate REVIEW_FLOOR == ACCEPT_THRESHOLD case, which must
reduce exactly to E6's two-outcome behavior.
"""
import pytest

import tune_threshold_v3 as tt


def _record(score=None, response="answerable", request_id="r001",
            store_id=1, product_id="p1"):
    results = [] if score is None else [
        {"store_id": store_id, "product_id": product_id, "score": score, "row": 0}]
    return {"request_id": request_id, "response": response, "results": results}


def _lookup(conservative="Acceptable", request_id="r001", store_id=1, product_id="p1"):
    import evaluation_metrics as em
    return {em._pair_key(request_id, store_id, product_id):
            {"conservative": conservative, "practical": conservative, "is_best_guess": False}}


# --- three-way outcome ------------------------------------------------------

def test_score_at_or_above_accept_is_an_automatic_match():
    assert tt.apply_cut_points(_record(0.80), accept=0.80, review=0.50) == "accept"


def test_score_between_the_cut_points_is_review():
    assert tt.apply_cut_points(_record(0.60), accept=0.80, review=0.50) == "review"


def test_score_at_the_review_floor_is_review_not_no_match():
    assert tt.apply_cut_points(_record(0.50), accept=0.80, review=0.50) == "review"


def test_score_below_the_review_floor_is_no_match():
    assert tt.apply_cut_points(_record(0.49), accept=0.80, review=0.50) == "no_match"


def test_needs_clarification_is_review_regardless_of_score():
    """A parser gate is not something a score threshold can overturn."""
    assert tt.apply_cut_points(_record(0.99, response="needs_clarification"),
                               accept=0.10, review=0.05) == "review"


def test_no_acceptable_match_stays_no_match():
    assert tt.apply_cut_points(_record(None, response="no_acceptable_match"),
                               accept=0.10, review=0.05) == "no_match"


def test_answerable_with_empty_results_is_no_match():
    assert tt.apply_cut_points(_record(None), accept=0.10, review=0.05) == "no_match"


# --- the degenerate case ----------------------------------------------------

def test_equal_cut_points_reduce_to_two_outcomes():
    """With REVIEW_FLOOR == ACCEPT_THRESHOLD there is no band, and behavior
    must match E6's accept/no-match split exactly."""
    outcomes = {tt.apply_cut_points(_record(s), accept=0.65, review=0.65)
                for s in (0.90, 0.65, 0.64, 0.10)}
    assert outcomes == {"accept", "no_match"}
    assert tt.apply_cut_points(_record(0.65), accept=0.65, review=0.65) == "accept"
    assert tt.apply_cut_points(_record(0.6499), accept=0.65, review=0.65) == "no_match"


# --- cost table -------------------------------------------------------------

def test_acceptable_automatic_match_costs_zero():
    r = _record(0.9)
    assert tt.request_cost(r, "accept", "answerable", _lookup("Acceptable"), 0.5) == 0.0


def test_incorrect_automatic_match_costs_two():
    r = _record(0.9)
    assert tt.request_cost(r, "accept", "answerable", _lookup("Incorrect"), 0.5) == 2.0


def test_unresolved_best_guess_top1_costs_two():
    """A best-guess pair whose conservative label reverted to Needs
    clarification is treated as cost 2 at tuning time -- a policy choice, not
    a claim the guess is wrong."""
    r = _record(0.9)
    assert tt.request_cost(r, "accept", "answerable",
                           _lookup("Needs clarification"), 0.5) == 2.0


def test_abstaining_on_an_answerable_request_costs_one():
    assert tt.request_cost(_record(0.1), "no_match", "answerable", _lookup(), 0.5) == 1.0


def test_correct_abstention_on_an_unanswerable_request_costs_zero():
    assert tt.request_cost(_record(0.1), "no_match", "no_acceptable_match", {}, 0.5) == 0.0


def test_automatic_match_on_an_unanswerable_request_costs_two():
    """A response-policy error regardless of how compatible the candidate
    looks."""
    r = _record(0.9)
    assert tt.request_cost(r, "accept", "no_acceptable_match", _lookup("Acceptable"), 0.5) == 2.0


def test_review_costs_the_declared_review_cost_on_an_answerable_request():
    assert tt.request_cost(_record(0.6), "review", "answerable", _lookup(), 0.5) == 0.5


def test_review_costs_the_same_on_an_unanswerable_request():
    """Deferring on a genuinely unanswerable request is mildly wasteful
    rather than correct, which is why it is not 0."""
    assert tt.request_cost(_record(0.6), "review", "no_acceptable_match", {}, 0.5) == 0.5


def test_review_cost_is_parameterised_for_the_sensitivity_sweep():
    for rc in (0.25, 0.5, 0.75):
        assert tt.request_cost(_record(0.6), "review", "answerable", _lookup(), rc) == rc


def test_review_is_cheaper_than_abstaining_but_dearer_than_a_correct_match():
    correct = tt.request_cost(_record(0.9), "accept", "answerable", _lookup("Acceptable"), 0.5)
    review = tt.request_cost(_record(0.6), "review", "answerable", _lookup(), 0.5)
    abstain = tt.request_cost(_record(0.1), "no_match", "answerable", _lookup(), 0.5)
    wrong = tt.request_cost(_record(0.9), "accept", "answerable", _lookup("Incorrect"), 0.5)
    assert correct < review < abstain < wrong


def test_missing_label_raises_rather_than_scoring_silently():
    """Every full-catalog top-1 is judged; an unjudged one means the lookup is
    broken, not that the case is legitimately unresolved."""
    with pytest.raises(KeyError):
        tt.request_cost(_record(0.9), "accept", "answerable", {}, 0.5)


# --- grid -------------------------------------------------------------------

def test_grid_spans_the_observed_score_range_and_includes_zero():
    records = {"a": _record(0.2, request_id="a"), "b": _record(0.8, request_id="b")}
    grid = tt.grid_for(records, ["a", "b"])
    assert grid[0] == 0.0
    assert min(g for g in grid if g > 0) == pytest.approx(0.2)
    assert max(grid) == pytest.approx(0.8)


def test_grid_handles_a_single_observed_score():
    records = {"a": _record(0.5, request_id="a")}
    grid = tt.grid_for(records, ["a"])
    assert grid == [0.0, pytest.approx(0.5)]


def test_grid_ignores_excluded_requests():
    records = {"a": _record(0.2, request_id="a"), "b": _record(0.9, request_id="b")}
    grid = tt.grid_for(records, ["a"])
    assert max(grid) == pytest.approx(0.2)


def test_grid_with_no_scoring_records_is_just_zero():
    assert tt.grid_for({"a": _record(None, request_id="a")}, ["a"]) == [0.0]


# --- selection --------------------------------------------------------------

def _point(accept, review, cost, correct=0):
    return {"accept_threshold": accept, "review_floor": review, "avg_cost": cost,
            "n": 10, "outcomes": {}, "confirmed_correct_accepts": correct}


def test_selection_takes_the_lowest_average_cost():
    chosen = tt.select([_point(0.5, 0.2, 0.40), _point(0.7, 0.3, 0.25), _point(0.9, 0.4, 0.60)])
    assert chosen["accept_threshold"] == 0.7


def test_ties_prefer_more_confirmed_correct_accepts():
    chosen = tt.select([_point(0.5, 0.2, 0.30, correct=4), _point(0.7, 0.3, 0.30, correct=9)])
    assert chosen["confirmed_correct_accepts"] == 9


def test_ties_then_prefer_a_narrower_review_band():
    chosen = tt.select([_point(0.8, 0.2, 0.30, correct=5), _point(0.8, 0.7, 0.30, correct=5)])
    assert chosen["review_floor"] == 0.7


def test_ties_then_prefer_a_lower_accept_threshold():
    chosen = tt.select([_point(0.9, 0.8, 0.30, correct=5), _point(0.6, 0.5, 0.30, correct=5)])
    assert chosen["accept_threshold"] == 0.6


# --- sweep ------------------------------------------------------------------

def test_sweep_never_emits_a_floor_above_the_accept_threshold():
    records = {"a": _record(0.5, request_id="a")}
    surface = tt.sweep(records, {"a": "answerable"}, _lookup(request_id="a"), ["a"],
                       [0.0, 0.3, 0.6], 0.5)
    assert all(p["review_floor"] <= p["accept_threshold"] for p in surface)


def test_sweep_counts_every_included_request_exactly_once():
    records = {"a": _record(0.5, request_id="a"), "b": _record(0.1, request_id="b")}
    lookup = {**_lookup(request_id="a"), **_lookup(request_id="b")}
    surface = tt.sweep(records, {"a": "answerable", "b": "answerable"}, lookup,
                       ["a", "b"], [0.0, 0.4], 0.5)
    assert all(sum(p["outcomes"].values()) == 2 for p in surface)


# --- frozen config ----------------------------------------------------------

def test_frozen_cut_points_cover_every_baseline_family():
    import checkpoint4_config as c4
    assert set(c4.CUT_POINTS) == {
        "embed", "embed_dimension_size_filter",
        "hybrid_dimension_size_filter", "hybrid_identity_filter",
    }


def test_every_frozen_pair_has_the_floor_at_or_below_the_threshold():
    import checkpoint4_config as c4
    for name, entry in c4.CUT_POINTS.items():
        assert entry["review_floor"] <= entry["accept_threshold"], name


def test_cut_points_for_raises_on_an_unknown_family():
    """No silent default -- a thresholded baseline must not run on a guessed
    floor, the same convention tfidf_baseline.py set."""
    import checkpoint4_config as c4
    with pytest.raises(KeyError):
        c4.cut_points_for("not_a_baseline")


def test_module_level_threshold_constants_stay_none():
    """There is no project-wide threshold; a module-level constant would
    invite treating one score scale's cutoff as universal."""
    import checkpoint4_config as c4
    assert c4.ACCEPT_THRESHOLD is None
    assert c4.REVIEW_FLOOR is None
