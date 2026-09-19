#!/usr/bin/env python3
"""Checkpoint 3 evaluation, Checkpoint E6: tune benchmark_config.MIN_SIMILARITY
on the dev split only, then freeze it.

The grid, cost function, and tie-break are pure (dev_cost, best_threshold)
so they're independently testable against hand-calculated fixtures; main()
does the real run: loads dev-split tfidf_dimension_filter predictions
(already computed by Checkpoint E4, at floor 0.0 -- pre-threshold), derives
what tfidf_dimension_filter_threshold would return at each grid value via
tfidf_baseline.apply_threshold (no re-running retrieval), scores the
development cost curve, picks the minimum, and only THEN edits
benchmark_config.py's MIN_SIMILARITY constant to freeze it.

Cost per dev request (0 lowest, 2 highest), matching the plan exactly:
  0 -- an appropriate acceptable return (true answerable, returned, and the
       top-1's CONSERVATIVE label is Acceptable), or a correct abstention
       on a true-unanswerable request.
  1 -- abstaining on a true-answerable request (false abstention).
  2 -- an incorrect return (true answerable, returned, top-1 not
       Acceptable and not the "unresolved" case below), a return on a
       true-unanswerable request (regardless of whether the candidate is
       loosely compatible -- a response-policy error either way), or an
       "unresolved" top-1 under conservative labels (a best-guess pair
       whose practical label is Acceptable but whose conservative label
       reverted to Needs clarification -- treating this as cost 2 is a
       tuning-time policy choice, not a claim the guessed label is wrong).

Requests are EXCLUDED from tuning (and the count disclosed) when their own
request-level answerability assertion is itself unresolved: specifically,
the no_acceptable_match requests whose Checkpoint E1 NO_MATCH_AUDIT entry
is "pattern-consistent, not independently re-searched" rather than
"confirmed" or "confirmed by construction" -- tuning against a ground-truth
label that E1 itself flagged as not fully verified would make the chosen
threshold no more trustworthy than that flag.

Outputs: evaluation/threshold_selection.json (grid, full development curve,
chosen threshold + tie-break trail, excluded requests, and a one-time
validation-split inspection -- informational only, never fed back into
selection). Freezes benchmark_config.MIN_SIMILARITY in place.

Usage:
    python3 tune_threshold.py
"""
import json
import re
from pathlib import Path

from build_benchmark import NO_MATCH_AUDIT
from tfidf_baseline import apply_threshold

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "evaluation"
CONFIG_PATH = HERE / "benchmark_config.py"

GRID = [round(i * 0.05, 2) for i in range(17)]  # 0.00 .. 0.80 step 0.05

RESOLVED_CONFIDENCES = {"confirmed", "confirmed by construction"}


def excluded_request_ids() -> list:
    """no_acceptable_match requests whose own answerability assertion is
    still unresolved per Checkpoint E1's audit -- see module docstring."""
    return sorted(
        rid for rid, entry in NO_MATCH_AUDIT.items()
        if entry["confidence"] not in RESOLVED_CONFIDENCES
    )


def dev_cost(record: dict, true_answerability: str, lookup: dict) -> int:
    """record: a (possibly threshold-derived) baseline prediction for one
    request: {"request_id", "response", "results"}. lookup: from
    evaluation_metrics.load_label_lookup. Returns the integer cost (see
    module docstring)."""
    returned = record["response"] == "answerable" and bool(record["results"])

    if true_answerability != "answerable":
        return 0 if not returned else 2

    if not returned:
        return 1

    top1 = record["results"][0]
    key = (record["request_id"], int(top1["store_id"]), str(top1["product_id"]))
    entry = lookup.get(key)
    if entry is None:
        # Every full-catalog top-1 in this project is judged by Checkpoint
        # E4 (zero unjudged, confirmed there) -- an unjudged top-1 here
        # would mean the label lookup wasn't built correctly, not a
        # legitimate "unresolved" case, so this is a loud failure.
        raise KeyError(f"no label for top-1 result {key} -- label lookup is incomplete")

    if entry["conservative"] == "Acceptable":
        return 0
    return 2  # confirmed incorrect return, or an unresolved best-guess top-1


def cost_curve_point(threshold: float, dev_records: dict, true_answerability: dict, lookup: dict,
                      included_ids: list) -> dict:
    """dev_records: {request_id: tfidf_dimension_filter pre-threshold record}."""
    costs = {0: 0, 1: 0, 2: 0}
    confirmed_correct_returns = 0
    for rid in included_ids:
        derived = apply_threshold(dev_records[rid], threshold)
        cost = dev_cost(derived, true_answerability[rid], lookup)
        costs[cost] += 1
        if (
            true_answerability[rid] == "answerable"
            and derived["response"] == "answerable"
            and derived["results"]
            and lookup.get((
                rid, int(derived["results"][0]["store_id"]), str(derived["results"][0]["product_id"])
            ), {}).get("conservative") == "Acceptable"
        ):
            confirmed_correct_returns += 1

    n = len(included_ids)
    avg_cost = (costs[0] * 0 + costs[1] * 1 + costs[2] * 2) / n if n else None
    return {
        "threshold": threshold,
        "n": n,
        "avg_cost": avg_cost,
        "cost_0_count": costs[0],
        "cost_1_count": costs[1],
        "cost_2_count": costs[2],
        "confirmed_correct_returns": confirmed_correct_returns,
    }


def best_threshold(curve: list) -> dict:
    """Lowest avg_cost; ties broken by greater confirmed_correct_returns,
    then by lower threshold -- all three keys explicit, regardless of
    `curve`'s own iteration order."""
    return min(curve, key=lambda p: (p["avg_cost"], -p["confirmed_correct_returns"], p["threshold"]))


def freeze_min_similarity(threshold: float):
    """Edits benchmark_config.py's MIN_SIMILARITY constant in place. Only
    ever called after best_threshold() has already chosen a value from a
    dev-only curve -- this function does no tuning of its own."""
    text = CONFIG_PATH.read_text()
    pattern = re.compile(r"^MIN_SIMILARITY = .*$", re.MULTILINE)
    if not pattern.search(text):
        raise RuntimeError(f"MIN_SIMILARITY assignment not found in {CONFIG_PATH}")
    new_text = pattern.sub(
        f"MIN_SIMILARITY = {threshold!r}  # frozen by tune_threshold.py (Checkpoint E6) "
        f"-- see evaluation/threshold_selection.json for the dev-only selection that set this",
        text,
        count=1,
    )
    CONFIG_PATH.write_text(new_text)


def main():
    import evaluation_metrics as em

    requests = json.loads((OUT_DIR / "benchmark_requests.json").read_text())
    splits = json.loads((OUT_DIR / "splits.json").read_text())["request_split"]
    predictions = [json.loads(line) for line in open(OUT_DIR / "predictions.jsonl")]
    lookup = em.load_label_lookup(OUT_DIR / "benchmark_pairs.jsonl", OUT_DIR / "additional_judgments.json")

    true_answerability = {r["request_id"]: r["answerability"] for r in requests}

    def split_dimension_filter_records(split_name):
        return {
            rec["request_id"]: rec for rec in predictions
            if rec["experiment"] == "full_catalog" and rec["baseline"] == "tfidf_dimension_filter"
            and splits.get(rec["request_id"]) == split_name
        }

    dev_records = split_dimension_filter_records("dev")
    excluded = excluded_request_ids()
    excluded_in_dev = [rid for rid in excluded if rid in dev_records]
    included_dev_ids = [rid for rid in dev_records if rid not in excluded]

    curve = [
        cost_curve_point(t, dev_records, true_answerability, lookup, included_dev_ids)
        for t in GRID
    ]
    chosen = best_threshold(curve)
    threshold = chosen["threshold"]

    # One-time validation inspection -- reported, never used to pick `threshold`.
    val_records = split_dimension_filter_records("validation")
    val_included = [rid for rid in val_records if rid not in excluded]
    val_point = cost_curve_point(threshold, val_records, true_answerability, lookup, val_included)

    result = {
        "objective": (
            "minimize mean dev_cost (0=appropriate return/correct abstention, "
            "1=false abstention, 2=incorrect return / return on unanswerable / "
            "unresolved best-guess top-1 under conservative labels), tie-break "
            "by greater confirmed_correct_returns then lower threshold"
        ),
        "grid": GRID,
        "excluded_request_ids": excluded,
        "excluded_from_dev_tuning": excluded_in_dev,
        "excluded_from_dev_tuning_count": len(excluded_in_dev),
        "development_curve": curve,
        "chosen": chosen,
        "chosen_threshold": threshold,
        "validation_inspection": {
            "note": "reported once, informational only -- not used to select the threshold",
            **val_point,
        },
    }

    (OUT_DIR / "threshold_selection.json").write_text(json.dumps(result, indent=2))
    freeze_min_similarity(threshold)

    print(f"Dev grid search over {len(GRID)} thresholds, {len(included_dev_ids)} included dev requests "
          f"({len(excluded_in_dev)} excluded: {excluded_in_dev})")
    print(f"Chosen threshold: {threshold} (avg_cost={chosen['avg_cost']:.4f}, "
          f"confirmed_correct_returns={chosen['confirmed_correct_returns']})")
    print(f"Validation inspection at this threshold: avg_cost={val_point['avg_cost']:.4f} "
          f"over {val_point['n']} requests (informational only)")
    print(f"Wrote {OUT_DIR / 'threshold_selection.json'}")
    print(f"Froze MIN_SIMILARITY={threshold!r} in {CONFIG_PATH}")


if __name__ == "__main__":
    main()
