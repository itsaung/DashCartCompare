#!/usr/bin/env python3
"""Checkpoint 4, S7: final evaluation under the frozen three-way response policy.

What this adds over evaluation_metrics_v3.py, which scored a two-way response
(returned / abstained) at floor 0.0: S6 gave every family an accept threshold
and a review floor, so the shipped response is three-way, and the acceptance
criterion is defined over *automatic matches only*.

AUTOMATIC-MATCH PRECISION, measured exactly as CHECKPOINT_4_PLAN.md S7 defines it:

    numerator   requests whose outcome is an automatic match, whose ground-truth
                answerability is "answerable", and whose top-1 label is Acceptable
    denominator ALL requests receiving an automatic match

Review-band outcomes are in NEITHER -- they are not automatic matches. So are
abstentions. An automatic match on a needs_clarification or no_acceptable_match
request counts against the numerator and never for it, even where the candidate
looks compatible: that is evaluation_metrics.returned_match_accuracy's existing
response-policy rule, reused here rather than restated.

Reported in BOTH label views. The 95% criterion is judged against the
CONSERVATIVE lower bound -- clearing it on the practical view only is reported
as exactly that.

Coverage always travels with it: automatic-match rate, review rate and
abstention rate are a three-way partition summing to 1, reported with counts, so
that rejecting everything cannot look like success.

Outputs:
    evaluation_v3/final_metrics.json
    evaluation_v3/constraint_violation_check.json
    evaluation_v3/RESULTS_TABLE.md

Usage:
    .venv/bin/python final_evaluation.py
"""
import json
from pathlib import Path

import pandas as pd

import evaluation_metrics as em
import evaluation_metrics_v3 as v3
import checkpoint4_config as cfg
from normalize import parse_package_size
from parse_query import parse_shopping_line
from product_identity import build_brand_lexicon, extract_request_identity, variants_conflict
from retrieval import (PACKAGE_SIZE_ROUNDING_TOLERANCE, _identity_lookup,
                       _requested_canonical_total)
from run_experiments import _load_catalog
from tune_threshold_v3 import apply_cut_points

HERE = Path(__file__).resolve().parent
V1_DIR = HERE / "evaluation"
V2_DIR = HERE / "evaluation_v2"
OUT_DIR = HERE / "evaluation_v3"
IDENTITY_PATH = OUT_DIR / "catalog_identity.csv"

SPLITS = ("dev", "validation", "test")
VIEWS = em.VIEWS

CRITERION = 0.95


def _rate(numerator, denominator):
    return {
        "n": numerator,
        "of": denominator,
        "rate": (numerator / denominator) if denominator else None,
    }


def load_all_predictions() -> list:
    """v3's four families plus the v2 incumbent. evaluation_v2/ is read-only."""
    rows = [json.loads(line) for line in open(OUT_DIR / "predictions.jsonl")]
    rows += [json.loads(line) for line in open(V2_DIR / "predictions.jsonl")]
    return [r for r in rows if r["experiment"] == "full_catalog"]


def outcome_partition(records, accept, review) -> dict:
    """The three-way response partition for one split, with counts."""
    counts = {"accept": 0, "review": 0, "no_match": 0}
    for rec in records:
        counts[apply_cut_points(rec, accept, review)] += 1
    n = len(records)
    return {
        "n_requests": n,
        "counts": counts,
        "automatic_match_rate": _rate(counts["accept"], n),
        "review_rate": _rate(counts["review"], n),
        "abstention_rate": _rate(counts["no_match"], n),
        "sums_to_one": n == sum(counts.values()),
    }


def automatic_match_precision(records, accept, review, lookup, answerability, view) -> dict:
    """Numerator and denominator both restricted to automatic matches."""
    correct, total, unjudged = 0, 0, []
    for rec in records:
        if apply_cut_points(rec, accept, review) != "accept":
            continue
        total += 1
        top1 = rec["results"][0]
        key = em._pair_key(rec["request_id"], top1["store_id"], top1["product_id"])
        entry = lookup.get(key)
        if entry is None:
            unjudged.append(rec["request_id"])
            continue
        if answerability[rec["request_id"]] != "answerable":
            continue  # a return on an unanswerable request never counts for
        if entry[view] == "Acceptable":
            correct += 1
    out = _rate(correct, total)
    out["unjudged_top1_request_ids"] = sorted(unjudged)
    return out


def _mode_breakdown(records, accept, review, lookup, answerability, by_id) -> dict:
    out = {}
    for mode in ("exact", "flexible"):
        subset = [r for r in records if by_id[r["request_id"]]["matching_mode"] == mode]
        part = outcome_partition(subset, accept, review)
        out[mode] = {
            "n_requests": part["n_requests"],
            "counts": part["counts"],
            "automatic_match_precision": {
                view: automatic_match_precision(subset, accept, review, lookup,
                                                answerability, view)
                for view in VIEWS
            },
        }
    return out


def split_report(records, accept, review, lookup, answerability, by_id) -> dict:
    report = outcome_partition(records, accept, review)
    report["n_answerable"] = sum(
        1 for r in records if answerability[r["request_id"]] == "answerable")
    report["automatic_match_precision"] = {
        view: automatic_match_precision(records, accept, review, lookup, answerability, view)
        for view in VIEWS
    }
    cons = report["automatic_match_precision"]["conservative"]["rate"]
    prac = report["automatic_match_precision"]["practical"]["rate"]
    report["meets_criterion_conservative"] = cons is not None and cons >= CRITERION
    report["meets_criterion_practical_only"] = (
        prac is not None and prac >= CRITERION and not report["meets_criterion_conservative"])
    report["by_matching_mode"] = _mode_breakdown(
        records, accept, review, lookup, answerability, by_id)
    return report


# --- constraint-violation check ---------------------------------------------
#
# A distinct pass criterion from the 95% number, and deliberately NOT computed
# from the retrieval pipeline's own filters: re-deriving each conflict here from
# the catalog row and the request means a bug in a filter shows up as a
# violation rather than hiding behind the filter that should have caught it.
#
# The standing rule everywhere in this codebase applies: unknown on either side
# is a third state, never a conflict.

def _brands_conflict(requested: str, candidate: str) -> bool:
    """A CONFIRMED brand conflict between two known brand strings.

    Token-prefix compatibility is not a conflict. The two sides of S2's
    extractor routinely resolve different spans of the same brand -- the
    catalog side reads "Chobani" off a title that begins "Chobani Flip ...",
    the request side reads "Chobani Flip"; likewise "Land" / "Land O'Lakes
    Unsalted" and "PurAqua" / "PurAqua Belle Vie". Treating a longer form as
    conflicting with its own prefix reports the extractor's span disagreement
    as a product mismatch, which it is not.

    Added after the first test run of this check, as an evaluator bug fix and
    disclosed as one: CHECKPOINT_4_PLAN.md S7 permits correcting a test result
    for an evaluator bug, transparently. It does not change any matcher, any
    threshold or any label -- only which pairs this check calls a conflict.
    """
    a = requested.casefold().split()
    b = candidate.casefold().split()
    n = min(len(a), len(b))
    return a[:n] != b[:n]


def constraint_violations(rec, catalog_df, catalog_index, identity_lookup,
                          lexicon, request_text, matching_mode) -> list:
    top1 = rec["results"][0]
    row_idx = catalog_index.get((str(top1["store_id"]), str(top1["product_id"])))
    if row_idx is None:
        return ["catalog_row_not_found"]
    row = catalog_df.iloc[row_idx]

    structured = parse_shopping_line(request_text)
    ident = extract_request_identity(request_text, lexicon)
    cand = identity_lookup.get((str(row["store_id"]), str(row["product_id"])))

    violations = []

    # brand: only when BOTH sides are known, and only in exact mode -- flexible
    # mode does not require the request's brand to be honored.
    cand_brand = getattr(cand, "brand", None) if cand is not None else None
    if isinstance(cand_brand, float):
        cand_brand = None
    if (matching_mode == "exact" and ident["brand"] and cand_brand
            and _brands_conflict(ident["brand"], cand_brand)):
        violations.append("brand_conflict")

    raw_variant = getattr(cand, "variant_tokens", "") if cand is not None else ""
    cand_variant = frozenset(str(raw_variant).split()) if isinstance(raw_variant, str) else frozenset()
    if variants_conflict(ident["variant_tokens"], cand_variant):
        violations.append("variant_conflict")

    dimension = structured.get("dimension")
    row_dimension = row["pkg_dimension"]
    if dimension and pd.notna(row_dimension) and row_dimension != dimension:
        violations.append("dimension_conflict")

    unit, total = _requested_canonical_total(request_text, structured)
    row_unit, row_total = row.get("pkg_canonical_unit"), row.get("pkg_canonical_total")
    if (unit and total is not None and pd.notna(row_unit) and pd.notna(row_total)
            and row_unit == unit
            and abs(row_total - total) / total > PACKAGE_SIZE_ROUNDING_TOLERANCE):
        violations.append("size_conflict")

    return violations


def run_constraint_check(records, accept, review, by_id, catalog_df, catalog_index,
                         identity_lookup, lexicon) -> dict:
    checked, offenders = 0, []
    for rec in records:
        if apply_cut_points(rec, accept, review) != "accept":
            continue
        checked += 1
        req = by_id[rec["request_id"]]
        found = constraint_violations(rec, catalog_df, catalog_index, identity_lookup,
                                      lexicon, req["text"], req["matching_mode"])
        if found:
            top1 = rec["results"][0]
            offenders.append({
                "request_id": rec["request_id"],
                "request_text": req["text"],
                "matching_mode": req["matching_mode"],
                "store_id": top1["store_id"],
                "product_id": top1["product_id"],
                "violations": found,
            })
    return {
        "n_automatic_matches_checked": checked,
        "n_violations": len(offenders),
        "passes": not offenders,
        "violations": offenders,
    }


# Warm latency per family, from run_experiments_v3.py's own timings
# (evaluation_v3/metrics.json) and evaluation_v2/metrics.json for the incumbent.
# Read rather than re-measured: re-timing here would report THIS machine's load
# at THIS moment against numbers taken during the prediction runs.
def _latency_table() -> dict:
    out = {}
    for path in (OUT_DIR / "metrics.json", V2_DIR / "metrics.json"):
        for name, entry in json.loads(path.read_text())["baselines"].items():
            out[name] = entry["latency_ms"]
    return out


def _rate_str(d) -> str:
    return "N/A" if d["rate"] is None else f"{d['rate']:.1%} ({d['n']}/{d['of']})"


def write_results_table(report, check, latency, path) -> None:
    """The numbers alone. SEMANTIC_RESULTS.md carries the narrative and caveats;
    this is generated so it cannot drift from final_metrics.json."""
    f = report["frozen_config"]
    cp = f["cut_points"]
    selected = f["selected_baseline"]
    order = ([selected] + [n for n in sorted(report["baselines"]) if n != selected])

    L = ["# Checkpoint 4 -- final results table", "",
         "Generated from `final_metrics.json` by `final_evaluation.py`. Full narrative, caveats",
         "and failure analysis in `SEMANTIC_RESULTS.md`; this file is the numbers alone.", "",
         f"Shipped: **`{selected}`**, accept {cp['accept_threshold']:.5f} / review floor "
         f"{cp['review_floor']:.6f}, selected on validation, frozen at `{f['code_sha'][:10]}` "
         "before the test split was scored.", "",
         "Every rate carries its numerator and denominator. Precision is automatic-match",
         "precision: review-band outcomes and abstentions are excluded from numerator and",
         "denominator both. The 95% criterion is judged on the conservative view, test split.", ""]

    for name in order:
        b = report["baselines"][name]
        bcp = b["cut_points"]
        lat = latency.get(name, {})
        star = " -- **shipped**" if name == selected else ""
        L += [f"## `{name}`{star}", "",
              f"Cut points: accept {bcp['accept_threshold']:.6f} / review floor "
              f"{bcp['review_floor']:.6f}. Warm latency: median {lat.get('median', 0):,.1f} ms, "
              f"p95 {lat.get('p95', 0):,.1f} ms (n={lat.get('n', 0)}).", "",
              "| split | n | answerable | auto / review / abstain | auto-match rate | review rate "
              "| abstention rate | precision (conservative) | precision (practical) |",
              "|---|---|---|---|---|---|---|---|---|"]
        for sp in SPLITS:
            sr = b["splits"][sp]
            c = sr["counts"]
            ap = sr["automatic_match_precision"]
            L.append(f"| {sp} | {sr['n_requests']} | {sr['n_answerable']} | "
                     f"{c['accept']} / {c['review']} / {c['no_match']} | "
                     f"{_rate_str(sr['automatic_match_rate'])} | {_rate_str(sr['review_rate'])} | "
                     f"{_rate_str(sr['abstention_rate'])} | {_rate_str(ap['conservative'])} | "
                     f"{_rate_str(ap['practical'])} |")
        L += ["", "| split | mode | n | auto / review / abstain | precision (conservative) |",
              "|---|---|---|---|---|"]
        for sp in SPLITS:
            for mode in ("exact", "flexible"):
                bm = b["splits"][sp]["by_matching_mode"][mode]
                c = bm["counts"]
                L.append(f"| {sp} | {mode} | {bm['n_requests']} | "
                         f"{c['accept']} / {c['review']} / {c['no_match']} | "
                         f"{_rate_str(bm['automatic_match_precision']['conservative'])} |")
        L.append("")

    L += ["## Constraint-violation check", "",
          f"Baseline `{check['baseline']}`. A violation is a confirmed brand (exact mode), variant,",
          "dimension or package-size conflict between the request and the automatically matched",
          "top-1, re-derived from the catalog row rather than read back from the retrieval filters.",
          "", "| split | automatic matches checked | violations | passes |", "|---|---|---|---|"]
    for sp in SPLITS:
        s_ = check["splits"][sp]
        L.append(f"| {sp} | {s_['n_automatic_matches_checked']} | {s_['n_violations']} | "
                 f"{'yes' if s_['passes'] else '**no**'} |")
    if not check["test_passes"]:
        L += ["", "**Test does not pass.** See `SEMANTIC_RESULTS.md` section 4, which lists every",
              "violation with its matched title."]
    L += ["", "## Sample sizes", "",
          "Held-out splits are 30 requests each (16 exact / 14 flexible; 20 answerable on test, 25",
          "on validation). One request is 3.3 percentage points of a split rate and 5-6 points of a",
          "precision denominator. **No single-split difference of a few points here is",
          "interpretable.**", ""]
    path.write_text("\n".join(L))


def main():
    requests = json.loads((V1_DIR / "benchmark_requests.json").read_text())
    splits = json.loads((V1_DIR / "splits.json").read_text())["request_split"]
    frozen = json.loads((OUT_DIR / "frozen_config.json").read_text())
    lookup = v3.load_merged_label_lookup()
    answerability = {r["request_id"]: r["answerability"] for r in requests}
    by_id = {r["request_id"]: r for r in requests}
    predictions = load_all_predictions()

    selected = frozen["selected_baseline"]
    families = sorted({r["baseline"] for r in predictions} & set(cfg.CUT_POINTS))

    report = {
        "frozen_config": {k: frozen[k] for k in
                          ("selected_baseline", "selected_on_split", "cut_points",
                           "code_sha", "frozen_at")},
        "criterion": CRITERION,
        "criterion_judged_on": "conservative view, test split",
        "label_note": (
            "Every label underlying these numbers is AI adjudication from frozen "
            "catalog text and images, not independent human review or live "
            "product-page verification. A difference measured here is a difference "
            "against that adjudication."
        ),
        "baselines": {},
    }

    for family in families:
        accept, review = cfg.cut_points_for(family)
        entry = {"cut_points": {"accept_threshold": accept, "review_floor": review},
                 "splits": {}}
        for split in SPLITS:
            recs = [r for r in predictions
                    if r["baseline"] == family and splits.get(r["request_id"]) == split]
            entry["splits"][split] = split_report(
                recs, accept, review, lookup, answerability, by_id)
        report["baselines"][family] = entry

    # Constraint check, run for the selected baseline on every split. Test is
    # the pass criterion; dev and validation are reported for completeness.
    print("loading catalog for the constraint check...", flush=True)
    catalog_df = _load_catalog()
    catalog_index = {(str(r.store_id), str(r.product_id)): i
                     for i, r in enumerate(catalog_df.itertuples())}
    identity_lookup = _identity_lookup(pd.read_csv(IDENTITY_PATH))
    lexicon = build_brand_lexicon(catalog_df)
    accept, review = cfg.cut_points_for(selected)

    check = {
        "baseline": selected,
        "cut_points": {"accept_threshold": accept, "review_floor": review},
        "rule": (
            "A hard-constraint violation is a CONFIRMED conflict between the request "
            "and the automatically matched top-1: brand (exact mode only, both sides "
            "known), variant, package dimension, or package size beyond "
            f"{PACKAGE_SIZE_ROUNDING_TOLERANCE:.0%} relative. Unknown on either side is "
            "never a conflict. Re-derived here from the catalog row rather than read "
            "back from the retrieval filters, so a filter bug surfaces as a violation."
        ),
        "splits": {},
    }
    for split in SPLITS:
        recs = [r for r in predictions
                if r["baseline"] == selected and splits.get(r["request_id"]) == split]
        check["splits"][split] = run_constraint_check(
            recs, accept, review, by_id, catalog_df, catalog_index, identity_lookup, lexicon)
    check["test_passes"] = check["splits"]["test"]["passes"]

    (OUT_DIR / "final_metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    (OUT_DIR / "constraint_violation_check.json").write_text(json.dumps(check, indent=2) + "\n")
    write_results_table(report, check, _latency_table(), OUT_DIR / "RESULTS_TABLE.md")

    print(f"\nSelected: {selected}  accept {accept:.5f} / review floor {review:.5f}\n")
    for family in families:
        print(family)
        for split in SPLITS:
            sr = report["baselines"][family]["splits"][split]
            c = sr["counts"]
            cons = sr["automatic_match_precision"]["conservative"]
            prac = sr["automatic_match_precision"]["practical"]
            fmt = lambda d: ("N/A" if d["rate"] is None
                             else f"{d['rate']:.1%} ({d['n']}/{d['of']})")
            print(f"  {split:11} A/R/N {c['accept']:>2}/{c['review']:>2}/{c['no_match']:>2}"
                  f"   auto-match precision  conservative {fmt(cons):>16}"
                  f"   practical {fmt(prac):>16}")
    print()
    for split in SPLITS:
        s = check["splits"][split]
        print(f"constraint check {split:11} {s['n_violations']} violation(s) "
              f"in {s['n_automatic_matches_checked']} automatic matches")
    print(f"\nWrote {OUT_DIR / 'final_metrics.json'}")
    print(f"Wrote {OUT_DIR / 'constraint_violation_check.json'}")
    print(f"Wrote {OUT_DIR / 'RESULTS_TABLE.md'}")


if __name__ == "__main__":
    main()
