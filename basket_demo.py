"""Demo matching layer: one shopping list -> a best match per store.

Deliberately separate from the Streamlit app (demo_app.py) so it can be tested
without a UI, the same separation PROJECT_PLAN.md §2 asks for.

Why there is a score floor at all: with no floor, an unanswerable request
returns its best lexical match anyway ("5 gal whole milk" -> "Whole Carrots",
$1.49). In a basket comparison that is worse than a bad metric, because wrong
matches are systematically *cheap* and a cheapest-basket ranking therefore
prefers them -- one fake match can hand a store a fake win. The threshold is
load-bearing for the product in a way the retrieval metrics alone understate.

SCOPE WARNING, stated here because it is easy to mistake this for Checkpoint 5:
this is *not* the basket comparison engine. It does no package-count
arithmetic -- no ceiling(requested / per-package), no excess-quantity
reporting, no cheapest-sufficient-package selection. It reports the price of
one matched package per line, which is only the true line cost when the
requested quantity fits in a single package. Checkpoint 5 replaces this.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

import benchmark_config as cfg
import retrieval
from parse_query import parse_shopping_line
from product_identity import build_brand_lexicon, extract_request_identity

IDENTITY_PATH = Path(__file__).resolve().parent / "evaluation_v3" / "catalog_identity.csv"

# Deep enough that every store with a plausible match is represented before
# the per-store grouping happens. Not tuned against any evaluation metric --
# the demo reports matches, it is not a scored baseline.
_DEMO_SEARCH_DEPTH = 400


@dataclass
class LineMatch:
    store_id: str
    store_name: str
    product_id: str
    title: str
    price_cents: int | None
    score: float
    source_url: str | None = None


@dataclass
class LineResult:
    text: str
    structured: dict
    response: str                       # answerable | needs_clarification | no_acceptable_match
    matches: dict = field(default_factory=dict)   # store_id -> LineMatch
    note: str = ""


def load_identity(path: Path = IDENTITY_PATH):
    return pd.read_csv(path)


def build_context(catalog_df):
    """Everything the demo needs, built once and reused across lines."""
    vectorizer, matrix = retrieval.fit_tfidf(catalog_df)
    identity_df = load_identity()
    return {
        "catalog": catalog_df,
        "vectorizer": vectorizer,
        "matrix": matrix,
        "identity_lookup": retrieval._identity_lookup(identity_df),
        "brand_lexicon": build_brand_lexicon(catalog_df),
        "stores": (
            catalog_df[["store_id", "store_name"]]
            .drop_duplicates()
            .set_index("store_id")["store_name"]
            .to_dict()
        ),
    }


# A blunt score floor for the demo. NOT a tuned threshold and deliberately not
# benchmark_config.MIN_SIMILARITY (0.65): that value was tuned by Checkpoint E6
# on the dev split for a different filter stack, and applying it here removes
# correct generic matches -- "1 gallon whole milk" tops out at 0.401 because a
# short generic query against a short title simply cannot score high on TF-IDF
# cosine, while an exact-brand query like "12 oz Barissimo French Vanilla
# ground coffee" scores 1.000.
#
# Measured on the demo's own examples, right and wrong matches DO NOT separate
# cleanly on this scale:
#     1 gallon whole milk   -> 0.401  (right)
#     5 gal whole milk      -> 0.306  ("Whole Carrots", wrong)
#     2 lb chicken breast   -> 0.574  ("Roasted Chicken Breast Hot", wrong --
#                                      no 2 lb fixed package exists, per r051)
# A wrong match outscores a right one. No single global floor fixes that, and
# 0.35 does not pretend to: it removes the most obvious junk and nothing more.
# Choosing it against these examples is a form of tuning on the demo, which is
# why it is stated here rather than presented as a result. Checkpoint S6 is
# where a threshold and a review band get derived properly, on dev, with a
# declared cost function.
DEFAULT_MIN_SCORE = 0.35


def match_line(text: str, ctx: dict, mode: str = "flexible",
               min_score: float = DEFAULT_MIN_SCORE) -> LineResult:
    """Best surviving candidate per store for one shopping-list line.

    Runs the same filter stack as the S3 baseline -- parser gate, dimension,
    package size, identity -- then groups what survives by store instead of
    truncating to a single global top-k, because the demo needs one answer per
    store rather than one answer overall.
    """
    catalog = ctx["catalog"]
    structured = parse_shopping_line(text)
    if structured["needs_review"]:
        return LineResult(text, structured, "needs_clarification",
                          note=structured.get("review_reason") or "ambiguous request")

    candidates = retrieval.lexical_search(
        text, ctx["vectorizer"], ctx["matrix"], catalog, top_k=_DEMO_SEARCH_DEPTH)
    survivors = retrieval.filter_by_dimension(candidates, catalog, structured.get("dimension"))
    survivors = retrieval.filter_by_package_size(survivors, catalog, text, structured)

    request_identity = extract_request_identity(text, ctx["brand_lexicon"])
    survivors, needs_review = retrieval.filter_by_identity(
        survivors, catalog, ctx["identity_lookup"], request_identity, mode)

    survivors = [c for c in survivors if c["score"] >= min_score]

    if not survivors:
        if needs_review:
            return LineResult(text, structured, "needs_clarification",
                              note="could not confirm brand or variant for this request")
        return LineResult(text, structured, "no_acceptable_match",
                          note="no product in the snapshot satisfies this request "
                               f"above the {min_score:.2f} score floor")

    survivors.sort(key=cfg.tie_break_key)

    best: dict[str, LineMatch] = {}
    for c in survivors:
        row = catalog.iloc[c["row"]]
        store_id = str(row["store_id"])
        if store_id in best:
            continue                     # already sorted, so the first is the best
        price = row.get("price_cents")
        best[store_id] = LineMatch(
            store_id=store_id,
            store_name=ctx["stores"].get(row["store_id"], store_id),
            product_id=str(row["product_id"]),
            title=str(row["raw_title"]),
            price_cents=int(price) if pd.notna(price) else None,
            score=float(c["score"]),
        )

    note = "" if not needs_review else "some candidates could not be identity-confirmed"
    return LineResult(text, structured, "answerable", matches=best, note=note)


def compare_basket(lines: list[str], ctx: dict, mode: str = "flexible",
                   min_score: float = DEFAULT_MIN_SCORE):
    """Per-store subtotals over a whole list.

    A store is 'complete' only when every answerable line matched there. A
    store missing any line is reported separately and never ranked against a
    complete one -- PROJECT_PLAN.md Checkpoint 5's rule, honored here even
    though the arithmetic itself is out of scope.
    """
    results = [match_line(t, ctx, mode, min_score) for t in lines if t.strip()]
    answerable = [r for r in results if r.response == "answerable"]

    totals = {}
    for store_id, store_name in ctx["stores"].items():
        sid = str(store_id)
        matched, missing, subtotal, priced = [], [], 0, True
        for r in answerable:
            m = r.matches.get(sid)
            if m is None:
                missing.append(r.text)
            elif m.price_cents is None:
                matched.append(m)
                priced = False
            else:
                matched.append(m)
                subtotal += m.price_cents
        totals[sid] = {
            "store_name": store_name,
            "matched": matched,
            "missing": missing,
            "subtotal_cents": subtotal,
            "complete": not missing and bool(answerable),
            "fully_priced": priced,
        }
    return results, totals


def rank_complete_stores(totals: dict) -> list:
    """Complete, fully-priced stores cheapest-first. Ties are all returned;
    an incomplete basket never outranks a complete one because it never
    enters this list at all."""
    complete = [(sid, t) for sid, t in totals.items() if t["complete"] and t["fully_priced"]]
    return sorted(complete, key=lambda kv: (kv[1]["subtotal_cents"], kv[1]["store_name"]))
