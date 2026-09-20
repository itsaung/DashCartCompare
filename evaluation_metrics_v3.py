#!/usr/bin/env python3
"""Checkpoint 4, S4: compute the same E5 metrics for the embedding baselines.

Reuses evaluation_metrics.py's pure scoring functions unchanged -- no metric
is reimplemented here, the same rule evaluation_metrics_v2.py followed. The
only differences from v2 are the input directory and that this handles
MORE THAN ONE baseline per predictions file (v2 assumed a single baseline and
read predictions[0]["baseline"]; v3 runs `embed` and
`embed_dimension_size_filter` together).

Label lookup is merged from four sources: v1's pool, v1's 153 additional
judgments, v2's 94 additional judgments, and v3's own additional judgments
once they exist. A pair judged in any earlier round keeps that judgment.

Writes evaluation_v3/metrics.json + evaluation_v3/RESULTS_TABLE.md. Never
touches evaluation/ or evaluation_v2/.

Usage:
    .venv/bin/python evaluation_metrics_v3.py
"""
import json
from collections import defaultdict
from pathlib import Path

import evaluation_metrics as em

HERE = Path(__file__).resolve().parent
V1_DIR = HERE / "evaluation"
V2_DIR = HERE / "evaluation_v2"
OUT_DIR = HERE / "evaluation_v3"
CANDIDATE_POOL_PATH = HERE / "candidate_pool.json"

VIEWS = em.VIEWS


def load_merged_label_lookup() -> dict:
    """v1 pool + v1 additional + v2 additional + v3 additional.

    setdefault, not assignment: an earlier round's judgment for a pair wins,
    so re-running this can never silently relabel something already frozen.
    """
    lookup = em.load_label_lookup(V1_DIR / "benchmark_pairs.jsonl",
                                  V1_DIR / "additional_judgments.json")
    for path in (V2_DIR / "additional_judgments.json", OUT_DIR / "additional_judgments.json"):
        if path.exists():
            for row in json.loads(path.read_text()).values():
                key = em._pair_key(row["request_id"], row["store_id"], row["product_id"])
                lookup.setdefault(key, {
                    "conservative": row["conservative_label"],
                    "practical": row["reviewer_label"],
                    "is_best_guess": bool(row.get("is_best_guess", False)),
                })
    return lookup


def _split_report(split_request_ids, fc_records, pool_records, full_pool, lookup,
                  request_answerability, by_id):
    answerable_ids = {rid for rid in split_request_ids
                      if request_answerability[rid] == "answerable"}
    answerable_records = [r for r in fc_records if r["request_id"] in answerable_ids]

    report = {
        "n_requests": len(split_request_ids),
        "n_answerable": len(answerable_ids),
        "confusion_table": em.confusion_table(fc_records, request_answerability),
        "return_coverage": em.return_coverage(fc_records),
        "false_return_rate_on_unanswerable": em.false_return_rate(fc_records, request_answerability),
        "false_abstention_rate": em.false_abstention_rate(fc_records, request_answerability),
        "views": {},
    }
    for view in VIEWS:
        report["views"][view] = {
            "success_at_1": em.success_at_1(answerable_records, lookup, view),
            "hit_at_5": em.hit_at_5(answerable_records, lookup, view),
            "mrr_at_5": em.mrr_at_5(answerable_records, lookup, view),
            "returned_match_accuracy": em.returned_match_accuracy(
                fc_records, lookup, view, request_answerability),
            "pool_recall_at_5": em.pool_recall_at_5(pool_records, full_pool, lookup, view),
        }
    report["conservative_success_at_1_bounds"] = em.success_at_1_bounds(answerable_records, lookup)
    report["practical_guessed_label_exposure"] = em.guessed_label_exposure(answerable_records, lookup)

    report["by_matching_mode"] = {}
    for mode in ("exact", "flexible"):
        mode_ids = {rid for rid in answerable_ids if by_id[rid]["matching_mode"] == mode}
        mode_records = [r for r in answerable_records if r["request_id"] in mode_ids]
        report["by_matching_mode"][mode] = {
            "n": len(mode_records),
            "success_at_1": em.success_at_1(mode_records, lookup, "practical"),
            "hit_at_5": em.hit_at_5(mode_records, lookup, "practical"),
        }
    return report


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
    splits_present = sorted(set(splits.values()))
    baseline_names = sorted({rec["baseline"] for rec in predictions})

    report = {"baselines": {}}
    for name in baseline_names:
        recs = [r for r in predictions if r["baseline"] == name]
        full_catalog = defaultdict(list)
        pool_by_request = {}
        for rec in recs:
            if rec["experiment"] == "full_catalog":
                full_catalog[splits.get(rec["request_id"])].append(rec)
            elif rec["experiment"] == "pool":
                pool_by_request[rec["request_id"]] = rec

        report["baselines"][name] = {"splits": {}}
        for split in splits_present:
            split_ids = [rid for rid, s in splits.items() if s == split]
            report["baselines"][name]["splits"][split] = _split_report(
                split_ids,
                full_catalog[split],
                [pool_by_request[rid] for rid in split_ids if rid in pool_by_request],
                {rid: full_pool[rid] for rid in split_ids if rid in full_pool},
                lookup, request_answerability, by_id,
            )

        times = sorted(r["elapsed_ms"] for r in recs
                       if r["experiment"] == "full_catalog" and "elapsed_ms" in r)
        report["baselines"][name]["latency_ms"] = {
            "n": len(times),
            "median": times[len(times) // 2] if times else None,
            "p95": times[int(len(times) * 0.95) - 1] if len(times) >= 20 else None,
        }

    (OUT_DIR / "metrics.json").write_text(json.dumps(report, indent=2))
    print(f"Wrote {OUT_DIR / 'metrics.json'}")

    lines = ["# Checkpoint 4 S4 metrics -- embedding baselines", "",
             "Same frozen catalog, requests, pool and splits as v1/v2. "
             "Embedding scores are not comparable to TF-IDF scores; only these metrics are.", ""]
    for name in baseline_names:
        lines.append(f"\n## `{name}`")
        lat = report["baselines"][name]["latency_ms"]
        if lat["median"] is not None:
            lines.append(f"\nFull-catalog latency: median {lat['median']:.1f} ms, "
                         f"p95 {lat['p95']:.1f} ms (n={lat['n']}).")
        for split in splits_present:
            sr = report["baselines"][name]["splits"][split]
            lines.append(f"\n### {split} (n={sr['n_requests']}, answerable n={sr['n_answerable']})\n")
            lines.append("| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 |")
            lines.append("|---|---|---|---|---|")
            for view in VIEWS:
                v = sr["views"][view]
                s1, h5 = v["success_at_1"], v["hit_at_5"]
                mrr, pr = v["mrr_at_5"]["mrr"], v["pool_recall_at_5"]
                s1s = f"{s1['rate']:.1%} ({s1['successes']}/{s1['n']})" if s1["rate"] is not None else "N/A"
                h5s = f"{h5['rate']:.1%} ({h5['hits']}/{h5['n']})" if h5["rate"] is not None else "N/A"
                mrrs = f"{mrr:.3f}" if mrr is not None else "N/A"
                prs = f"{pr['mean_recall']:.1%}" if pr["mean_recall"] is not None else "N/A"
                lines.append(f"| {view} | {s1s} | {h5s} | {mrrs} | {prs} |")
            rc = sr["return_coverage"]["rate"]
            lines.append(
                f"\nReturn coverage {rc:.1%} · "
                f"false return on unanswerable {sr['false_return_rate_on_unanswerable']['rate']} · "
                f"false abstention {sr['false_abstention_rate']['rate']}")
            bm = sr["by_matching_mode"]
            ex, fl = bm["exact"]["success_at_1"], bm["flexible"]["success_at_1"]
            exs = f"{ex['rate']:.1%} ({ex['successes']}/{ex['n']})" if ex["rate"] is not None else "N/A"
            fls = f"{fl['rate']:.1%} ({fl['successes']}/{fl['n']})" if fl["rate"] is not None else "N/A"
            lines.append(f"\nSuccess@1 by mode (practical): exact {exs} · flexible {fls}")

    (OUT_DIR / "RESULTS_TABLE.md").write_text("\n".join(lines) + "\n")
    print(f"Wrote {OUT_DIR / 'RESULTS_TABLE.md'}")


if __name__ == "__main__":
    main()
