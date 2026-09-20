"""Checkpoint 4, S2: brand and variant extraction, catalog side and query side.

Prerequisite for S3's exact mode, which requires brand, variant and package
size. `normalized_catalog.csv` carries `brand`/`variant` as explicit nulls on
every row -- `build_normalized_catalog.py` writes None deliberately and
PARSING_AUDIT.md records that extraction was deferred to Checkpoint 4. This is
that extraction.

Nothing here is written back into the frozen catalog. Output is a derived
side-car (evaluation_v3/catalog_identity.csv) so `catalog_version` never moves
and no existing label goes stale.

Standing rule throughout, the same one filter_by_dimension already follows:
unknown is a third state, never a match and never a conflict. A brand that
cannot be resolved is None, not a guess.

Deliberate deviation from CHECKPOINT_4_PLAN.md S2, recorded here because the
plan's rule was checked against real data and found wrong: the plan requires a
brand n-gram to appear in >= 2 distinct `raw_category` values. Measured against
the real catalog that rule discards 2,059 legitimate single-category brands
(A&W, Advil, Afrin, A.1., 3M among them), because plenty of real brands sell
into exactly one department. The category requirement is dropped; the
frequency requirement (MIN_BRAND_PRODUCTS) and the position requirement are
kept, and a dominant-continuation rule was added. See IDENTITY_EXTRACTION_AUDIT.md.
"""

from __future__ import annotations

import collections
import re
from pathlib import Path

import pandas as pd

IDENTITY_VERSION = "v1"

# An n-gram must begin this many distinct products within the catalog before it
# is treated as a brand. Declared before any evaluation metric was computed.
MIN_BRAND_PRODUCTS = 5

# Extend a brand n-gram by one token only when the longer form accounts for at
# least this share of the shorter form's products -- i.e. the continuation is
# the brand itself ("Signature" -> "Signature Select"), not a product line
# ("Signature Select" -/-> "Signature Select Double Zipper"). Measured
# insensitive across 0.40-0.75 on the real catalog; 0.50 is the declared value.
BRAND_EXTENSION_DOMINANCE = 0.50

MAX_BRAND_TOKENS = 3

_TOKEN_RE = re.compile(r"[A-Za-z0-9&'.\-]+")

# Words that are never a brand on their own. A multi-word n-gram made entirely
# of these is rejected too ("Great Value" is handled by the store-brand list).
GENERIC_LEADING = {
    "organic", "whole", "fresh", "natural", "premium", "classic", "original",
    "the", "gluten", "free", "great", "good", "value", "simply", "real", "pure",
    "raw", "hard", "non", "extra", "dry", "red", "white", "baby", "kids",
}

# Store/private-label brands, listed explicitly rather than inferred.
STORE_BRANDS = {
    "Signature Select", "O Organics", "Value Corner", "Lucerne", "Open Nature",
    "Primo Taglio", "Waterfront Bistro", "Debi Lilly", "Soleil",
    "Kroger", "Simple Truth", "Private Selection", "Home Chef",
    "Sprouts", "Sprouts Farmers Market",
    "Friendly Farms", "Simply Nature", "Specially Selected", "Happy Farms",
    "Clancy's", "Millville", "Crofton", "Benton's", "Burman's", "Casa Mamita",
    "Barissimo", "Fit & Active", "Never Any", "Southern Grove", "Berryhill",
    "Chef's Cupboard", "Countryside Creamery", "Dakota's Pride", "Earth Grown",
    "Elevation", "Goldhen", "Little Salad Bar", "Mama Cozzi's", "Nature's Nectar",
    "Priano", "Pueblo Lindo", "Reggano", "Season's Choice", "Simply Gum",
    "Stonemill", "Sundae Shoppe", "Tuscan Garden", "Village Bakery",
}

# Descriptor vocabulary for variant extraction. A token only becomes a variant
# if it is in here -- residual words outside the vocabulary are dropped, never
# invented into a variant.
VARIANT_VOCABULARY = {
    # dietary / process
    "organic", "nonorganic", "unsweetened", "sweetened", "unsalted", "salted",
    "gluten-free", "glutenfree", "lactose-free", "dairy-free", "sugar-free",
    "fat-free", "low-fat", "lowfat", "nonfat", "reduced-fat", "light",
    "decaf", "decaffeinated", "caffeine-free", "kosher", "halal", "vegan",
    "grass-fed", "free-range", "cage-free", "pasture-raised", "wild-caught",
    "non-gmo", "keto", "plant-based",
    # milk-fat / strength forms
    "whole", "skim", "1%", "2%",
    # preparation / state
    "frozen", "fresh", "canned", "dried", "raw", "cooked", "smoked", "roasted",
    "ground", "shredded", "sliced", "diced", "crushed", "creamy", "crunchy",
    "chunky", "fine", "coarse", "boneless", "skinless", "seedless", "pitted",
    "unbleached", "bleached", "instant", "concentrated",
    # flavor / variety
    "vanilla", "chocolate", "strawberry", "blueberry", "raspberry", "banana",
    "peach", "mango", "lemon", "lime", "orange", "cherry", "grape", "apple",
    "coconut", "almond", "peanut", "hazelnut", "caramel", "honey", "maple",
    "cinnamon", "mint", "peppermint", "original", "plain", "unflavored",
    "spicy", "mild", "medium", "hot", "sweet", "sour", "smoky", "garlic",
    "onion", "herb", "ranch", "bbq", "barbecue", "buffalo", "sea-salt",
    # color / type qualifiers that change the product
    "white", "brown", "black", "green", "red", "yellow", "dark", "milk",
    "extra-virgin", "virgin", "unrefined", "refined",
}

# Tokens that look like a size and must never leak into variant_tokens.
_SIZE_LIKE = re.compile(
    r"^(?:[\d.,/]+|oz|lb|lbs|g|kg|mg|ml|l|ct|pk|pack|fl|gal|qt|pt|x|count)$",
    re.IGNORECASE,
)


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(str(text or ""))


def _is_plausible_brand_ngram(ngram: str) -> bool:
    parts = ngram.split()
    if any(re.fullmatch(r"[\d.]+", p) for p in parts):
        return False
    if len(ngram) < 3:
        return False
    if all(p.lower() in GENERIC_LEADING for p in parts):
        return False
    return True


def build_brand_lexicon(catalog_df) -> dict[str, int]:
    """Induce a brand lexicon from the catalog's own leading n-grams.

    Returns {ngram: distinct product count}. Position is enforced here by
    construction -- only *leading* n-grams are counted, so a brand name
    appearing mid-title ("... made with Oreo cookies") never enters the
    lexicon on that row's account.
    """
    counts: dict[str, set] = collections.defaultdict(set)
    for row in catalog_df.itertuples():
        tokens = tokenize(row.raw_title)
        for n in range(1, MAX_BRAND_TOKENS + 1):
            if len(tokens) >= n:
                counts[" ".join(tokens[:n])].add((row.store_id, str(row.product_id)))
    return {
        ngram: len(ids)
        for ngram, ids in counts.items()
        if len(ids) >= MIN_BRAND_PRODUCTS and _is_plausible_brand_ngram(ngram)
    }


def _strip_trailing_generic(ngram: str) -> str:
    """Trim descriptor words off the end of a matched brand.

    "Clancy's Original" and "Simply Nature Organic" both qualify as leading
    n-grams, but "Original"/"Organic" are variant descriptors, not part of the
    brand -- leaving them attached would put the same word on both the brand
    and the variant side and make an exact-mode brand comparison depend on
    phrasing. Trimming happens identically on the catalog and query sides, so
    the two stay comparable.
    """
    parts = ngram.split()
    while len(parts) > 1 and parts[-1].lower() in GENERIC_LEADING:
        parts.pop()
    return " ".join(parts)


def extract_brand(title: str, lexicon: dict[str, int]) -> str | None:
    """Longest leading lexicon match, extended only while each longer form
    dominates its parent (BRAND_EXTENSION_DOMINANCE).

    Returns None when no leading n-gram qualifies -- explicitly unknown.
    """
    tokens = tokenize(title)
    best = None
    for n in range(1, MAX_BRAND_TOKENS + 1):
        if len(tokens) < n:
            break
        ngram = " ".join(tokens[:n])
        if ngram in lexicon:
            if best is None:
                best = ngram
            elif lexicon[ngram] / lexicon[best] >= BRAND_EXTENSION_DOMINANCE:
                best = ngram
            else:
                break
        elif best is not None:
            break
    if best is None:
        # A listed store brand is accepted on its own, even below the
        # frequency floor, because it is known rather than inferred.
        for n in range(MAX_BRAND_TOKENS, 0, -1):
            if len(tokens) >= n:
                candidate = " ".join(tokens[:n])
                if candidate in STORE_BRANDS:
                    return _strip_trailing_generic(candidate)
    return _strip_trailing_generic(best) if best else None


def extract_variant_tokens(text: str, brand: str | None = None) -> frozenset[str]:
    """Descriptor tokens, as a set.

    Set-based so word order, intervening descriptors and formatting never
    create a false conflict (LABELING_GUIDELINES.md v2). Size-like tokens are
    excluded explicitly so a package size can never masquerade as a variant.
    """
    tokens = tokenize(text)
    if brand:
        brand_tokens = {t.lower() for t in tokenize(brand)}
        tokens = [t for t in tokens if t.lower() not in brand_tokens]

    found = set()
    normalized = [t.lower().strip(".") for t in tokens]
    for i, tok in enumerate(normalized):
        if _SIZE_LIKE.match(tok):
            continue
        if tok in VARIANT_VOCABULARY:
            found.add(tok)
            continue
        # Hyphen-joined forms are already handled above; also try joining a
        # two-token form ("sea salt" -> "sea-salt", "extra virgin").
        if i + 1 < len(normalized):
            joined = f"{tok}-{normalized[i + 1]}"
            if joined in VARIANT_VOCABULARY:
                found.add(joined)
    return frozenset(found)


def variants_conflict(a: frozenset[str], b: frozenset[str]) -> bool:
    """True only when both sides state something and they disagree on a
    mutually exclusive attribute. An empty set on either side is unknown, not
    a conflict."""
    if not a or not b:
        return False
    for group in _EXCLUSIVE_GROUPS:
        a_in, b_in = a & group, b & group
        if a_in and b_in and a_in != b_in:
            return True
    return False


# Attributes where two different values are a genuine conflict, rather than
# two descriptors that can both be true of one product.
_EXCLUSIVE_GROUPS = [
    frozenset({"whole", "skim", "1%", "2%", "nonfat", "low-fat", "lowfat", "reduced-fat"}),
    frozenset({"frozen", "fresh", "canned", "dried"}),
    frozenset({"creamy", "crunchy", "chunky"}),
    frozenset({"unsweetened", "sweetened"}),
    frozenset({"unsalted", "salted"}),
    frozenset({"decaf", "decaffeinated", "caffeine-free"}) | frozenset({"instant"}),
    frozenset({"vanilla", "chocolate", "strawberry", "blueberry", "raspberry",
               "banana", "peach", "mango", "lemon", "lime", "orange", "cherry",
               "grape", "coconut", "caramel", "honey", "maple", "cinnamon",
               "mint", "peppermint", "plain", "unflavored"}),
    frozenset({"boneless", "skinless"}) | frozenset({"ground", "shredded", "sliced", "diced"}),
]


def build_catalog_identity(catalog_df) -> pd.DataFrame:
    """Derive brand/variant for every catalog row. Side-car only."""
    lexicon = build_brand_lexicon(catalog_df)
    rows = []
    for row in catalog_df.itertuples():
        brand = extract_brand(row.raw_title, lexicon)
        variant = extract_variant_tokens(row.raw_title, brand)
        rows.append({
            "store_id": row.store_id,
            "product_id": row.product_id,
            "brand": brand,
            "brand_confidence": "lexicon" if brand else "unknown",
            "variant_tokens": " ".join(sorted(variant)),
            "identity_status": "resolved" if brand else "brand_unknown",
            "identity_version": IDENTITY_VERSION,
        })
    return pd.DataFrame(rows)


def extract_request_identity(request_text: str, lexicon: dict[str, int]) -> dict:
    """Query-side counterpart. A shopping request rarely leads with a brand, so
    the lexicon is searched anywhere in the text here -- but only as a whole
    token run, and only for entries already established as brands by the
    catalog-side position rule."""
    tokens = tokenize(request_text)
    lowered = [t.lower() for t in tokens]
    brand = None
    for n in range(MAX_BRAND_TOKENS, 0, -1):
        for i in range(len(tokens) - n + 1):
            candidate = " ".join(tokens[i:i + n])
            if candidate in lexicon or candidate in STORE_BRANDS:
                if _is_plausible_brand_ngram(candidate):
                    brand = _strip_trailing_generic(candidate)
                    break
        if brand:
            break
    del lowered
    return {
        "brand": brand,
        "brand_confidence": "lexicon" if brand else "unknown",
        "variant_tokens": extract_variant_tokens(request_text, brand),
    }


OUTPUT_PATH = Path(__file__).resolve().parent / "evaluation_v3" / "catalog_identity.csv"


def main() -> None:
    from run_experiments import _load_catalog

    catalog_df = _load_catalog()
    lexicon = build_brand_lexicon(catalog_df)
    identity = build_catalog_identity(catalog_df)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    identity.to_csv(OUTPUT_PATH, index=False)

    resolved = int((identity["identity_status"] == "resolved").sum())
    with_variant = int((identity["variant_tokens"] != "").sum())
    total = len(identity)
    print(f"lexicon entries: {len(lexicon)}")
    print(f"brand resolved:  {resolved}/{total} = {resolved / total:.1%}")
    print(f"variant present: {with_variant}/{total} = {with_variant / total:.1%}")
    print(f"wrote {OUTPUT_PATH.relative_to(OUTPUT_PATH.parent.parent)}")


if __name__ == "__main__":
    main()
