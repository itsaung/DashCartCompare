"""Tests for claude_auto_label.py's auto_label: the improved rule set that
adds numeric package-size comparison and known-variant-conflict detection
on top of build_candidate_pool.py's rougher draft_label -- both gaps a human
spot-check of the real pilot pool actually caught (a 15 oz vs 16 oz butter,
and an Oatly "Barista Edition" vs "Original" mislabel)."""
from claude_auto_label import auto_label


def _row(title, size, dimension, dimension_review_flag=False):
    return {"raw_title": title, "raw_size": size, "pkg_dimension": dimension,
            "dimension_review_flag": dimension_review_flag}


def _request(text, brand=None, variant=None, size=None, substitutions=None):
    return {
        "text": text,
        "expected": {"brand": brand, "variant": variant, "size": size,
                     "allowed_substitutions": substitutions or {}},
    }


def test_size_mismatch_is_incorrect():
    row = _row("Countryside Creamery Spreadable Butter with Canola Oil (15 oz)", "15 oz", "weight")
    request = _request("16 oz Countryside Creamery Unsalted Butter", brand="Countryside Creamery",
                        variant="unsalted", size="16 oz")
    label, reason = auto_label(row, request)
    assert label == "Incorrect"
    assert "size mismatch" in reason


def test_size_match_within_tolerance_is_not_flagged():
    # Same size expressed differently (0.5 gal == 64 fl oz) must not be a mismatch.
    row = _row("Some Brand Whole Milk (64 fl oz)", "64 fl oz", "volume")
    request = _request("0.5 gal whole milk", size="0.5 gal")
    label, reason = auto_label(row, request)
    assert label != "Incorrect" or "size mismatch" not in reason


def test_known_variant_conflict_is_incorrect_not_needs_clarification():
    row = _row("Barissimo Ground Coffee Caramel (12 oz)", "12 oz", "weight")
    request = _request("12 oz Barissimo French Vanilla ground coffee", brand="Barissimo",
                        variant="French Vanilla", size="12 oz")
    label, reason = auto_label(row, request)
    assert label == "Incorrect"
    assert "different named variant" in reason


def test_unconfirmable_variant_is_needs_clarification():
    row = _row("Generic Ground Coffee (12 oz)", "12 oz", "weight")
    request = _request("12 oz Barissimo French Vanilla ground coffee", brand="Generic",
                        variant="French Vanilla", size="12 oz", substitutions={"brand": "any"})
    label, reason = auto_label(row, request)
    assert label == "Needs clarification"


def test_variant_match_and_size_match_is_acceptable():
    row = _row("Barissimo Ground Coffee French Vanilla (12 oz)", "12 oz", "weight")
    request = _request("12 oz Barissimo French Vanilla ground coffee", brand="Barissimo",
                        variant="French Vanilla", size="12 oz")
    label, reason = auto_label(row, request)
    assert label == "Acceptable"


def test_dimension_mismatch_still_incorrect():
    row = _row("Oat Milk Chocolate Bar (7 oz)", "7 oz", "weight")
    request = _request("0.5 gal oat milk", size="0.5 gal")
    label, reason = auto_label(row, request)
    assert label == "Incorrect"
    assert "dimension" in reason


def test_wrong_product_type_is_incorrect_even_with_no_other_conflict():
    # Pilot audit: corn snacks labeled Acceptable against a yogurt request,
    # candy against a chips request -- nothing in `expected` states the
    # product type, so brand/variant/size/dimension checks alone never
    # catch this.
    row = _row("Chester's Fries Chili Cheese Flavored Corn Snacks (5.25 oz)", "5.25 oz", "weight")
    request = _request("5.3 oz flavored greek yogurt, any flavor", size="5.3 oz",
                        substitutions={"brand": "any", "flavor": "any"})
    label, reason = auto_label(row, request)
    assert label == "Incorrect"
    assert "product-type" in reason


def test_product_type_check_ignores_stray_comma_clause_words():
    # "a dozen large eggs, any brand is fine" leaves "any brand is fine"
    # stuck onto product_type after parse_query.py's comma-form parse gives
    # up (see LABELING_GUIDELINES.md's pilot notes) -- a real eggs candidate
    # must still pass, not get flagged just because of that stray text.
    row = _row("Goldhen Cage Free Grade A Large Brown Eggs (12 ct)", "12 ct", "count")
    request = _request("a dozen large eggs, any brand is fine", substitutions={"brand": "any"})
    label, reason = auto_label(row, request)
    assert label != "Incorrect" or "product-type" not in reason


def test_product_type_check_rejects_unrelated_product():
    row = _row("Dozen Roses - Yellow", None, None)
    request = _request("a dozen large eggs, any brand is fine", substitutions={"brand": "any"})
    label, reason = auto_label(row, request)
    assert label == "Incorrect"
    assert "product-type" in reason
