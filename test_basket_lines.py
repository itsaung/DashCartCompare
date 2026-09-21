"""Tests for Checkpoint 5 B4: duplicates, the three-way response, overrides."""
import pytest

import basket
import build_availability as ba

ACCEPT, REVIEW = 0.75, 0.69


def C(pid, price_cents, per_package, unit="oz", score=0.9, title=None):
    return basket.Candidate(store_id="s1", product_id=pid, title=title or pid,
                            price_cents=price_cents, per_package_total=per_package,
                            canonical_unit=unit, score=score)


# --- duplicate resolution ---------------------------------------------------

def test_two_lines_of_the_same_thing_become_one():
    """'2 lb chicken' + '1 lb chicken' = 3 lb = 48 oz, counted once."""
    lines = basket.resolve_lines(["2 lb chicken", "1 lb chicken"])
    assert len(lines) == 1
    assert lines[0].canonical_quantity == pytest.approx(48.0)
    assert lines[0].merged
    assert lines[0].texts == ("2 lb chicken", "1 lb chicken")


def test_three_duplicates_all_merge():
    lines = basket.resolve_lines(["1 lb chicken", "1 lb chicken", "2 lb chicken"])
    assert len(lines) == 1
    assert lines[0].canonical_quantity == pytest.approx(64.0)


def test_different_products_do_not_merge():
    lines = basket.resolve_lines(["1 lb chicken", "1 lb beef"])
    assert len(lines) == 2


def test_the_same_product_in_different_units_does_not_merge():
    """The plan's explicit 'must not merge' case: a count of eggs and a weight
    of eggs are not the same request, and summing them is meaningless."""
    lines = basket.resolve_lines(["12 eggs", "16 oz eggs"])
    assert len(lines) == 2


def test_the_same_product_in_different_modes_does_not_merge():
    """Exact and flexible are different requests for the same words."""
    lines = basket.resolve_lines(["1 lb chicken", "1 lb chicken"],
                                 modes_by_index={0: "exact", 1: "flexible"})
    assert len(lines) == 2


def test_unparseable_lines_never_merge_with_each_other():
    """They have no canonical unit to merge ON, and guessing two unparseable
    lines are the same request is the fuzzy matching this rule excludes."""
    lines = basket.resolve_lines(["milk", "milk"])
    assert len(lines) == 2
    assert all(l.needs_review for l in lines)


def test_merging_preserves_list_order():
    lines = basket.resolve_lines(["16 oz peanut butter", "1 lb chicken",
                                  "2 lb chicken", "12 oz pasta"])
    assert [l.product_type for l in lines] == ["peanut butter", "chicken", "pasta"]


def test_a_merged_line_keeps_every_original_text_for_the_explanation():
    lines = basket.resolve_lines(["2 lb chicken", "1 lb chicken"])
    assert len(lines[0].texts) == 2


# --- the three-way response -------------------------------------------------

def test_the_three_states_are_distinct():
    assert basket.line_state("answerable", 0.80, ACCEPT, REVIEW) == basket.LINE_PRICED
    assert basket.line_state("answerable", 0.70, ACCEPT, REVIEW) == basket.LINE_REVIEW
    assert basket.line_state("answerable", 0.50, ACCEPT, REVIEW) == basket.LINE_MISSING


def test_a_parser_gate_is_review_regardless_of_score():
    assert basket.line_state("needs_clarification", 0.99, ACCEPT, REVIEW) == basket.LINE_REVIEW


def test_an_abstention_is_missing():
    assert basket.line_state("no_acceptable_match", None, ACCEPT, REVIEW) == basket.LINE_MISSING


def test_the_boundaries_land_where_the_thresholds_say():
    assert basket.line_state("answerable", ACCEPT, ACCEPT, REVIEW) == basket.LINE_PRICED
    assert basket.line_state("answerable", REVIEW, ACCEPT, REVIEW) == basket.LINE_REVIEW


def test_line_state_agrees_with_the_frozen_threshold_rule():
    """One rule, two implementations, pinned together.

    basket.line_state restates tune_threshold_v3.apply_cut_points rather than
    importing it (that module pulls in the whole evaluation stack, and pricing
    a line should not depend on the benchmark). This asserts the restatement
    did not drift from the rule Checkpoint 4's cut points were selected under.
    """
    from tune_threshold_v3 import apply_cut_points
    mapping = {"accept": basket.LINE_PRICED, "review": basket.LINE_REVIEW,
               "no_match": basket.LINE_MISSING}
    for response in ("answerable", "needs_clarification", "no_acceptable_match"):
        for score in (0.0, 0.50, 0.689, REVIEW, 0.72, ACCEPT, 0.99):
            record = {"request_id": "r1", "response": response,
                      "results": [{"store_id": 1, "product_id": "p", "score": score}]}
            expected = mapping[apply_cut_points(record, ACCEPT, REVIEW)]
            assert basket.line_state(response, score, ACCEPT, REVIEW) == expected, (
                response, score)


def test_a_review_line_is_never_priced():
    """The plan's hardest anti-goal: review is the matcher declining to commit,
    and pricing it anyway converts a declared uncertainty into a number."""
    line = basket.resolve_lines(["32 oz peanut butter"])[0]
    got = basket.resolve_line(line, [C("a", 199, 32.0, score=0.70)], ACCEPT, REVIEW)
    assert got.state == basket.LINE_REVIEW
    assert got.selection is None and got.line_cost_cents is None


def test_a_review_line_still_carries_its_candidates():
    """It is 'show the shopper the options', not 'return nothing'."""
    line = basket.resolve_lines(["32 oz peanut butter"])[0]
    got = basket.resolve_line(line, [C("a", 199, 32.0, score=0.70)], ACCEPT, REVIEW)
    assert len(got.candidates) == 1


def test_a_line_whose_parse_failed_is_review_before_any_retrieval():
    line = basket.resolve_lines(["milk"])[0]
    got = basket.resolve_line(line, [], ACCEPT, REVIEW)
    assert got.state == basket.LINE_REVIEW
    assert "no recognizable quantity" in got.reason


def test_accepted_but_unpriceable_is_review_not_a_match_and_not_an_abstention():
    """There IS a product; its package size is unknown. Neither of the other
    two states says that."""
    line = basket.resolve_lines(["32 oz peanut butter"])[0]
    got = basket.resolve_line(line, [C("nosize", 199, None, score=0.95)], ACCEPT, REVIEW)
    assert got.state == basket.LINE_REVIEW
    assert "no resolvable package size" in got.reason


def test_a_priced_line_prices():
    line = basket.resolve_lines(["32 oz peanut butter"])[0]
    got = basket.resolve_line(line, [C("a", 249, 16.0, score=0.95)], ACCEPT, REVIEW)
    assert got.state == basket.LINE_PRICED
    assert got.line_cost_cents == 498          # 2 x 249, hand-calculated


# --- availability ------------------------------------------------------------

def test_out_of_stock_candidates_are_excluded_before_pricing():
    """The cheap one is out of stock, so the line prices against the other."""
    line = basket.resolve_lines(["32 oz peanut butter"])[0]
    av = {("s1", "oos"): ba.Availability(ba.OUT_OF_STOCK),
          ("s1", "ok"): ba.Availability(ba.IN_STOCK)}
    got = basket.resolve_line(line, [C("oos", 99, 32.0, score=0.95),
                                     C("ok", 249, 16.0, score=0.90)],
                              ACCEPT, REVIEW, availability_by_key=av)
    assert got.selection.candidate.product_id == "ok"
    assert got.line_cost_cents == 498


def test_an_excluded_candidate_is_named_not_silently_dropped():
    """An exclusion the shopper cannot see is indistinguishable from the store
    not carrying the product."""
    line = basket.resolve_lines(["32 oz peanut butter"])[0]
    av = {("s1", "oos"): ba.Availability(ba.OUT_OF_STOCK)}
    got = basket.resolve_line(line, [C("oos", 99, 32.0), C("ok", 249, 16.0)],
                              ACCEPT, REVIEW, availability_by_key=av)
    assert [c.product_id for c in got.excluded_out_of_stock] == ["oos"]


def test_an_unverified_candidate_is_still_eligible():
    """49% of the catalog is unverified; excluding it would empty the basket."""
    line = basket.resolve_lines(["32 oz peanut butter"])[0]
    av = {("s1", "a"): ba.Availability(ba.UNVERIFIED)}
    got = basket.resolve_line(line, [C("a", 249, 16.0)], ACCEPT, REVIEW,
                              availability_by_key=av)
    assert got.state == basket.LINE_PRICED


def test_everything_out_of_stock_leaves_the_line_missing():
    line = basket.resolve_lines(["32 oz peanut butter"])[0]
    av = {("s1", "a"): ba.Availability(ba.OUT_OF_STOCK)}
    got = basket.resolve_line(line, [C("a", 249, 16.0)], ACCEPT, REVIEW,
                              availability_by_key=av)
    assert got.state == basket.LINE_MISSING
    assert len(got.excluded_out_of_stock) == 1


# --- overrides ----------------------------------------------------------------

def test_an_override_recalculates_count_cost_and_excess():
    """20 oz wanted; shopper picks a 12 oz package at $1.79.
    ceil(20/12) = 2 · 2 x 179 = 358c · excess 24 - 20 = 4 oz."""
    line = basket.resolve_lines(["20 oz peanut butter"])[0]
    before = basket.resolve_line(line, [C("a", 249, 20.0, score=0.95)], ACCEPT, REVIEW)
    assert before.line_cost_cents == 249

    after = basket.apply_override(before, C("chosen", 179, 12.0))
    assert after.state == basket.LINE_PRICED
    assert after.selection.arithmetic.packages == 2
    assert after.line_cost_cents == 358
    assert after.selection.arithmetic.excess == pytest.approx(4.0)
    assert after.overridden


def test_an_override_resolves_a_review_line():
    """The common case: the shopper picks from the candidates they were shown."""
    line = basket.resolve_lines(["32 oz peanut butter"])[0]
    before = basket.resolve_line(line, [C("a", 199, 32.0, score=0.70)], ACCEPT, REVIEW)
    assert before.state == basket.LINE_REVIEW

    after = basket.apply_override(before, C("a", 199, 32.0))
    assert after.state == basket.LINE_PRICED
    assert after.line_cost_cents == 199


def test_an_override_works_on_a_line_the_matcher_abstained_on():
    """An override is the shopper overruling the matcher, which is the point."""
    line = basket.resolve_lines(["32 oz peanut butter"])[0]
    before = basket.resolve_line(line, [], ACCEPT, REVIEW)
    assert before.state == basket.LINE_MISSING

    after = basket.apply_override(before, C("picked", 449, 48.0))
    assert after.state == basket.LINE_PRICED
    assert after.line_cost_cents == 449
    assert after.selection.arithmetic.excess == pytest.approx(16.0)


def test_an_override_never_patches_the_old_arithmetic():
    """Recomputed from scratch -- a partially-updated total is worse than none."""
    line = basket.resolve_lines(["20 oz peanut butter"])[0]
    before = basket.resolve_line(line, [C("a", 249, 20.0, score=0.95)], ACCEPT, REVIEW)
    after = basket.apply_override(before, C("b", 179, 12.0))
    assert before.selection.arithmetic.packages == 1      # untouched
    assert after.selection.arithmetic.packages == 2


def test_an_override_that_cannot_be_priced_raises():
    """Silently producing no cost would look like a successful selection."""
    line = basket.resolve_lines(["20 oz peanut butter"])[0]
    before = basket.resolve_line(line, [], ACCEPT, REVIEW)
    with pytest.raises(basket.UnresolvedSizeError):
        basket.apply_override(before, C("nosize", 199, None))


def test_an_override_on_a_line_with_no_resolvable_amount_raises():
    line = basket.resolve_lines(["milk"])[0]
    before = basket.resolve_line(line, [], ACCEPT, REVIEW)
    with pytest.raises(basket.BasketArithmeticError):
        basket.apply_override(before, C("a", 199, 64.0))


def test_an_override_in_the_wrong_unit_raises():
    line = basket.resolve_lines(["20 oz peanut butter"])[0]
    before = basket.resolve_line(line, [], ACCEPT, REVIEW)
    with pytest.raises(basket.UnitMismatchError):
        basket.apply_override(before, C("a", 199, 64.0, unit="fl oz"))


def test_an_override_on_a_merged_line_uses_the_merged_quantity():
    """'2 lb chicken' + '1 lb chicken' = 48 oz. Against a 16 oz pack at 599c:
    ceil(48/16) = 3 packages = 1797c."""
    line = basket.resolve_lines(["2 lb chicken", "1 lb chicken"])[0]
    before = basket.resolve_line(line, [], ACCEPT, REVIEW)
    after = basket.apply_override(before, C("pack", 599, 16.0))
    assert after.selection.arithmetic.packages == 3
    assert after.line_cost_cents == 1797
