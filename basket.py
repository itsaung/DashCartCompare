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
