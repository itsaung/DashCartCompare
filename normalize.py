"""Product package-size normalization: turn a free-text unit_size string like
"4.8 oz x 8 ct" into structured fields (pack count, amount per pack, unit,
total amount), without ever converting across incompatible dimensions.

Checkpoint 2 of the DashCartCompare plan. See DATA_DICTIONARY.md for why
unit_size exists as unparsed free text in the first place.

Core rule (dimensional analysis): a unit only has a size in one of three
independent dimensions -- weight, volume, or count. "12 oz" (weight) and
"12 fl oz" (volume) are not the same kind of quantity even though both say
"12" and both say "oz" -- an ounce of feathers and a fluid ounce of water
are unrelated measurements. This module never converts between dimensions;
it raises instead. It also never converts weight/volume into a dollar
amount or vice versa (that's a variable-weight product, handled by flagging
it, not estimating it).
"""
import math
import re

# Canonical unit per dimension. Chosen to match the whole-number, no-decimals
# style DoorDash already displays most package sizes in.
CANONICAL_UNIT = {"weight": "oz", "volume": "fl oz", "count": "ct"}

# Every unit this module understands, mapped to (dimension, amount in that
# dimension's canonical unit). E.g. 1 lb = 16 oz, so LB_TO_OZ = 16.
_UNIT_TABLE = {
    # weight -> oz
    "oz": ("weight", 1.0),
    "ounce": ("weight", 1.0),
    "ounces": ("weight", 1.0),
    "lb": ("weight", 16.0),
    "lbs": ("weight", 16.0),
    "pound": ("weight", 16.0),
    "pounds": ("weight", 16.0),
    "g": ("weight", 0.035274),
    "gram": ("weight", 0.035274),
    "grams": ("weight", 0.035274),
    "kg": ("weight", 35.274),
    # volume -> fl oz. "oz"/"ounce(s)" deliberately excluded here: bare "oz"
    # always means weight in this module (see module docstring). A source
    # string must say "fl oz" / "fluid ounce(s)" to be read as volume.
    "fl oz": ("volume", 1.0),
    "floz": ("volume", 1.0),
    "fluid ounce": ("volume", 1.0),
    "fluid ounces": ("volume", 1.0),
    "gal": ("volume", 128.0),
    "gallon": ("volume", 128.0),
    "gallons": ("volume", 128.0),
    "qt": ("volume", 32.0),
    "quart": ("volume", 32.0),
    "quarts": ("volume", 32.0),
    "pt": ("volume", 16.0),
    "pint": ("volume", 16.0),
    "pints": ("volume", 16.0),
    "ml": ("volume", 0.033814),
    "l": ("volume", 33.814),
    "liter": ("volume", 33.814),
    "liters": ("volume", 33.814),
    # count -> ct
    "ct": ("count", 1.0),
    "count": ("count", 1.0),
    "ea": ("count", 1.0),
    "each": ("count", 1.0),
}

# Strings that look like they could be a size but are known non-package-size
# noise observed in the real data (apparel/costume/diaper sizing, seasonal
# labels that leaked into the unit_size field from unrelated listings).
_NON_SIZE_TOKENS = {"xs", "s", "m", "l", "xl", "xxl", "xxxl", "one size"}
_SIZE_LABEL_RE = re.compile(
    r"^(x*small|small|x*large|extra large|medium|size\s*\d+(-\d+)?)$", re.I
)

_VARIABLE_WEIGHT_RE = re.compile(r"^\$[\d.]+\s*/\s*lb$", re.I)
_MULTIPACK_RE = re.compile(
    r"^([\d./]+)\s*(fl\s?oz|fluid\s?ounces?|floz|oz|ounces?|lbs?|pounds?|g|grams?|kg|"
    r"gal|gallons?|qt|quarts?|pt|pints?|ml|l|liters?|ct|count|ea|each)\s*[x×]\s*"
    r"(\d+)\s*(ct|count|pk|pack|ea|each)?$",
    re.I,
)
# "3 pk x 56 ct" -- a count of packs times a count per pack, no weight/volume
# unit involved at all (distinct from "4.8 oz x 8 ct" above).
_COUNT_MULTIPACK_RE = re.compile(r"^(\d+)\s*(?:pk|pack)\s*[x×]\s*(\d+)\s*(?:ct|count)$", re.I)
_SIMPLE_RE = re.compile(
    r"^([\d./]+)\s*(fl\s?oz|fluid\s?ounces?|floz|oz|ounces?|lbs?|pounds?|g|grams?|kg|"
    r"gal|gallons?|qt|quarts?|pt|pints?|ml|l|liters?|ct|count|ea|each)$",
    re.I,
)


def _to_float(token: str):
    """Parse a plain decimal ('1.5') or simple fraction ('1/2'). Returns
    None (never raises) on a malformed token ('1..2') or a zero/invalid
    denominator ('1/0') -- the caller treats that as unresolved, not a
    crash."""
    try:
        if "/" in token:
            num, den = token.split("/", 1)
            denom = float(den)
            if denom == 0:
                return None
            return float(num) / denom
        return float(token)
    except ValueError:
        return None


def _valid_positive_amount(amount) -> bool:
    return amount is not None and math.isfinite(amount) and amount > 0


def _canonical_unit_name(raw_unit: str):
    key = re.sub(r"\s+", " ", raw_unit.strip().lower())
    return _UNIT_TABLE.get(key)


def convert_amount(amount: float, from_unit: str, to_unit: str) -> float:
    """Convert `amount` from `from_unit` to `to_unit`. Raises ValueError if
    the two units are not in the same dimension -- there is no such thing as
    converting weight to volume without a density, which this project does
    not have and will not estimate."""
    from_info = _canonical_unit_name(from_unit)
    to_info = _canonical_unit_name(to_unit)
    if from_info is None:
        raise ValueError(f"unknown unit: {from_unit!r}")
    if to_info is None:
        raise ValueError(f"unknown unit: {to_unit!r}")
    from_dim, from_factor = from_info
    to_dim, to_factor = to_info
    if from_dim != to_dim:
        raise ValueError(f"cannot convert {from_dim} ({from_unit!r}) to {to_dim} ({to_unit!r})")
    return amount * from_factor / to_factor


def parse_package_size(raw: str) -> dict:
    """Parse a unit_size string into structured fields.

    Always returns a dict with these keys:
      raw              -- the original string, unchanged
      unresolved       -- True if this could not be parsed into a fixed size
      reason           -- why, when unresolved (None otherwise)
      variable_weight  -- True for priced-by-weight produce/deli/meat items
                           ("$5.49/lb", "by pound") -- these have no fixed
                           size at all, so they're excluded from automatic
                           basket math (see project plan, Checkpoint 2)
      dimension        -- "weight" | "volume" | "count" | None
      pack_count       -- number of packs/units bundled together (int)
      amount_per_pack  -- size of one pack, in its original unit (float)
      unit             -- the original unit token, lowercased
      total_amount     -- pack_count * amount_per_pack, in `unit`
      canonical_unit    -- CANONICAL_UNIT[dimension], or None
      canonical_total   -- total_amount converted to canonical_unit, or None
    """
    out = {
        "raw": raw,
        "unresolved": False,
        "reason": None,
        "variable_weight": False,
        "dimension": None,
        "pack_count": None,
        "amount_per_pack": None,
        "unit": None,
        "total_amount": None,
        "canonical_unit": None,
        "canonical_total": None,
    }
    text = (raw or "").strip()

    if not text:
        out["unresolved"] = True
        out["reason"] = "missing size"
        return out

    if _VARIABLE_WEIGHT_RE.match(text) or text.lower() in ("by pound", "by the pound"):
        out["variable_weight"] = True
        out["dimension"] = "weight"
        out["unresolved"] = True
        out["reason"] = "priced by weight, no fixed package size"
        return out

    if (
        text.lower() in _NON_SIZE_TOKENS
        or re.match(r"^(spring|summer|fall|winter)\s*\d*$", text, re.I)
        or _SIZE_LABEL_RE.match(text)
    ):
        out["unresolved"] = True
        out["reason"] = "not a package size (looks like an apparel/diaper/seasonal size label)"
        return out

    if text.lower() in ("each", "ea"):
        out.update(
            dimension="count",
            pack_count=1,
            amount_per_pack=1.0,
            unit="each",
            total_amount=1.0,
            canonical_unit=CANONICAL_UNIT["count"],
            canonical_total=1.0,
        )
        return out

    m = _COUNT_MULTIPACK_RE.match(text)
    if m:
        pack_count, per_pack = int(m.group(1)), int(m.group(2))
        if pack_count <= 0 or per_pack <= 0:
            out["unresolved"] = True
            out["reason"] = "non-positive quantity in package size"
            return out
        total = pack_count * per_pack
        out.update(
            dimension="count",
            pack_count=pack_count,
            amount_per_pack=float(per_pack),
            unit="ct",
            total_amount=float(total),
            canonical_unit=CANONICAL_UNIT["count"],
            canonical_total=float(total),
        )
        return out

    m = _MULTIPACK_RE.match(text)
    if m:
        amount = _to_float(m.group(1))
        unit_info = _canonical_unit_name(m.group(2))
        pack_count = int(m.group(3))
        if unit_info is None or not _valid_positive_amount(amount) or pack_count <= 0:
            out["unresolved"] = True
            out["reason"] = "invalid or non-positive quantity in package size"
            return out
        dimension, factor = unit_info
        out.update(
            dimension=dimension,
            pack_count=pack_count,
            amount_per_pack=amount,
            unit=m.group(2).strip().lower(),
            total_amount=round(amount * pack_count, 6),
        )
        out["canonical_unit"] = CANONICAL_UNIT[dimension]
        out["canonical_total"] = round(out["total_amount"] * factor, 6)
        return out

    m = _SIMPLE_RE.match(text)
    if m:
        amount = _to_float(m.group(1))
        unit_info = _canonical_unit_name(m.group(2))
        if unit_info is None or not _valid_positive_amount(amount):
            out["unresolved"] = True
            out["reason"] = "invalid or non-positive quantity in package size"
            return out
        dimension, factor = unit_info
        out.update(
            dimension=dimension,
            pack_count=1,
            amount_per_pack=amount,
            unit=m.group(2).strip().lower(),
            total_amount=amount,
        )
        out["canonical_unit"] = CANONICAL_UNIT[dimension]
        out["canonical_total"] = round(amount * factor, 6)
        return out

    out["unresolved"] = True
    out["reason"] = "unrecognized format"
    return out


# --- Modifier vocabulary -----------------------------------------------
# Deliberately small and deterministic (per the project plan: "deterministic
# quantity parsing and a small grocery vocabulary first"). Multi-word entries
# must come before any single-word entry they contain, since matching tries
# them in this order.
MODIFIER_VOCAB = [
    "gluten free", "fat free", "sugar free", "dairy free", "free range",
    "extra large", "extra virgin", "low fat", "non fat", "reduced fat",
    "organic", "unsweetened", "sweetened", "whole", "skim", "unsalted",
    "salted", "fresh", "frozen", "large", "small", "medium", "jumbo",
    "1%", "2%",
]


def extract_modifiers(text: str) -> tuple:
    """Pull known modifier words/phrases out of `text`. Returns (modifiers,
    remaining_text). Unknown descriptive words are left in remaining_text --
    this only removes words the vocabulary explicitly recognizes, per the
    plan's "keep unknown attributes unknown" rule.

    Hyphens are normalized to spaces before matching ("gluten-free" ->
    "gluten free") since MODIFIER_VOCAB's multi-word entries are written
    space-separated and a hyphenated variant is exactly the same attribute,
    not an unknown one."""
    working = f" {text.lower().replace('-', ' ')} "
    found = []
    for phrase in MODIFIER_VOCAB:
        token = f" {phrase} "
        if token in working:
            found.append(phrase)
            working = working.replace(token, " ")
    remaining = re.sub(r"\s+", " ", working).strip()
    return found, remaining
