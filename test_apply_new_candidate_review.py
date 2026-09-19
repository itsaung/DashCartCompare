"""Tests for apply_new_candidate_review.py's stricter product-type check.
This is a regression suite for a real bug found while reviewing the 153
Checkpoint E4 new candidates: claude_auto_label.py's own product-type check
uses substring containment and an "any token matches" rule, which let
"Friendly Farms Almond Milk" pass against a Friendly Farms *oat* milk
purely because "milk" is a substring of "oatmilk" and generic tokens
("friendly", "farms", "original") matched anyway."""
from apply_new_candidate_review import _core_product_type_confirmed


def _request(text, brand=None, variant=None):
    return {
        "text": text,
        "expected": {"brand": brand, "variant": variant, "allowed_substitutions": {}},
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
