"""Materialize the user-requested best guesses for the 114 uncertain pairs.

Saved photo observations are authored visual judgments, not model output.
The original conservative labels and evidence remain in the audit trail.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from audit.photo_adjudications import ACCEPTABLE, OBSERVATIONS
from label_review_ui import save_decisions_atomic

HERE = Path(__file__).resolve().parent
AUDIT = HERE / "audit"
REVIEW_ID = "2026-09-18-photo-v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_review():
    expected_hashes = json.loads((AUDIT / "photo_input_hashes.json").read_text())
    for name, expected_hash in expected_hashes.items():
        if sha(HERE / name) != expected_hash:
            raise ValueError(f"Photo audit input changed: {name}")
    before = json.loads((AUDIT / "label_decisions_before_photo_review.json").read_text())
    sources = json.loads((AUDIT / "photo_sources.json").read_text())
    by_product = {(r["store_id"], r["product_id"]): r for r in sources}
    originals = {r["key"]: r for r in json.loads((AUDIT / "label_audit_2026-09-18.json").read_text())}
    decisions = dict(before)
    reviewed, seen = [], set()
    for key, prior in before.items():
        if prior["reviewer_label"] != "Needs clarification":
            continue
        source = by_product[prior["store_id"], prior["product_id"]]
        index = source["photo_index"]
        reason, guess = OBSERVATIONS[index]
        rid = prior["request_id"]
        accepted = index in ACCEPTABLE.get(rid, [])
        if rid == "r130":
            guess = True
            reason += " For this request, assume three retail packs; this quantity interpretation is not confirmed."
        if rid == "r132" and index == 6:
            guess = True
            reason += " Best guess: a fluid-volume can is not an exact one-pound package."
        label = "Acceptable" if accepted else "Incorrect"
        evidence = {
            **source,
            "local_photo": f"audit/photos/{index:03}.img",
            "photo_sha256": sha(AUDIT / "photos" / f"{index:03}.img"),
            "observation": reason,
        }
        updated = {
            **prior,
            "reviewer_label": label,
            "reviewed_by": "codex_photo_review",
            "reviewed_by_reason": reason,
            "photo_review_id": REVIEW_ID,
            "label_quality": "best_guess" if guess else "photo_supported",
            "is_best_guess": guess,
            "conservative_label": "Needs clarification" if guess else label,
            "photo_evidence": evidence,
            "agreed_with_draft": (label == prior["draft_label"] if prior.get("draft_label") else None),
        }
        decisions[key] = updated
        reviewed.append({"key": key, "request": originals[key]["request"],
                         "catalog_evidence": originals[key]["evidence"],
                         "before": prior, "after": updated})
        seen.add(index)
    if len(reviewed) != 114 or seen != set(range(95)):
        raise ValueError("Expected exactly the 114 uncertain pairs and all 95 inspected photos")
    for rid, indices in ACCEPTABLE.items():
        for index in indices:
            if not any(r["request"]["request_id"] == rid and
                       r["after"]["photo_evidence"]["photo_index"] == index for r in reviewed):
                raise ValueError(f"Unused adjudication {rid}/{index}")
    return before, decisions, reviewed


def write_report(reviewed):
    counts = Counter(r["after"]["reviewer_label"] for r in reviewed)
    quality = Counter(r["after"]["label_quality"] for r in reviewed)
    report = ["# Photo review and best guesses — 2026-09-18", "",
              "Reviewed all 114 previously uncertain pairs using all 95 associated product photos.",
              f"Assigned {counts['Acceptable']} Acceptable and {counts['Incorrect']} Incorrect labels.",
              f"{quality['photo_supported']} decisions are supported by readable package details or visible form; "
              f"{quality['best_guess']} still depend on an explicit best guess.", "",
              "These are AI judgments using retailer product images. Images may be outdated or generic, "
              "and do not verify current stock or checkout behavior. Conflicting title/photo evidence is flagged as a guess.", "",
              "## How to use the labels", "",
              "`reviewer_label` contains the requested binary best judgment for every pair. "
              "`is_best_guess` and `label_quality` distinguish inference from photo support. "
              "For conservative evaluation, use `conservative_label` when present, otherwise `reviewer_label`. "
              "Do not describe inferred labels as independently verified ground truth. "
              "Request-level answerability remains unchanged: a plausible candidate does not necessarily resolve ambiguous shopper intent.", "",
              "The previous complete audit is preserved unchanged. The original heuristic remains a draft generator; "
              "these updates do not retrain it or tune retrieval against the benchmark.", "",
              "## Every reviewed pair", "",
              "| Request / product | Best label | Evidence level | Reason |", "|---|---|---|---|"]
    for r in reviewed:
        d = r["after"]
        photo = d["photo_evidence"]["local_photo"].removeprefix("audit/")
        reason = d["reviewed_by_reason"].replace("|", "/")
        report.append(f"| {r['key'].replace('|', ' / ')} | {d['reviewer_label']} | {d['label_quality']} | {reason} [Photo]({photo}) |")
    (AUDIT / "PHOTO_REVIEW_2026-09-18.md").write_text("\n".join(report) + "\n")
    (AUDIT / "photo_review_2026-09-18.json").write_text(json.dumps(reviewed, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    before, decisions, reviewed = build_review()
    if args.apply:
        current = json.loads((HERE / "label_review_decisions.json").read_text())
        if current != before and current != decisions:
            raise SystemExit("Newer decisions exist; refusing to overwrite them")
        write_report(reviewed)
        save_decisions_atomic(decisions)
        manifest_path = HERE / "benchmark_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["photo_review"] = {
            "review_id": REVIEW_ID, "pairs": 114, "distinct_photos": 95,
            "labels": dict(Counter(r["after"]["reviewer_label"] for r in reviewed)),
            "quality": dict(Counter(r["after"]["label_quality"] for r in reviewed)),
            "decisions_sha256": sha(HERE / "label_review_decisions.json"),
            "before_sha256": sha(AUDIT / "label_decisions_before_photo_review.json"),
            "report": "audit/PHOTO_REVIEW_2026-09-18.md",
            "independent_human_review": False,
        }
        manifest["current_decisions_sha256"] = sha(HERE / "label_review_decisions.json")
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"reviewed": len(reviewed), "labels": dict(Counter(r["after"]["reviewer_label"] for r in reviewed)),
                      "quality": dict(Counter(r["after"]["label_quality"] for r in reviewed)), "applied": args.apply}))


if __name__ == "__main__":
    main()
