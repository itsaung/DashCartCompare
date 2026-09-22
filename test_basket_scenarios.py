"""Checkpoint 5, B6 -- the hand-calculated scenario suite.

This is Checkpoint 5's actual pass criterion: PROJECT_PLAN.md asks for "at
least 20 hand-calculated basket scenarios pass exactly", covering multipacks,
ties, missing products, unknown package sizes, duplicate entries and
incompatible units.

Every expected value lives in evaluation_v4/basket_scenarios.json and was
computed by hand, with the arithmetic written out in each scenario's
`hand_calculation` field, BEFORE the engine was run against it. This file only
executes them. It deliberately contains no arithmetic of its own: a runner that
recomputed an expectation would be checking the engine against itself.

Prices and package sizes are real rows of benchmark_catalog_frozen.csv, cited by
(store_id, product_id). Scores are chosen to exercise a response state, which
the scenario file states explicitly.
"""
import json
from pathlib import Path

import pytest

import basket
import build_availability as ba

SCENARIOS_PATH = Path(__file__).resolve().parent / "evaluation_v4" / "basket_scenarios.json"
DOC = json.loads(SCENARIOS_PATH.read_text())
SCENARIOS = DOC["scenarios"]
ACCEPT = DOC["thresholds"]["accept"]
REVIEW = DOC["thresholds"]["review_floor"]


def _candidate(store_id, spec):
    return basket.Candidate(
        store_id=str(store_id), product_id=str(spec["product_id"]), title=spec["title"],
        price_cents=spec["price_cents"], per_package_total=spec["per_package_total"],
        canonical_unit=spec["unit"], score=spec["score"], pkg_count=spec.get("pkg_count"))


def _availability(scenario):
    table = scenario.get("availability")
    if not table:
        return None
    out = {}
    for store_id, specs in scenario["candidates"].items():
        for spec in _flatten(specs):
            state = table.get(str(spec["product_id"]))
            if state:
                out[(str(store_id), str(spec["product_id"]))] = ba.Availability(state)
    return out


def _flatten(specs):
    """A store's candidates are either one list for every line, or a list of
    per-line lists."""
    if specs and isinstance(specs[0], list):
        return [spec for line_specs in specs for spec in line_specs]
    return specs


def _per_line(specs, n_lines):
    if specs and isinstance(specs[0], list):
        assert len(specs) == n_lines, "per-line candidate lists must match the line count"
        return specs
    return [specs] * n_lines


def _run(scenario):
    """Scenario -> {store_id: StoreBasket}. No arithmetic here by design."""
    lines = basket.resolve_lines(scenario["lines"])
    availability = _availability(scenario)
    baskets = {}
    for store_id, specs in scenario["candidates"].items():
        per_line = _per_line(specs, len(lines))
        resolutions = [
            basket.resolve_line(line, [_candidate(store_id, c) for c in line_specs],
                                ACCEPT, REVIEW, availability_by_key=availability)
            for line, line_specs in zip(lines, per_line)
        ]
        baskets[str(store_id)] = basket.build_store_basket(
            store_id, str(store_id), resolutions, availability_by_key=availability)
    return lines, baskets


def _check_line(resolution, expected):
    assert resolution.state == expected["state"]
    if "packages" in expected:
        assert resolution.selection.arithmetic.packages == expected["packages"]
    if "line_cost_cents" in expected:
        assert resolution.line_cost_cents == expected["line_cost_cents"]
        assert isinstance(resolution.line_cost_cents, int)
    if "excess" in expected:
        assert resolution.selection.arithmetic.excess == pytest.approx(expected["excess"])
    if "product_id" in expected:
        assert resolution.selection.candidate.product_id == str(expected["product_id"])
    if "reason_contains" in expected:
        assert expected["reason_contains"] in resolution.reason
    if "n_candidates" in expected:
        assert len(resolution.candidates) == expected["n_candidates"]
    if "n_excluded_out_of_stock" in expected:
        assert len(resolution.excluded_out_of_stock) == expected["n_excluded_out_of_stock"]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
def test_scenario(scenario):
    lines, baskets = _run(scenario)

    if "expect_n_lines" in scenario:
        assert len(lines) == scenario["expect_n_lines"]

    if "expect_lines" in scenario:
        store_id = next(iter(scenario["candidates"]), None)
        if store_id is None:
            # No store at all: resolve the lines with an empty candidate list so
            # a duplicate-resolution-only scenario still asserts its states.
            resolutions = [basket.resolve_line(l, [], ACCEPT, REVIEW) for l in lines]
        else:
            resolutions = baskets[str(store_id)].resolutions
        assert len(resolutions) == len(scenario["expect_lines"])
        for resolution, expected in zip(resolutions, scenario["expect_lines"]):
            _check_line(resolution, expected)

    if "expect_total_cents" in scenario:
        store_id = next(iter(scenario["candidates"]), None)
        total = baskets[str(store_id)].total_cents if store_id else None
        assert total == scenario["expect_total_cents"]

    if "expect_unverified_lines" in scenario:
        store_id = next(iter(scenario["candidates"]))
        assert baskets[store_id].n_unverified == scenario["expect_unverified_lines"]

    if "expect_totals" in scenario:
        for store_id, expected_total in scenario["expect_totals"].items():
            assert baskets[store_id].total_cents == expected_total

    if "expect_winners" in scenario or "expect_incomplete" in scenario:
        comparison = basket.compare_stores(baskets.values())
        if "expect_winners" in scenario:
            assert sorted(b.store_id for b in comparison["winners"]) == sorted(
                str(s) for s in scenario["expect_winners"])
        if "expect_is_tie" in scenario:
            assert comparison["is_tie"] == scenario["expect_is_tie"]
        if "expect_incomplete" in scenario:
            assert sorted(b.store_id for b in comparison["incomplete"]) == sorted(
                str(s) for s in scenario["expect_incomplete"])
        if "expect_no_winner_reason" in scenario:
            assert comparison["no_winner_reason"] == scenario["expect_no_winner_reason"]

    if "override" in scenario:
        store_id = next(iter(scenario["candidates"]))
        before = baskets[store_id].resolutions[0]
        _check_line(before, scenario["expect_before"])
        after = basket.apply_override(before, _candidate(store_id, {**scenario["override"],
                                                                    "score": 1.0}))
        _check_line(after, scenario["expect_after"])
        assert after.overridden


# --- properties of the suite itself ------------------------------------------

def test_the_suite_meets_the_plans_minimum():
    assert len(SCENARIOS) >= 20


def test_every_scenario_shows_its_hand_arithmetic():
    """A scenario without written-out arithmetic is indistinguishable from one
    whose expectation was copied from a run."""
    for s in SCENARIOS:
        assert s["hand_calculation"].strip(), s["id"]


def test_every_named_category_is_covered():
    """The six PROJECT_PLAN.md names, plus the states Checkpoint 4 measured."""
    categories = " | ".join(s["category"] for s in SCENARIOS).lower()
    for required in ("multipack", "tie", "missing product", "unknown package size",
                     "duplicate entries", "incompatible units",
                     "review band", "out of stock", "unverified", "override"):
        assert required in categories, required


def test_every_product_is_a_real_catalog_row():
    """No invented products or prices: every (store_id, product_id) cited must
    exist in the frozen catalog at exactly the price the scenario claims."""
    import pandas as pd
    catalog = pd.read_csv(basket.__dict__.get("_CATALOG_PATH")
                          or Path(__file__).resolve().parent / "benchmark_catalog_frozen.csv",
                          usecols=["store_id", "product_id", "price_cents"])
    real = {(str(r.store_id), str(r.product_id)): int(r.price_cents)
            for r in catalog.itertuples()}
    checked = 0
    for s in SCENARIOS:
        for store_id, specs in s["candidates"].items():
            for spec in _flatten(specs):
                product_id = str(spec["product_id"])
                if product_id.startswith("SYNTHETIC-"):
                    continue          # declared as synthetic in the file's provenance
                key = (str(store_id), product_id)
                assert key in real, (s["id"], key, "not a catalog row and not marked SYNTHETIC-")
                assert real[key] == spec["price_cents"], (s["id"], key)
                checked += 1
    assert checked >= 15, f"only {checked} scenario products matched the real catalog"


def test_scenario_ids_are_unique():
    ids = [s["id"] for s in SCENARIOS]
    assert len(ids) == len(set(ids))
