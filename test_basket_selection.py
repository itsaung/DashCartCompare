"""Tests for Checkpoint 5 B2: size-sufficient candidates and cheapest selection.

Every expected value is hand-calculated. Prices are written as whole cents and
the arithmetic is spelled out in each docstring, so a failure says which sum is
wrong rather than which snapshot moved.
"""
import pandas as pd
import pytest

import basket
import retrieval
from parse_query import parse_shopping_line


def C(pid, price_cents, per_package, unit="oz", score=0.5, title=None, pkg_count=None):
    return basket.Candidate(store_id="s1", product_id=pid, title=title or pid,
                            price_cents=price_cents, per_package_total=per_package,
                            canonical_unit=unit, score=score, pkg_count=pkg_count)


# --- the plan's named selection cases ------------------------------------------

def test_two_small_packages_win_when_they_are_genuinely_cheaper():
    """32 oz wanted. 2 x 16 oz @ $2.49 = 498c. 1 x 64 oz @ $5.49 = 549c.
    The pair is cheaper, and wins despite being two packages."""
    got = basket.select_cheapest_sufficient([C("16oz", 249, 16.0), C("64oz", 549, 64.0)],
                                            32.0, "oz")
    assert got.candidate.product_id == "16oz"
    assert got.arithmetic.packages == 2
    assert got.line_cost_cents == 498


def test_one_big_package_wins_when_it_is_cheaper_despite_more_excess():
    """32 oz wanted. 2 x 16 oz @ $2.49 = 498c, no excess.
    1 x 64 oz @ $3.99 = 399c, 32 oz excess. Cost decides, not waste."""
    got = basket.select_cheapest_sufficient([C("16oz", 249, 16.0), C("64oz", 399, 64.0)],
                                            32.0, "oz")
    assert got.candidate.product_id == "64oz"
    assert got.line_cost_cents == 399
    assert got.arithmetic.excess == pytest.approx(32.0)


def test_a_cost_tie_is_broken_by_less_excess():
    """Both cost 400c for 30 oz: 2 x 16 oz (excess 2) vs 1 x 64 oz (excess 34).
    Excess only ever breaks a genuine tie -- it is never priced in."""
    got = basket.select_cheapest_sufficient([C("64oz", 400, 64.0), C("16oz", 200, 16.0)],
                                            30.0, "oz")
    assert got.candidate.product_id == "16oz"
    assert got.line_cost_cents == 400
    assert got.arithmetic.excess == pytest.approx(2.0)


def test_a_cost_and_excess_tie_is_broken_by_score_then_id():
    got = basket.select_cheapest_sufficient(
        [C("bbb", 200, 16.0, score=0.1), C("aaa", 200, 16.0, score=0.9)], 16.0, "oz")
    assert got.candidate.product_id == "aaa"


def test_the_ordering_is_total_so_a_rerun_cannot_reshuffle():
    cands = [C("bbb", 200, 16.0, score=0.5), C("aaa", 200, 16.0, score=0.5)]
    first = basket.select_cheapest_sufficient(cands, 16.0, "oz").candidate.product_id
    for _ in range(5):
        assert basket.select_cheapest_sufficient(
            list(reversed(cands)), 16.0, "oz").candidate.product_id == first


def test_unit_price_and_purchase_cost_disagree_and_purchase_cost_wins():
    """The case that makes this a cost ranking rather than a unit-price one.
    1 lb (16 oz) wanted. The 80 oz sack is 5c/oz -- much better value -- but
    costs 400c. The 16 oz box is 9.3c/oz and costs 149c. The shopper pays 149."""
    sack, box = C("sack", 400, 80.0), C("box", 149, 16.0)
    assert 400 / 80 < 149 / 16                      # sack has the better unit price
    got = basket.select_cheapest_sufficient([sack, box], 16.0, "oz")
    assert got.candidate.product_id == "box"


# --- unresolved sizes are surfaced, not dropped ----------------------------------

def test_an_unresolved_size_never_wins_a_line():
    """A 99c row with no package size must not beat a priced one by looking
    cheap -- the plan's explicit anti-goal."""
    got = basket.select_cheapest_sufficient([C("nosize", 99, None), C("16oz", 249, 16.0)],
                                            16.0, "oz")
    assert got.candidate.product_id == "16oz"


def test_unresolved_candidates_come_back_on_the_selection():
    got = basket.select_cheapest_sufficient(
        [C("nosize", 99, None), C("variable", 150, 0.0), C("16oz", 249, 16.0)], 16.0, "oz")
    assert {c.product_id for c in got.unresolved} == {"nosize", "variable"}


def test_nothing_priceable_returns_none_rather_than_a_guess():
    assert basket.select_cheapest_sufficient([C("nosize", 99, None)], 16.0, "oz") is None
    assert basket.select_cheapest_sufficient([], 16.0, "oz") is None


def test_a_mismatched_unit_candidate_is_skipped_not_raised():
    """A mixed-unit candidate list is ordinary at this level; compute_line's
    raise is right only once a caller has committed to one package."""
    got = basket.select_cheapest_sufficient(
        [C("volume", 99, 16.0, unit="fl oz"), C("weight", 249, 16.0, unit="oz")], 16.0, "oz")
    assert got.candidate.product_id == "weight"
    assert got.considered == 1


# --- runner-up and provenance ------------------------------------------------------

def test_the_runner_up_is_reported_for_the_explanation():
    got = basket.select_cheapest_sufficient(
        [C("cheap", 199, 32.0), C("dear", 299, 32.0)], 32.0, "oz")
    assert got.candidate.product_id == "cheap"
    assert got.runner_up.candidate.product_id == "dear"
    assert got.runner_up.line_cost_cents == 299
    assert got.considered == 2


def test_a_single_candidate_has_no_runner_up():
    got = basket.select_cheapest_sufficient([C("only", 199, 32.0)], 32.0, "oz")
    assert got.runner_up is None


def test_money_out_of_selection_is_an_int():
    got = basket.select_cheapest_sufficient([C("a", 199, 32.0)], 32.0, "oz")
    assert isinstance(got.line_cost_cents, int) and not isinstance(got.line_cost_cents, float)


# --- filter_by_size_sufficient ------------------------------------------------------

def _catalog():
    return pd.DataFrame([
        {"store_id": 1, "product_id": "ok", "pkg_canonical_unit": "oz",
         "pkg_canonical_total": 16.0},
        {"store_id": 1, "product_id": "nosize", "pkg_canonical_unit": None,
         "pkg_canonical_total": None},
        {"store_id": 1, "product_id": "variable", "pkg_canonical_unit": "oz",
         "pkg_canonical_total": 0.0},
        {"store_id": 1, "product_id": "otherunit", "pkg_canonical_unit": "fl oz",
         "pkg_canonical_total": 16.0},
    ])


def _cands():
    return [{"row": i, "score": 0.5} for i in range(4)]


def test_size_sufficient_separates_unresolved_from_incomparable():
    """An unresolved size is handed back; a different canonical unit is dropped.
    'No size' and 'wrong dimension' are different answers and a basket has to be
    able to tell a shopper which one it hit."""
    text = "32 oz peanut butter"
    sufficient, unresolved = retrieval.filter_by_size_sufficient(
        _cands(), _catalog(), text, parse_shopping_line(text))
    assert [c["row"] for c in sufficient] == [0]
    assert sorted(c["row"] for c in unresolved) == [1, 2]


def test_a_smaller_package_survives_the_sufficiency_gate():
    """The whole point: a 16 oz row is a legitimate answer to a 32 oz request
    (buy two), where filter_by_package_size would have dropped it."""
    text = "32 oz peanut butter"
    structured = parse_shopping_line(text)
    sufficient, _ = retrieval.filter_by_size_sufficient(
        _cands(), _catalog(), text, structured)
    assert [c["row"] for c in sufficient] == [0]
    kept_by_frozen = retrieval.filter_by_package_size(
        _cands(), _catalog(), text, structured)
    assert [c["row"] for c in kept_by_frozen] != [0]


def test_an_unresolvable_request_amount_claims_nothing():
    text = "some peanut butter"
    sufficient, unresolved = retrieval.filter_by_size_sufficient(
        _cands(), _catalog(), text, parse_shopping_line(text))
    assert len(sufficient) == 4 and unresolved == []


def test_the_frozen_size_filter_is_untouched():
    """Checkpoint 4's published numbers depend on filter_by_package_size
    byte-for-byte. B2 is a sibling, not a modification."""
    text = "16 oz peanut butter"
    structured = parse_shopping_line(text)
    kept = retrieval.filter_by_package_size(_cands(), _catalog(), text, structured)
    # row 0 matches exactly; row 1 has an unknown size (never filtered); row 3
    # is a different canonical unit (not this filter's concern). Row 2 is the
    # interesting one: its total is 0.0, which pd.notna() reads as a KNOWN size,
    # so the frozen filter treats it as a confirmed 16-oz-vs-0-oz conflict and
    # drops it. B2's sibling calls a non-positive total unresolved instead,
    # which is the better reading -- but filter_by_package_size stays exactly as
    # Checkpoint 4 published it, and this test pins that.
    assert sorted(c["row"] for c in kept) == [0, 1, 3]


# --- end-to-end against the parser, with hand arithmetic ---------------------------

def test_a_container_phrased_request_now_prices_correctly():
    """'3 boxes of 12 oz pasta' is 36 oz. Against a 16 oz box at 129c:
    ceil(36/16) = 3 packages = 387c, excess 48 - 36 = 12 oz."""
    structured = parse_shopping_line("3 boxes of 12 oz pasta")
    assert structured["canonical_quantity"] == pytest.approx(36.0)
    got = basket.select_cheapest_sufficient([C("16oz", 129, 16.0)], 36.0, "oz")
    assert got.arithmetic.packages == 3
    assert got.line_cost_cents == 387
    assert got.arithmetic.excess == pytest.approx(12.0)
