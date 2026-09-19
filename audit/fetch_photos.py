"""Download the public product photos already linked by the saved catalog."""
import concurrent.futures
import json
from pathlib import Path
import urllib.request

HERE = Path(__file__).resolve().parent
OUT = HERE / "photos"
OUT.mkdir(exist_ok=True)
rows = json.loads((HERE / "photo_sources.json").read_text())


def fetch(row):
    target = OUT / f"{row['photo_index']:03}.img"
    try:
        request = urllib.request.Request(row["image_url"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=25) as response:
            target.write_bytes(response.read())
        return {"photo_index": row["photo_index"], "path": str(target), "ok": True}
    except Exception as exc:
        return {"photo_index": row["photo_index"], "ok": False, "error": str(exc)}


with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
    results = list(executor.map(fetch, rows))
(HERE / "photo_downloads.json").write_text(json.dumps(results, indent=2))
print(f"Downloaded {sum(r['ok'] for r in results)}/{len(results)} photos")
