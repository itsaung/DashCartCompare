"""Independent re-check of a random 50-pair sample of the frozen benchmark.

WHY THIS EXISTS. 1,544 of the 1,658 pool labels were produced by
`claude_auto_label.py`, whose rule set compares dimension, package size, brand
and product type -- the *same* comparisons `retrieval.py`'s filters apply. The
benchmark and the matcher are therefore not fully independent, so a measured
matcher improvement is biased upward by an unknown amount. Nothing in the repo
measures that bias. This does.

WHAT MAKES IT INDEPENDENT. Re-reading the catalog title and re-applying the
same attribute comparison would repeat the circularity, not measure it -- the
exact failure mode Checkpoint 2's `manual_review.py` was rebuilt to avoid ("a
verification step that only compares stored data to itself is circular"). So
this check judges from the **product photograph**: the packaging as
photographed, fetched live from DoorDash's CDN, which is evidence the original
labeler never read. Where the photo and the title disagree, the photo is the
tiebreaker for what the product physically is.

WHAT IT DOES NOT ESTABLISH. The adjudicator is still an AI, not a human rater.
This measures agreement between the frozen labels and an independent-source
re-judgment; it does not establish ground truth, and it is not the human
review a published accuracy claim would need. Stated plainly in the report.
"""

from __future__ import annotations

import csv
import glob
import json
import random
import re
import urllib.request
from pathlib import Path

import pandas as pd

import benchmark_config as cfg

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "evaluation_v3" / "label_check"
SAMPLE_PATH = OUT_DIR / "sample.json"
PHOTO_DIR = OUT_DIR / "photos"

SAMPLE_SIZE = 50
# Its own seed, deliberately not cfg.RANDOM_SEED: reusing the split seed could
# correlate this sample with the dev/validation/test assignment.
CHECK_SEED = 50_2026

_CDN_SIZE_RE = re.compile(r"width=\d+,height=\d+")
THUMBNAIL_PX = 420


def thumbnail_url(image_url: str, size: int = THUMBNAIL_PX) -> str:
    if not image_url:
        return ""
    return _CDN_SIZE_RE.sub(f"width={size},height={size}", image_url, count=1)


def load_image_urls() -> dict:
    """(store_id, product_id) -> image_url, read from the raw scraper CSVs.

    Same source `label_review_ui.py` uses, and deliberately not the frozen
    catalog: image_url is not part of catalog_version, so reading it here
    cannot stale any existing decision.
    """
    out = {}
    for path in glob.glob(str(HERE / "runs" / "*" / "*" / "items.csv")):
        store_id = Path(path).parts[-3].split("_")[-1]
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                url = (row.get("image_url") or "").strip()
                if url:
                    out[(str(store_id), str(row.get("item_id", "")).strip())] = url
    for path in glob.glob(str(HERE / "doordash_*_items.csv")):
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                url = (row.get("image_url") or "").strip()
                if url:
                    out[("1042759", str(row.get("item_id", "")).strip())] = url
    return out


def draw_sample(pairs_path: Path, catalog_df, requests_by_id: dict, n=SAMPLE_SIZE):
    """A uniform random sample of the whole pool.

    Uniform on purpose: a difficulty-stratified sample would measure the rule
    set where it is weakest and overstate disagreement, and an easy sample
    would understate it. The point is an unbiased estimate of overall
    agreement.
    """
    pairs = [json.loads(line) for line in open(pairs_path)]
    rng = random.Random(CHECK_SEED)
    chosen = rng.sample(pairs, n)

    index = {(str(r.store_id), str(r.product_id)): r for r in catalog_df.itertuples()}
    images = load_image_urls()

    out = []
    for i, p in enumerate(chosen, 1):
        key = (str(p["store_id"]), str(p["product_id"]))
        row = index.get(key)
        req = requests_by_id.get(p["request_id"], {})
        out.append({
            "n": i,
            "request_id": p["request_id"],
            "request_text": req.get("text", ""),
            "matching_mode": req.get("matching_mode", ""),
            "store_id": p["store_id"],
            "product_id": p["product_id"],
            "catalog_title": getattr(row, "raw_title", None),
            "catalog_size": getattr(row, "raw_size", None),
            "frozen_label": p["reviewer_label"],
            "is_best_guess": p["is_best_guess"],
            "reviewed_by": p["reviewed_by"],
            "image_url": thumbnail_url(images.get(key, "")),
        })
    return out


def fetch_photos(sample: list, out_dir: Path = PHOTO_DIR) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    status = {}
    for item in sample:
        url = item["image_url"]
        dest = out_dir / f"{item['n']:02d}.jpg"
        if not url:
            status[item["n"]] = "no image_url in the raw scrape"
            continue
        if dest.exists() and dest.stat().st_size > 0:
            status[item["n"]] = "cached"
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
            dest.write_bytes(data)
            status[item["n"]] = f"ok ({len(data)} bytes)"
        except Exception as exc:
            status[item["n"]] = f"FAILED: {exc}"
    return status


def contact_sheet(sample: list, indices: list, path: Path, cols=3, cell=420):
    """Label each photo with its sample number so a judgment can be tied back
    to a specific pair rather than to a position in a grid."""
    from PIL import Image, ImageDraw

    rows = (len(indices) + cols - 1) // cols
    band = 64
    sheet = Image.new("RGB", (cols * cell, rows * (cell + band)), "white")
    draw = ImageDraw.Draw(sheet)

    for slot, n in enumerate(indices):
        x = (slot % cols) * cell
        y = (slot // cols) * (cell + band)
        src = PHOTO_DIR / f"{n:02d}.jpg"
        if src.exists():
            try:
                img = Image.open(src).convert("RGB")
                img.thumbnail((cell, cell))
                sheet.paste(img, (x + (cell - img.width) // 2, y + (cell - img.height) // 2))
            except Exception:
                draw.text((x + 10, y + cell // 2), "unreadable", fill="red")
        else:
            draw.text((x + 10, y + cell // 2), "no photo", fill="red")
        item = next(s for s in sample if s["n"] == n)
        draw.rectangle([x, y + cell, x + cell, y + cell + band], fill="#efefef")
        draw.text((x + 8, y + cell + 6), f"#{n}  {item['request_text'][:40]}", fill="black")
        draw.text((x + 8, y + cell + 24), f"-> {str(item['catalog_title'])[:46]}", fill="#333333")
        draw.text((x + 8, y + cell + 42), f"   {str(item['catalog_size'])[:30]}", fill="#666666")
    sheet.save(path)
    return path


def main() -> None:
    from run_experiments import _load_catalog

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    catalog = _load_catalog()
    reqs = json.load(open(HERE / "evaluation" / "benchmark_requests.json"))
    reqs = reqs["requests"] if isinstance(reqs, dict) else reqs
    by_id = {r["request_id"]: r for r in reqs}

    sample = draw_sample(HERE / "evaluation" / "benchmark_pairs.jsonl", catalog, by_id)
    SAMPLE_PATH.write_text(json.dumps(sample, indent=2) + "\n")

    status = fetch_photos(sample)
    ok = sum(1 for v in status.values() if v.startswith(("ok", "cached")))
    print(f"sample: {len(sample)} pairs -> {SAMPLE_PATH.relative_to(HERE)}")
    print(f"photos: {ok}/{len(sample)} available")
    for n, s in sorted(status.items()):
        if not s.startswith(("ok", "cached")):
            print(f"  #{n}: {s}")

    sheets = []
    nums = [s["n"] for s in sample]
    for i in range(0, len(nums), 9):
        chunk = nums[i:i + 9]
        p = OUT_DIR / f"sheet_{i // 9 + 1}.png"
        contact_sheet(sample, chunk, p)
        sheets.append(p)
    print(f"contact sheets: {len(sheets)}")


if __name__ == "__main__":
    main()
