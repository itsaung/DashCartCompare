"""Shopping-list line parsing: turn free text like "a dozen large eggs" into
a structured request (product type, quantity, unit, modifiers, unresolved
fields), per Checkpoint 2 of the DashCartCompare plan.

Deterministic and vocabulary-based on purpose -- no ML, no fuzzy guessing.
If a line doesn't match a known pattern, the result says so
(needs_review=True with a reason) instead of inventing an interpretation.
Reuses normalize.py's unit table so a shopping-list quantity and a product's
package size are measured in the exact same units, and the same
never-cross-dimensions rule applies to both.
"""
import re

from normalize import CANONICAL_UNIT, _canonical_unit_name, _to_float, convert_amount, extract_modifiers

# --- Quantity vocabulary ---------------------------------------------------
# Longest phrases first: matched by trying each key against the start of the
# line, longest match wins, so "a dozen" is checked before "a".
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_WORD_QUANTITIES = {
    "a dozen": 12, "dozen": 12,
    "half a dozen": 6, "half dozen": 6,
    "a couple": 2, "a couple of": 2, "couple": 2,
    "a pair": 2, "a pair of": 2,
    "a": 1, "an": 1,
    **_NUMBER_WORDS,
    # "<number word> dozen" combos, e.g. "two dozen" -> 24, generated rather
    # than hand-enumerated so every number word gets one consistently.
    **{f"{word} dozen": n * 12 for word, n in _NUMBER_WORDS.items()},
}
# Vague quantity words that have no fixed number -- these always need review,
# they're not a parsing failure to fix later.
_VAGUE_QUANTITY_WORDS = {"some", "a few", "few", "several", "a bunch of"}

# No \b after the digits: a \b never fires between a digit and a following
# letter (both are "word" characters), so "16oz" would otherwise fail to
# match at all and fall through to "no recognizable quantity". Deliberately
# no (?!%) lookahead here either -- an earlier version had one, but `\d+`
# backtracking to satisfy a lookahead means "12%" matches "1" (the shortest
# digit run for which "not followed by %" holds), not "reject this as a
# percentage token". The check for a trailing "%" is done explicitly after
# the match instead, against the *full* greedy digit run, in
# _parse_leading_quantity.
_NUMBER_RE = re.compile(r"^(\d+(?:\.\d+)?(?:/\d+)?)")
_BARE_FRACTION_RE = re.compile(r"^\d+/\d+$")

# Products conventionally sold by weight or volume, never as a bare count --
# "1 milk" is not a sellable quantity of milk the way "1 apple" is. A small,
# explicit list per the plan's "small grocery vocabulary" approach: this
# forces review rather than silently accepting "1 count" of something that
# was never sold by the count in the first place.
PRODUCTS_REQUIRING_SIZE = {
    "milk", "juice", "oil", "flour", "sugar", "rice", "pasta", "cereal",
    "yogurt", "cheese", "butter", "water", "soda", "coffee", "tea", "honey",
    "syrup", "broth", "soup", "cream", "vinegar",
}

# Units recognized with a known, fixed size (reuses normalize.py's table).
_KNOWN_UNIT_WORDS = {
    "gallon": "gal", "gallons": "gal", "gal": "gal",
    "quart": "qt", "quarts": "qt", "qt": "qt",
    "pint": "pt", "pints": "pt", "pt": "pt",
    "fl oz": "fl oz", "fluid ounce": "fl oz", "fluid ounces": "fl oz", "floz": "fl oz",
    "pound": "lb", "pounds": "lb", "lb": "lb", "lbs": "lb",
    "ounce": "oz", "ounces": "oz", "oz": "oz",
    "gram": "g", "grams": "g", "g": "g",
    "kilogram": "kg", "kilograms": "kg", "kg": "kg",
    "liter": "l", "liters": "l", "l": "l",
    "milliliter": "ml", "milliliters": "ml", "ml": "ml",
    "count": "ct", "ct": "ct",
}
# Container words with no standardized size -- DoorDash/grocery bag, box, and
# can sizes vary by product, so a raw count of these can't become a fixed
# quantity without asking the user which size they mean.
_AMBIGUOUS_CONTAINER_WORDS = {
    "bag", "bags", "box", "boxes", "can", "cans", "bottle", "bottles",
    "pack", "packs", "carton", "cartons", "jar", "jars",
    # A "loaf" is a real, ordinary way to order bread, but loaf sizes vary
    # (mini/regular/artisan) just like a "bag" or "box" does -- treated the
    # same way rather than assumed to be one standard size.
    "loaf", "loaves",
}


def _match_longest(words: list, vocab: dict):
    """Try 1-word, then 2-word, then 3-word phrases from the start of
    `words` against `vocab`. Case-insensitive (a user writing "1 GAL milk"
    should match "gal" the same as "gal"). Returns (value, n_words_consumed)
    or (None, 0)."""
    for n in (3, 2, 1):
        if len(words) >= n:
            phrase = " ".join(words[:n]).lower()
            if phrase in vocab:
                return vocab[phrase], n
    return None, 0


def _parse_leading_quantity(text: str):
    """Returns (quantity_or_None, rest_of_text, review_reason_or_None)."""
    stripped = text.strip()

    m = _NUMBER_RE.match(stripped)
    # A number immediately followed by "%" is a percentage token (fat
    # content, e.g. "2% milk"), not a quantity -- checked against the full
    # greedy digit match, not via a regex lookahead (which backtracking
    # could dodge by matching fewer digits; see _NUMBER_RE's comment).
    if m and stripped[m.end():m.end() + 1] == "%":
        m = None
    if m:
        token = m.group(1)
        qty = _to_float(token)
        rest = stripped[m.end():].strip()
        if qty is None:
            return None, rest, f"invalid numeric quantity: {token!r}"

        rest_words = rest.split()
        # Mixed number: "1 1/2 lb apples" -> 1 + 1/2, not just the leading
        # "1" with "1/2 lb apples" left dangling as if it were the product.
        # Only applies when the leading token itself was a plain integer
        # (not already "1.5" or "1/2" on its own).
        if rest_words and "." not in token and "/" not in token and _BARE_FRACTION_RE.match(rest_words[0]):
            frac = _to_float(rest_words[0])
            if frac is not None:
                qty += frac
                rest = " ".join(rest_words[1:])
        # "<digit> dozen": the word-quantity table only combines number
        # *words* with "dozen" (e.g. "two dozen"); a numeral needs the same
        # treatment so "2 dozen eggs" doesn't leave "dozen" stuck in the
        # product name with a quantity of 2.
        elif rest_words and rest_words[0].lower() == "dozen":
            qty *= 12
            rest = " ".join(rest_words[1:])

        return qty, rest, None

    words = stripped.split()
    vague, n = _match_longest(words, {w.lower(): w for w in _VAGUE_QUANTITY_WORDS})
    if vague:
        rest = " ".join(words[n:])
        return None, rest, f"vague quantity word: {vague!r}"

    qty, n = _match_longest(words, _WORD_QUANTITIES)
    if qty is not None:
        rest = " ".join(words[n:])
        return qty, rest, None

    return None, stripped, "no recognizable quantity at the start of the line"


def parse_shopping_line(text: str) -> dict:
    """Parse one shopping-list line into a structured request.

    Always returns a dict with:
      raw                -- original input text
      needs_review        -- True if any part of this couldn't be resolved
                              deterministically (per the plan: uncertain
                              fields trigger review, never a silent guess)
      review_reasons      -- list of strings explaining why, if needs_review
      product_type        -- best-effort leftover noun phrase, or None
      requested_quantity  -- number, in `unit` (before any conversion)
      unit                -- canonical unit token ("gal", "lb", "ct", ...),
                              or an ambiguous container word (e.g. "bag"),
                              or None for a bare count of items
      dimension           -- "weight" | "volume" | "count" | None
      canonical_quantity  -- requested_quantity converted to
                              CANONICAL_UNIT[dimension], or None if not
                              resolvable (ambiguous unit, vague quantity, etc.)
      canonical_unit       -- CANONICAL_UNIT[dimension], or None
      modifiers            -- list of recognized modifier words (organic, etc.)
    """
    out = {
        "raw": text,
        "needs_review": False,
        "review_reasons": [],
        "product_type": None,
        "requested_quantity": None,
        "unit": None,
        "dimension": None,
        "canonical_quantity": None,
        "canonical_unit": None,
        "modifiers": [],
    }

    # Comma form: "<description>, <quantity> <unit>" e.g. "organic
    # strawberries, 1 lb". Tried first since it's unambiguous when present.
    if "," in text:
        pre, _, tail = text.rpartition(",")
        m = re.match(r"^\s*([\d./]+)\s*([a-zA-Z ]+?)\s*$", tail)
        if m:
            qty_token, unit_token = m.group(1), m.group(2).strip().lower()
            qty = _to_float(qty_token)
            if qty is None or qty <= 0:
                out["needs_review"] = True
                reason = f"invalid numeric quantity: {qty_token!r}" if qty is None else f"non-positive quantity: {qty!r}"
                out["review_reasons"].append(reason)
                modifiers, product_type = extract_modifiers(pre.strip())
                out["modifiers"] = modifiers
                out["product_type"] = product_type or None
                return out
            canon = _KNOWN_UNIT_WORDS.get(unit_token)
            modifiers, product_type = extract_modifiers(pre.strip())
            out["modifiers"] = modifiers
            out["product_type"] = product_type or None
            out["requested_quantity"] = qty
            if canon:
                out["unit"] = canon
                dim_info = _canonical_unit_name(canon)
                if dim_info:
                    dimension, _factor = dim_info
                    out["dimension"] = dimension
                    out["canonical_unit"] = CANONICAL_UNIT[dimension]
                    out["canonical_quantity"] = convert_amount(qty, canon, CANONICAL_UNIT[dimension])
            else:
                out["unit"] = unit_token
                out["needs_review"] = True
                out["review_reasons"].append(f"unrecognized unit: {unit_token!r}")
            if not out["product_type"]:
                out["needs_review"] = True
                out["review_reasons"].append("no product type found before the comma")
            return out

    # Leading-quantity form: "<quantity> [unit] [modifiers] <product type>"
    qty, rest, reason = _parse_leading_quantity(text)
    if qty is None:
        out["needs_review"] = True
        out["review_reasons"].append(reason)
        # Still try to extract a product type from the whole line so a
        # reviewer sees *something* to correct rather than a blank line.
        modifiers, product_type = extract_modifiers(rest)
        out["modifiers"] = modifiers
        out["product_type"] = product_type or None
        return out

    out["requested_quantity"] = qty
    if qty <= 0:
        out["needs_review"] = True
        out["review_reasons"].append(f"non-positive quantity: {qty!r}")
    words = rest.split()

    unit_canon, n = _match_longest(words, _KNOWN_UNIT_WORDS)
    dim_info = _canonical_unit_name(unit_canon) if unit_canon else None
    if unit_canon and dim_info:
        words = words[n:]
        out["unit"] = unit_canon
        dimension, _factor = dim_info
        out["dimension"] = dimension
        out["canonical_unit"] = CANONICAL_UNIT[dimension]
        out["canonical_quantity"] = convert_amount(qty, unit_canon, CANONICAL_UNIT[dimension])
    else:
        container, n = _match_longest(words, {w: w for w in _AMBIGUOUS_CONTAINER_WORDS})
        if container:
            words = words[n:]
            if words[:1] == ["of"]:
                words = words[1:]
            out["unit"] = container
            out["needs_review"] = True
            out["review_reasons"].append(f"ambiguous unit: {container!r} (no standard size)")
        else:
            # No unit word at all: a bare count of items, e.g. "3 apples".
            out["unit"] = None
            out["dimension"] = "count"
            out["canonical_unit"] = CANONICAL_UNIT["count"]
            out["canonical_quantity"] = qty

    modifiers, product_type = extract_modifiers(" ".join(words))
    out["modifiers"] = modifiers
    out["product_type"] = product_type or None
    if not out["product_type"]:
        out["needs_review"] = True
        out["review_reasons"].append("no product type found")
    elif out["unit"] is None and out["product_type"] in PRODUCTS_REQUIRING_SIZE:
        # Bare count with no unit at all (e.g. "1 milk"), but this product
        # isn't conventionally sold by the count -- a fixed size/container
        # was clearly intended but not stated. Keep the parsed fields (a
        # reviewer can see what was guessed at) but don't trust them silently.
        out["needs_review"] = True
        out["review_reasons"].append(
            f"{out['product_type']!r} is typically sold by weight/volume, not by count -- package size unspecified"
        )

    return out
