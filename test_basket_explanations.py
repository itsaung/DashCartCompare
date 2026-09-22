"""Tests for Checkpoint 5 B7: itemized explanations."""
import pytest

import basket
import build_availability as ba

ACCEPT, REVIEW = 0.75, 0.69


def C(pid, price_cents, per_package, unit="oz", score=0.9, title=None):
    return basket.Candidate(store_id="s1", product_id=pid, title=title or pid,
                            price_cents=price_cents, per_package_total=per_package,
                            canonical_unit=unit, score=score)


def _resolve(text, candidates, availability=None):
    line = basket.resolve_lines([text])[0]
    return basket.resolve_line(line, candidates, ACCEPT, REVIEW,
                               availability_by_key=availability)


# --- unit price is display only ---------------------------------------------

def test_unit_price_is_per_canonical_unit():
    """169c for 16 oz = 10.5625c per oz."""
    assert basket.unit_price_cents_per_unit(C("a", 169, 16.0)) == pytest.approx(10.5625)


def test_unit_price_is_none_for_an_unpriceable_row_not_an_error():
    assert basket.unit_price_cents_per_unit(C("a", 169, None)) is None
    assert basket.unit_price_cents_per_unit(C("a", 169, 0.0)) is None


def test_the_explanation_says_unit_price_does_not_rank():
    got = basket.explain_line(_resolve("16 oz peanut butter", [C("a", 169, 16.0)]))
    assert "display only" in got["unit_price_note"]


def test_the_better_unit_price_can_lose_and_the_explanation_shows_both():
    """An 80 oz sack at 400c is 5c/oz; a 16 oz box at 149c is 9.3c/oz. For a
    16 oz request the shopper pays 149c, and both numbers are on the page."""
    got = basket.explain_line(_resolve(
        "16 oz peanut butter", [C("sack", 400, 80.0, score=0.90),
                                C("box", 149, 16.0, score=0.895)]))
    assert got["line_cost_cents"] == 149
    assert got["unit_price_cents_per_unit"] > basket.unit_price_cents_per_unit(C("s", 400, 80.0))


# --- why this package -------------------------------------------------------

def test_a_cost_decision_names_the_runner_up_and_the_difference():
    got = basket.explain_line(_resolve(
        "32 oz peanut butter", [C("dear", 189, 18.0, score=0.900, title="18 oz jar"),
                                C("cheap", 169, 16.0, score=0.895, title="16 oz jar")]))
    assert got["line_cost_cents"] == 338
    assert "cheapest accepted option" in got["chosen_because"]
    assert "40c difference" in got["chosen_because"]
    assert got["runner_up"]["line_cost_cents"] == 378


def test_a_match_quality_decision_says_so_rather_than_implying_cost():
    """Outside the near-tie band the better match wins despite being dearer,
    and the explanation must not read as if it were the cheapest."""
    got = basket.explain_line(_resolve(
        "16 oz peanut butter", [C("best", 519, 16.0, score=0.90, title="best match"),
                                C("cheap", 349, 16.0, score=0.85, title="cheaper")]))
    assert got["line_cost_cents"] == 519
    assert "best match among accepted options" in got["chosen_because"]
    assert "170c cheaper" in got["chosen_because"]


def test_a_tie_says_how_it_was_broken():
    got = basket.explain_line(_resolve(
        "16 oz peanut butter", [C("a", 299, 16.0, score=0.900),
                                C("b", 299, 16.0, score=0.895)]))
    assert "tied on cost" in got["chosen_because"]


def test_a_sole_candidate_says_so():
    got = basket.explain_line(_resolve("16 oz peanut butter", [C("only", 169, 16.0)]))
    assert got["runner_up"] is None
    assert "only" in got["chosen_because"]


# --- excess and packages -----------------------------------------------------

def test_excess_is_spelled_out_in_words_when_there_is_any():
    got = basket.explain_line(_resolve("20 oz peanut butter", [C("a", 179, 12.0)]))
    assert got["packages"] == 2
    assert got["excess"] == pytest.approx(4.0)
    assert "4 oz more than requested" in got["excess_note"]


def test_no_excess_note_when_the_fit_is_exact():
    got = basket.explain_line(_resolve("16 oz peanut butter", [C("a", 169, 16.0)]))
    assert got["excess_note"] is None


def test_the_package_price_and_the_line_cost_are_both_shown():
    """A shopper seeing only 338c cannot tell it is two jars."""
    got = basket.explain_line(_resolve("32 oz peanut butter", [C("a", 169, 16.0)]))
    assert (got["package_price_cents"], got["packages"], got["line_cost_cents"]) == (169, 2, 338)


# --- non-priced lines ---------------------------------------------------------

def test_a_review_line_shows_what_it_would_not_commit_to():
    """Showing nothing is what makes a review feel like a failure rather than a
    question."""
    got = basket.explain_line(_resolve("32 oz peanut butter", [C("a", 189, 18.0, score=0.70)]))
    assert got["state"] == basket.LINE_REVIEW
    assert len(got["candidates"]) == 1
    assert got["candidates"][0]["price_cents"] == 189


def test_a_review_line_has_no_cost_fields_at_all():
    got = basket.explain_line(_resolve("32 oz peanut butter", [C("a", 189, 18.0, score=0.70)]))
    assert "line_cost_cents" not in got


def test_a_missing_line_explains_itself():
    got = basket.explain_line(_resolve("32 oz peanut butter", []))
    assert got["state"] == basket.LINE_MISSING
    assert got["reason"]


def test_a_merged_line_shows_every_text_it_came_from():
    line = basket.resolve_lines(["2 lb chicken", "1 lb chicken"])[0]
    res = basket.resolve_line(line, [C("a", 599, 16.0)], ACCEPT, REVIEW)
    got = basket.explain_line(res)
    assert got["merged_from"] == ["2 lb chicken", "1 lb chicken"]
    assert got["requested"] == "48 oz"


def test_an_unmerged_line_has_no_merged_from():
    got = basket.explain_line(_resolve("16 oz peanut butter", [C("a", 169, 16.0)]))
    assert got["merged_from"] is None


# --- availability -------------------------------------------------------------

def test_availability_state_travels_with_a_priced_line():
    av = {("s1", "a"): ba.Availability(ba.IN_STOCK_LIMITED, remaining=3)}
    got = basket.explain_line(_resolve("16 oz peanut butter", [C("a", 169, 16.0)], av),
                              availability_by_key=av)
    assert got["availability"]["state"] == ba.IN_STOCK_LIMITED
    assert got["availability"]["remaining"] == 3
    assert got["availability"]["verified"]


def test_excluded_out_of_stock_candidates_are_named_in_the_explanation():
    av = {("s1", "oos"): ba.Availability(ba.OUT_OF_STOCK)}
    got = basket.explain_line(_resolve("32 oz peanut butter",
                                       [C("oos", 99, 32.0), C("ok", 169, 16.0)], av),
                              availability_by_key=av)
    assert [x["product_id"] for x in got["excluded_out_of_stock"]] == ["oos"]


# --- whole basket ---------------------------------------------------------------

def test_a_basket_total_never_appears_without_its_state():
    got = basket.explain_basket(basket.build_store_basket(
        "s1", "Store", [_resolve("16 oz peanut butter", [C("a", 169, 16.0)])]))
    assert got["total_cents"] == 169
    assert got["complete"] is True
    assert got["lines"] == {"total": 1, "priced": 1, "review": 0, "missing": 0}
    assert "verified_lines" in got["availability"]


def test_an_incomplete_basket_reports_no_total_and_says_why():
    got = basket.explain_basket(basket.build_store_basket("s1", "Store", [
        _resolve("16 oz peanut butter", [C("a", 169, 16.0)]),
        _resolve("32 oz crackers", []),
    ]))
    assert got["total_cents"] is None
    assert got["complete"] is False
    assert got["lines"]["missing"] == 1


def test_the_basket_carries_the_unverified_caveat():
    av = {("s1", "a"): ba.Availability(ba.UNVERIFIED)}
    got = basket.explain_basket(
        basket.build_store_basket("s1", "Store",
                                  [_resolve("16 oz peanut butter", [C("a", 169, 16.0)], av)],
                                  availability_by_key=av),
        availability_by_key=av)
    assert got["availability"]["unverified_lines"] == 1
    assert "best effort" in got["availability"]["note"]


def test_every_line_is_itemised():
    got = basket.explain_basket(basket.build_store_basket("s1", "Store", [
        _resolve("16 oz peanut butter", [C("a", 169, 16.0)]),
        _resolve("32 oz crackers", []),
    ]))
    assert len(got["items"]) == 2
    assert [i["state"] for i in got["items"]] == [basket.LINE_PRICED, basket.LINE_MISSING]
