"""Tests for final_evaluation.py.

The numbers here are hand-calculated from CHECKPOINT_4_PLAN.md S7's definition
of automatic-match precision, not read off a run. The definition's whole point
is what it EXCLUDES -- review-band outcomes and abstentions, from numerator and
denominator both -- so most of these tests are about the denominator.
"""
import pandas as pd
import pytest

import evaluation_metrics as em
import final_evaluation as fe


def _record(score=None, response="answerable", request_id="r001",
            store_id=1, product_id="p1"):
    results = [] if score is None else [
        {"store_id": store_id, "product_id": product_id, "score": score, "row": 0}]
    return {"request_id": request_id, "response": response, "results": results}


def _lookup(**by_request):
    """{request_id: label} -> the merged-lookup shape, one pair each."""
    return {em._pair_key(rid, 1, "p1"):
            {"conservative": label, "practical": label, "is_best_guess": False}
            for rid, label in by_request.items()}


ACCEPT, REVIEW = 0.80, 0.50


# --- the three-way partition ------------------------------------------------

def test_partition_counts_sum_to_the_request_count():
    records = [_record(0.90, request_id="r1"), _record(0.60, request_id="r2"),
               _record(0.10, request_id="r3"), _record(None, request_id="r4",
                                                       response="no_acceptable_match")]
    part = fe.outcome_partition(records, ACCEPT, REVIEW)
    assert part["counts"] == {"accept": 1, "review": 1, "no_match": 2}
    assert part["sums_to_one"]
    assert part["automatic_match_rate"] == {"n": 1, "of": 4, "rate": 0.25}
    assert part["review_rate"]["rate"] == 0.25
    assert part["abstention_rate"]["rate"] == 0.5


def test_rates_are_none_not_zero_on_an_empty_split():
    part = fe.outcome_partition([], ACCEPT, REVIEW)
    assert part["automatic_match_rate"]["rate"] is None


# --- automatic-match precision ----------------------------------------------

def test_only_automatic_matches_are_in_the_denominator():
    """A review outcome and an abstention are in NEITHER numerator nor
    denominator. Three requests, one automatic match: the denominator is 1."""
    records = [_record(0.90, request_id="r1"), _record(0.60, request_id="r2"),
               _record(0.10, request_id="r3")]
    lookup = _lookup(r1="Acceptable", r2="Acceptable", r3="Acceptable")
    answerability = {"r1": "answerable", "r2": "answerable", "r3": "answerable"}
    got = fe.automatic_match_precision(records, ACCEPT, REVIEW, lookup,
                                       answerability, "conservative")
    assert (got["n"], got["of"], got["rate"]) == (1, 1, 1.0)


def test_a_return_on_an_unanswerable_request_counts_against_never_for():
    """In the denominator, out of the numerator, even though its top-1 is
    labeled Acceptable -- evaluation_metrics' existing response-policy rule."""
    records = [_record(0.90, request_id="r1"), _record(0.90, request_id="r2")]
    lookup = _lookup(r1="Acceptable", r2="Acceptable")
    answerability = {"r1": "answerable", "r2": "needs_clarification"}
    got = fe.automatic_match_precision(records, ACCEPT, REVIEW, lookup,
                                       answerability, "conservative")
    assert (got["n"], got["of"], got["rate"]) == (1, 2, 0.5)


def test_the_two_views_can_disagree():
    """A best guess reverts to Needs clarification under the conservative view,
    which is the lower bound the 95% criterion is judged against."""
    records = [_record(0.90, request_id="r1")]
    lookup = {em._pair_key("r1", 1, "p1"): {"conservative": "Needs clarification",
                                            "practical": "Acceptable",
                                            "is_best_guess": True}}
    answerability = {"r1": "answerable"}
    assert fe.automatic_match_precision(records, ACCEPT, REVIEW, lookup,
                                        answerability, "practical")["rate"] == 1.0
    assert fe.automatic_match_precision(records, ACCEPT, REVIEW, lookup,
                                        answerability, "conservative")["rate"] == 0.0


def test_an_unjudged_top1_is_reported_by_request_id_not_silently_counted():
    records = [_record(0.90, request_id="r1")]
    got = fe.automatic_match_precision(records, ACCEPT, REVIEW, {},
                                       {"r1": "answerable"}, "conservative")
    assert got["unjudged_top1_request_ids"] == ["r1"]
    assert (got["n"], got["of"]) == (0, 1)


def test_precision_is_none_when_nothing_was_automatically_matched():
    """A matcher that accepts nothing has no precision, not 0% and not 100% --
    the guard against rejecting everything looking like success."""
    got = fe.automatic_match_precision([_record(0.10, request_id="r1")], ACCEPT, REVIEW,
                                       _lookup(r1="Acceptable"), {"r1": "answerable"},
                                       "conservative")
    assert got["of"] == 0 and got["rate"] is None


# --- the criterion ----------------------------------------------------------

def _split(records, lookup, answerability, modes):
    by_id = {rid: {"matching_mode": m, "text": ""} for rid, m in modes.items()}
    return fe.split_report(records, ACCEPT, REVIEW, lookup, answerability, by_id)


def test_the_criterion_is_judged_on_the_conservative_view():
    """20 automatic matches, 19 acceptable conservatively, all 20 practically:
    95.0% conservative clears, and the practical-only flag stays off."""
    records = [_record(0.90, request_id=f"r{i}") for i in range(20)]
    lookup = {}
    for i in range(20):
        label = "Acceptable" if i else "Needs clarification"
        lookup.update({em._pair_key(f"r{i}", 1, "p1"):
                       {"conservative": label, "practical": "Acceptable",
                        "is_best_guess": i == 0}})
    answerability = {f"r{i}": "answerable" for i in range(20)}
    modes = {f"r{i}": "exact" for i in range(20)}
    report = _split(records, lookup, answerability, modes)
    assert report["automatic_match_precision"]["conservative"]["rate"] == 0.95
    assert report["meets_criterion_conservative"]
    assert not report["meets_criterion_practical_only"]


def test_clearing_on_the_practical_view_only_is_flagged_as_exactly_that():
    records = [_record(0.90, request_id=f"r{i}") for i in range(20)]
    lookup = {}
    for i in range(20):
        label = "Acceptable" if i > 1 else "Needs clarification"
        lookup.update({em._pair_key(f"r{i}", 1, "p1"):
                       {"conservative": label, "practical": "Acceptable",
                        "is_best_guess": i <= 1}})
    answerability = {f"r{i}": "answerable" for i in range(20)}
    modes = {f"r{i}": "flexible" for i in range(20)}
    report = _split(records, lookup, answerability, modes)
    assert report["automatic_match_precision"]["conservative"]["rate"] == 0.90
    assert not report["meets_criterion_conservative"]
    assert report["meets_criterion_practical_only"]


# --- brand-conflict predicate -----------------------------------------------

@pytest.mark.parametrize("requested,candidate", [
    ("Chobani Flip", "Chobani"),
    ("Chobani", "Chobani Flip"),
    ("Land O'Lakes Unsalted", "Land"),
    ("PurAqua Belle Vie", "PurAqua"),
    ("Millville", "millville"),
])
def test_the_same_brand_read_at_different_spans_is_not_a_conflict(requested, candidate):
    assert not fe._brands_conflict(requested, candidate)


@pytest.mark.parametrize("requested,candidate", [
    ("Millville", "Savoritz"),
    ("Peanut Butter", "Millville"),
    ("Chobani Flip", "Yoplait Flip"),
])
def test_two_different_brands_do_conflict(requested, candidate):
    assert fe._brands_conflict(requested, candidate)


# --- constraint violations --------------------------------------------------

class _Ident:
    def __init__(self, brand=None, variant_tokens=""):
        self.brand = brand
        self.variant_tokens = variant_tokens


def _catalog(title, dimension="weight", unit="oz", total=16.0):
    return pd.DataFrame([{
        "store_id": 1, "product_id": "p1", "raw_title": title,
        "pkg_dimension": dimension, "pkg_canonical_unit": unit,
        "pkg_canonical_total": total,
    }])


def _violations(request_text, title, mode="exact", cand_brand=None, cand_variant="",
                dimension="weight", unit="oz", total=16.0):
    catalog = _catalog(title, dimension, unit, total)
    rec = _record(0.9)
    return fe.constraint_violations(
        rec, catalog, {("1", "p1"): 0},
        {("1", "p1"): _Ident(cand_brand, cand_variant)},
        {}, request_text, mode)


def test_a_clean_match_has_no_violations():
    assert _violations("16 oz Millville Peanut Butter",
                       "Millville Peanut Butter (16 oz)",
                       cand_brand="Millville", total=16.0) == []


def test_a_confirmed_size_conflict_is_a_violation():
    """15 oz requested against a 16 oz row: ~6.7% apart, well past the 1%
    rounding tolerance."""
    got = _violations("15 oz peanut butter", "Peanut Butter (16 oz)",
                      mode="flexible", total=16.0)
    assert "size_conflict" in got


def test_a_different_canonical_unit_is_not_this_checks_concern():
    """filter_by_package_size compares totals only within one canonical unit; a
    unit difference is filter_by_dimension's business, not this one's."""
    got = _violations("16 oz peanut butter", "Peanut Butter (454 g)",
                      mode="flexible", unit="g", total=454.0)
    assert "size_conflict" not in got


def test_an_unknown_package_size_on_the_catalog_row_is_never_a_conflict():
    got = _violations("15 oz peanut butter", "Peanut Butter",
                      mode="flexible", unit=None, total=None)
    assert got == []


def test_an_unknown_brand_on_either_side_is_never_a_conflict():
    assert _violations("16 oz Millville Peanut Butter", "Peanut Butter (16 oz)",
                       cand_brand=None) == []


def test_brand_is_not_enforced_in_flexible_mode():
    got = _violations("16 oz Millville Peanut Butter", "Savoritz Peanut Butter (16 oz)",
                      mode="flexible", cand_brand="Savoritz")
    assert "brand_conflict" not in got


def test_a_missing_catalog_row_is_reported_rather_than_skipped():
    rec = _record(0.9)
    got = fe.constraint_violations(rec, _catalog("x"), {}, {}, {}, "16 oz peanut butter",
                                   "flexible")
    assert got == ["catalog_row_not_found"]


def test_the_check_only_inspects_automatic_matches():
    """A review-band or abstained request cannot violate a constraint, because
    it never made a claim."""
    records = [_record(0.60, request_id="r1"), _record(0.10, request_id="r2")]
    by_id = {"r1": {"text": "16 oz peanut butter", "matching_mode": "flexible"},
             "r2": {"text": "16 oz peanut butter", "matching_mode": "flexible"}}
    got = fe.run_constraint_check(records, ACCEPT, REVIEW, by_id, _catalog("x"),
                                  {("1", "p1"): 0}, {}, {})
    assert got["n_automatic_matches_checked"] == 0
    assert got["passes"]
