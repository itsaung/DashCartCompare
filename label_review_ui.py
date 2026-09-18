#!/usr/bin/env python3
"""Local browser UI for reviewing candidate_pool.json's draft labels.

    python3 label_review_ui.py            # serve on http://127.0.0.1:8766
    python3 label_review_ui.py -p 9000

Bound to 127.0.0.1 only -- this is a local review tool, never meant to be
reachable off this machine. Requests are queued grouped by paraphrase_group.
For each (request, candidate) pair the UI shows the request text + `expected`
+ the candidate's real catalog attributes, but never the draft label,
retrieval source(s), or similarity score until *after* the reviewer submits
their own independent decision -- only then can they optionally reveal the
draft, logged for calibration but never substituted for the reviewer's call.

Decisions are written to label_review_decisions.json, keyed by
"request_id|store_id|product_id", atomically (temp file + os.replace) so a
crash mid-write can't corrupt the file. Each decision stamps the three
versions it was made under (catalog_version's sha256, REQUEST_VERSION,
LABELING_GUIDELINE_VERSION) -- build_benchmark.py treats a decision as stale
if any of the three no longer match current.
"""
import argparse
import csv
import json
import os
import re
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from benchmark_requests import REQUEST_VERSION, REQUESTS
from coverage_report import DASHMART_CSV, DASHMART_ID, RUN_STORES, RUNS_ROOT, latest_run_dir, latest_snapshot_only

HERE = Path(__file__).resolve().parent
CANDIDATE_POOL_PATH = HERE / "candidate_pool.json"
DECISIONS_PATH = HERE / "label_review_decisions.json"
MANIFEST_PATH = HERE / "benchmark_manifest.json"
FROZEN_CATALOG_PATH = HERE / "benchmark_catalog_frozen.csv"

CATALOG_DISPLAY_FIELDS = ["store_name", "raw_title", "raw_category", "raw_size", "brand", "variant", "price_cents"]

# All five stores' image_url values are DoorDash's own cdn4dd.com Cloudflare
# image-resize proxy in front of the real asset, e.g.
# ".../cdn-cgi/image/fit=contain,width=1200,height=672,format=auto/https://...".
# Rewriting width/height gets a small thumbnail straight from that CDN --
# no need to fetch/resize/store a copy of ~83k product photos ourselves.
_CDN_SIZE_RE = re.compile(r"width=\d+,height=\d+")
THUMBNAIL_PX = 280


def thumbnail_url(image_url: str, size: int = THUMBNAIL_PX) -> str:
    if not image_url:
        return ""
    return _CDN_SIZE_RE.sub(f"width={size},height={size}", image_url, count=1)


def load_catalog_by_key() -> dict:
    """(store_id, product_id) -> dict of the display fields the review UI
    shows for a candidate. Loaded once per process; this is a review tool,
    not a long-running server, so no cache invalidation is needed."""
    by_key = {}
    with open(FROZEN_CATALOG_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (int(row["store_id"]), row["product_id"])
            by_key[key] = {field: row.get(field, "") for field in CATALOG_DISPLAY_FIELDS}
    return by_key


def load_image_by_key() -> dict:
    """(store_id, product_id) -> raw image_url, read straight from the raw
    scraper CSVs rather than the frozen/normalized catalog. image_url was
    never part of the frozen schema, so adding it here can't change
    catalog_version and can't stale any existing review decision."""
    by_key = {}
    for _name, run_prefix, store_id in RUN_STORES:
        store_dir = RUNS_ROOT / run_prefix
        run_dir = latest_run_dir(store_dir) if store_dir.exists() else None
        if run_dir is None:
            continue
        with open(run_dir / "items.csv", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                url = (row.get("image_url") or "").strip()
                if url:
                    by_key[(int(store_id), row.get("item_id", ""))] = url

    if DASHMART_CSV.exists():
        with open(DASHMART_CSV, newline="", encoding="utf-8") as f:
            all_rows = list(csv.DictReader(f))
        dashmart_rows, _snapshot_id = latest_snapshot_only(all_rows)
        for row in dashmart_rows:
            url = (row.get("image_url") or "").strip()
            if url:
                by_key[(int(DASHMART_ID), row.get("item_id", ""))] = url
    return by_key


CATALOG_BY_KEY = load_catalog_by_key()
IMAGE_BY_KEY = load_image_by_key()

# Kept in sync by hand with the "Version: vN" line at the top of
# LABELING_GUIDELINES.md -- bump both together.
LABELING_GUIDELINE_VERSION = "v1"

VALID_LABELS = {"Acceptable", "Needs clarification", "Incorrect"}

REQUESTS_BY_ID = {r["request_id"]: r for r in REQUESTS}


def _decision_key(request_id, store_id, product_id) -> str:
    return f"{request_id}|{store_id}|{product_id}"


def load_pools() -> list:
    if not CANDIDATE_POOL_PATH.exists():
        raise SystemExit(f"{CANDIDATE_POOL_PATH.name} not found -- run build_candidate_pool.py first")
    return json.loads(CANDIDATE_POOL_PATH.read_text())


def load_decisions() -> dict:
    if DECISIONS_PATH.exists():
        return json.loads(DECISIONS_PATH.read_text())
    return {}


def save_decisions_atomic(decisions: dict) -> None:
    fd, tmp_path = tempfile.mkstemp(dir=HERE, prefix=".label_review_decisions_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(decisions, f, indent=2, sort_keys=True)
        os.replace(tmp_path, DECISIONS_PATH)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def current_catalog_sha256() -> str:
    if not MANIFEST_PATH.exists():
        return None
    manifest = json.loads(MANIFEST_PATH.read_text())
    return manifest.get("catalog_version", {}).get("sha256")


def build_queue(pools: list, decisions: dict) -> list:
    """Flat list of {request_id, store_id, product_id} items, grouped by
    paraphrase_group so related requests are reviewed near each other.

    Excludes candidates claude_auto_label.py already resolved by explicit
    attribute comparison (reviewed_by == "claude_auto") -- those are the
    "clear and obvious" cases. Also excludes anything already decided at
    all (reviewed_by == "human" from a prior UI session or chat), so this
    queue holds only the still-pending stratified sample -- nothing
    "Recorded" left to scroll past."""
    pools_by_id = {p["request_id"]: p for p in pools}
    groups = {}
    for r in REQUESTS:
        groups.setdefault(r["paraphrase_group"], []).append(r["request_id"])

    queue = []
    for group in sorted(groups):
        for request_id in groups[group]:
            pool = pools_by_id.get(request_id)
            if not pool:
                continue
            for c in pool["candidates"]:
                key = _decision_key(request_id, c["store_id"], c["product_id"])
                if key in decisions:
                    continue
                queue.append({"request_id": request_id, "store_id": c["store_id"], "product_id": c["product_id"]})
    return queue


class Handler(BaseHTTPRequestHandler):
    server_version = "LabelReviewUI/1"

    def log_message(self, fmt, *args):
        pass  # quiet -- this is a local review tool, not a debugged service

    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw or b"{}")

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/api/queue":
            pools = load_pools()
            pools_by_key = {
                (p["request_id"], c["store_id"], c["product_id"]): c
                for p in pools for c in p["candidates"]
            }
            decisions = load_decisions()
            queue = build_queue(pools, decisions)
            items = []
            for item in queue:
                request = REQUESTS_BY_ID[item["request_id"]]
                candidate = pools_by_key.get((item["request_id"], item["store_id"], item["product_id"]), {})
                key = _decision_key(item["request_id"], item["store_id"], item["product_id"])
                decision = decisions.get(key)
                product = CATALOG_BY_KEY.get((item["store_id"], item["product_id"]), {})
                image_url = IMAGE_BY_KEY.get((item["store_id"], item["product_id"]), "")
                items.append({
                    "key": key,
                    "request_id": item["request_id"],
                    "request_text": request["text"],
                    "expected": request["expected"],
                    "paraphrase_group": request["paraphrase_group"],
                    "store_id": item["store_id"],
                    "product_id": item["product_id"],
                    "product": product,
                    "thumbnail_url": thumbnail_url(image_url),
                    "reviewed": decision is not None,
                    "reviewer_label": decision["reviewer_label"] if decision else None,
                    "revealed": decision.get("revealed", False) if decision else False,
                    "draft_label": candidate.get("draft_label"),
                    "draft_reason": candidate.get("draft_reason"),
                    "sources": candidate.get("sources"),
                })
            self._send_json({"items": items})
            return

        self.send_error(404)

    def do_POST(self):
        if self.path == "/api/decide":
            body = self._read_json_body()
            request_id, store_id, product_id, label = (
                body.get("request_id"), body.get("store_id"), body.get("product_id"), body.get("label"),
            )
            if label not in VALID_LABELS:
                self._send_json({"error": f"label must be one of {sorted(VALID_LABELS)}"}, status=400)
                return

            decisions = load_decisions()
            key = _decision_key(request_id, store_id, product_id)
            existing = decisions.get(key, {})
            decisions[key] = {
                **existing,
                "request_id": request_id,
                "store_id": store_id,
                "product_id": product_id,
                "reviewer_label": label,
                "catalog_version_sha256": current_catalog_sha256(),
                "request_version": REQUEST_VERSION,
                "labeling_guideline_version": LABELING_GUIDELINE_VERSION,
                "reviewed_by": "human",
                "revealed": existing.get("revealed", False),
                "draft_label": existing.get("draft_label"),
                "agreed_with_draft": existing.get("agreed_with_draft"),
            }
            save_decisions_atomic(decisions)
            self._send_json({"ok": True})
            return

        if self.path == "/api/reveal":
            body = self._read_json_body()
            request_id, store_id, product_id = body.get("request_id"), body.get("store_id"), body.get("product_id")
            key = _decision_key(request_id, store_id, product_id)
            decisions = load_decisions()
            if key not in decisions:
                self._send_json({"error": "submit a decision before revealing the draft"}, status=400)
                return

            pools = load_pools()
            draft = None
            for p in pools:
                if p["request_id"] == request_id:
                    for c in p["candidates"]:
                        if c["store_id"] == store_id and c["product_id"] == product_id:
                            draft = c
                            break
            if draft is None:
                self._send_json({"error": "candidate not found"}, status=404)
                return

            decisions[key]["revealed"] = True
            decisions[key]["draft_label"] = draft["draft_label"]
            decisions[key]["agreed_with_draft"] = decisions[key]["reviewer_label"] == draft["draft_label"]
            save_decisions_atomic(decisions)
            self._send_json({
                "draft_label": draft["draft_label"],
                "draft_reason": draft["draft_reason"],
                "sources": draft["sources"],
                "scores": draft["scores"],
            })
            return

        self.send_error(404)


PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Checkpoint 3 label review</title>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; }
  .progress { color: #666; margin-bottom: 1rem; }
  .card { border: 1px solid #ccc; border-radius: 8px; padding: 1.25rem; }
  .request-text { font-size: 1.2rem; font-weight: 600; }
  .expected { color: #555; font-size: 0.9rem; margin: 0.5rem 0 1rem; }
  .candidate { font-size: 1.05rem; margin: 0.75rem 0; display: flex; gap: 1rem; align-items: flex-start; }
  .thumb { width: 280px; height: 280px; object-fit: contain; border: 1px solid #ddd; border-radius: 6px; background: #fafafa; flex-shrink: 0; }
  .attr { color: #444; font-size: 0.95rem; }
  .buttons { display: flex; gap: 0.5rem; margin-top: 1rem; }
  button { padding: 0.6rem 1rem; font-size: 1rem; cursor: pointer; }
  button.acceptable { background: #d6f5d6; }
  button.clarify { background: #fff3cd; }
  button.incorrect { background: #f8d7da; }
  .reveal { margin-top: 1rem; color: #333; }
  .nav { margin-top: 1rem; display: flex; gap: 0.5rem; }
  .done { color: green; font-weight: 600; }
</style>
</head>
<body>
<div class="progress" id="progress"></div>
<div class="card" id="card">Loading...</div>
<div class="nav">
  <button onclick="prevItem()">&larr; prev</button>
  <button onclick="nextItem()">next &rarr;</button>
  <button onclick="revealDraft()" id="revealBtn" style="display:none">reveal AI suggestion</button>
</div>
<script>
let items = [];
let idx = 0;

async function loadQueue() {
  const res = await fetch('/api/queue');
  const data = await res.json();
  items = data.items;
  idx = items.findIndex(it => !it.reviewed);
  if (idx === -1) idx = 0;
  render();
}

function render() {
  const it = items[idx];
  document.getElementById('progress').textContent =
    `Item ${idx + 1} of ${items.length} -- request ${it.request_id} (group ${it.paraphrase_group}) -- `
    + `${items.filter(x => x.reviewed).length} reviewed so far`;

  const expectedBits = Object.entries(it.expected || {})
    .filter(([k, v]) => v !== null && v !== undefined && !(typeof v === 'object' && Object.keys(v).length === 0))
    .map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(' | ');

  let html = `
    <div class="request-text">${escapeHtml(it.request_text)}</div>
    <div class="expected">expected: ${escapeHtml(expectedBits || '(none specified)')}</div>
    <div class="candidate">
      ${it.thumbnail_url ? `<img class="thumb" src="${it.thumbnail_url}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">` : '<div class="thumb" style="display:flex;align-items:center;justify-content:center;color:#bbb;font-size:0.8rem;">no photo</div>'}
      <div>
        <b>${escapeHtml(it.product.raw_title || '(no title)')}</b>
        <div class="attr">
          ${escapeHtml(it.product.store_name || it.store_id)}
          &middot; size: ${escapeHtml(it.product.raw_size || '(none)')}
          &middot; category: ${escapeHtml(it.product.raw_category || '(none)')}
          ${it.product.price_cents ? '&middot; $' + (parseInt(it.product.price_cents) / 100).toFixed(2) : ''}
        </div>
        <div class="attr" style="color:#999">product ${it.product_id}</div>
      </div>
    </div>
    <div class="buttons">
      <button class="acceptable" onclick="decide('Acceptable')">1: Acceptable</button>
      <button class="clarify" onclick="decide('Needs clarification')">2: Needs clarification</button>
      <button class="incorrect" onclick="decide('Incorrect')">3: Incorrect</button>
    </div>
  `;
  if (it.reviewed) {
    html += `<div class="done">Recorded: ${it.reviewer_label}</div>`;
  }
  document.getElementById('card').innerHTML = html;
  document.getElementById('revealBtn').style.display = it.reviewed ? 'inline-block' : 'none';
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function decide(label) {
  const it = items[idx];
  await fetch('/api/decide', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({request_id: it.request_id, store_id: it.store_id, product_id: it.product_id, label}),
  });
  it.reviewed = true;
  it.reviewer_label = label;
  nextItem();
}

async function revealDraft() {
  const it = items[idx];
  const res = await fetch('/api/reveal', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({request_id: it.request_id, store_id: it.store_id, product_id: it.product_id}),
  });
  const data = await res.json();
  if (data.error) { alert(data.error); return; }
  document.getElementById('card').innerHTML += `
    <div class="reveal">
      AI draft was: <b>${escapeHtml(data.draft_label)}</b><br>
      reason: ${escapeHtml(data.draft_reason)}<br>
      sources: ${escapeHtml((data.sources || []).join(', '))}
    </div>`;
}

function nextItem() { if (idx < items.length - 1) { idx++; render(); } else { render(); } }
function prevItem() { if (idx > 0) { idx--; render(); } }

document.addEventListener('keydown', (e) => {
  if (e.key === '1') decide('Acceptable');
  else if (e.key === '2') decide('Needs clarification');
  else if (e.key === '3') decide('Incorrect');
  else if (e.key === 'ArrowRight') nextItem();
  else if (e.key === 'ArrowLeft') prevItem();
});

loadQueue();
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", type=int, default=8766)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Serving label review UI on {url}")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
