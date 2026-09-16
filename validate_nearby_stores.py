#!/usr/bin/env python3
"""Sample at most ten unique products per discovered store; never run a full crawl.
Discovery input comes from DoorDash's 92117 browser listing, not a nationwide API.
A page response contains more than ten cards; only ten are decoded/retained.
"""
import csv, json, re, time
from pathlib import Path
from datetime import datetime, timezone
import requests
from doordash_dashmart_scraper import BASE_HEADERS, extract_flight

ROOT = Path(__file__).resolve().parent / 'validation_92117'
DECODER = json.JSONDecoder()
LIMIT = 10

def objects(text, marker, object_marker=False):
    for m in re.finditer(re.escape(marker), text):
        try:
            yield DECODER.raw_decode(text, m.start() if object_marker else m.end())[0]
        except (ValueError, TypeError):
            continue

def sample(text, store_id, found, source):
    flight = extract_flight(text)
    for obj in objects(flight, '"item_data":'):
        if str(obj.get('store_id')) != store_id:
            continue
        price = obj.get('price') or {}
        iid, name = str(obj.get('item_id') or ''), obj.get('item_name')
        if not iid or not name or price.get('unit_amount') is None:
            continue
        found.setdefault(iid, dict(item_id=iid, item_name=name,
            price=price.get('display_string'), currency=price.get('currency'),
            price_amount=price['unit_amount']/10**price.get('decimal_places',2),
            source_url=source, parser='retail_item_data'))
        if len(found) == LIMIT:
            return
    for obj in objects(flight, '{"__typename":"MenuPageItem",', True):
        iid, name = str(obj.get('id') or ''), obj.get('name')
        price = (obj.get('quickAddContext') or {}).get('price') or {}
        display = obj.get('displayPrice') or price.get('displayString')
        if not iid or not name or not display:
            continue
        found.setdefault(iid, dict(item_id=iid,item_name=name,price=display,
            currency=price.get('currency'), price_amount=(price['unitAmount']/10**price.get('decimalPlaces',2)) if price.get('unitAmount') is not None else None,
            source_url=source,parser='standard_menu_item'))
        if len(found) == LIMIT:
            return

def main():
    stores=list(csv.DictReader((ROOT/'discovered_stores.tsv').open(),delimiter='\t'))
    report_path=ROOT/'validation.json'
    reports=json.loads(report_path.read_text()) if report_path.exists() else []
    done={r['store_id'] for r in reports}
    session=requests.Session();session.headers.update(BASE_HEADERS)
    for n,store in enumerate(stores,1):
        sid=store['store_id']
        if sid in done: continue
        prefix='/convenience/store/' if store['layout']=='retail' else '/store/'
        url=f'https://www.doordash.com{prefix}{sid}/'
        result={**store,'discovery_zip':'92117','source_url':url,'checked_at':datetime.now(timezone.utc).isoformat(),'requests':[]}
        found={};queue=[url];seen=set()
        while queue and len(found)<LIMIT and len(seen)<3:
            current=queue.pop(0)
            if current in seen: continue
            seen.add(current)
            try:
                response=session.get(current,timeout=25)
                result['requests'].append({'url':current,'status':response.status_code})
                if response.status_code in (429,500,502,503,504):
                    time.sleep(12)
                    response=session.get(current,timeout=25)
                    result['requests'].append({'url':current,'status':response.status_code})
                if response.status_code!=200: continue
                sample(response.text,sid,found,response.url)
                if len(found)<LIMIT:
                    paths=list(dict.fromkeys(re.findall(rf'/convenience/store/{sid}/category/[a-zA-Z0-9%\-]+',response.text)))
                    queue.extend('https://www.doordash.com'+p for p in paths[:2])
            except requests.RequestException as e:
                result['requests'].append({'url':current,'error':type(e).__name__})
            time.sleep(1)
        assert len(found)<=LIMIT
        result['products_found']=len(found)
        result['status']='passed' if len(found)==LIMIT else 'insufficient_products' if found else 'no_products_or_blocked'
        # Publish complete groups only: never pad or duplicate to reach ten.
        result['products']=list(found.values()) if len(found)==LIMIT else []
        reports.append(result)
        report_path.write_text(json.dumps(reports,ensure_ascii=False,indent=2))
        print(f'{n}/{len(stores)} {store["store_name"]} ({sid}): {result["status"]} [{len(found)}/10]',flush=True)
    print('Complete:',sum(r['status']=='passed' for r in reports),'passed of',len(reports),flush=True)

if __name__=='__main__': main()
