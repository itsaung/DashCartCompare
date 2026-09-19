"""Apply the explicitly adjudicated 2026-09-18 frozen-pool audit.

This is an audit materializer, not a labeling model. The decisions were made
by reading every candidate. Input hashes prevent positional adjudications
from being reused against a reordered pool or changed catalog/request.
Run without arguments to validate; --apply writes reviewed decisions/report.
"""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from benchmark_requests import REQUESTS, REQUEST_VERSION
from label_review_ui import LABELING_GUIDELINE_VERSION, save_decisions_atomic
from normalize import parse_package_size

HERE = Path(__file__).resolve().parent
AUDIT_ID = "2026-09-18-complete-v2"
AUDIT = HERE / "audit"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_audit():
    manifest = json.loads((AUDIT / "input_manifest_2026-09-18.json").read_text())
    for name, expected in manifest.items():
        if digest(HERE / name) != expected:
            raise ValueError(f"Audit inputs changed: {name}; re-adjudicate before applying")
    pools = json.loads((HERE / "candidate_pool.json").read_text())
    adjudications = json.loads((AUDIT / "adjudications_2026-09-18.json").read_text())
    before = json.loads((AUDIT / "label_decisions_before_2026-09-18.json").read_text())
    requests = {r["request_id"]: r for r in REQUESTS}
    with (HERE / "benchmark_catalog_frozen.csv").open() as f:
        rows = list(csv.DictReader(f))
    catalog = {(int(r["store_id"]), r["product_id"]): r for r in rows}
    if len(catalog) != len(rows):
        raise ValueError("Duplicate catalog identities")
    if set(requests) != set(adjudications) or set(requests) != {p["request_id"] for p in pools}:
        raise ValueError("Audit must cover every request exactly")
    catalog_sha = manifest["benchmark_catalog_frozen.csv"]
    decisions, records = {}, []
    grouped = defaultdict(list)
    for pool in pools:
        rid = pool["request_id"]
        request, spec = requests[rid], adjudications[rid]
        acceptable, uncertain = set(spec["a"]), set(spec.get("n", []))
        valid = set(range(len(pool["candidates"])))
        if acceptable & uncertain or not (acceptable | uncertain) <= valid:
            raise ValueError(f"Invalid adjudication indexes for {rid}")
        for index, candidate in enumerate(pool["candidates"]):
            store_id, product_id = candidate["store_id"], candidate["product_id"]
            row = catalog[store_id, product_id]
            key = f"{rid}|{store_id}|{product_id}"
            if key in decisions:
                raise ValueError(f"Duplicate candidate {key}")
            previous = before[key]
            label = ("Acceptable" if index in acceptable else
                     "Needs clarification" if index in uncertain else "Incorrect")
            rationale = {
                "Acceptable": "Catalog identity, stated variant and required package information satisfy the request under the v2 rules.",
                "Incorrect": "Catalog product type, explicit variant/brand, package size/count or form conflicts with the request; matching words alone do not establish a match.",
                "Needs clarification": "Catalog evidence does not establish all required attributes or the request permits materially different interpretations; do not assume a match or a proven mismatch.",
            }[label]
            if spec.get("note"):
                rationale += " " + spec["note"]
            # Explanatory evidence only: these calculations never choose a
            # label. In particular, do not reuse query-parser dimensions.
            if label == "Incorrect" and request["expected"].get("size"):
                wanted = parse_package_size(request["expected"]["size"])
                actual = parse_package_size(row["raw_size"])
                if (not wanted["unresolved"] and not actual["unresolved"]
                        and wanted["dimension"] == actual["dimension"]
                        and wanted["canonical_total"] and actual["canonical_total"]
                        and abs(wanted["canonical_total"] - actual["canonical_total"])
                        / wanted["canonical_total"] > 0.001):
                    rationale = (f"Confirmed package mismatch: requested {request['expected']['size']}; "
                                 f"catalog states {row['raw_size']}. " + rationale)
            evidence = {field: row[field] for field in (
                "raw_title", "raw_category", "raw_size", "pkg_dimension",
                "pkg_count", "pkg_canonical_total", "dimension_review_flag")}
            request_sha = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
            current = {
                "request_id": rid, "store_id": store_id, "product_id": product_id,
                "reviewer_label": label, "reviewed_by": "codex_ai_audit",
                "reviewed_by_reason": rationale, "audit_id": AUDIT_ID,
                "catalog_version_sha256": catalog_sha,
                "request_version": REQUEST_VERSION,
                "request_content_sha256": request_sha,
                "labeling_guideline_version": LABELING_GUIDELINE_VERSION,
                "prior_reviewed_by": previous.get("reviewed_by"),
                "prior_label": previous["reviewer_label"],
                "revealed": previous.get("revealed", False),
                "draft_label": previous.get("draft_label"),
                "agreed_with_draft": (label == previous["draft_label"]
                                      if previous.get("draft_label") else None),
            }
            decisions[key] = current
            records.append({"key": key, "request": request, "evidence": evidence,
                            "previous": previous, "decision": current,
                            "label_changed": label != previous["reviewer_label"]})
            grouped[request["paraphrase_group"], store_id, product_id].append(label)
    if any(len(set(labels)) > 1 for labels in grouped.values()):
        raise ValueError("Conflicting labels for shared candidates in paraphrase groups")
    return decisions, records, before


def write_report(decisions, records, before):
    changed = [r for r in records if r["label_changed"]]
    counts = Counter(d["reviewer_label"] for d in decisions.values())
    transitions = Counter((r["previous"]["reviewer_label"], r["decision"]["reviewer_label"]) for r in changed)
    report = ["# Complete label audit — 2026-09-18", "",
              f"Reviewed all {len(decisions)} current pairs across {len(REQUESTS)} requests.",
              f"Changed {len(changed)} labels; confirmed {len(decisions)-len(changed)}.",
              f"Archived {len(set(before)-set(decisions))} obsolete decisions outside the current pool in the before snapshot.",
              "", "AI adjudication against the frozen catalog; not independent human review or live verification.",
              "Uncertain labels intentionally remain unresolved. No retrieval scores or thresholds were tuned.", "",
              "## Results", ""]
    report += [f"- {label}: {count}" for label, count in sorted(counts.items())]
    report += ["", "## Changes", "", "| Previous | Audited | Count |", "|---|---|---:|"]
    report += [f"| {a} | {b} | {n} |" for (a, b), n in sorted(transitions.items())]
    report += ["", "## Method and remaining limits", "",
               "Every candidate title, category and package was inspected in request groups. "
               "Explicit per-request adjudications were materialized only after validating catalog/pool/request hashes. "
               "Shared candidates within paraphrase groups were checked for agreement.", "",
               "The request schema was corrected for r096/r144 (no invented water-only tuna restriction), "
               "r083 (ambiguous bare oz on ice cream), and r039 (no fixed 12 oz unsalted dairy butter "
               "found in the full frozen catalog; the 12 oz macadamia nut butter is a different product). "
               "Request and guideline versions are now v2.", "",
               "Candidate-level uncertainty does not by itself prove that a request has no answer in the entire catalog. "
               "Most other no-match request assertions have not been exhaustively searched beyond their pools. "
               "Exact package matching, including multipack count, is the benchmark policy; basket quantity optimization is separate.", "",
               "The old heuristic remains a draft-label generator for future unseen candidates, not gold truth. "
               "It must not overwrite these adjudications. Independent human review of held-out labels remains valuable.", "",
               "Full evidence, old decisions and new rationales: `label_audit_2026-09-18.json`. "
               "Complete original file: `label_decisions_before_2026-09-18.json`.", "",
               "## Changed pairs", "", "| Key | Request | Candidate | Before | After |", "|---|---|---|---|---|"]
    def cell(value):
        return str(value).replace("|", " / ").replace("\n", " ")
    for r in changed:
        report.append("| " + " | ".join(map(cell, [r["key"], r["request"]["text"], r["evidence"]["raw_title"],
                                                   r["previous"]["reviewer_label"], r["decision"]["reviewer_label"]])) + " |")
    (AUDIT / "label_audit_2026-09-18.json").write_text(json.dumps(records, indent=2) + "\n")
    (AUDIT / "LABEL_AUDIT_2026-09-18.md").write_text("\n".join(report) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    decisions, records, before = build_audit()
    if args.apply:
        # Do not replay the audit over later human work or a different run.
        current = json.loads((HERE / "label_review_decisions.json").read_text())
        if current != before and current != decisions:
            raise SystemExit("Decisions changed since the before snapshot; refusing to overwrite newer work")
        write_report(decisions, records, before)
        save_decisions_atomic(decisions)
    print(json.dumps({"pairs": len(decisions), "changed": sum(r["label_changed"] for r in records),
                      "labels": dict(Counter(d["reviewer_label"] for d in decisions.values())),
                      "applied": args.apply}))


if __name__ == "__main__":
    main()
