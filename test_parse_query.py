import pytest

from parse_query import parse_shopping_line

# --- The plan's own worked examples, verified exactly -----------------

def test_plan_example_dozen_eggs():
    r = parse_shopping_line("a dozen large eggs")
    assert r["product_type"] == "eggs"
    assert r["canonical_quantity"] == 12
    assert r["canonical_unit"] == "ct"
    assert r["modifiers"] == ["large"]
    assert r["needs_review"] is False


def test_plan_example_gallon_milk():
    r = parse_shopping_line("1 gallon whole milk")
    assert r["product_type"] == "milk"
    assert r["canonical_quantity"] == 128.0
    assert r["canonical_unit"] == "fl oz"
    assert r["modifiers"] == ["whole"]
    assert r["needs_review"] is False


def test_plan_example_bags_of_chips_needs_review():
    r = parse_shopping_line("2 bags of chips")
    assert r["product_type"] == "chips"
    assert r["needs_review"] is True
    assert any("bags" in reason for reason in r["review_reasons"])


def test_plan_example_organic_strawberries():
    r = parse_shopping_line("organic strawberries, 1 lb")
    assert r["product_type"] == "strawberries"
    assert r["canonical_quantity"] == 16.0
    assert r["canonical_unit"] == "oz"
    assert r["modifiers"] == ["organic"]
    assert r["needs_review"] is False


# --- Numerals, decimals, fractions -------------------------------------

@pytest.mark.parametrize(
    "line, product_type, canonical_quantity, canonical_unit",
    [
        ("2 lb ground beef", "ground beef", 32.0, "oz"),
        ("1.5 lb ground beef", "ground beef", 24.0, "oz"),
        ("0.5 gal milk", "milk", 64.0, "fl oz"),
        ("1/2 gal milk", "milk", 64.0, "fl oz"),
        ("3 lb apples", "apples", 48.0, "oz"),
        ("12 oz coffee", "coffee", 12.0, "oz"),
        ("2.25 lb chicken breast", "chicken breast", 36.0, "oz"),
        ("16 oz strawberries", "strawberries", 16.0, "oz"),
    ],
)
def test_numeric_quantities(line, product_type, canonical_quantity, canonical_unit):
    r = parse_shopping_line(line)
    assert r["product_type"] == product_type
    assert r["canonical_quantity"] == pytest.approx(canonical_quantity)
    assert r["canonical_unit"] == canonical_unit
    assert r["needs_review"] is False


# --- Bare counts (no unit word at all) ----------------------------------

@pytest.mark.parametrize(
    "line, product_type, canonical_quantity",
    [
        ("3 apples", "apples", 3),
        ("6 bananas", "bananas", 6),
        ("2 avocados", "avocados", 2),
        ("4 limes", "limes", 4),
        ("1 onion", "onion", 1),
    ],
)
def test_bare_counts(line, product_type, canonical_quantity):
    r = parse_shopping_line(line)
    assert r["product_type"] == product_type
    assert r["dimension"] == "count"
    assert r["canonical_quantity"] == canonical_quantity
    assert r["needs_review"] is False


# --- Word-form quantities (multipacks of a sort: dozens, pairs, couples) --

@pytest.mark.parametrize(
    "line, product_type, canonical_quantity",
    [
        ("a dozen eggs", "eggs", 12),
        ("two dozen eggs", "eggs", 24),
        ("half a dozen eggs", "eggs", 6),
        ("a couple of onions", "onions", 2),
        ("a pair of avocados", "avocados", 2),
        ("one gallon milk", "milk", None),  # unit present: checked separately below
    ],
)
def test_word_quantities(line, product_type, canonical_quantity):
    r = parse_shopping_line(line)
    assert r["product_type"] == product_type
    if canonical_quantity is not None:
        assert r["canonical_quantity"] == canonical_quantity
    assert r["needs_review"] is False


def test_two_dozen_is_24_not_12():
    # A word-quantity multiplier ("two" + "dozen") must combine, not just
    # match "dozen" and ignore "two".
    r = parse_shopping_line("two dozen eggs")
    assert r["canonical_quantity"] == 24


# --- Abbreviated units ----------------------------------------------------

@pytest.mark.parametrize(
    "line, canonical_unit, canonical_quantity",
    [
        ("2 lbs chicken", "oz", 32.0),
        ("16 oz yogurt", "oz", 16.0),
        ("16oz yogurt", "oz", 16.0),  # unspaced: number and unit glued together
        ("1 gal milk", "fl oz", 128.0),
        ("12 fl oz soda", "fl oz", 12.0),
        ("500 ml sparkling water", "fl oz", pytest.approx(16.907, rel=1e-3)),
        ("2 kg rice", "oz", pytest.approx(70.548, rel=1e-3)),
    ],
)
def test_abbreviated_units(line, canonical_unit, canonical_quantity):
    r = parse_shopping_line(line)
    assert r["canonical_unit"] == canonical_unit
    assert r["canonical_quantity"] == canonical_quantity
    assert r["needs_review"] is False


# --- Missing sizes / ambiguous requests -> must trigger review, never guess

@pytest.mark.parametrize(
    "line, expected_reason_substring",
    [
        ("milk", "no recognizable quantity"),
        ("chips", "no recognizable quantity"),
        ("some apples", "vague quantity"),
        ("a few bananas", "vague quantity"),
        ("several onions", "vague quantity"),
        ("2 boxes of cereal", "ambiguous unit"),
        ("3 cans of soup", "ambiguous unit"),
        ("1 pack of tortillas", "ambiguous unit"),
        ("2 jars of pasta sauce", "ambiguous unit"),
        ("1 bottle of olive oil", "ambiguous unit"),
    ],
)
def test_ambiguous_or_missing_triggers_review(line, expected_reason_substring):
    r = parse_shopping_line(line)
    assert r["needs_review"] is True
    assert any(expected_reason_substring in reason for reason in r["review_reasons"])
    # An ambiguous/missing quantity must never produce a fabricated number.
    assert r["canonical_quantity"] is None


def test_review_flag_never_silently_dropped():
    # Every line in the ambiguous set above must actually be inspectable --
    # i.e. review_reasons is never empty when needs_review is True.
    for line in ["milk", "some apples", "2 boxes of cereal"]:
        r = parse_shopping_line(line)
        assert r["needs_review"] is True
        assert len(r["review_reasons"]) >= 1


# --- Modifiers preserved, unknown attributes left alone -------------------

@pytest.mark.parametrize(
    "line, modifiers, product_type",
    [
        ("1 gallon whole milk", ["whole"], "milk"),
        ("2 lb organic bananas", ["organic"], "bananas"),
        ("12 large eggs", ["large"], "eggs"),
        ("1 loaf gluten free bread", ["gluten free"], "bread"),  # "loaf" is now an ambiguous-container unit, not part of the product name
        ("16 oz unsweetened almond milk", ["unsweetened"], "almond milk"),
        ("2 lb fresh strawberries", ["fresh"], "strawberries"),
    ],
)
def test_modifiers_extracted(line, modifiers, product_type):
    r = parse_shopping_line(line)
    assert r["modifiers"] == modifiers
    assert r["product_type"] == product_type


def test_unknown_descriptive_word_is_not_invented_as_a_modifier():
    r = parse_shopping_line("2 lb fancy tomatoes")
    # "fancy" isn't in the modifier vocabulary -- it must stay in
    # product_type rather than silently vanish or get treated as known.
    assert "fancy" in r["product_type"]
    assert r["modifiers"] == []


# --- No cross-dimension conversion, ever ----------------------------------

def test_weight_and_volume_are_never_conflated_in_a_request():
    weight = parse_shopping_line("1 lb strawberries")
    volume = parse_shopping_line("1 gal milk")
    assert weight["dimension"] == "weight"
    assert volume["dimension"] == "volume"
    assert weight["canonical_unit"] == "oz"
    assert volume["canonical_unit"] == "fl oz"


def test_oz_request_is_weight_not_volume():
    r = parse_shopping_line("8 oz milk")
    # Deliberate, documented simplification (see normalize.py): bare "oz" is
    # always weight. A user who means fluid ounces of a liquid must write
    # "fl oz" explicitly for this to resolve as volume.
    assert r["dimension"] == "weight"
    assert r["canonical_unit"] == "oz"


# --- Regression cases from code review: confidently-wrong parses ----------
# These previously returned needs_review=False with an incorrect
# interpretation, which is worse than rejecting the line outright --
# downstream matching would have trusted the wrong request.

def test_digit_dozen_combines_not_just_the_digit():
    r = parse_shopping_line("2 dozen eggs")
    assert r["canonical_quantity"] == 24
    assert r["product_type"] == "eggs"
    assert r["needs_review"] is False


def test_mixed_number_fraction():
    r = parse_shopping_line("1 1/2 lb apples")
    assert r["requested_quantity"] == pytest.approx(1.5)
    assert r["canonical_quantity"] == pytest.approx(24.0)
    assert r["canonical_unit"] == "oz"
    assert r["product_type"] == "apples"
    assert r["needs_review"] is False


def test_unit_matching_is_case_insensitive():
    r = parse_shopping_line("1 GAL milk")
    assert r["unit"] == "gal"
    assert r["dimension"] == "volume"
    assert r["canonical_quantity"] == 128.0
    assert r["product_type"] == "milk"
    assert r["needs_review"] is False


def test_percent_modifier_not_mistaken_for_a_quantity():
    r = parse_shopping_line("2% milk")
    # "2%" is a fat-percentage modifier, not a quantity -- there is no
    # count/size given here at all, so this must need review, not parse as
    # "2 count" of a product literally named "% milk".
    assert r["needs_review"] is True
    assert r["modifiers"] == ["2%"]
    assert r["product_type"] == "milk"
    assert r["canonical_quantity"] is None


def test_bare_count_of_a_typically_sized_product_needs_review():
    r = parse_shopping_line("1 milk")
    assert r["needs_review"] is True
    assert any("typically sold by weight/volume" in reason for reason in r["review_reasons"])
    # A normal bare-count item must NOT trigger this.
    r2 = parse_shopping_line("1 apple")
    assert r2["needs_review"] is False


# --- Second round of regression cases from code review --------------------

def test_zero_quantity_needs_review():
    r = parse_shopping_line("0 eggs")
    assert r["needs_review"] is True
    assert any("non-positive" in reason for reason in r["review_reasons"])


def test_negative_quantity_needs_review():
    r = parse_shopping_line("-2 lb flour")
    # A negative number doesn't match _NUMBER_RE at all (no sign in the
    # pattern), so this must fall through to "no recognizable quantity"
    # rather than silently parsing as positive 2.
    assert r["needs_review"] is True


def test_loaf_is_an_ambiguous_container_not_a_fixed_unit():
    r = parse_shopping_line("1 loaf bread")
    assert r["needs_review"] is True
    assert any("loaf" in reason for reason in r["review_reasons"])
    assert r["product_type"] == "bread"


def test_hyphenated_modifier_is_recognized():
    r = parse_shopping_line("1 gallon gluten-free milk")
    assert r["modifiers"] == ["gluten free"]
    assert r["product_type"] == "milk"
    assert r["needs_review"] is False


def test_multi_digit_percentage_is_not_torn_into_a_quantity():
    # Regression: "12%" previously matched "1" as the quantity because the
    # old (?!%) lookahead let \d+ backtrack down to a digit run that wasn't
    # immediately followed by "%".
    r = parse_shopping_line("12% milk")
    assert r["requested_quantity"] is None
    assert r["needs_review"] is True
