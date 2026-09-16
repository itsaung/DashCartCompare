import csv
import glob

import pytest

from normalize import CANONICAL_UNIT, convert_amount, extract_modifiers, parse_package_size

# --- Targeted cases -------------------------------------------------------


@pytest.mark.parametrize(
    "raw, dimension, total_amount, canonical_total",
    [
        ("16 oz", "weight", 16.0, 16.0),
        ("0.87 oz", "weight", 0.87, 0.87),
        ("2 lb", "weight", 2.0, 32.0),
        ("100 g", "weight", 100.0, pytest.approx(3.5274, rel=1e-3)),
        ("1 kg", "weight", 1.0, pytest.approx(35.274, rel=1e-3)),
        ("12 fl oz", "volume", 12.0, 12.0),
        ("1 gal", "volume", 1.0, 128.0),
        ("1/2 gal", "volume", 0.5, 64.0),
        ("2.5 gal", "volume", 2.5, 320.0),
        ("750 ml", "volume", 750.0, pytest.approx(25.3605, rel=1e-3)),
        ("1 L", "volume", 1.0, pytest.approx(33.814, rel=1e-3)),
        ("100 ct", "count", 100.0, 100.0),
        ("12 fl oz x 12 ct", "volume", 144.0, 144.0),
        ("4.8 oz x 8 ct", "weight", 38.4, 38.4),
        ("23.7 fl oz x 6 ct", "volume", 142.2, 142.2),
        ("3.75 oz x 2 ct", "weight", 7.5, 7.5),
        # Regression: plural forms accepted by the regex but previously
        # missing from the unit table, which crashed instead of resolving.
        ("1 quarts", "volume", 1.0, 32.0),
        ("2 pints", "volume", 2.0, 32.0),
        ("each", "count", 1.0, 1.0),
        ("3 pk x 56 ct", "count", 168.0, 168.0),
    ],
)
def test_resolved_sizes(raw, dimension, total_amount, canonical_total):
    r = parse_package_size(raw)
    assert not r["unresolved"], r["reason"]
    assert r["dimension"] == dimension
    assert r["total_amount"] == pytest.approx(total_amount, rel=1e-6)
    assert r["canonical_total"] == canonical_total
    assert r["canonical_unit"] == CANONICAL_UNIT[dimension]


@pytest.mark.parametrize(
    "raw, expected_reason_substring, variable_weight",
    [
        ("", "missing", False),
        ("   ", "missing", False),
        ("$5.49/lb", "priced by weight", True),
        ("$13.79/lb", "priced by weight", True),
        ("by pound", "priced by weight", True),
        ("bunch", "unrecognized", False),
        ("L", "apparel", False),
        ("XL", "apparel", False),
        ("Fall 2", "apparel", False),
        ("asdfgh", "unrecognized", False),
        # Regression cases from code review: these used to raise instead of
        # returning an unresolved result.
        ("1/0 oz", "invalid or non-positive", False),
        ("1..2 oz", "invalid or non-positive", False),
        ("0 oz", "invalid or non-positive", False),
        ("0 ct x 5 ct", "invalid or non-positive", False),
    ],
)
def test_unresolved_sizes_are_flagged_not_guessed(raw, expected_reason_substring, variable_weight):
    r = parse_package_size(raw)
    assert r["unresolved"] is True
    assert expected_reason_substring in r["reason"]
    assert r["variable_weight"] is variable_weight
    # An unresolved size must never claim a fixed amount -- that would be
    # silently inventing a size the source data didn't give us.
    assert r["total_amount"] is None
    assert r["canonical_total"] is None


def test_convert_amount_rejects_cross_dimension():
    with pytest.raises(ValueError):
        convert_amount(1, "lb", "fl oz")
    with pytest.raises(ValueError):
        convert_amount(1, "gal", "oz")
    with pytest.raises(ValueError):
        convert_amount(1, "ct", "oz")


def test_convert_amount_same_dimension():
    assert convert_amount(16, "oz", "lb") == pytest.approx(1.0)
    assert convert_amount(1, "gal", "fl oz") == pytest.approx(128.0)
    assert convert_amount(1, "lb", "oz") == pytest.approx(16.0)


def test_oz_and_fl_oz_are_never_conflated():
    weight = parse_package_size("12 oz")
    volume = parse_package_size("12 fl oz")
    assert weight["dimension"] == "weight"
    assert volume["dimension"] == "volume"
    assert weight["canonical_total"] == volume["canonical_total"] == 12.0  # same number
    with pytest.raises(ValueError):
        convert_amount(weight["canonical_total"], "oz", "fl oz")


# --- Modifier extraction ---------------------------------------------------


@pytest.mark.parametrize(
    "text, expected_modifiers, expected_remaining",
    [
        ("organic strawberries", ["organic"], "strawberries"),
        ("large eggs", ["large"], "eggs"),
        ("whole milk", ["whole"], "milk"),
        ("gluten free bread", ["gluten free"], "bread"),
        ("plain yogurt", [], "plain yogurt"),  # "plain" not in vocab: stays, doesn't get invented
    ],
)
def test_extract_modifiers(text, expected_modifiers, expected_remaining):
    modifiers, remaining = extract_modifiers(text)
    assert modifiers == expected_modifiers
    assert remaining == expected_remaining


# --- Full-corpus sweep: no crashes, and unresolved rate stays bounded -----
#
# Row-collecting logic (per-store latest-run selection, and DashMart's
# latest-scraped_at-only filtering) intentionally mirrors coverage_report.py
# rather than reimplementing it differently -- these two files disagreeing
# about what "the current DashMart snapshot" means is exactly the bug this
# was written to catch (see coverage_report.py's latest_snapshot_only).

CSV_GLOBS = [
    "runs/aldi_29631686/*/items.csv",
    "runs/ralphs_35802549/*/items.csv",
    "runs/vons_1742136/*/items.csv",
    "runs/sprouts_24325284/*/items.csv",
]
DASHMART_CSV = "doordash_store_1042759_items.csv"


def _corpus_rows():
    from coverage_report import latest_snapshot_only

    rows = []
    for pattern in CSV_GLOBS:
        matches = sorted(glob.glob(pattern))
        if matches:
            with open(matches[-1], newline="", encoding="utf-8") as f:
                rows.extend(csv.DictReader(f))
    with open(DASHMART_CSV, newline="", encoding="utf-8") as f:
        dashmart_rows, _snapshot_id = latest_snapshot_only(list(csv.DictReader(f)))
    rows.extend(dashmart_rows)
    return rows


def test_full_corpus_parses_without_crashing_and_bounded_unresolved():
    rows = _corpus_rows()
    total = len(rows)
    unresolved = sum(1 for row in rows if parse_package_size(row["unit_size"])["unresolved"])
    assert total > 1000, "expected to actually load real snapshot data"
    rate = unresolved / total
    # Not a target to hit exactly -- a ceiling. If this creeps up, something
    # about real unit_size strings changed and the parser needs a look, not
    # a silently-raised threshold.
    assert rate < 0.35, f"unresolved rate {rate:.1%} exceeds expected ceiling"
