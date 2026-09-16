import json,html
from pathlib import Path
from collections import Counter
p=Path(__file__).resolve().parent
rows=json.loads((p/'validation.json').read_text())
e=lambda x:html.escape(str(x if x is not None else ''))
passed=sum(r['status']=='passed' for r in rows)
items=[dict(store_id=r['store_id'],store_name=r['store_name'],**v) for r in rows for v in r['products']]
counts=Counter(i['store_id'] for i in items)
assert all(v==10 for v in counts.values())
assert len({(i['store_id'],i['item_id']) for i in items})==len(items)
assert all(i['item_name'] and i['price'] for i in items)
(p/'products_10_each.json').write_text(json.dumps(items,indent=2,ensure_ascii=False))
body=[]
for r in sorted(rows,key=lambda r:r['store_name'].lower()):
 products=''.join('<tr><td>'+e(i['item_name'])+'</td><td>'+e(i['item_id'])+'</td><td>'+e(i['price'])+'</td></tr>' for i in r['products'])
 detail=('<details><summary>View 10 products</summary><table><tr><th>Product</th><th>Product ID</th><th>Price</th></tr>'+products+'</table></details>') if products else '<span class="muted">'+e(r['products_found'])+' valid products found; no sample published.</span>'
 status='10 / 10' if products else r['status'].replace('_',' ')
 body.append('<tr class="store"><td><a href="'+e(r['source_url'])+'">'+e(r['store_name'])+'</a></td><td>'+e(r['store_id'])+'</td><td>'+e(r['layout'])+'</td><td>'+e(status)+'</td><td>'+detail+'</td></tr>')
page='''<!doctype html><html><head><meta charset="utf-8"><title>92117 store validation</title><style>
body{font:15px system-ui,sans-serif;max-width:1450px;margin:40px auto;padding:0 24px;color:#182722;background:#f8faf9}h1{font-size:34px}p{max-width:1000px;line-height:1.6}.stats{font-size:22px;color:#136546}table{border-collapse:collapse;width:100%;background:white}td,th{text-align:left;padding:12px;border-bottom:1px solid #dce5df;vertical-align:top}th{background:#e8f0eb}a{color:#136546}summary{cursor:pointer;white-space:nowrap}details table{margin-top:12px;font-size:13px}.muted{color:#66746b}input{font:inherit;padding:12px;width:320px;margin:12px 0 20px;border:1px solid #aabbaf;border-radius:6px}footer{margin:25px 0;color:#66746b}</style></head><body>
<h1>Nearby stores · 92117</h1>'''+f'<p class="stats">{len(rows)} stores tested · {passed} passed · {len(rows)-passed} incomplete · {len(items)} products saved</p>'+'''<p>Stores discovered in DoorDash’s expanded Grocery listing with delivery location set to ZIP 92117. This view also includes liquor, deli, and specialty listings, and stores marked farther away. This is one listing snapshot, not a complete geographic census or a delivery guarantee.</p><p>Each successful store has exactly 10 unique products. Incomplete stores have no published product sample. Store pages were fetched fresh; closed stores may still expose their catalogs.</p><input id="filter" placeholder="Filter by store name or ID" aria-label="Filter stores"><table><thead><tr><th>Store</th><th>Store ID</th><th>Page format</th><th>Validation</th><th>Product sample</th></tr></thead><tbody>'''+''.join(body)+'''</tbody></table><footer>Source: DoorDash · Original inventory files preserved. Details and request status are in validation.json.</footer><script>document.getElementById('filter').addEventListener('input',e=>{let q=e.target.value.toLowerCase();document.querySelectorAll('tr.store').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q));});</script></body></html>'''
(p/'report.html').write_text(page)
print(f'{len(rows)} stores; {passed} passed; {len(items)} products; all groups exactly ten, unique and priced.')
print('Incomplete:',[(r['store_name'],r['store_id'],r['products_found']) for r in rows if r['status']!='passed'])
