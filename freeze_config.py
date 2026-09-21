#!/usr/bin/env python3
"""Checkpoint 4, S7 step 2: freeze the shipped configuration BEFORE the test
split is scored.

The selection rule, declared in CHECKPOINT_4_PLAN.md S7 and in PROJECT_PLAN.md,
is: dev is where all analysis happens, validation arbitrates between methods,
test is a one-time check of the acceptance criterion. This script writes down
what validation selected, along with everything needed to reproduce it -- the
pinned model revision, both cut points, the fusion constants, the identity
extraction version and the code SHA -- and that file is committed before
final_evaluation.py is ever pointed at test.

The commit is the control. If the selection here were revised after a test
number were seen, git history would show it.

Usage:
    .venv/bin/python freeze_config.py
"""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import checkpoint4_config as cfg
import embed_catalog
import product_identity
import retrieval

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "evaluation_v3"
FROZEN_PATH = OUT_DIR / "frozen_config.json"

# The four candidates CHECKPOINT_4_PLAN.md S7 step 2 allows, plus `embed`,
# which S4 measured and S6 tuned.
#
# Validation selects. At the dev-tuned cut points the one-time validation
# inspection recorded in threshold_selection.json gives:
#
#     embed_dimension_size_filter    0.1833   <- selected
#     hybrid_dimension_size_filter   0.1833
#     hybrid_identity_filter         0.2833
#     embed                          0.3167
#     tfidf_dimension_size_filter    0.3167   (the incumbent)
#
# The top two TIE, on cost and on outcome split (23 accept / 3 review /
# 4 no_match each), and S5 already found them tied on validation Success@1
# (92.0%, 23/25 each). The tie-break is the plan's own "simplest method with
# the best validation tradeoff": the embedding baseline is one retriever
# rather than two plus a fusion step, and is ~12x faster (421 ms median vs
# 4,904 ms). Hybrid's only advantage is on dev, which is the split it was
# tuned on -- that advantage failed to reproduce on validation twice, on two
# different metrics.
SELECTED_BASELINE = "embed_dimension_size_filter"

SELECTION_RATIONALE = (
    "Validation selects. embed_dimension_size_filter and hybrid_dimension_size_filter "
    "tie on validation average cost (0.1833) with identical outcome splits "
    "(23 accept / 3 review / 4 no_match), and S5 found them tied on validation "
    "Success@1 (92.0%, 23/25). The tie is broken by the pre-declared preference for "
    "the simpler method: one retriever instead of two plus fusion, and ~12x lower "
    "latency (421 ms vs 4,904 ms median). Hybrid leads only on dev, the split its "
    "cut points were tuned on, and that lead did not reproduce on validation on "
    "either metric. The incumbent tfidf_dimension_size_filter is beaten on "
    "validation cost (0.3167 vs 0.1833) once it is given cut points from the same "
    "dev-only sweep."
)


def code_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE,
                          capture_output=True, text=True, check=True).stdout.strip()


def git_is_clean() -> bool:
    out = subprocess.run(["git", "status", "--porcelain"], cwd=HERE,
                         capture_output=True, text=True, check=True).stdout
    return not out.strip()


def build() -> dict:
    manifest = json.loads((OUT_DIR / "model_manifest.json").read_text())
    accept, review = cfg.cut_points_for(SELECTED_BASELINE)
    entry = cfg.CUT_POINTS[SELECTED_BASELINE]
    return {
        "frozen_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "selected_baseline": SELECTED_BASELINE,
        "selection_rationale": SELECTION_RATIONALE,
        "selected_on_split": "validation",
        "validation_avg_cost": entry["validation_avg_cost"],
        "dev_avg_cost": entry["dev_avg_cost"],
        "cut_points": {"accept_threshold": accept, "review_floor": review},
        "cut_points_tuned_on": "dev only, 88 of 90 requests (r052, r129 excluded)",
        "fusion_constants": {
            # Recorded even though the selected baseline does not fuse -- the
            # frozen config has to reproduce the comparison, not just the winner.
            "hybrid_retriever_depth": cfg.HYBRID_RETRIEVER_DEPTH,
            "rrf_k": cfg.RRF_K,
        },
        "model": {
            "model_id": manifest["model_id"],
            "model_revision": manifest["model_revision"],
            "dimension": manifest["dimension"],
            "max_seq_length": manifest["max_seq_length"],
            "device": manifest["device"],
            "package_versions": manifest["package_versions"],
        },
        "versions": {
            "identity_extraction": product_identity.IDENTITY_VERSION,
            "text_construction": retrieval.TEXT_CONSTRUCTION_VERSION,
            "embed_construction": embed_catalog.EMBED_CONSTRUCTION_VERSION,
        },
        "catalog": {
            "rows": manifest["catalog_rows"],
            "sha256": manifest["catalog_sha256"],
        },
        "code_sha": code_sha(),
        "working_tree_clean_at_freeze": git_is_clean(),
        "test_split_status": "untouched at time of freeze",
        "note": (
            "Committed before final_evaluation.py was pointed at the test split. "
            "Any later change to the selection above is visible in git history as a "
            "commit after this one."
        ),
    }


def main():
    OUT_DIR.mkdir(exist_ok=True)
    config = build()
    FROZEN_PATH.write_text(json.dumps(config, indent=2) + "\n")
    print(f"Wrote {FROZEN_PATH}")
    print(f"  selected: {config['selected_baseline']}")
    print(f"  accept {config['cut_points']['accept_threshold']:.5f} / "
          f"review floor {config['cut_points']['review_floor']:.5f}")
    print(f"  code SHA {config['code_sha']} "
          f"({'clean' if config['working_tree_clean_at_freeze'] else 'DIRTY tree'})")


if __name__ == "__main__":
    main()
