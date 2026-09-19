#!/usr/bin/env python3
"""Checkpoint 3.1: compute the same E5 metrics for the new
tfidf_dimension_size_filter baseline, using the exact same pure scoring
functions from evaluation_metrics.py (no reimplementation) -- just pointed
at evaluation_v2/predictions.jsonl and a label lookup merged from three
sources: v1's original pool (evaluation/benchmark_pairs.jsonl), v1's 153
additional judgments (evaluation/additional_judgments.json), and v2's own
94 additional judgments (evaluation_v2/additional_judgments.json).

Writes evaluation_v2/metrics.json + evaluation_v2/RESULTS_TABLE.md --
never touches evaluation/metrics.json, so v1's report stays reproducible
and immutable.

Usage:
    python3 evaluation_metrics_v2.py
"""
import json
from collections import defaultdict
from pathlib import Path

import evaluation_metrics as em

HERE = Path(__file__).resolve().parent
V1_DIR = HERE / "evaluation"
OUT_DIR = HERE / "evaluation_v2"
CANDIDATE_POOL_PATH = HERE / "candidate_pool.json"

VIEWS = em.VIEWS


def load_merged_label_lookup() -> dict:
    lookup = em.load_label_lookup(V1_DIR / "benchmark_pairs.jsonl", V1_DIR / "additional_judgments.json")
    v2_path = OUT_DIR / "additional_judgments.json"
    if v2_path.exists():
        for row in json.loads(v2_path.read_text()).values():
            key = em._pair_key(row["request_id"], row["store_id"], row["product_id"])
            lookup.setdefault(key, {
                "conservative": row["conservative_label"],
                "practical": row["reviewer_label"],
                "is_best_guess": bool(row.get("is_best_guess", False)),
            })
    return lookup


def main():
    requests = json.loads((V1_DIR / "benchmark_requests.json").read_text())
    splits = json.loads((V1_DIR / "splits.json").read_text())["request_split"]
    predictions = [json.loads(line) for line in open(OUT_DIR / "predictions.jsonl")]
    lookup = load_merged_label_lookup()
    full_pool = {
        p["request_id"]: [(c["store_id"], str(c["product_id"])) for c in p["candidates"]]
        for p in json.loads(CANDIDATE_POOL_PATH.read_text())
    }

    request_answerability = {r["request_id"]: r["answerability"] for r in requests}
    by_id = {r["request_id"]: r for r in requests}

    full_catalog = defaultdict(list)
    pool_records_by_request = {}
    for rec in predictions:
        if rec["experiment"] == "full_catalog":
            split = splits.get(rec["request_id"])
            full_catalog[split].append(rec)
        elif rec["experiment"] == "pool":
            pool_records_by_request[rec["request_id"]] = rec

    baseline_name = predictions[0]["baseline"]
    splits_present = sorted(set(splits.values()))

    report = {"baselines": {baseline_name: {"splits": {}}}}

    for split in splits_present:
        split_request_ids = [rid for rid, s in splits.items() if s == split]
        answerable_ids = {rid for rid in split_request_ids if request_answerability[rid] == "answerable"}
        fc_records = full_catalog[split]
        answerable_records = [r for r in fc_records if r["request_id"] in answerable_ids]

        split_pool_records = [pool_records_by_request[rid] for rid in split_request_ids if rid in pool_records_by_request]
        split_full_pool = {rid: full_pool[rid] for rid in split_request_ids if rid in full_pool}

        split_report = {
            "n_requests": len(split_request_ids),
            "n_answerable": len(answerable_ids),
            "confusion_table": em.confusion_table(fc_records, request_answerability),
            "return_coverage": em.return_coverage(fc_records),
            "false_return_rate_on_unanswerable": em.false_return_rate(fc_records, request_answerability),
            "false_abstention_rate": em.false_abstention_rate(fc_records, request_answerability),
            "views": {},
        }
        for view in VIEWS:
            split_report["views"][view] = {
                "success_at_1": em.success_at_1(answerable_records, lookup, view),
                "hit_at_5": em.hit_at_5(answerable_records, lookup, view),
                "mrr_at_5": em.mrr_at_5(answerable_records, lookup, view),
                "returned_match_accuracy": em.returned_match_accuracy(fc_records, lookup, view, request_answerability),
                "pool_recall_at_5": em.pool_recall_at_5(split_pool_records, split_full_pool, lookup, view),
            }
        split_report["conservative_success_at_1_bounds"] = em.success_at_1_bounds(answerable_records, lookup)
        split_report["practical_guessed_label_exposure"] = em.guessed_label_exposure(answerable_records, lookup)

        split_report["by_matching_mode"] = {}
        for mode in ("exact", "flexible"):
            mode_ids = {rid for rid in answerable_ids if by_id[rid]["matching_mode"] == mode}
            mode_records = [r for r in answerable_records if r["request_id"] in mode_ids]
            split_report["by_matching_mode"][mode] = {
                "success_at_1": em.success_at_1(mode_records, lookup, "practical"),
                "hit_at_5": em.hit_at_5(mode_records, lookup, "practical"),
            }

        report["baselines"][baseline_name]["splits"][split] = split_report

    times = sorted(rec["elapsed_ms"] for rec in predictions if rec["experiment"] == "full_catalog")
    report["baselines"][baseline_name]["latency_ms"] = {
        "n": len(times),
        "median": times[len(times) // 2],
        "p95": times[int(len(times) * 0.95) - 1] if len(times) >= 20 else None,
    }

    (OUT_DIR / "metrics.json").write_text(json.dumps(report, indent=2))
    print(f"Wrote {OUT_DIR / 'metrics.json'}")

    lines = [f"# Checkpoint 3.1 metrics -- {baseline_name}", ""]
    for split in splits_present:
        sr = report["baselines"][baseline_name]["splits"][split]
        lines.append(f"\n## {split} (n={sr['n_requests']}, answerable n={sr['n_answerable']})\n")
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
        lines.append(f"\nReturn coverage: {sr['return_coverage']['rate']:.2%}. "
                     f"False return on unanswerable: {sr['false_return_rate_on_unanswerable']['rate']}. "
                     f"False abstention: {sr['false_abstention_rate']['rate']}.")

    (OUT_DIR / "RESULTS_TABLE.md").write_text("\n".join(lines))
    print(f"Wrote {OUT_DIR / 'RESULTS_TABLE.md'}")


if __name__ == "__main__":
    main()
