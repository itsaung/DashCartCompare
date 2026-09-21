#!/usr/bin/env python3
"""Checkpoint 4, S6: tune an acceptance threshold AND a review band, dev only.

E6 tuned a single cutoff for one baseline. Checkpoint 4 needs two cut points,
and needs them per baseline family, because the three families' scores are not
on a common scale at all:

    TF-IDF cosine          a correct generic match tops out near 0.40,
                           an exact-brand match reaches 1.00
    embedding cosine       compressed into a much narrower high band
    RRF                    ~0.03 for a top result, by construction

benchmark_config.MIN_SIMILARITY (0.65) applies to none of them and is left
untouched. So is v1's and v2's output.

THREE-WAY OUTCOME, for a top-1 score s:
    s >= ACCEPT            automatic match
    REVIEW <= s < ACCEPT   review band: candidates shown, no automatic answer
    s <  REVIEW            no match

COST, per included dev request, averaged. Extends E6's 0/1/2 with one new
outcome:
    0    an acceptable automatic match, or a correct abstention on a
         true-unanswerable request
    0.5  deferred to review, on ANY request. Not free -- it costs the user
         attention and is a match the system could not make -- but cheaper
         than a confident wrong answer and cheaper than silently abstaining on
         an answerable request, because the user is shown candidates and can
         resolve it in one step. Deferring on a genuinely unanswerable request
         is mildly wasteful rather than correct, which is why it is not 0.
    1    abstaining outright on a true-answerable request
    2    an incorrect automatic match, an automatic match on a
         true-unanswerable request, or an unresolved best-guess top-1

The 0.5 is a DECLARED DESIGN PREFERENCE, not an estimate of anything measured.
It encodes "one wrong automatic grocery match costs about four review
deferrals." The sweep is also run at 0.25 and 0.75 as a pre-declared
sensitivity check and all three selections are reported; the 0.5 run is the one
that selects, chosen in advance.

Requests excluded from tuning (count disclosed): the dev no_acceptable_match
requests whose own E1 NO_MATCH_AUDIT confidence is not "confirmed" or
"confirmed by construction" -- tuning against a ground-truth label E1 itself
flagged as unverified would make the chosen cut points no more trustworthy
than that flag. Same rule and same requests as E6.

Usage:
    .venv/bin/python tune_threshold_v3.py
"""
import json
from pathlib import Path

import evaluation_metrics as em
import evaluation_metrics_v3 as v3
from build_benchmark import NO_MATCH_AUDIT

HERE = Path(__file__).resolve().parent
V1_DIR = HERE / "evaluation"
OUT_DIR = HERE / "evaluation_v3"
CONFIG_PATH = HERE / "checkpoint4_config.py"

RESOLVED_CONFIDENCES = {"confirmed", "confirmed by construction"}

# Declared before any cost is computed. The 0.5 run selects.
REVIEW_COSTS = (0.5, 0.25, 0.75)
SELECTING_REVIEW_COST = 0.5

# Grid resolution per family. The grid VALUES are derived from each family's
# own dev score quantiles (below) rather than hardcoded, because a 0.00-0.80
# grid copied from E6 would put every RRF score in one bucket. Deriving a grid
# from dev scores is itself a use of dev data; that is permitted -- dev is the
# tuning split -- and is stated in the report.
GRID_POINTS = 17


def excluded_request_ids(splits, request_answerability) -> list:
    out = []
    for rid, answerability in request_answerability.items():
        if splits.get(rid) != "dev" or answerability != "no_acceptable_match":
            continue
        entry = NO_MATCH_AUDIT.get(rid)
        confidence = (entry or {}).get("confidence", "")
        if confidence not in RESOLVED_CONFIDENCES:
            out.append(rid)
    return sorted(out)


def apply_cut_points(record: dict, accept: float, review: float) -> str:
    """The three-way outcome for one pre-threshold record.

    Returns "accept", "review" or "no_match". A record whose response was
    already needs_clarification or no_acceptable_match keeps that meaning:
    a parser gate or an empty candidate list is not something a score
    threshold can overturn.
    """
    if record["response"] == "needs_clarification":
        return "review"
    if record["response"] != "answerable" or not record["results"]:
        return "no_match"

    score = record["results"][0]["score"]
    if score >= accept:
        return "accept"
    if score >= review:
        return "review"
    return "no_match"


def request_cost(record: dict, outcome: str, true_answerability: str, lookup: dict,
                 review_cost: float) -> float:
    if outcome == "review":
        return review_cost

    returned = outcome == "accept"

    if true_answerability != "answerable":
        return 0.0 if not returned else 2.0

    if not returned:
        return 1.0

    top1 = record["results"][0]
    key = em._pair_key(record["request_id"], top1["store_id"], top1["product_id"])
    entry = lookup.get(key)
    if entry is None:
        raise KeyError(f"no label for top-1 result {key} -- label lookup is incomplete")
    return 0.0 if entry["conservative"] == "Acceptable" else 2.0


def grid_for(dev_records: dict, included_ids: list) -> list:
    """A family's grid, from its own dev top-1 score distribution.

    Spans min..max of the observed top-1 scores in GRID_POINTS steps, so the
    sweep has comparable resolution whatever the underlying scale. 0.0 is
    always included so "no floor at all" is on the grid.
    """
    scores = [
        r["results"][0]["score"]
        for rid, r in dev_records.items()
        if rid in included_ids and r["response"] == "answerable" and r["results"]
    ]
    if not scores:
        return [0.0]
    lo, hi = min(scores), max(scores)
    step = (hi - lo) / (GRID_POINTS - 1) if hi > lo else 0.0
    grid = sorted({0.0} | {round(lo + i * step, 6) for i in range(GRID_POINTS)})
    return grid


def sweep(dev_records: dict, true_answerability: dict, lookup: dict, included_ids: list,
          grid: list, review_cost: float) -> list:
    surface = []
    for accept in grid:
        for review in grid:
            if review > accept:
                continue
            counts = {"accept": 0, "review": 0, "no_match": 0}
            total = 0.0
            confirmed_correct = 0
            for rid in included_ids:
                record = dev_records.get(rid)
                if record is None:
                    continue
                outcome = apply_cut_points(record, accept, review)
                counts[outcome] += 1
                cost = request_cost(record, outcome, true_answerability[rid], lookup, review_cost)
                total += cost
                if outcome == "accept" and cost == 0.0 and true_answerability[rid] == "answerable":
                    confirmed_correct += 1
            n = sum(counts.values())
            surface.append({
                "accept_threshold": accept,
                "review_floor": review,
                "avg_cost": total / n if n else None,
                "n": n,
                "outcomes": counts,
                "confirmed_correct_accepts": confirmed_correct,
            })
    return surface


def select(surface: list) -> dict:
    """Lowest average cost. Ties broken by more confirmed-correct automatic
    matches, then a narrower review band, then a lower accept threshold.
    Declared before the sweep ran."""
    return min(surface, key=lambda p: (
        p["avg_cost"],
        -p["confirmed_correct_accepts"],
        p["accept_threshold"] - p["review_floor"],
        p["accept_threshold"],
    ))


def main():
    requests = json.loads((V1_DIR / "benchmark_requests.json").read_text())
    splits = json.loads((V1_DIR / "splits.json").read_text())["request_split"]
    predictions = [json.loads(line) for line in open(OUT_DIR / "predictions.jsonl")]
    lookup = v3.load_merged_label_lookup()
    request_answerability = {r["request_id"]: r["answerability"] for r in requests}

    excluded = excluded_request_ids(splits, request_answerability)
    dev_ids = [rid for rid, s in splits.items() if s == "dev"]
    included_ids = [rid for rid in dev_ids if rid not in excluded]

    families = sorted({r["baseline"] for r in predictions})
    report = {
        "grid_points": GRID_POINTS,
        "review_costs_swept": list(REVIEW_COSTS),
        "selecting_review_cost": SELECTING_REVIEW_COST,
        "excluded_dev_request_ids": excluded,
        "n_dev_requests": len(dev_ids),
        "n_included": len(included_ids),
        "tie_break": "min avg_cost, then more confirmed-correct accepts, then narrower band, "
                     "then lower accept threshold",
        "families": {},
    }

    for family in families:
        dev_records = {
            r["request_id"]: r
            for r in predictions
            if r["baseline"] == family and r["experiment"] == "full_catalog"
            and splits.get(r["request_id"]) == "dev"
        }
        grid = grid_for(dev_records, included_ids)

        by_cost = {}
        for review_cost in REVIEW_COSTS:
            surface = sweep(dev_records, request_answerability, lookup, included_ids,
                            grid, review_cost)
            chosen = select(surface)
            by_cost[str(review_cost)] = {
                "chosen": chosen,
                "surface": surface if review_cost == SELECTING_REVIEW_COST else None,
            }

        selected = by_cost[str(SELECTING_REVIEW_COST)]["chosen"]

        def _same_as_selected(rc):
            c = by_cost[str(rc)]["chosen"]
            return (c["accept_threshold"] == selected["accept_threshold"]
                    and c["review_floor"] == selected["review_floor"])

        # A boolean over all three is too coarse to be useful -- it hides
        # whether one outlier disagrees or all of them do. Report which.
        agreeing = [rc for rc in REVIEW_COSTS if _same_as_selected(rc)]
        report["families"][family] = {
            "grid": grid,
            "score_range_dev": [grid[1] if len(grid) > 1 else 0.0, grid[-1]],
            "by_review_cost": by_cost,
            "selected": selected,
            "review_costs_agreeing_with_selection": agreeing,
            "sensitivity_note": (
                "the selected pair is stable across all swept review costs"
                if len(agreeing) == len(REVIEW_COSTS) else
                f"the selected pair holds for review cost(s) {agreeing} but not "
                f"{[rc for rc in REVIEW_COSTS if rc not in agreeing]} -- the 0.5 "
                "choice is load-bearing and has no measured basis"
            ),
            "validation_inspection": None,
        }

        print(f"\n{family}")
        print(f"  grid {grid[1]:.4f} .. {grid[-1]:.4f} ({len(grid)} points)")
        for rc in REVIEW_COSTS:
            c = by_cost[str(rc)]["chosen"]
            mark = " <- selects" if rc == SELECTING_REVIEW_COST else ""
            print(f"  review_cost {rc}: accept {c['accept_threshold']:.4f} "
                  f"review {c['review_floor']:.4f} avg_cost {c['avg_cost']:.4f} "
                  f"{c['outcomes']}{mark}")
        print(f"  selection holds at review cost(s): "
              f"{report['families'][family]['review_costs_agreeing_with_selection']}")

    # One-time validation inspection, informational only. Never fed back into
    # selection -- the cut points above are already fixed by the time this
    # runs. Same discipline E6 followed.
    print("\nValidation inspection at the dev-selected cut points "
          "(informational, not used to select):")
    for family in families:
        sel = report["families"][family]["selected"]
        val_records = {
            r["request_id"]: r
            for r in predictions
            if r["baseline"] == family and r["experiment"] == "full_catalog"
            and splits.get(r["request_id"]) == "validation"
        }
        counts = {"accept": 0, "review": 0, "no_match": 0}
        total = 0.0
        for rid, record in val_records.items():
            outcome = apply_cut_points(record, sel["accept_threshold"], sel["review_floor"])
            counts[outcome] += 1
            total += request_cost(record, outcome, request_answerability[rid], lookup,
                                  SELECTING_REVIEW_COST)
        avg = total / len(val_records) if val_records else None
        report["families"][family]["validation_inspection"] = {
            "avg_cost": avg, "n": len(val_records), "outcomes": counts,
        }
        print(f"  {family:30} dev {sel['avg_cost']:.4f} vs validation {avg:.4f}  {counts}")

    (OUT_DIR / "threshold_selection.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nWrote {OUT_DIR / 'threshold_selection.json'}")
    print(f"Included {len(included_ids)}/{len(dev_ids)} dev requests "
          f"(excluded {excluded or 'none'})")


if __name__ == "__main__":
    main()
