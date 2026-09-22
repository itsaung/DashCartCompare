#!/usr/bin/env python3
"""Checkpoint 5, B7: run the basket engine end to end and print an itemized
comparison. Not a test -- the tests are hand-calculated; this is the artifact a
reader looks at, and the source of the worked example in BASKET_RESULTS.md.

Usage:
    .venv/bin/python run_basket_demo.py            # the default list
    .venv/bin/python run_basket_demo.py "16 oz peanut butter" "15 oz cereal"
"""
import json
import sys
from pathlib import Path

import basket
import build_availability as ba
import checkpoint4_config as cfg
import embed_catalog
import embedding_retrieval as er
import retrieval
from embedding_retrieval import _ranked_top, encode_query
from run_experiments import _load_catalog

HERE = Path(__file__).resolve().parent
OUT_PATH = HERE / "evaluation_v4" / "basket_demo_run.json"
DEFAULT_LIST = ["32 oz peanut butter", "15 oz cereal", "13.7 oz crackers",
                "a 67.6 fl oz bottle of Coke soda"]
SEARCH_DEPTH = 400
DIMENSION_BY_UNIT = {"oz": "weight", "fl oz": "volume", "ct": "count"}


def main():
    texts = sys.argv[1:] or DEFAULT_LIST
    accept, floor = cfg.cut_points_for("embed_dimension_size_filter")
    catalog = _load_catalog()
    embeddings = embed_catalog.load_or_build(catalog)
    model = er.get_model()
    availability = ba.load()
    stores = [(str(int(s)), n) for s, n in
              catalog[["store_id", "store_name"]].drop_duplicates().values]

    lines = basket.resolve_lines(texts)
    per_store = {sid: [] for sid, _ in stores}
    for line in lines:
        if line.needs_review:
            for sid, _ in stores:
                per_store[sid].append(basket.resolve_line(line, [], accept, floor))
            continue
        ranked = _ranked_top(catalog, embeddings @ encode_query(line.text, model), SEARCH_DEPTH)
        ranked = retrieval.filter_by_dimension(
            ranked, catalog, DIMENSION_BY_UNIT.get(line.canonical_unit))
        sufficient, _unresolved = retrieval.filter_by_size_sufficient(
            ranked, catalog, line.text,
            {"canonical_unit": line.canonical_unit, "canonical_quantity": line.canonical_quantity})
        by_store = {sid: [] for sid, _ in stores}
        for c in sufficient:
            row = catalog.iloc[c["row"]]
            by_store[str(int(row["store_id"]))].append(basket.Candidate(
                str(row["store_id"]), str(row["product_id"]), row["raw_title"],
                int(row["price_cents"]), row["pkg_canonical_total"],
                row["pkg_canonical_unit"], c["score"]))
        for sid, _ in stores:
            per_store[sid].append(basket.resolve_line(
                line, by_store[sid], accept, floor, availability_by_key=availability))

    baskets = [basket.build_store_basket(sid, name, per_store[sid],
                                         availability_by_key=availability)
               for sid, name in stores]
    comparison = basket.compare_stores(baskets)

    print(f"{len(texts)} written lines -> {len(lines)} after duplicate resolution\n")
    for b in comparison["ranked"]:
        print(f"  {b.store_name:10} ${b.total_cents / 100:>7.2f}  complete   "
              f"verified {b.n_verified}/{b.n_priced}")
    for b in comparison["incomplete"]:
        print(f"  {b.store_name:10} {'--':>8}   incomplete  "
              f"priced {b.n_priced}/{len(b.resolutions)} review {b.n_review} "
              f"missing {b.n_missing}")
    print(f"\n  winner: {[b.store_name for b in comparison['winners']] or comparison['no_winner_reason']}")

    explained = {b.store_id: basket.explain_basket(b, availability) for b in baskets}
    for b in comparison["ranked"][:1]:
        print(f"\n  {b.store_name} itemized:")
        for item in explained[b.store_id]["items"]:
            if item["state"] != basket.LINE_PRICED:
                print(f"    [{item['state']}] {item['request']}: {item['reason']}")
                continue
            print(f"    {item['packages']}x {item['title'][:44]:44} "
                  f"{item['line_cost_cents']:>5}c")
            print(f"        {item['chosen_because'][:96]}")

    OUT_PATH.write_text(json.dumps({
        "list": texts,
        "thresholds": {"accept": accept, "review_floor": floor,
                       "near_tie_band": basket.SCORE_NEAR_TIE_BAND},
        "winners": [b.store_id for b in comparison["winners"]],
        "no_winner_reason": comparison["no_winner_reason"],
        "baskets": explained,
    }, indent=2, default=str) + "\n")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
