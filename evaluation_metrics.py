#!/usr/bin/env python3
"""Checkpoint 3 evaluation, Checkpoint E5: metrics with explicit
denominators over the predictions Checkpoint E4 produced.

Every scoring function here is pure -- it takes already-shaped small
records and a label lookup, and returns counts alongside rates, never just
a bare percentage, so every number is hand-verifiable against
test_evaluation_metrics.py's fixtures. Loading real data and writing
evaluation/metrics.json is main(), at the bottom.

Two label views throughout, per the plan:
  conservative -- best-guess labels revert to Needs clarification
                  (`conservative_label` in benchmark_pairs.jsonl /
                  additional_judgments.json already encodes this).
  practical    -- the requested binary best-guess labels (`reviewer_label`).

`view` is always an explicit parameter -- nothing here silently defaults to
one or the other.
"""
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "evaluation"
CANDIDATE_POOL_PATH = HERE / "candidate_pool.json"

ANSWERABILITY_VALUES = ("answerable", "needs_clarification", "no_acceptable_match")
VIEWS = ("conservative", "practical")


def _pair_key(request_id, store_id, product_id):
    return (request_id, int(store_id), str(product_id))


def load_label_lookup(pairs_path: Path, additional_judgments_path: Path) -> dict:
    """{(request_id, store_id, product_id): {"conservative": label, "practical": label,
    "is_best_guess": bool}}, merged from the original labeled pool and Checkpoint E4's
    additional judgments on newly-discovered candidates."""
    lookup = {}
    with open(pairs_path) as f:
        for line in f:
            row = json.loads(line)
            key = _pair_key(row["request_id"], row["store_id"], row["product_id"])
            lookup[key] = {
                "conservative": row["conservative_label"],
                "practical": row["reviewer_label"],
                "is_best_guess": bool(row.get("is_best_guess", False)),
            }
    if additional_judgments_path.exists():
        for row in json.loads(additional_judgments_path.read_text()).values():
            key = _pair_key(row["request_id"], row["store_id"], row["product_id"])
            lookup.setdefault(key, {
                "conservative": row["conservative_label"],
                "practical": row["reviewer_label"],
                "is_best_guess": bool(row.get("is_best_guess", False)),
            })
    return lookup


def label_of(lookup: dict, request_id, store_id, product_id, view: str):
    assert view in VIEWS
    entry = lookup.get(_pair_key(request_id, store_id, product_id))
    return entry[view] if entry else None


# --- Success@1 / Hit@5 / MRR@5 (answerable ground-truth requests only) -----

def success_at_1(records: list, lookup: dict, view: str) -> dict:
    """records: one row per evaluated request: {"request_id", "response", "results"}.
    Caller filters to ground-truth-answerable requests before calling --
    N is exactly len(records), made explicit in the return value rather
    than inferred here. Abstention (response != "answerable") or an empty
    result list contributes zero, per the plan, but the request still
    counts toward N."""
    n = len(records)
    successes = 0
    for r in records:
        if r["response"] != "answerable" or not r["results"]:
            continue
        top1 = r["results"][0]
        if label_of(lookup, r["request_id"], top1["store_id"], top1["product_id"], view) == "Acceptable":
            successes += 1
    return {"successes": successes, "n": n, "rate": (successes / n) if n else None}


def hit_at_5(records: list, lookup: dict, view: str) -> dict:
    n = len(records)
    hits = 0
    for r in records:
        if r["response"] != "answerable":
            continue
        for res in r["results"][:5]:
            if label_of(lookup, r["request_id"], res["store_id"], res["product_id"], view) == "Acceptable":
                hits += 1
                break
    return {"hits": hits, "n": n, "rate": (hits / n) if n else None}


def mrr_at_5(records: list, lookup: dict, view: str) -> dict:
    n = len(records)
    total = 0.0
    for r in records:
        if r["response"] != "answerable":
            continue
        for rank, res in enumerate(r["results"][:5], start=1):
            if label_of(lookup, r["request_id"], res["store_id"], res["product_id"], view) == "Acceptable":
                total += 1.0 / rank
                break
    return {"sum_reciprocal_rank": total, "n": n, "mrr": (total / n) if n else None}


# --- Pool Recall@5 -----------------------------------------------------------

def pool_recall_at_5(pool_records: list, full_pool_pairs: dict, lookup: dict, view: str) -> dict:
    """pool_records: one row per request: {"request_id", "results"} (the
    request's own pool, ranked -- top 5 of this list is what's "retrieved").
    full_pool_pairs: {request_id: [(store_id, product_id), ...]} -- the
    COMPLETE pool, independent of what a filtering baseline's `results` may
    have dropped, so the denominator is never silently shrunk by the
    baseline's own gates. Only averaged over pools with at least one known
    positive under `view`; zero-positive pools are reported as N/A, never
    folded into the mean as either a 0 or excluded silently."""
    per_pool_recall = []
    zero_positive_pools = 0
    by_request = {r["request_id"]: r for r in pool_records}

    for request_id, pairs in full_pool_pairs.items():
        positives = [p for p in pairs if label_of(lookup, request_id, p[0], p[1], view) == "Acceptable"]
        if not positives:
            zero_positive_pools += 1
            continue
        rec = by_request.get(request_id, {"results": []})
        top5 = {(res["store_id"], str(res["product_id"])) for res in rec["results"][:5]}
        retrieved = sum(1 for p in positives if (p[0], str(p[1])) in top5)
        per_pool_recall.append(retrieved / len(positives))

    mean_recall = (sum(per_pool_recall) / len(per_pool_recall)) if per_pool_recall else None
    return {
        "mean_recall": mean_recall,
        "n_pools_with_positive": len(per_pool_recall),
        "n_zero_positive_pools": zero_positive_pools,
    }


# --- Abstention / response-policy metrics -----------------------------------

def confusion_table(records: list, request_answerability: dict) -> dict:
    """records: [{"request_id", "response"}]. Rows are ground-truth
    answerability, columns are the baseline's response -- both already
    share the same three-value vocabulary."""
    table = {true: {pred: 0 for pred in ANSWERABILITY_VALUES} for true in ANSWERABILITY_VALUES}
    for r in records:
        true = request_answerability[r["request_id"]]
        table[true][r["response"]] += 1
    return table


def return_coverage(records: list) -> dict:
    n = len(records)
    returned = sum(1 for r in records if r["response"] == "answerable")
    return {"returned": returned, "n": n, "rate": (returned / n) if n else None}


def returned_match_accuracy(records: list, lookup: dict, view: str, request_answerability: dict) -> dict:
    """Denominator is every request that received a match (response ==
    "answerable"), regardless of ground truth -- "requests receiving a
    match," per the plan. The numerator is stricter: a returned match only
    counts as correct when the request's true answerability is itself
    "answerable" AND the top-1 label is Acceptable. Returning on a request
    that needed clarification or had no acceptable match is a response-
    policy error "even if the candidate is loosely compatible" (the plan's
    own words) -- it must never count as a correct returned match just
    because the candidate happens to carry an Acceptable label."""
    returned = [r for r in records if r["response"] == "answerable"]
    n = len(returned)
    correct = 0
    for r in returned:
        if not r["results"]:
            continue
        if request_answerability[r["request_id"]] != "answerable":
            continue
        top1 = r["results"][0]
        if label_of(lookup, r["request_id"], top1["store_id"], top1["product_id"], view) == "Acceptable":
            correct += 1
    return {"correct": correct, "n": n, "rate": (correct / n) if n else None}


def false_return_rate(records: list, request_answerability: dict) -> dict:
    """Requests whose ground truth is needs_clarification/no_acceptable_match
    but that received a match anyway -- a response-policy error regardless
    of whether the returned candidate happens to be loosely compatible."""
    unanswerable = [r for r in records if request_answerability[r["request_id"]] != "answerable"]
    n = len(unanswerable)
    false_returns = sum(1 for r in unanswerable if r["response"] == "answerable")
    return {"false_returns": false_returns, "n": n, "rate": (false_returns / n) if n else None}


def false_abstention_rate(records: list, request_answerability: dict) -> dict:
    answerable = [r for r in records if request_answerability[r["request_id"]] == "answerable"]
    n = len(answerable)
    abstentions = sum(1 for r in answerable if r["response"] != "answerable")
    return {"abstentions": abstentions, "n": n, "rate": (abstentions / n) if n else None}


# --- Conservative bounds -----------------------------------------------------

def success_at_1_bounds(records: list, lookup: dict) -> dict:
    """Conservative-view Success@1, split into confirmed-correct,
    confirmed-incorrect, and unresolved top-one outcomes. Lower bound
    treats unresolved as nonpositive; upper bound treats them as
    potentially acceptable. Unresolved cases are never called confirmed
    errors, and never dropped from the denominator.

    "Unresolved" is any is_best_guess pair, full stop -- regardless of
    which way its practical label points. All 56 best-guess pairs revert
    to a conservative label of Needs clarification (never Acceptable), so
    conservative == "Acceptable" already excludes every guess; anything
    left with is_best_guess=True is a guess whose conservative label
    reverted to Needs clarification specifically because it wasn't
    independently confirmed -- that is unresolved whether the guess itself
    leaned Acceptable (practical) or Incorrect. Treating a guessed-negative
    as a "confirmed incorrect" would be exactly the "unresolved cases...
    called confirmed errors" the plan says not to do; only a genuinely
    non-guess Needs clarification/Incorrect decision is a confirmed error."""
    n = len(records)
    confirmed_correct = confirmed_incorrect = unresolved = 0
    for r in records:
        if r["response"] != "answerable" or not r["results"]:
            continue
        top1 = r["results"][0]
        key = _pair_key(r["request_id"], top1["store_id"], top1["product_id"])
        entry = lookup.get(key)
        if entry is None:
            continue
        if entry["conservative"] == "Acceptable":
            confirmed_correct += 1
        elif entry["is_best_guess"]:
            unresolved += 1
        else:
            confirmed_incorrect += 1

    return {
        "n": n,
        "confirmed_correct": confirmed_correct,
        "confirmed_incorrect": confirmed_incorrect,
        "unresolved": unresolved,
        "lower_bound_rate": (confirmed_correct / n) if n else None,
        "upper_bound_rate": ((confirmed_correct + unresolved) / n) if n else None,
    }


# --- practical-view guess exposure -------------------------------------------

def guessed_label_exposure(records: list, lookup: dict) -> dict:
    """How many of THESE SCORED top-1 predictions touch an is_best_guess
    label -- not the dataset-wide count of guessed labels, which would
    overstate exposure for a metric that only ever looks at one candidate
    per request."""
    touched = 0
    scored = 0
    for r in records:
        if r["response"] != "answerable" or not r["results"]:
            continue
        scored += 1
        top1 = r["results"][0]
        entry = lookup.get(_pair_key(r["request_id"], top1["store_id"], top1["product_id"]))
        if entry and entry["is_best_guess"]:
            touched += 1
    return {"scored_top1_predictions": scored, "touching_a_guessed_label": touched}


def main():
    import time

    requests = json.loads((OUT_DIR / "benchmark_requests.json").read_text())
    splits = json.loads((OUT_DIR / "splits.json").read_text())["request_split"]
    predictions = [json.loads(line) for line in open(OUT_DIR / "predictions.jsonl")]
    lookup = load_label_lookup(OUT_DIR / "benchmark_pairs.jsonl", OUT_DIR / "additional_judgments.json")
    full_pool = {
        p["request_id"]: [(c["store_id"], str(c["product_id"])) for c in p["candidates"]]
        for p in json.loads(CANDIDATE_POOL_PATH.read_text())
    }

    by_id = {r["request_id"]: r for r in requests}
    request_answerability = {r["request_id"]: r["answerability"] for r in requests}

    full_catalog = defaultdict(list)  # (baseline, split) -> records
    pool_by_baseline = defaultdict(list)  # baseline -> records (pool experiment is split-agnostic input; sliced later)

    for rec in predictions:
        split = splits.get(rec["request_id"])
        if rec["experiment"] == "full_catalog":
            full_catalog[(rec["baseline"], split)].append(rec)
        elif rec["experiment"] == "pool":
            pool_by_baseline[rec["baseline"]].append(rec)

    baselines = sorted({rec["baseline"] for rec in predictions})
    splits_present = sorted(set(splits.values()))

    report = {"baselines": {}}

    for baseline in baselines:
        report["baselines"][baseline] = {"splits": {}}

        # pool recall is computed once per baseline (over ALL requests --
        # the pool itself isn't split-scoped in the plan's E5 description),
        # then also broken out per split for the results table.
        pool_records_by_request = {r["request_id"]: r for r in pool_by_baseline[baseline]}

        for split in splits_present:
            split_request_ids = [rid for rid, s in splits.items() if s == split]
            answerable_ids = {rid for rid in split_request_ids if request_answerability[rid] == "answerable"}
            fc_records = full_catalog[(baseline, split)]
            answerable_records = [r for r in fc_records if r["request_id"] in answerable_ids]

            split_pool_records = [pool_records_by_request[rid] for rid in split_request_ids if rid in pool_records_by_request]
            split_full_pool = {rid: full_pool[rid] for rid in split_request_ids if rid in full_pool}

            split_report = {
                "n_requests": len(split_request_ids),
                "n_answerable": len(answerable_ids),
                "confusion_table": confusion_table(fc_records, request_answerability),
                "return_coverage": return_coverage(fc_records),
                "false_return_rate_on_unanswerable": false_return_rate(fc_records, request_answerability),
                "false_abstention_rate": false_abstention_rate(fc_records, request_answerability),
                "views": {},
            }

            for view in VIEWS:
                split_report["views"][view] = {
                    "success_at_1": success_at_1(answerable_records, lookup, view),
                    "hit_at_5": hit_at_5(answerable_records, lookup, view),
                    "mrr_at_5": mrr_at_5(answerable_records, lookup, view),
                    "returned_match_accuracy": returned_match_accuracy(fc_records, lookup, view, request_answerability),
                    "pool_recall_at_5": pool_recall_at_5(split_pool_records, split_full_pool, lookup, view),
                }
            split_report["conservative_success_at_1_bounds"] = success_at_1_bounds(answerable_records, lookup)
            split_report["practical_guessed_label_exposure"] = guessed_label_exposure(answerable_records, lookup)

            # Plan-required exact/flexible breakdown, practical view only --
            # a small-slice sanity check, not a headline number (dev's
            # exact/flexible split alone can be under 30 requests each).
            split_report["by_matching_mode"] = {}
            for mode in ("exact", "flexible"):
                mode_ids = {rid for rid in answerable_ids if by_id[rid]["matching_mode"] == mode}
                mode_records = [r for r in answerable_records if r["request_id"] in mode_ids]
                split_report["by_matching_mode"][mode] = {
                    "success_at_1": success_at_1(mode_records, lookup, "practical"),
                    "hit_at_5": hit_at_5(mode_records, lookup, "practical"),
                }

            report["baselines"][baseline]["splits"][split] = split_report

    # Latency: warm-query median/p95 across the full_catalog experiment's
    # per-request elapsed_ms (excludes model fit/labeling entirely -- this
    # script never fits a model, it only reads already-written predictions).
    for baseline in baselines:
        times = sorted(
            rec["elapsed_ms"] for rec in predictions
            if rec["baseline"] == baseline and rec["experiment"] == "full_catalog"
        )
        if times:
            report["baselines"][baseline]["latency_ms"] = {
                "n": len(times),
                "median": times[len(times) // 2],
                "p95": times[int(len(times) * 0.95) - 1] if len(times) >= 20 else None,
                "note": "p95 omitted below n=20 -- not enough samples for a meaningful tail estimate" if len(times) < 20 else None,
            }

    (OUT_DIR / "metrics.json").write_text(json.dumps(report, indent=2))
    print(f"Wrote {OUT_DIR / 'metrics.json'}")

    lines = ["# Checkpoint 3 baseline metrics (E5)", ""]
    for baseline in baselines:
        lines.append(f"## {baseline}")
        for split in splits_present:
            sr = report["baselines"][baseline]["splits"][split]
            lines.append(f"\n### {split} (n={sr['n_requests']}, answerable n={sr['n_answerable']})\n")
            lines.append("| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 (n pools) |")
            lines.append("|---|---|---|---|---|")
            for view in VIEWS:
                v = sr["views"][view]
                s1 = v["success_at_1"]["rate"]
                h5 = v["hit_at_5"]["rate"]
                mrr = v["mrr_at_5"]["mrr"]
                pr = v["pool_recall_at_5"]
                s1s = f"{s1:.2%} ({v['success_at_1']['successes']}/{v['success_at_1']['n']})" if s1 is not None else "N/A"
                h5s = f"{h5:.2%} ({v['hit_at_5']['hits']}/{v['hit_at_5']['n']})" if h5 is not None else "N/A"
                mrrs = f"{mrr:.3f}" if mrr is not None else "N/A"
                prs = (f"{pr['mean_recall']:.2%} ({pr['n_pools_with_positive']} pools, "
                       f"{pr['n_zero_positive_pools']} N/A)") if pr["mean_recall"] is not None else "N/A"
                lines.append(f"| {view} | {s1s} | {h5s} | {mrrs} | {prs} |")
            lines.append(f"\nReturn coverage: {sr['return_coverage']['rate']:.2%} "
                         f"({sr['return_coverage']['returned']}/{sr['return_coverage']['n']}). "
                         f"False return on unanswerable: {sr['false_return_rate_on_unanswerable']['rate']}. "
                         f"False abstention: {sr['false_abstention_rate']['rate']}.")
        lines.append("")

    (OUT_DIR / "RESULTS_TABLE.md").write_text("\n".join(lines))
    print(f"Wrote {OUT_DIR / 'RESULTS_TABLE.md'}")


if __name__ == "__main__":
    main()
