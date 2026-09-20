"""Tests for product_identity.py: hand-built fixtures, not the real 31k-row
catalog. Every expected brand/variant below was worked out by hand from the
rules in the module, not by running the code and recording what it said."""
import pandas as pd
import pytest

from product_identity import (
    MIN_BRAND_PRODUCTS, build_brand_lexicon, build_catalog_identity, extract_brand,
    extract_request_identity, extract_variant_tokens, variants_conflict,
)


def _catalog(titles):
    return pd.DataFrame([
        {"store_id": "s1", "product_id": f"p{i}", "raw_title": t, "raw_category": "Grocery"}
        for i, t in enumerate(titles)
    ])


def _lexicon_with(ngram, count=MIN_BRAND_PRODUCTS):
    """A lexicon containing exactly one entry, so a test states its own
    premise instead of depending on induction."""
    return {ngram: count}


# --- lexicon induction ------------------------------------------------------

def test_ngram_below_frequency_floor_is_not_a_brand():
    # 4 products < MIN_BRAND_PRODUCTS (5), so "Palmini" never enters.
    lex = build_brand_lexicon(_catalog([f"Palmini Hearts of Palm {i}" for i in range(4)]))
    assert "Palmini" not in lex


def test_ngram_at_frequency_floor_is_a_brand():
    lex = build_brand_lexicon(_catalog([f"Palmini Hearts of Palm {i}" for i in range(5)]))
    assert "Palmini" in lex
    assert lex["Palmini"] == 5


def test_brand_must_lead_the_title():
    """A name appearing mid-title must not become a brand on that row's
    account -- this is the position rule."""
    lex = build_brand_lexicon(_catalog([f"Ice Cream with Oreo Cookies {i}" for i in range(8)]))
    assert "Oreo" not in lex


def test_purely_generic_ngram_is_rejected():
    lex = build_brand_lexicon(_catalog([f"Organic Lemons Bag {i}" for i in range(9)]))
    assert "Organic" not in lex


def test_numeric_ngram_is_rejected():
    lex = build_brand_lexicon(_catalog([f"12 Pack Soda {i}" for i in range(9)]))
    assert "12" not in lex


def test_single_category_brand_is_kept():
    """The plan's >=2-category rule was dropped: a brand selling into exactly
    one department is still a brand (measured: that rule discarded 2,059 of
    them on the real catalog)."""
    lex = build_brand_lexicon(_catalog([f"Advil Pain Reliever {i}" for i in range(6)]))
    assert "Advil" in lex


# --- brand extraction -------------------------------------------------------

def test_unknown_brand_is_none_not_a_guess():
    assert extract_brand("Palmini Hearts of Palm Linguine", {}) is None


def test_longest_match_wins_when_extension_dominates():
    # "Signature" begins 10 products, "Signature Select" begins 9 of those:
    # 9/10 = 0.90 >= 0.50, so the longer form is the brand.
    lex = {"Signature": 10, "Signature Select": 9}
    assert extract_brand("Signature Select Chocolate Chip Waffles", lex) == "Signature Select"


def test_extension_is_rejected_when_it_does_not_dominate():
    # "Signature Select Double" begins 2 of "Signature Select"'s 9 products:
    # 2/9 = 0.22 < 0.50, so it is a product line, not part of the brand.
    lex = {"Signature": 10, "Signature Select": 9, "Signature Select Double": 2}
    assert extract_brand("Signature Select Double Zipper Bags", lex) == "Signature Select"


def test_trailing_generic_is_trimmed_off_the_brand():
    lex = {"Clancy's": 20, "Clancy's Original": 12}
    assert extract_brand("Clancy's Original Potato Chips", lex) == "Clancy's"


def test_store_brand_is_accepted_below_the_frequency_floor():
    # Not in the induced lexicon at all, but explicitly listed.
    assert extract_brand("Barissimo French Vanilla Ground Coffee", {}) == "Barissimo"


# --- variant extraction -----------------------------------------------------

def test_variant_picks_up_vocabulary_tokens_only():
    # "Linguine" and "Pouch" are outside the vocabulary and must be dropped,
    # not invented into a variant.
    assert extract_variant_tokens("Organic Frozen Linguine Pouch") == frozenset({"organic", "frozen"})


def test_variant_is_order_independent():
    a = extract_variant_tokens("Organic Unsweetened Almond Milk")
    b = extract_variant_tokens("Unsweetened Almond Organic Milk")
    assert a == b


def test_size_tokens_never_leak_into_variant():
    v = extract_variant_tokens("Whole Milk 1 gal 64 fl oz 12 ct")
    assert v == frozenset({"whole", "milk"})
    assert not {"1", "gal", "64", "fl", "oz", "12", "ct"} & v


def test_brand_tokens_are_removed_from_variant():
    # "Original" is the brand's own word here and must not also be a variant.
    v = extract_variant_tokens("Original Recipe Chicken", brand="Original Recipe")
    assert "original" not in v


def test_hyphen_joined_two_token_descriptor_is_found():
    assert "extra-virgin" in extract_variant_tokens("Extra Virgin Olive Oil")


# --- variant conflict -------------------------------------------------------

def test_empty_variant_on_either_side_is_unknown_not_a_conflict():
    assert variants_conflict(frozenset(), frozenset({"whole"})) is False
    assert variants_conflict(frozenset({"whole"}), frozenset()) is False


def test_mutually_exclusive_values_conflict():
    assert variants_conflict(frozenset({"whole"}), frozenset({"2%"})) is True
    assert variants_conflict(frozenset({"frozen"}), frozenset({"fresh"})) is True
    assert variants_conflict(frozenset({"vanilla"}), frozenset({"chocolate"})) is True


def test_same_value_does_not_conflict():
    assert variants_conflict(frozenset({"whole"}), frozenset({"whole"})) is False


def test_co_occurring_descriptors_do_not_conflict():
    # Both can be true of one product; they are in different groups.
    assert variants_conflict(frozenset({"organic"}), frozenset({"frozen"})) is False


def test_extra_descriptor_on_one_side_is_not_a_conflict():
    assert variants_conflict(
        frozenset({"organic", "whole"}), frozenset({"whole"})
    ) is False


# --- query side -------------------------------------------------------------

def test_request_brand_found_mid_string():
    """A request rarely leads with the brand ("12 oz Barissimo ... coffee"),
    unlike a catalog title."""
    out = extract_request_identity("12 oz Barissimo French Vanilla ground coffee", {})
    assert out["brand"] == "Barissimo"


def test_flexible_request_without_a_brand_reports_unknown():
    out = extract_request_identity("0.5 gal almond milk, any brand", {})
    assert out["brand"] is None
    assert out["brand_confidence"] == "unknown"


def test_request_variant_tokens_extracted():
    out = extract_request_identity("1 gallon whole milk", {})
    assert "whole" in out["variant_tokens"]


def test_request_and_catalog_agree_on_the_same_wording():
    """The two sides must be comparable -- that is the whole point of S2."""
    lex = _lexicon_with("Oatly", 12)
    cat_brand = extract_brand("Oatly Original Oat Milk (0.5 gal)", lex)
    req = extract_request_identity("0.5 gal Oatly Original Oat Milk", lex)
    assert cat_brand == req["brand"] == "Oatly"


# --- side-car table ---------------------------------------------------------

def test_build_catalog_identity_marks_unknown_brands_explicitly():
    df = build_catalog_identity(_catalog(["Palmini Hearts of Palm Linguine"]))
    assert df.iloc[0]["brand"] is None
    assert df.iloc[0]["identity_status"] == "brand_unknown"
    assert df.iloc[0]["brand_confidence"] == "unknown"


def test_build_catalog_identity_keys_every_row():
    # Varied continuations, as a real brand has -- see the over-extension test
    # below for what happens when they aren't varied.
    titles = [
        "Advil Pain Reliever Caplets", "Advil Liqui-Gels", "Advil PM Tablets",
        "Advil Cold and Sinus", "Advil Junior Chewable", "Advil Dual Action",
    ]
    df = build_catalog_identity(_catalog(titles))
    assert len(df) == len(titles)
    assert set(df.columns) >= {"store_id", "product_id", "brand", "variant_tokens",
                               "identity_status", "identity_version"}
    assert (df["brand"] == "Advil").all()


def test_brand_over_extends_when_every_product_shares_a_leading_word():
    """Known limitation, asserted so it is visible rather than surprising.

    When a brand's products all begin with the same following word, that word
    is indistinguishable from the brand by frequency alone -- the dominance
    ratio is 1.0. On the real catalog this shows up as "Birds Eye Steamfresh"
    (should be "Birds Eye"). It is a false *extension*, not a false brand, and
    it is symmetric: the catalog and query sides over-extend identically, so
    an exact-mode comparison of two such titles still agrees. Recorded in
    IDENTITY_EXTRACTION_AUDIT.md.
    """
    titles = [f"Birds Eye Steamfresh Vegetable Mix {i}" for i in range(6)]
    df = build_catalog_identity(_catalog(titles))
    assert (df["brand"] == "Birds Eye Steamfresh").all()
