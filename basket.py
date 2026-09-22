"""Checkpoint 5, B1: package-count arithmetic.

The primitive the basket engine sits on, built in isolation so it can be
exhaustively tested before a catalog row or a matcher result reaches it.

    packages needed = ceiling(requested quantity / quantity per package)
    line cost       = packages needed * package price

Two rules this module exists to enforce, both of which are easy to lose once
this logic is inlined into something bigger:

MONEY IS INTEGER CENTS, END TO END. No float arrives in, passes through, or
leaves the money path. PROJECT_PLAN.md requires integer-cent summation, and the
way that requirement is normally lost is a float sneaking in at one boundary and
being rounded back at another. `line_cost_cents` rejects a float price outright
rather than coercing it -- a coercion here would be the exact silent failure the
rule is meant to prevent. Quantities ARE floats (that is how `normalize.py`
canonicalizes them), but they only ever reach money through an integer package
count.

UNIT COMPATIBILITY IS A PRECONDITION, NOT A CONVERSION. Given a request in
`fl oz` and a package in `oz`, this module raises. It does not convert. Whether
a 2 L bottle may satisfy a 67.6 fl oz request is a live product question
(CHECKPOINT_5_PLAN.md B2, open question 1) and PROJECT_PLAN.md Appendix A item 8
records cross-unit comparison as a known broken area. Answering it implicitly
here, with a conversion table nobody reviewed, is how a broken area becomes an
invisible one.

WHY THERE IS A TOLERANCE AT ALL. `normalize.py` canonicalizes to oz / fl oz / ct
through lossy float factors rounded to 6dp, so two labels for the same physical
package do not produce the same number:

    "500 g"   -> 17.637   oz          "17.6 oz" -> 17.6  oz    quotient 1.0021
    "454 g"   -> 16.014396 oz         "1 lb"    -> 16.0  oz
    "2 L"     -> 67.628   fl oz       "67.6 fl oz" -> 67.6 fl oz

A naive ceiling turns that first pair into TWO packages -- doubling a shopper's
cost because a manufacturer printed grams and a store printed ounces. The
quotient is therefore snapped down to a whole package when it sits within
`retrieval.PACKAGE_SIZE_ROUNDING_TOLERANCE` (1%, relative) of one. That constant
is reused rather than redeclared: it already answers exactly this question
elsewhere in the codebase ("are these two printed sizes the same package?"), its
1% value was argued against real data, and a second copy here would be free to
drift from it.

The tolerance is deliberately ONE-SIDED. It can only ever reduce a package count
that float dust or label rounding inflated; it can never let a genuinely
insufficient package satisfy a request. 13 oz against a 12 oz package is 8.3%
over and still needs two.

B1 knows nothing about stores, stock, scores or ranking. B2 adds exactly one
thing on top: choosing which package to buy, by actual purchase cost.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from build_availability import OUT_OF_STOCK, lookup as availability_lookup
from parse_query import parse_shopping_line
from retrieval import PACKAGE_SIZE_ROUNDING_TOLERANCE


class BasketArithmeticError(ValueError):
    """Base for every precondition this module refuses to guess past."""


class UnitMismatchError(BasketArithmeticError):
    """The request and the package are not measured in the same canonical unit."""


class UnresolvedSizeError(BasketArithmeticError):
    """A package size that cannot be divided by: missing, zero or negative.

    3,122 rows of the frozen catalog have no `pkg_canonical_total` and 1,000 are
    `variable_weight`. Those rows have no package size, so they have no package
    count -- they are surfaced to the caller as unresolved, never defaulted to 1.
    """


@dataclass(frozen=True)
class LineArithmetic:
    """One shopping-list line against one chosen package."""
    packages: int
    line_cost_cents: int
    excess: float
    requested_total: float
    per_package_total: float
    canonical_unit: str
    pkg_count: int | None = None   # carried for display only, never divided by


def require_same_unit(requested_unit, package_unit) -> str:
    """The unit both sides must already agree on. Raises otherwise.

    An unknown unit on either side is a mismatch, not a wildcard -- the standing
    rule in this codebase is that unknown is a third state, and the one thing it
    must never do is silently satisfy a check.
    """
    if not requested_unit or not package_unit:
        raise UnitMismatchError(
            f"unit unknown on one side (request {requested_unit!r}, "
            f"package {package_unit!r}) -- unknown is not a match")
    if requested_unit != package_unit:
        raise UnitMismatchError(
            f"{requested_unit!r} vs {package_unit!r}: this module does not convert "
            "between canonical units (see module docstring)")
    return requested_unit


def _validate_totals(requested_total, per_package_total) -> None:
    if requested_total is None or not isinstance(requested_total, (int, float)):
        raise BasketArithmeticError(f"requested total is not a number: {requested_total!r}")
    if requested_total <= 0:
        raise BasketArithmeticError(f"requested total must be positive, got {requested_total!r}")
    if per_package_total is None or not isinstance(per_package_total, (int, float)):
        raise UnresolvedSizeError(f"package size unresolved: {per_package_total!r}")
    if per_package_total <= 0:
        raise UnresolvedSizeError(
            f"package size must be positive, got {per_package_total!r}")
    if math.isnan(requested_total) or math.isnan(per_package_total):
        raise UnresolvedSizeError("NaN package size or requested total")


def packages_needed(requested_total, per_package_total,
                    tolerance: float = PACKAGE_SIZE_ROUNDING_TOLERANCE) -> int:
    """ceiling(requested / per_package), with the one-sided rounding tolerance
    described in the module docstring. Always >= 1 for a positive request."""
    _validate_totals(requested_total, per_package_total)

    quotient = requested_total / per_package_total
    whole = math.floor(quotient)
    # Snap down only when the overshoot past a whole number of packages is
    # within tolerance OF THOSE PACKAGES -- i.e. it is label rounding, not a
    # real shortfall. Never applies below one package.
    if whole >= 1 and quotient <= whole * (1 + tolerance):
        return int(whole)
    return int(math.ceil(quotient))


def line_cost_cents(packages: int, price_cents: int) -> int:
    """packages * price_cents, both integers, result an integer.

    `bool` is rejected explicitly although it is an `int` subclass: `True` as a
    package count would silently price one package, and a type check that lets
    that through is not doing its job.
    """
    for name, value in (("packages", packages), ("price_cents", price_cents)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise BasketArithmeticError(
                f"{name} must be an int in whole units, got {value!r} "
                f"({type(value).__name__}) -- money never touches a float here")
    if packages < 1:
        raise BasketArithmeticError(f"packages must be at least 1, got {packages}")
    if price_cents < 0:
        raise BasketArithmeticError(f"price_cents must not be negative, got {price_cents}")
    return packages * price_cents


def excess_quantity(packages: int, per_package_total, requested_total) -> float:
    """What the shopper ends up with beyond what they asked for, in canonical
    units. Reported, never silently absorbed -- PROJECT_PLAN.md requires excess
    to be displayed when whole packages are purchased.

    Floors at 0.0. A small negative value here is the rounding tolerance doing
    its job (a 17.6 oz package accepted for a 17.637 oz request), not a
    shortfall, and reporting it as "-0.037 oz short" would be a worse lie than
    reporting zero excess.
    """
    _validate_totals(requested_total, per_package_total)
    if isinstance(packages, bool) or not isinstance(packages, int):
        raise BasketArithmeticError(f"packages must be an int, got {packages!r}")
    return max(0.0, packages * per_package_total - requested_total)


def compute_line(requested_total, requested_unit, per_package_total, package_unit,
                 price_cents: int, pkg_count: int | None = None) -> LineArithmetic:
    """The whole B1 computation for one line against one package.

    Single entry point on purpose: it checks the units BEFORE it divides, so a
    caller cannot forget that step and get a plausible-looking number out of two
    incompatible quantities.

    `pkg_count` is carried through untouched and never divided by -- a row's
    `pkg_canonical_total` is already the total across the whole pack (which is
    why `retrieval._requested_canonical_total` was made multipack-aware in
    Checkpoint 3.1), so multiplying by the pack count here would double-count it.
    """
    unit = require_same_unit(requested_unit, package_unit)
    packages = packages_needed(requested_total, per_package_total)
    return LineArithmetic(
        packages=packages,
        line_cost_cents=line_cost_cents(packages, price_cents),
        excess=excess_quantity(packages, per_package_total, requested_total),
        requested_total=float(requested_total),
        per_package_total=float(per_package_total),
        canonical_unit=unit,
        pkg_count=pkg_count,
    )


# ---------------------------------------------------------------------------
# B2 -- cheapest sufficient package
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    """One catalog row offered for one line. Deliberately not a DataFrame row:
    the selection below should be testable with five hand-written objects and
    no catalog on disk."""
    store_id: str
    product_id: str
    title: str
    price_cents: int
    per_package_total: float | None
    canonical_unit: str | None
    score: float = 0.0
    pkg_count: int | None = None


@dataclass(frozen=True)
class Selection:
    """The chosen package for a line, with what it beat and why."""
    candidate: Candidate
    arithmetic: LineArithmetic
    runner_up: "Selection | None" = None
    considered: int = 0
    unresolved: tuple = ()

    @property
    def line_cost_cents(self) -> int:
        return self.arithmetic.line_cost_cents


def _selection_sort_key(priced) -> tuple:
    """Declared before the first run, per CHECKPOINT_5_PLAN.md B2.

    Cost first: PROJECT_PLAN.md asks flexible mode to "select the cheapest
    accepted product sufficient for the requested quantity", and that is a cost
    question, not a unit-price one. Unit price and actual purchase cost disagree
    exactly when excess is large -- a 5 lb sack may have the better unit price
    and still be the wrong answer for a 1 lb request -- and it is actual outlay
    the shopper pays.

    Then LESS EXCESS, which is the whole role excess plays in ranking: it breaks
    genuine cost ties and nothing else. Excess is displayed, never priced into
    the ranking, because a waste cost would be an undeclared weight nobody has
    measured -- the same class of knob that S6's 0.5 review cost turned out to
    be, and that one at least was declared in advance.

    Then higher match score, then product id so the order is total and a
    re-run cannot reshuffle a tie.
    """
    candidate, arithmetic = priced
    return (arithmetic.line_cost_cents, arithmetic.excess,
            -candidate.score, str(candidate.product_id))


def select_cheapest_sufficient(candidates, requested_total, requested_unit,
                               min_score: float | None = None) -> Selection | None:
    """The cheapest package that covers the request, with its runner-up.

    `min_score` IS NOT OPTIONAL IN PRACTICE, and the default of None exists only
    so the arithmetic can be tested without a matcher. PROJECT_PLAN.md says
    flexible mode selects "the cheapest **accepted** product sufficient for the
    requested quantity" -- the acceptance bar is load-bearing, and ranking by
    cost without it does not degrade gracefully, it inverts.

    Measured on flexible dev requests, 2026-09-21, ranking over the
    size-sufficient pool with no acceptance bar:

        "2 lb Honeycrisp Apples"  -> Sweet Onions Bag (2 lb), $1.69
        "10 oz potato chips"      -> Happy Harvest Whole Potatoes (15 oz), $1.19
        "12 oz ground coffee"     -> a 15 oz caramel vanilla coffee, $4.49

    The sufficiency gate is deliberately weak -- any positive package size can
    cover any request by buying enough of them -- so it admits ~190 of 200
    retrieved rows. The cheapest thing in a bag of 190 groceries is essentially
    never the thing the shopper asked for. Cost may only choose among products
    that have already been judged acceptable matches; it must never be what
    decides whether a product matches.

    Returns None when nothing could be priced. Candidates whose size cannot be
    resolved are not dropped on the floor -- they come back on the Selection as
    `unresolved`, so a caller can report "3 possibilities had no package size"
    instead of silently narrowing the shopper's options.

    A candidate in a different canonical unit is skipped rather than raising:
    at this level a mixed-unit candidate list is an ordinary occurrence, and
    `compute_line`'s raise is the right behavior only when a caller has already
    committed to one specific package.
    """
    priced, unresolved = [], []
    for c in candidates:
        if min_score is not None and c.score < min_score:
            continue
        try:
            arithmetic = compute_line(
                requested_total, requested_unit, c.per_package_total, c.canonical_unit,
                c.price_cents, pkg_count=c.pkg_count)
        except UnitMismatchError:
            continue
        except UnresolvedSizeError:
            unresolved.append(c)
            continue
        priced.append((c, arithmetic))

    if not priced:
        return None

    priced.sort(key=_selection_sort_key)
    best_candidate, best_arithmetic = priced[0]

    runner_up = None
    if len(priced) > 1:
        second_candidate, second_arithmetic = priced[1]
        runner_up = Selection(candidate=second_candidate, arithmetic=second_arithmetic,
                              considered=len(priced), unresolved=tuple(unresolved))

    return Selection(candidate=best_candidate, arithmetic=best_arithmetic,
                     runner_up=runner_up, considered=len(priced),
                     unresolved=tuple(unresolved))


# ---------------------------------------------------------------------------
# B4 -- line resolution: duplicates, the three-way response, overrides
# ---------------------------------------------------------------------------

LINE_PRICED = "priced"
LINE_REVIEW = "review"
LINE_MISSING = "missing"


@dataclass(frozen=True)
class ShoppingLine:
    """One line of a shopping list, after duplicate resolution.

    `texts` is a tuple rather than a string because a merged line came from
    more than one thing the shopper wrote, and an explanation has to be able to
    show both.
    """
    texts: tuple
    product_type: str | None
    matching_mode: str
    canonical_unit: str | None
    canonical_quantity: float | None
    needs_review: bool
    review_reasons: tuple = ()

    @property
    def text(self) -> str:
        return self.texts[0] if self.texts else ""

    @property
    def merged(self) -> bool:
        return len(self.texts) > 1


@dataclass(frozen=True)
class LineResolution:
    """What the basket can say about one line at one store."""
    line: ShoppingLine
    state: str
    selection: Selection | None = None
    candidates: tuple = ()
    reason: str = ""
    overridden: bool = False
    excluded_out_of_stock: tuple = ()

    @property
    def line_cost_cents(self) -> int | None:
        return self.selection.line_cost_cents if self.selection else None


def resolve_lines(texts, matching_mode="flexible", modes_by_index=None) -> list:
    """Shopping-list text -> ShoppingLines, with duplicates summed.

    MERGE RULE, deliberately narrow: same product_type AND same canonical unit
    AND same matching mode. "2 lb chicken" + "1 lb chicken" is one line of
    3 lb. Anything else stays two lines.

    It is narrow on purpose. A loose merge -- fuzzy product similarity, or
    ignoring the unit -- silently changes what the shopper asked for, and a
    basket that quietly combines "1 lb chicken breast" with "2 lb chicken
    thighs" has invented an order nobody placed. Two lines that should have
    merged and did not cost the shopper a duplicate purchase they can see and
    fix; two lines that merged and should not have produce a wrong basket they
    cannot see.

    A line whose parse failed never merges: it has no canonical unit to merge
    ON, and guessing that two unparseable lines are the same request is exactly
    the fuzzy matching this rule exists to avoid.
    """
    parsed = []
    for i, text in enumerate(texts):
        mode = (modes_by_index or {}).get(i, matching_mode)
        s = parse_shopping_line(text)
        parsed.append((text, mode, s))

    merged = {}
    order = []
    for text, mode, s in parsed:
        key = (s["product_type"], s["canonical_unit"], mode)
        mergeable = (not s["needs_review"] and s["product_type"]
                     and s["canonical_unit"] and s["canonical_quantity"] is not None)
        if mergeable and key in merged:
            prior = merged[key]
            merged[key] = ShoppingLine(
                texts=prior.texts + (text,),
                product_type=prior.product_type,
                matching_mode=prior.matching_mode,
                canonical_unit=prior.canonical_unit,
                canonical_quantity=prior.canonical_quantity + s["canonical_quantity"],
                needs_review=False,
                review_reasons=(),
            )
            continue

        line = ShoppingLine(
            texts=(text,),
            product_type=s["product_type"],
            matching_mode=mode,
            canonical_unit=s["canonical_unit"],
            canonical_quantity=s["canonical_quantity"],
            needs_review=bool(s["needs_review"]),
            review_reasons=tuple(s["review_reasons"]),
        )
        if mergeable:
            merged[key] = line
            order.append(("key", key))
        else:
            order.append(("line", line))

    out = []
    for kind, value in order:
        out.append(merged[value] if kind == "key" else value)
    return out


def line_state(response: str, top_score, accept_threshold: float,
               review_floor: float) -> str:
    """The frozen three-way response, as a basket line state.

    Deliberately the same rule as tune_threshold_v3.apply_cut_points, which is
    what Checkpoint 4's cut points were selected under; a test pins the two
    together across a grid so this cannot drift from the thresholds' meaning.
    It is restated here rather than imported because that module pulls in the
    whole evaluation stack, and the basket engine should not depend on the
    benchmark to price a line.

    REVIEW IS NOT "CLOSE ENOUGH TO PRICED". A review-band line is never priced
    to improve completeness -- it is the matcher declining to commit, and a
    basket that prices it anyway has converted a declared uncertainty into a
    confident number.
    """
    if response == "needs_clarification":
        return LINE_REVIEW
    if response != "answerable" or top_score is None:
        return LINE_MISSING
    if top_score >= accept_threshold:
        return LINE_PRICED
    if top_score >= review_floor:
        return LINE_REVIEW
    return LINE_MISSING


def resolve_line(line: ShoppingLine, candidates, accept_threshold: float,
                 review_floor: float, availability_by_key=None,
                 response: str | None = None) -> LineResolution:
    """One ShoppingLine against one store's candidates.

    Out-of-stock candidates are removed before anything is scored or priced,
    and are reported on the resolution so the explanation can name them --
    PROJECT_PLAN.md asks for out-of-stock items to be excluded, and an
    exclusion the shopper cannot see is indistinguishable from the store not
    carrying the product.
    """
    if line.needs_review:
        return LineResolution(line=line, state=LINE_REVIEW, candidates=tuple(candidates),
                              reason="; ".join(line.review_reasons) or "line needs review")

    excluded = ()
    if availability_by_key is not None:
        kept = []
        dropped = []
        for c in candidates:
            if availability_lookup(availability_by_key, c.store_id, c.product_id).state == OUT_OF_STOCK:
                dropped.append(c)
            else:
                kept.append(c)
        candidates, excluded = kept, tuple(dropped)

    top_score = max((c.score for c in candidates), default=None)
    state = line_state(response or ("answerable" if candidates else "no_acceptable_match"),
                       top_score, accept_threshold, review_floor)

    if state != LINE_PRICED:
        return LineResolution(
            line=line, state=state, candidates=tuple(candidates),
            reason=("no candidate cleared the review floor" if state == LINE_MISSING
                    else "score in the review band -- candidates shown, not priced"),
            excluded_out_of_stock=excluded)

    selection = select_for_line(
        candidates, line.canonical_quantity, line.canonical_unit,
        min_score=accept_threshold)
    if selection is None:
        # Accepted by score, but nothing could be priced -- every accepted
        # candidate had an unresolvable package size. That is a review, not a
        # match and not an abstention: there IS a product, its size is unknown.
        return LineResolution(
            line=line, state=LINE_REVIEW, candidates=tuple(candidates),
            reason="accepted candidates have no resolvable package size",
            excluded_out_of_stock=excluded)

    return LineResolution(line=line, state=LINE_PRICED, selection=selection,
                          candidates=tuple(candidates), excluded_out_of_stock=excluded)


def apply_override(resolution: LineResolution, candidate: Candidate) -> LineResolution:
    """The shopper picks a specific product for a line.

    Recomputes package count, line cost and excess from scratch against the
    chosen candidate -- it never patches the previous arithmetic, because a
    partially-updated total is worse than no total. Works from any state,
    including a line the matcher abstained on: an override is the shopper
    overruling the matcher, which is the entire point of offering one.

    Raises rather than guessing when the chosen product cannot be priced --
    an override that silently produced no cost would look like a successful
    selection.
    """
    line = resolution.line
    if line.canonical_quantity is None or not line.canonical_unit:
        raise BasketArithmeticError(
            f"cannot price an override for a line with no resolvable amount: {line.text!r}")

    arithmetic = compute_line(
        line.canonical_quantity, line.canonical_unit, candidate.per_package_total,
        candidate.canonical_unit, candidate.price_cents, pkg_count=candidate.pkg_count)
    selection = Selection(candidate=candidate, arithmetic=arithmetic, considered=1)
    return LineResolution(line=line, state=LINE_PRICED, selection=selection,
                          candidates=resolution.candidates, reason="chosen by the shopper",
                          overridden=True,
                          excluded_out_of_stock=resolution.excluded_out_of_stock)


# ---------------------------------------------------------------------------
# B5 -- basket assembly, comparison and ranking
# ---------------------------------------------------------------------------

# How close in match score a candidate must be to the best accepted one before
# cost is allowed to decide between them. DECLARED BEFORE FIRST USE, 2026-09-21.
#
# Why cost is not the primary key. B2 measured what happens when it is: ranking
# by cost across everything the sufficiency gate admits selected Sweet Onions
# for "2 lb Honeycrisp Apples" and Whole Potatoes for "10 oz potato chips".
# PROJECT_PLAN.md says "the cheapest ACCEPTED product"; acceptance has to come
# first, and a 0.02-worse match that happens to be cheap is not the same
# product the shopper asked for.
#
# Where 0.01 comes from. Measured over the 347 accepted-but-not-best candidates
# on 30 flexible dev lines, the gap below the best accepted score has its 5th
# percentile at 0.0106. A candidate inside that band is in the tightest 5% of
# the accepted distribution -- effectively the same match quality, which is
# exactly when price should decide. Deriving it from dev scores IS a use of the
# tuning split; that is permitted (dev is the tuning split) and is stated here
# rather than left implicit, the same disclosure S6 made about its grid.
#
# Sensitivity, on those 30 lines (total basket cost, and lines whose selection
# differs from pure score ranking):
#
#     band       total     lines changed
#     0.000     20,389          0   (pure score)
#     0.005     19,959          2
#     0.010     19,769          3   <- declared
#     0.020     18,277          6
#     0.050     13,454         16
#     cost-only 10,482         20   (B2's original behavior)
#
# The band is load-bearing and this is a design preference, not a measurement of
# anything: widening it buys a cheaper basket by accepting worse matches, and
# the far end of that trade is the onions. Do not read 0.01 as tuned.
SCORE_NEAR_TIE_BAND = 0.01

BASKET_COMPLETE = "complete"
BASKET_INCOMPLETE = "incomplete"


def select_for_line(candidates, requested_total, requested_unit, min_score=None,
                    near_tie_band: float = SCORE_NEAR_TIE_BAND) -> Selection | None:
    """The shipped selection rule: best match first, cost breaks near-ties.

    Narrows to candidates within `near_tie_band` of the best accepted score,
    then hands that set to `select_cheapest_sufficient`. With a band of 0.0 this
    is pure score ranking; with an unbounded band it is B2's original cost-only
    behavior. Both remain reachable for tests and for the sensitivity table.
    """
    pool = [c for c in candidates if min_score is None or c.score >= min_score]
    if not pool:
        return None
    best = max(c.score for c in pool)
    near = [c for c in pool if c.score >= best - near_tie_band]
    return select_cheapest_sufficient(near, requested_total, requested_unit)


@dataclass(frozen=True)
class StoreBasket:
    store_id: str
    store_name: str
    resolutions: tuple
    total_cents: int | None
    state: str
    n_priced: int
    n_review: int
    n_missing: int
    n_verified: int
    n_unverified: int
    n_out_of_stock_excluded: int

    @property
    def complete(self) -> bool:
        return self.state == BASKET_COMPLETE


def build_store_basket(store_id, store_name, resolutions, availability_by_key=None) -> StoreBasket:
    """One store's basket. Complete only when EVERY line priced.

    A review line makes this store's basket incomplete and nothing more -- the
    comparison as a whole is unaffected. Review is per (line, store): a score
    below the accept threshold at one store says nothing about another, which
    may carry the same product under a cleaner title. Blocking every store on
    one store's review would suppress the ranking on most real lists, since
    review runs ~17% of lines across the frozen benchmark.
    """
    resolutions = tuple(resolutions)
    n_priced = sum(1 for r in resolutions if r.state == LINE_PRICED)
    n_review = sum(1 for r in resolutions if r.state == LINE_REVIEW)
    n_missing = sum(1 for r in resolutions if r.state == LINE_MISSING)
    complete = bool(resolutions) and n_priced == len(resolutions)

    n_verified = n_unverified = 0
    if availability_by_key is not None:
        for r in resolutions:
            if r.selection is None:
                continue
            state = availability_lookup(availability_by_key, r.selection.candidate.store_id,
                                        r.selection.candidate.product_id)
            if state.verified:
                n_verified += 1
            else:
                n_unverified += 1

    # A total is computed only for a complete basket. A partial sum is the
    # number most likely to be misread as a price, and PROJECT_PLAN.md forbids
    # ranking on it -- so it is not produced at all rather than produced and
    # hidden behind a flag a caller can ignore.
    total = sum(r.line_cost_cents for r in resolutions) if complete else None

    return StoreBasket(
        store_id=str(store_id), store_name=store_name, resolutions=resolutions,
        total_cents=total, state=BASKET_COMPLETE if complete else BASKET_INCOMPLETE,
        n_priced=n_priced, n_review=n_review, n_missing=n_missing,
        n_verified=n_verified, n_unverified=n_unverified,
        n_out_of_stock_excluded=sum(len(r.excluded_out_of_stock) for r in resolutions),
    )


def compare_stores(baskets) -> dict:
    """Rank complete baskets by total. Incomplete ones are reported, never ranked.

    PROJECT_PLAN.md: "A smaller incomplete basket never outranks a complete
    basket." That is enforced by construction -- an incomplete basket has no
    total to rank with -- rather than by sorting carefully and hoping.

    `winners` is a LIST because ties are shown in full. Collapsing a tie to one
    store would invent a preference the prices do not support.
    """
    baskets = list(baskets)
    complete = [b for b in baskets if b.complete]
    incomplete = [b for b in baskets if not b.complete]
    ranked = sorted(complete, key=lambda b: (b.total_cents, b.store_id))

    winners, cheapest = [], None
    if ranked:
        cheapest = ranked[0].total_cents
        winners = [b for b in ranked if b.total_cents == cheapest]

    return {
        "ranked": ranked,
        "incomplete": incomplete,
        "winners": winners,
        "cheapest_total_cents": cheapest,
        "is_tie": len(winners) > 1,
        # No winner and an explicit reason, rather than a cheapest-of-the-broken
        # ranking that reads like an answer.
        "no_winner_reason": (
            None if ranked else
            "no store can complete this basket" if baskets else "no stores compared"),
        "n_compared": len(baskets),
        "n_complete": len(complete),
        "verification": {
            b.store_id: {"verified_lines": b.n_verified, "unverified_lines": b.n_unverified}
            for b in baskets
        },
        "caveat": (
            "Verification rate is a storefront artifact, not a stock difference -- "
            "DashMart publishes a per-product count and the other storefronts do not. "
            "It is reported per store and is never an input to this ranking."
        ),
    }
