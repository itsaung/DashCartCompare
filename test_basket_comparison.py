"""Tests for Checkpoint 5 B5: selection rule, basket assembly, comparison."""
import pytest

import basket
import build_availability as ba

ACCEPT, REVIEW = 0.75, 0.69


def C(pid, price_cents, per_package, unit="oz", score=0.9, title=None, store="s1"):
    return basket.Candidate(store_id=store, product_id=pid, title=title or pid,
                            price_cents=price_cents, per_package_total=per_package,
                            canonical_unit=unit, score=score)


def _priced(store="s1", cost=100, score=0.9, text="16 oz peanut butter"):
    line = basket.resolve_lines([text])[0]
    return basket.resolve_line(line, [C("p", cost, 16.0, score=score, store=store)],
                               ACCEPT, REVIEW)


def _review(text="16 oz peanut butter"):
    line = basket.resolve_lines([text])[0]
    return basket.resolve_line(line, [C("p", 100, 16.0, score=0.70)], ACCEPT, REVIEW)


def _missing(text="16 oz peanut butter"):
    line = basket.resolve_lines([text])[0]
    return basket.resolve_line(line, [], ACCEPT, REVIEW)


# --- the selection rule: score first, cost breaks near-ties -------------------

def test_the_best_match_wins_over_a_cheaper_worse_match():
    """B2's failure inverted: a 0.05-worse match that is half the price loses."""
    got = basket.select_for_line(
        [C("right", 499, 16.0, score=0.90), C("cheap_wrong", 199, 16.0, score=0.85)],
        16.0, "oz", min_score=ACCEPT)
    assert got.candidate.product_id == "right"


def test_cost_decides_inside_the_near_tie_band():
    """0.005 apart is inside 0.01 -- effectively the same match, so price wins."""
    got = basket.select_for_line(
        [C("dear", 499, 16.0, score=0.900), C("cheap", 299, 16.0, score=0.895)],
        16.0, "oz", min_score=ACCEPT)
    assert got.candidate.product_id == "cheap"


def test_cost_does_not_reach_outside_the_band():
    """0.02 apart is outside 0.01."""
    got = basket.select_for_line(
        [C("best", 499, 16.0, score=0.900), C("cheap", 199, 16.0, score=0.880)],
        16.0, "oz", min_score=ACCEPT)
    assert got.candidate.product_id == "best"


def test_a_zero_band_is_pure_score_ranking():
    got = basket.select_for_line(
        [C("dear", 499, 16.0, score=0.900), C("cheap", 299, 16.0, score=0.895)],
        16.0, "oz", min_score=ACCEPT, near_tie_band=0.0)
    assert got.candidate.product_id == "dear"


def test_an_unbounded_band_reproduces_cost_only_ranking():
    """B2's original behavior stays reachable, for the sensitivity table."""
    got = basket.select_for_line(
        [C("best", 499, 16.0, score=0.95), C("cheap", 199, 16.0, score=0.76)],
        16.0, "oz", min_score=ACCEPT, near_tie_band=99.0)
    assert got.candidate.product_id == "cheap"


def test_the_declared_band_is_what_ships():
    assert basket.SCORE_NEAR_TIE_BAND == 0.01


def test_the_band_does_not_rescue_a_matcher_error():
    """Honesty check on the tuna case. The cat food OUTSCORES the StarKist
    (0.8044 vs 0.7887), so it is top-1 on match quality and wins whatever cost
    does. The band stops cost from amplifying matcher errors; it cannot fix
    one."""
    got = basket.select_for_line(
        [C("catfood", 69, 5.5, score=0.8044), C("starkist", 149, 5.0, score=0.7887)],
        5.0, "oz", min_score=ACCEPT)
    assert got.candidate.product_id == "catfood"


def test_nothing_accepted_returns_none():
    assert basket.select_for_line([C("a", 99, 16.0, score=0.10)], 16.0, "oz",
                                  min_score=ACCEPT) is None


# --- store basket assembly ------------------------------------------------------

def test_a_basket_is_complete_only_when_every_line_priced():
    got = basket.build_store_basket("s1", "Store", [_priced(cost=100), _priced(cost=250)])
    assert got.complete
    assert got.total_cents == 350


def test_a_review_line_makes_the_basket_incomplete():
    got = basket.build_store_basket("s1", "Store", [_priced(cost=100), _review()])
    assert not got.complete
    assert got.n_review == 1


def test_a_missing_line_makes_the_basket_incomplete():
    got = basket.build_store_basket("s1", "Store", [_priced(cost=100), _missing()])
    assert not got.complete
    assert got.n_missing == 1


def test_an_incomplete_basket_has_no_total_at_all():
    """Not a hidden partial sum. A partial total is the number most likely to be
    misread as a price, so it is never produced."""
    got = basket.build_store_basket("s1", "Store", [_priced(cost=100), _review()])
    assert got.total_cents is None


def test_an_empty_basket_is_incomplete():
    assert not basket.build_store_basket("s1", "Store", []).complete


def test_totals_are_integer_cents():
    got = basket.build_store_basket("s1", "Store", [_priced(cost=199), _priced(cost=250)])
    assert got.total_cents == 449
    assert isinstance(got.total_cents, int) and not isinstance(got.total_cents, float)


def test_verified_and_unverified_lines_are_counted():
    av = {("s1", "p"): ba.Availability(ba.IN_STOCK)}
    got = basket.build_store_basket("s1", "Store", [_priced(cost=100)],
                                    availability_by_key=av)
    assert got.n_verified == 1 and got.n_unverified == 0

    av2 = {("s1", "p"): ba.Availability(ba.UNVERIFIED)}
    got2 = basket.build_store_basket("s1", "Store", [_priced(cost=100)],
                                     availability_by_key=av2)
    assert got2.n_unverified == 1


# --- comparison -------------------------------------------------------------------

def _basket(store, cost=None, complete=True, review=0):
    lines = [] if cost is None else [_priced(store=store, cost=cost)]
    if not complete or review:
        lines = lines + [_review()]
    return basket.build_store_basket(store, store.upper(), lines)


def test_the_cheapest_complete_basket_wins():
    got = basket.compare_stores([_basket("a", 500), _basket("b", 300), _basket("c", 900)])
    assert [b.store_id for b in got["winners"]] == ["b"]
    assert got["cheapest_total_cents"] == 300
    assert not got["is_tie"]


def test_a_cheaper_incomplete_basket_never_outranks_a_complete_one():
    """The plan's hard invariant, enforced by construction: an incomplete basket
    has no total to rank with."""
    got = basket.compare_stores([_basket("complete", 900),
                                 _basket("cheap_but_incomplete", 100, complete=False)])
    assert [b.store_id for b in got["winners"]] == ["complete"]
    assert [b.store_id for b in got["incomplete"]] == ["cheap_but_incomplete"]
    assert all(b.complete for b in got["ranked"])


def test_incomplete_baskets_are_reported_not_discarded():
    got = basket.compare_stores([_basket("a", 500), _basket("b", 100, complete=False)])
    assert len(got["incomplete"]) == 1
    assert got["n_compared"] == 2 and got["n_complete"] == 1


def test_a_three_way_tie_returns_three_stores():
    got = basket.compare_stores([_basket("a", 400), _basket("b", 400), _basket("c", 400)])
    assert len(got["winners"]) == 3
    assert got["is_tie"]


def test_a_two_way_tie_returns_both_not_the_first():
    got = basket.compare_stores([_basket("a", 400), _basket("b", 400), _basket("c", 900)])
    assert {b.store_id for b in got["winners"]} == {"a", "b"}


def test_no_store_can_complete_gives_no_winner_and_a_reason():
    got = basket.compare_stores([_basket("a", 100, complete=False),
                                 _basket("b", 200, complete=False)])
    assert got["winners"] == []
    assert got["cheapest_total_cents"] is None
    assert got["no_winner_reason"] == "no store can complete this basket"


def test_comparing_no_stores_says_so():
    got = basket.compare_stores([])
    assert got["winners"] == [] and got["no_winner_reason"] == "no stores compared"


def test_the_ranking_is_deterministic_on_equal_totals():
    a = basket.compare_stores([_basket("a", 400), _basket("b", 400)])["ranked"]
    b = basket.compare_stores([_basket("b", 400), _basket("a", 400)])["ranked"]
    assert [x.store_id for x in a] == [x.store_id for x in b]


def test_verification_counts_travel_with_every_comparison():
    """Not hidden behind a flag the caller can ignore."""
    got = basket.compare_stores([_basket("a", 500), _basket("b", 300)])
    assert set(got["verification"]) == {"a", "b"}
    assert "storefront artifact" in got["caveat"]


def test_a_review_line_blocks_only_its_own_store():
    """The B5 decision: review is per (line, store). A score below threshold at
    one store says nothing about another, and blocking the whole comparison
    would suppress the ranking on most real lists."""
    got = basket.compare_stores([_basket("has_review", 100, complete=False),
                                 _basket("clean", 800)])
    assert [b.store_id for b in got["winners"]] == ["clean"]
    assert got["n_complete"] == 1
    assert [b.store_id for b in got["incomplete"]] == ["has_review"]


# --- hand-calculated end to end -----------------------------------------------------

def test_a_two_line_basket_totals_to_the_cent():
    """32 oz peanut butter against 16 oz @ 249c = 2 x 249 = 498.
    20 oz pasta against 12 oz @ 179c = 2 x 179 = 358.  Total 856."""
    pb_line = basket.resolve_lines(["32 oz peanut butter"])[0]
    pasta_line = basket.resolve_lines(["20 oz pasta"])[0]
    pb = basket.resolve_line(pb_line, [C("pb", 249, 16.0)], ACCEPT, REVIEW)
    pasta = basket.resolve_line(pasta_line, [C("pa", 179, 12.0)], ACCEPT, REVIEW)
    got = basket.build_store_basket("s1", "Store", [pb, pasta])
    assert (pb.line_cost_cents, pasta.line_cost_cents) == (498, 358)
    assert got.total_cents == 856
