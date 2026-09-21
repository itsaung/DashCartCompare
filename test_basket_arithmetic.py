"""Tests for basket.py (Checkpoint 5, B1).

Every expected value below is hand-calculated and written out in the test, not
read off a run. This module is arithmetic; a test that asserts whatever the code
already returns would assert nothing.
"""
import math

import pytest

import basket
from retrieval import PACKAGE_SIZE_ROUNDING_TOLERANCE


# --- packages_needed: the plan's four named cases -------------------------------

def test_exact_fit_needs_one_package():
    """12 oz requested, 12 oz package: 12 / 12 = 1.0 -> 1."""
    assert basket.packages_needed(12.0, 12.0) == 1


def test_overshoot_rounds_up():
    """13 / 12 = 1.083 -> 2 packages."""
    assert basket.packages_needed(13.0, 12.0) == 2


def test_less_than_one_package_still_needs_one():
    """5 / 12 = 0.417 -> 1. You cannot buy 0.417 of a package."""
    assert basket.packages_needed(5.0, 12.0) == 1


def test_a_multipack_is_divided_by_its_total_not_its_pack_count():
    """A 12 fl oz x 12 ct case canonicalizes to 144 fl oz TOTAL. A 288 fl oz
    request is 2 cases, not 24."""
    assert basket.packages_needed(288.0, 144.0) == 2


def test_several_whole_multiples():
    assert basket.packages_needed(48.0, 16.0) == 3
    assert basket.packages_needed(49.0, 16.0) == 4


# --- the rounding tolerance -----------------------------------------------------

def test_label_rounding_does_not_buy_a_second_package():
    """The case this tolerance exists for: normalize.py turns "500 g" into
    17.637 oz and "17.6 oz" into 17.6, a quotient of 1.0021. Without the
    tolerance a shopper pays for two packages because one label was printed in
    grams."""
    assert 17.637 / 17.6 > 1.0                      # genuinely over, by float dust
    assert basket.packages_needed(17.637, 17.6) == 1


def test_a_real_shortfall_still_rounds_up():
    """13 oz against a 12 oz package is 8.3% over -- far outside the 1%
    tolerance, and a real second package."""
    assert basket.packages_needed(13.0, 12.0) == 2


def test_the_tolerance_is_one_sided_and_never_creates_a_shortfall():
    """Just outside tolerance must round up. 12 oz * 1.02 = 12.24 requested
    against a 12 oz package: 2% over, tolerance is 1%, so 2 packages."""
    assert PACKAGE_SIZE_ROUNDING_TOLERANCE == 0.01
    assert basket.packages_needed(12.24, 12.0) == 2


def test_the_tolerance_applies_at_every_whole_multiple_not_just_one():
    """Two packages plus float dust is still two packages: 24.05 / 12 = 2.004,
    within 1% of 2."""
    assert basket.packages_needed(24.05, 12.0) == 2


def test_the_tolerance_never_applies_below_one_package():
    """0.5 / 12 is nowhere near a whole package and must not snap to zero."""
    assert basket.packages_needed(0.5, 12.0) == 1


def test_tolerance_is_relative_not_absolute():
    """1% of 1000 is 10 units; 1005/1000 = 1.005 snaps down, 1015 does not."""
    assert basket.packages_needed(1005.0, 1000.0) == 1
    assert basket.packages_needed(1015.0, 1000.0) == 2


# --- unresolved and invalid sizes -----------------------------------------------

@pytest.mark.parametrize("bad", [None, 0, 0.0, -1.0])
def test_an_unresolvable_package_size_raises_rather_than_defaulting(bad):
    """3,122 frozen-catalog rows have no pkg_canonical_total and 1,000 are
    variable_weight. Defaulting any of them to 1 package would invent a price."""
    with pytest.raises(basket.UnresolvedSizeError):
        basket.packages_needed(12.0, bad)


def test_nan_package_size_raises():
    with pytest.raises(basket.UnresolvedSizeError):
        basket.packages_needed(12.0, float("nan"))


@pytest.mark.parametrize("bad", [None, 0, -5.0, "12"])
def test_a_non_positive_or_non_numeric_request_raises(bad):
    with pytest.raises(basket.BasketArithmeticError):
        basket.packages_needed(bad, 12.0)


def test_unresolved_size_error_is_a_basket_arithmetic_error():
    """Callers that only want to catch 'this line could not be computed' should
    not need to enumerate subclasses."""
    assert issubclass(basket.UnresolvedSizeError, basket.BasketArithmeticError)
    assert issubclass(basket.UnitMismatchError, basket.BasketArithmeticError)


# --- units are a precondition, never a conversion --------------------------------

def test_mismatched_units_raise():
    with pytest.raises(basket.UnitMismatchError):
        basket.require_same_unit("oz", "fl oz")


def test_the_cross_unit_case_this_module_refuses_to_guess():
    """A 2 L bottle (67.628 fl oz) against a 67.6 fl oz request is the r017
    failure. Numerically it would divide fine; whether it SHOULD is B2's open
    question 1, so B1 raises rather than answering it silently."""
    with pytest.raises(basket.UnitMismatchError):
        basket.compute_line(67.6, "fl oz", 453.592, "oz", 199)


@pytest.mark.parametrize("requested,package", [(None, "oz"), ("oz", None), ("", "oz"), ("oz", "")])
def test_an_unknown_unit_is_a_mismatch_not_a_wildcard(requested, package):
    with pytest.raises(basket.UnitMismatchError):
        basket.require_same_unit(requested, package)


def test_matching_units_pass_through():
    assert basket.require_same_unit("fl oz", "fl oz") == "fl oz"


# --- money is integer cents ------------------------------------------------------

def test_line_cost_is_packages_times_price():
    """3 packages at $2.49 = 747 cents, hand-calculated."""
    assert basket.line_cost_cents(3, 249) == 747


def test_line_cost_returns_an_int_not_a_float():
    cost = basket.line_cost_cents(3, 249)
    assert isinstance(cost, int) and not isinstance(cost, bool)
    assert not isinstance(cost, float)


def test_a_float_price_is_rejected_not_coerced():
    """2.49 dollars is the exact mistake this module exists to catch. Coercing
    it would produce 2 cents and look like it worked."""
    with pytest.raises(basket.BasketArithmeticError):
        basket.line_cost_cents(3, 2.49)


def test_a_float_package_count_is_rejected():
    with pytest.raises(basket.BasketArithmeticError):
        basket.line_cost_cents(3.0, 249)


def test_bool_is_rejected_although_it_is_an_int_subclass():
    """True would silently price exactly one package."""
    with pytest.raises(basket.BasketArithmeticError):
        basket.line_cost_cents(True, 249)
    with pytest.raises(basket.BasketArithmeticError):
        basket.line_cost_cents(1, True)


def test_zero_or_negative_packages_are_rejected():
    for bad in (0, -1):
        with pytest.raises(basket.BasketArithmeticError):
            basket.line_cost_cents(bad, 249)


def test_a_negative_price_is_rejected():
    with pytest.raises(basket.BasketArithmeticError):
        basket.line_cost_cents(1, -1)


def test_a_free_item_is_allowed():
    """0 cents is a legitimate price; only negative is not."""
    assert basket.line_cost_cents(2, 0) == 0


# --- excess ----------------------------------------------------------------------

def test_excess_on_an_overshoot():
    """2 packages x 12 oz = 24 oz bought against 13 oz requested -> 11 oz."""
    assert basket.excess_quantity(2, 12.0, 13.0) == pytest.approx(11.0)


def test_excess_when_one_package_overshoots_a_small_request():
    """1 x 12 oz against 5 oz requested -> 7 oz excess."""
    assert basket.excess_quantity(1, 12.0, 5.0) == pytest.approx(7.0)


def test_excess_is_zero_on_an_exact_fit():
    assert basket.excess_quantity(1, 12.0, 12.0) == 0.0


def test_excess_floors_at_zero_inside_the_rounding_tolerance():
    """17.6 - 17.637 is -0.037. Reporting that as a shortfall would be a worse
    lie than reporting no excess, because the package was accepted as
    sufficient."""
    assert basket.excess_quantity(1, 17.6, 17.637) == 0.0


def test_excess_rejects_a_non_integer_package_count():
    with pytest.raises(basket.BasketArithmeticError):
        basket.excess_quantity(1.5, 12.0, 13.0)


# --- compute_line: the composed entry point ---------------------------------------

def test_compute_line_hand_calculated_end_to_end():
    """32 oz requested, 16 oz packages at $2.49 each.
    packages = ceil(32/16) = 2 · cost = 2 x 249 = 498 · excess = 32 - 32 = 0."""
    got = basket.compute_line(32.0, "oz", 16.0, "oz", 249)
    assert (got.packages, got.line_cost_cents, got.excess) == (2, 498, 0.0)
    assert got.canonical_unit == "oz"


def test_compute_line_with_overshoot_hand_calculated():
    """20 oz requested, 12 oz packages at $1.79.
    packages = ceil(20/12) = ceil(1.667) = 2 · cost = 358 · excess = 24 - 20 = 4."""
    got = basket.compute_line(20.0, "oz", 12.0, "oz", 179)
    assert got.packages == 2
    assert got.line_cost_cents == 358
    assert got.excess == pytest.approx(4.0)


def test_compute_line_carries_pack_count_without_dividing_by_it():
    """A 144 fl oz case (12 fl oz x 12 ct) against a 288 fl oz request is 2
    cases. If pkg_count were divided by, this would be 24."""
    got = basket.compute_line(288.0, "fl oz", 144.0, "fl oz", 799, pkg_count=12)
    assert got.packages == 2
    assert got.pkg_count == 12
    assert got.line_cost_cents == 1598


def test_compute_line_checks_units_before_dividing():
    """The whole reason compute_line exists: two numbers that divide cleanly but
    are not the same quantity must not produce a plausible answer."""
    with pytest.raises(basket.UnitMismatchError):
        basket.compute_line(24.0, "ct", 12.0, "oz", 199)


def test_compute_line_propagates_unresolved_size():
    with pytest.raises(basket.UnresolvedSizeError):
        basket.compute_line(16.0, "oz", None, "oz", 199)


def test_compute_line_result_is_immutable():
    """A line's arithmetic should not be edited in place by a later stage; B4's
    overrides recompute rather than mutate."""
    got = basket.compute_line(16.0, "oz", 16.0, "oz", 199)
    with pytest.raises(Exception):
        got.packages = 5


def test_every_money_value_out_of_compute_line_is_an_int():
    for requested, per_pack, price in [(32.0, 16.0, 249), (5.0, 12.0, 99), (288.0, 144.0, 799)]:
        got = basket.compute_line(requested, "oz", per_pack, "oz", price)
        assert isinstance(got.line_cost_cents, int)
        assert not isinstance(got.line_cost_cents, float)


# --- invariants across a range ------------------------------------------------------

@pytest.mark.parametrize("requested", [0.5, 1.0, 5.0, 11.9, 12.0, 12.1, 23.9, 24.0, 100.0])
def test_bought_amount_always_covers_the_request_within_tolerance(requested):
    """The core guarantee: whatever the tolerance does, the shopper is never
    left materially short."""
    per_pack = 12.0
    packages = basket.packages_needed(requested, per_pack)
    bought = packages * per_pack
    assert bought >= requested * (1 - PACKAGE_SIZE_ROUNDING_TOLERANCE)


@pytest.mark.parametrize("requested", [0.5, 5.0, 12.0, 13.0, 25.0, 100.0])
def test_never_buys_a_package_that_is_not_needed(requested):
    """One fewer package must always be insufficient (outside tolerance)."""
    per_pack = 12.0
    packages = basket.packages_needed(requested, per_pack)
    if packages > 1:
        assert (packages - 1) * per_pack < requested


def test_packages_needed_is_always_a_positive_int():
    for requested in (0.001, 1.0, 999.0):
        got = basket.packages_needed(requested, 12.0)
        assert isinstance(got, int) and got >= 1
        assert not isinstance(got, bool)
