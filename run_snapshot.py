#!/usr/bin/env python3
"""Run the existing DoorDash scraper for one store into a fresh timestamped
runs/<slug>_<store_id>/<timestamp>/items.csv directory, instead of appending
to a shared per-store CSV.

Keeping each collection in its own folder (rather than editing
doordash_dashmart_scraper.py's append-CSV behavior) means every snapshot is
independently inspectable and nothing about the existing DashMart pipeline
changes.

Usage:
    python3 run_snapshot.py <store_id> <slug> [-- extra scraper args...]

Example:
    python3 run_snapshot.py 29631686 aldi
    python3 run_snapshot.py 35802549 ralphs --paginate
"""
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS_ROOT = HERE / "runs"


def main():
    if len(sys.argv) < 3:
        print("usage: run_snapshot.py <store_id> <slug> [extra scraper args...]")
        sys.exit(1)
    store_id, slug = sys.argv[1], sys.argv[2]
    extra_args = sys.argv[3:]

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    run_dir = RUNS_ROOT / f"{slug}_{store_id}" / ts
    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = run_dir / "items.csv"

    cmd = [
        sys.executable,
        "doordash_dashmart_scraper.py",
        store_id,
        "-o",
        str(out_path),
        "--name",
        slug.replace("-", " ").replace("_", " ").title(),
        *extra_args,
    ]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=HERE)
    print(f"Snapshot written to {out_path}")


if __name__ == "__main__":
    main()
