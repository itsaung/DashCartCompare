#!/usr/bin/env python3
"""Checkpoint 3 evaluation, Checkpoint E2: freeze grouped dev/validation/test
splits over the 150 requests exported by Checkpoint E1.

Reads evaluation/benchmark_requests.json (not benchmark_requests.py directly)
-- E2 only ever operates on E1's already-validated, already-frozen export, so
a splits.json can never exist without a passing validation behind it.

Assignment rule (approximately 90/30/30 by request count, groups preserved
over exact ratios):
  1. Every pilot paraphrase_group (is_pilot on any member) is pinned to dev,
     unconditionally -- these requests, and everything that paraphrases them,
     shaped LABELING_GUIDELINES.md itself and are never eligible for held-out
     evaluation.
  2. Cross-group reference-product overlap (a "flexible" request and an
     "exact" request that happen to accept the same product) is documented,
     not merged -- a shared product does not make two differently-scoped
     requests the same intent (see EVALUATION_PLAN.md Checkpoint E2, steps
     3-4). build_benchmark.py's own validation already confirmed no group
     needs merging on stronger grounds (no duplicate request text, no
     inconsistent matching_mode/answerability within a group).
  3. Remaining non-pilot groups are assigned with a seeded, deterministic
     greedy: each group (visited in a `random.Random(RANDOM_SEED)`-shuffled
     order over a sorted group-id list, so re-runs are identical) goes to
     whichever split has the largest remaining quota slack; ties are broken
     toward whichever split's exact/flexible composition most needs this
     group's mode, then by split name order. This is a best-effort balance,
     not an exact guarantee -- EVALUATION_PLAN.md only asks that it be
     "balanced ... where feasible".

Outputs: evaluation/splits.json, evaluation/run_manifest.json.

Usage:
    python3 build_splits.py
"""
import hashlib
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import benchmark_config as cfg
from build_benchmark import LABELING_GUIDELINE_VERSION, PILOT_REQUEST_IDS

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "evaluation"
REQUESTS_PATH = OUT_DIR / "benchmark_requests.json"
PAIRS_PATH = OUT_DIR / "benchmark_pairs.jsonl"
MANIFEST_PATH = HERE / "benchmark_manifest.json"

SPLITS = ("dev", "validation", "test")


def _sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def group_requests(requests: list) -> dict:
    groups = defaultdict(list)
    for r in requests:
        groups[r["paraphrase_group"]].append(r)
    return dict(groups)


def audit_cross_group_overlaps(groups: dict) -> list:
    """Non-pilot groups whose full reference_product_id set exactly matches
    another group's. Documented for the report, never merged."""
    by_refset = defaultdict(list)
    for g, members in groups.items():
        refset = frozenset(tuple(p) for m in members for p in m["reference_product_ids"])
        if refset:
            by_refset[refset].append(g)
    overlaps = []
    for refset, gs in by_refset.items():
        if len(gs) > 1:
            overlaps.append({
                "groups": sorted(gs),
                "request_ids": sorted(m["request_id"] for g in gs for m in groups[g]),
                "shared_reference_product_ids": sorted([list(p) for p in refset]),
            })
    return sorted(overlaps, key=lambda o: o["groups"])


def assign_splits(requests: list) -> dict:
    """Returns {"group_split": {group: split}, "request_split": {request_id: split},
    "counts": {...}, "target": {...}}."""
    groups = group_requests(requests)

    pilot_groups = sorted({g for g, members in groups.items()
                            if any(m["request_id"] in PILOT_REQUEST_IDS for m in members)})
    non_pilot_groups = sorted(g for g in groups if g not in set(pilot_groups))

    total_requests = len(requests)
    target = {
        "dev": round(cfg.SPLIT_RATIOS["dev"] * total_requests),
        "validation": round(cfg.SPLIT_RATIOS["validation"] * total_requests),
    }
    target["test"] = total_requests - target["dev"] - target["validation"]

    group_split = {g: "dev" for g in pilot_groups}
    counts = {"dev": 0, "validation": 0, "test": 0}
    exact_count = {"dev": 0, "validation": 0, "test": 0}
    flexible_count = {"dev": 0, "validation": 0, "test": 0}

    def _tally(split, members):
        counts[split] += len(members)
        for m in members:
            if m["matching_mode"] == "exact":
                exact_count[split] += 1
            elif m["matching_mode"] == "flexible":
                flexible_count[split] += 1

    for g in pilot_groups:
        _tally("dev", groups[g])

    rng = random.Random(cfg.RANDOM_SEED)
    shuffled = non_pilot_groups[:]  # sorted() above makes this reproducible before shuffling
    rng.shuffle(shuffled)

    for g in shuffled:
        members = groups[g]
        slack = {s: target[s] - counts[s] for s in SPLITS}
        max_slack = max(slack.values())
        candidates = [s for s in SPLITS if slack[s] == max_slack]

        if len(candidates) > 1:
            group_is_exact = all(m["matching_mode"] == "exact" for m in members)
            group_is_flexible = all(m["matching_mode"] == "flexible" for m in members)
            if group_is_exact:
                candidates.sort(key=lambda s: exact_count[s] / max(counts[s], 1))
            elif group_is_flexible:
                candidates.sort(key=lambda s: flexible_count[s] / max(counts[s], 1))

        chosen = candidates[0]
        group_split[g] = chosen
        _tally(chosen, members)

    request_split = {m["request_id"]: group_split[g] for g, members in groups.items() for m in members}

    return {
        "group_split": group_split,
        "request_split": request_split,
        "counts": counts,
        "target": target,
        "pilot_groups": pilot_groups,
        "exact_count_by_split": exact_count,
        "flexible_count_by_split": flexible_count,
    }


def check_invariants(assignment: dict, groups: dict) -> list:
    """Returns a list of violation strings (empty means clean). These are
    invariants of the assignment algorithm itself, not external data
    checks -- a non-empty result means a bug in assign_splits, not bad
    input data."""
    violations = []

    for g in assignment["pilot_groups"]:
        if assignment["group_split"][g] != "dev":
            violations.append(f"pilot group {g} not assigned to dev")

    for g, split in assignment["group_split"].items():
        member_splits = {assignment["request_split"][m["request_id"]] for m in groups[g]}
        if member_splits != {split}:
            violations.append(f"group {g} has members in more than one split: {member_splits}")

    if sum(assignment["counts"].values()) != sum(len(m) for m in groups.values()):
        violations.append("total assigned request count does not match total request count")

    return violations


def main():
    if not REQUESTS_PATH.exists():
        raise SystemExit(f"{REQUESTS_PATH} missing -- run build_benchmark.py first (Checkpoint E1)")

    requests = json.loads(REQUESTS_PATH.read_text())
    groups = group_requests(requests)

    assignment = assign_splits(requests)
    violations = check_invariants(assignment, groups)
    if violations:
        raise SystemExit(f"build_splits.py produced an invalid assignment: {violations}")

    # Determinism check: re-running assign_splits from the same input must
    # produce byte-identical output (Checkpoint E2's pass criterion).
    repeat = assign_splits(requests)
    if repeat["request_split"] != assignment["request_split"]:
        raise SystemExit("assign_splits is not deterministic -- repeat build produced a different assignment")

    overlaps = audit_cross_group_overlaps(groups)

    splits_out = {
        "seed": cfg.RANDOM_SEED,
        "split_ratios_target": cfg.SPLIT_RATIOS,
        "target_counts": assignment["target"],
        "actual_counts": assignment["counts"],
        "pilot_groups": assignment["pilot_groups"],
        "group_split": assignment["group_split"],
        "request_split": assignment["request_split"],
        "exact_count_by_split": assignment["exact_count_by_split"],
        "flexible_count_by_split": assignment["flexible_count_by_split"],
        "cross_group_reference_overlaps": overlaps,
    }
    (OUT_DIR / "splits.json").write_text(json.dumps(splits_out, indent=2))

    manifest = json.loads(MANIFEST_PATH.read_text())
    run_manifest = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ"),
        "catalog_version_sha256": manifest.get("catalog_version", {}).get("sha256"),
        "labeling_guideline_version": LABELING_GUIDELINE_VERSION,
        "random_seed": cfg.RANDOM_SEED,
        "split_ratios_target": cfg.SPLIT_RATIOS,
        "split_counts": assignment["counts"],
        "cross_group_overlap_count": len(overlaps),
        "benchmark_requests_sha256": _sha256_bytes(REQUESTS_PATH),
        "benchmark_pairs_sha256": _sha256_bytes(PAIRS_PATH),
        "splits_sha256": hashlib.sha256((OUT_DIR / "splits.json").read_bytes()).hexdigest(),
    }
    (OUT_DIR / "run_manifest.json").write_text(json.dumps(run_manifest, indent=2))

    print(f"Assigned {len(groups)} groups ({len(assignment['pilot_groups'])} pilot) -> "
          f"dev={assignment['counts']['dev']} validation={assignment['counts']['validation']} "
          f"test={assignment['counts']['test']} (target {assignment['target']})")
    print(f"Cross-group reference overlaps documented (not merged): {len(overlaps)}")
    print(f"Wrote {OUT_DIR / 'splits.json'}")
    print(f"Wrote {OUT_DIR / 'run_manifest.json'}")


if __name__ == "__main__":
    main()
