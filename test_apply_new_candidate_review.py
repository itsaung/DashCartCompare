"""Tests for apply_new_candidate_review.py's stricter checks. This is a
regression suite for real bugs found in two rounds of review:

Round 1 (this session's own E4 work): claude_auto_label.py's product-type
check uses substring containment and an "any token matches" rule, which let
"Friendly Farms Almond Milk" pass against a Friendly Farms *oat* milk
purely because "milk" is a substring of "oatmilk" and generic tokens
("friendly", "farms", "original") matched anyway.

Round 2 (external review of the 153 additional judgments this script
produced): three more real false positives reusing auto_label() unmodified
-- "a bag of chips" accepting chocolate baking chips, "12 ct large eggs"
accepting "extra large" eggs, and "15 oz cereal" accepting a 15.4 oz box
via auto_label's own 3% size tolerance, which LABELING_GUIDELINES.md v2
explicitly rejects as arbitrary."""
from apply_new_candidate_review import (
    _core_product_type_confirmed,
    _no_false_friend_product_type_conflict,
    _size_confirmed_without_arbitrary_tolerance,
    _variant_not_shadowed_by_a_more_specific_known_variant,
)


def _request(text, brand=None, variant=None, size=None, size_any=False):
    substitutions = {}
    if size_any:
        substitutions["size"] = "any"
    return {
        "text": text,
        "expected": {"brand": brand, "variant": variant, "size": size, "allowed_substitutions": substitutions},
    }


def test_catches_the_oatmilk_vs_almond_milk_false_positive():
    request = _request("64 fl oz Friendly Farms Almond Milk Original", brand="Friendly Farms", variant="Original")
    title = "friendly farms organic original oatmilk (64 fl oz)".lower()
    assert _core_product_type_confirmed(request, title) is False


def test_confirms_a_genuine_match():
    request = _request("32 oz greek yogurt")
    title = "sprouts whole 5% greek yogurt plain (32 oz)".lower()
    assert _core_product_type_confirmed(request, title) is True


def test_substring_concatenation_does_not_falsely_confirm():
    # "almond milk" as two words must not be satisfied by "almondmilk" as
    # one concatenated word -- word-boundary matching, not substring.
    request = _request("96 fl oz almond milk")
    title = "almond breeze vanilla almondmilk (96 fl oz)".lower()
    assert _core_product_type_confirmed(request, title) is False


def test_brand_and_variant_tokens_alone_are_not_enough_to_confirm_a_leftover_noun():
    # Brand/variant are already checked elsewhere by auto_label -- a title
    # that only echoes the brand/variant name, without the request's actual
    # remaining product noun ("soda"), must not count as confirmed.
    request = _request("some Acme Cola soda", brand="Acme", variant="Cola")
    title = "acme brand snack chips".lower()  # brand present, but no "soda" anywhere
    assert _core_product_type_confirmed(request, title) is False


def test_brand_and_variant_tokens_fully_covering_product_type_trivially_passes():
    # If every product-type token is already accounted for by brand/variant
    # (separately checked elsewhere), there's nothing left for this check
    # to meaningfully evaluate -- it must not manufacture a false failure.
    request = _request("some Acme Cola", brand="Acme", variant="Cola")
    title = "acme brand snack chips".lower()
    assert _core_product_type_confirmed(request, title) is True


def test_no_product_type_tokens_trivially_passes():
    request = _request("please")  # degenerate: parses to no product_type tokens
    assert _core_product_type_confirmed(request, "anything at all") is True


# --- _variant_not_shadowed_by_a_more_specific_known_variant -----------------

def test_catches_extra_large_eggs_shadowing_a_large_eggs_request():
    request = _request("12 ct large eggs", variant="large")
    title = "kroger cage free extra large white eggs (12 ct)".lower()
    assert _variant_not_shadowed_by_a_more_specific_known_variant(request, title) is False


def test_genuine_large_eggs_are_not_shadowed():
    request = _request("12 ct large eggs", variant="large")
    title = "sprouts cage free grade a large white eggs (12 ct)".lower()
    assert _variant_not_shadowed_by_a_more_specific_known_variant(request, title) is True


def test_variant_any_substitution_skips_the_check():
    request = _request("some eggs", variant="large")
    request["expected"]["allowed_substitutions"] = {"variant": "any"}
    title = "extra large eggs".lower()
    assert _variant_not_shadowed_by_a_more_specific_known_variant(request, title) is True


def test_no_expected_variant_trivially_passes():
    request = _request("some eggs")
    assert _variant_not_shadowed_by_a_more_specific_known_variant(request, "anything") is True


# --- _no_false_friend_product_type_conflict ---------------------------------

def test_catches_chocolate_baking_chips_for_a_bag_of_chips():
    request = _request("a bag of chips")
    title = "ghirardelli premium milk chocolate baking chips bag (11.5 oz)".lower()
    assert _no_false_friend_product_type_conflict(request, title) is False


def test_real_snack_chips_are_not_flagged():
    request = _request("a bag of chips")
    title = "clancy's original potato chips (10 oz)".lower()
    assert _no_false_friend_product_type_conflict(request, title) is True


# --- _size_confirmed_without_arbitrary_tolerance -----------------------------

def test_catches_same_unit_15_vs_15_4_oz_despite_being_within_3_percent():
    request = _request("15 oz cereal", size="15 oz")
    candidate = {"raw_size": "15.4 oz"}
    assert _size_confirmed_without_arbitrary_tolerance(request, candidate) is False


def test_exact_same_unit_size_passes():
    request = _request("15 oz cereal", size="15 oz")
    candidate = {"raw_size": "15 oz"}
    assert _size_confirmed_without_arbitrary_tolerance(request, candidate) is True


def test_genuine_cross_unit_rounding_passes():
    # 2 L == 67.628 fl oz; a printed "67.6 fl oz" label is ordinary rounding
    # of a genuine unit conversion, not a distinct size.
    request = _request("2 L soda", size="2 L")
    candidate = {"raw_size": "67.6 fl oz"}
    assert _size_confirmed_without_arbitrary_tolerance(request, candidate) is True


def test_no_expected_size_trivially_passes():
    request = _request("some cereal")
    assert _size_confirmed_without_arbitrary_tolerance(request, {"raw_size": "15.4 oz"}) is True


def test_size_any_substitution_skips_the_check():
    request = _request("some cereal", size="15 oz", size_any=True)
    assert _size_confirmed_without_arbitrary_tolerance(request, {"raw_size": "40 oz"}) is True


def test_unresolvable_candidate_size_does_not_block_acceptance():
    request = _request("15 oz cereal", size="15 oz")
    assert _size_confirmed_without_arbitrary_tolerance(request, {"raw_size": "by pound"}) is True
