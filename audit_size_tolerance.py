#!/usr/bin/env python3
"""Audit the original 1,658-pair labeled pool (label_review_decisions.json)
for the same size-tolerance issue found in Checkpoint E4's 153 additional
candidates: an `Acceptable` label whose expected/candidate sizes only agree
within `claude_auto_label.py`'s 3% relative tolerance -- which
LABELING_GUIDELINES.md v2 explicitly rejects as arbitrary -- rather than
being genuinely unit-equivalent (see apply_new_candidate_review.py's
`_size_confirmed_without_arbitrary_tolerance`, reused here directly rather
than re-implemented, per this project's "reuse one already-exercised rule
set" convention).

This only ever reports; it does not relabel anything on its own. If it
finds violations, review them individually before deciding how to act --
the original pool's decisions carry their own provenance chain
(prior_label/prior_reviewed_by/audit_id) that any correction should extend
the same way the 2026-09-18 audits did, not overwrite silently.

Usage:
    python3 audit_size_tolerance.py
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from apply_new_candidate_review import _load_catalog_by_key, _size_confirmed_without_arbitrary_tolerance
from benchmark_requests import REQUESTS

HERE = Path(__file__).resolve().parent
DECISIONS_PATH = HERE / "label_review_decisions.json"
OUT_DIR = HERE / "audit"


def find_size_tolerance_violations(decisions: dict, requests_by_id: dict, catalog_by_key: dict) -> list:
    """Returns a list of dicts, one per Acceptable-labeled pair whose size
    agreement relies on more than unit-equivalent rounding. Skips pairs
    with no expected size, an `allowed_substitutions.size == "any"`
    request, or unparseable/dimension-mismatched sizes (a different
    concern -- dimension mismatches like the ice cream weight/volume
    ambiguity are already tracked separately via dimension_review_flag,
    not by this check)."""
    violations = []
    for key, dec in decisions.items():
        if dec.get("reviewer_label") != "Acceptable":
            continue
        request_id, store_id, product_id = key.split("|")
        request = requests_by_id.get(request_id)
        if request is None:
            continue
        row = catalog_by_key.get((int(store_id), product_id))
        if row is None:
            continue
        if not _size_confirmed_without_arbitrary_tolerance(request, row):
            violations.append({
                "key": key,
                "request_id": request_id,
                "request_text": request["text"],
                "expected_size": request["expected"].get("size"),
                "raw_size": row.get("raw_size"),
                "raw_title": row.get("raw_title"),
                "reviewed_by": dec.get("reviewed_by"),
            })
    return violations


def main():
    decisions = json.loads(DECISIONS_PATH.read_text())
    requests_by_id = {r["request_id"]: r for r in REQUESTS}
    catalog_by_key = _load_catalog_by_key()

    total_acceptable = sum(1 for d in decisions.values() if d.get("reviewer_label") == "Acceptable")
    violations = find_size_tolerance_violations(decisions, requests_by_id, catalog_by_key)

    OUT_DIR.mkdir(exist_ok=True)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    report_path = OUT_DIR / "SIZE_TOLERANCE_AUDIT_2026-09-19.md"

    lines = [
        "# Size-tolerance audit of the original 1,658-pair pool -- 2026-09-19",
        "",
        f"Generated {generated_at}. Checked all {total_acceptable} `Acceptable`-labeled pairs in "
        "`label_review_decisions.json` for the same issue found in Checkpoint E4's 153 additional "
        "candidates: a label that only holds up under `claude_auto_label.py`'s 3% relative size "
        "tolerance, which `LABELING_GUIDELINES.md` v2 explicitly rejects as arbitrary, rather than "
        "genuine unit-equivalent rounding.",
        "",
        f"**Result: {len(violations)} violations found.**",
        "",
    ]
    if violations:
        lines.append("| Request | Expected size | Candidate | Candidate size | Reviewed by |")
        lines.append("|---|---|---|---|---|")
        for v in violations:
            lines.append(
                f"| {v['request_id']} `{v['request_text']}` | {v['expected_size']} | "
                f"{v['raw_title']} | {v['raw_size']} | {v['reviewed_by']} |"
            )
        lines.append("")
        lines.append("These were NOT relabeled by this script -- review individually before acting.")
    else:
        lines.append(
            "Every `Acceptable`-labeled size comparison in the original pool is either an exact "
            "match on the same printed unit, or a genuine cross-unit conversion within a tight "
            "1% rounding tolerance (e.g. 2 L / 67.6 fl oz). The 2026-09-18 complete audit "
            "(`codex_ai_audit`) did not rely on the 3% tolerance for any of its 475 Acceptable "
            "labels -- unlike the later, separate 153-additional-candidate review, which did and "
            "was corrected for it. No action needed here."
        )
    report_path.write_text("\n".join(lines) + "\n")

    evidence_path = OUT_DIR / "size_tolerance_audit_2026-09-19.json"
    evidence_path.write_text(json.dumps({
        "generated_at": generated_at,
        "total_acceptable_checked": total_acceptable,
        "violations": violations,
    }, indent=2))

    print(f"Checked {total_acceptable} Acceptable pairs, found {len(violations)} size-tolerance violations")
    print(f"Wrote {report_path}")
    print(f"Wrote {evidence_path}")


if __name__ == "__main__":
    main()
