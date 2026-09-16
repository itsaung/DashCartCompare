#!/usr/bin/env python3
"""
DoorDash DashMart / convenience-store catalog scraper.

Given a store ID (the number in a URL like
https://www.doordash.com/convenience/store/1042759/), this pulls every
item it can find across every category and sub-category into a CSV.

How it works (see doordash_scrape_findings.md for the full writeup):
  - DoorDash server-renders each page's data as JSON inside
    <script>self.__next_f.push([id, "..."])</script> tags (Next.js RSC
    "flight" payloads). We fetch the raw HTML with `requests` (no
    headless browser, no login) and regex/JSON-parse that data out
    directly.
  - A category page (e.g. /category/snacks-758) only server-renders a
    partial batch of items even though it reports a much larger
    `results` count. Each category also has "sub-category" chip pages
    (e.g. /category/snacks-758/sub-category/chips-765) which are
    individually smaller and mostly load in full. Crawling every
    category + every sub-category recovers the large majority of the
    catalog (~75-95% typically; a handful of oversized sub-categories,
    e.g. "Chips", still exceed a single page's batch).
  - DoorDash rate-limits (HTTP 429) after roughly 100-150 rapid
    requests. This script retries 429/5xx with exponential backoff plus
    jitter (a fixed-multiple linear delay in an earlier version looked
    like backoff but wasn't, and gave every worker the same retry time,
    which just re-synchronizes a burst instead of spreading it out). A
    shared `Pacer` also puts every worker on a brief global cooldown the
    moment any one of them sees a 429, and honors a server `Retry-After`
    header outright when present, rather than each thread independently
    retrying back into the same rate limit.
  - Every attempt of every fetch is logged (status code, exception type,
    elapsed time, response size) -- not just the last one, which used to
    erase evidence of transient failures a later attempt recovered from --
    and a run's retry pass reports pages recovered vs. pages still failing
    after the retry, instead of only the final item total. A page that
    returns HTTP success but parses zero items is counted and reported
    separately, since that's currently indistinguishable from a genuinely
    empty sub-category without manual inspection. A summary
    (`<output>.summary.json`, with the run's concurrency/pacing settings and
    wall-clock duration) and, when anything didn't fully recover, a
    `<output>.failed_pages.json` are written next to the CSV every run.
    None of this claims full catalog completeness -- see the SSR-truncation
    point above, which this logging does not measure.

  - Beyond that, DoorDash's actual "load more" pagination is a GraphQL
    query (`categorySearch` -> `retailStoreCategoryFeed`) that takes a
    `cursor`: a base64-encoded JSON blob whose only field that changes
    across pages is `offset`. It requires DoorDash-specific client
    headers (apollographql-client-name, x-csrftoken, x-channel-id,
    x-experience-id) that a bare `requests` call doesn't send by
    default; without them the query is accepted but silently returns
    `products: []`. The exact header set and cursor shape here were
    extracted from a genuine request captured via Playwright network
    interception while scrolling, not guessed. This endpoint has a much
    stricter, longer-lived rate limit than the plain page fetches, so
    pagination is opt-in (`--paginate`) and runs sequentially with
    real delays, giving up gracefully per-page rather than hammering
    the endpoint into a long block.

Usage:
    python3 doordash_dashmart_scraper.py 1042759
    python3 doordash_dashmart_scraper.py 1042759 -o items.csv -c 6
    python3 doordash_dashmart_scraper.py 1042759 --paginate   # slower, more complete
    python3 doordash_dashmart_scraper.py 1042759 --details    # also fetch every product page

The CSV includes a scraped_at timestamp plus sale/original price, discount %,
stock count, unit size/$ per oz (derived from the package size when DoorDash
omits it on the card), and expires-soon. Each run appends to the output file
so snapshots accumulate for later analysis. Best-by dates and "recently sold"
are rendered only in the hydrated product modal, not in list HTML or the
item-page API — those columns stay blank unless a later source appears.

Requires only the `requests` package.
"""

import argparse
import base64
import csv
import json
import os
import random
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

import requests

BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "sec-ch-ua": '"Chromium";v="120", "Not(A:Brand";v="24", "Google Chrome";v="120"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "referer": "https://www.doordash.com/",
}

PUSH_RE = re.compile(r"self\.__next_f\.push\(")

# --- GraphQL pagination (opt-in, see module docstring) ---

GRAPHQL_HEADERS = {
    "content-type": "application/json",
    "accept": "*/*",
    "apollographql-client-name": "@doordash/app-consumer-production-ssr-client",
    "apollographql-client-version": "3.0",
    "x-csrftoken": "",
    "x-channel-id": "marketplace",
    "x-experience-id": "doordash",
}

CATEGORY_SEARCH_QUERY = """query categorySearch($storeId: ID!, $categoryId: ID!, $subCategoryId: ID, $limit: Int, $cursor: String, $sortBysList: [RetailSortByOption!]!, $filterQuery: String, $filterKeysList: [String!], $aggregateStoreIds: [String!]) {
  retailStoreCategoryFeed(storeId: $storeId, l1CategoryId: $categoryId, l2CategoryId: $subCategoryId, limit: $limit, cursor: $cursor, sortBysList: $sortBysList, filterQuery: $filterQuery, filterKeysList: $filterKeysList, aggregateStoreIds: $aggregateStoreIds) {
    totalItemCount
    products {
      id
      name
      imageUrl
      itemLimit
      soldAsInfoShortText
      soldAsInfoLongText
      displayUnit
      badgeEntries
      logging
      price { currency displayString decimalPlaces unitAmount sign symbol }
      priceList { priceType price { displayString unitAmount } additionalDisplayString }
      badges { type text }
      metadata {
        soldAsInfo {
          measurementUnit
          measurementFactor { decimalPlaces unitAmount }
          measurementPrice { currency displayString decimalPlaces unitAmount }
        }
      }
      ratings { averageRating displayNumRatings numOfRatings }
    }
    pageInfo { cursor hasNextPage }
  }
}"""

_CURSOR_TEMPLATE = {
    "offset": 0, "content_ids": [], "request_parent_id": "", "request_child_id": "",
    "request_child_component_id": "", "cross_vertical_page_type": "DEFAULT_HOMEPAGE",
    "page_stack_trace": [], "vertical_ids": [], "vertical_context_id": None,
    "layout_override": "UNSPECIFIED", "single_store_id": None, "search_item_carousel_cursor": None,
    "category_ids": [], "collection_ids": [], "is_pagination_fallback": None, "source_page_type": None,
    "geo_type": "", "geo_id": "", "keyword": "", "ads_cursor_cache_key": None,
    "visual_aisles_insertion_index": 0,
    "baseCursor": {"page_id": "", "page_type": "NOT_APPLICABLE", "cursor_version": "FACET"},
    "vertical_names": {}, "item_ids": [], "merchant_supplied_ids": [], "is_out_of_stock": None,
    "menu_id": None, "tracking": None, "dietary_tag": None, "origin_title": None,
    "ranked_remaining_collection_ids": None, "previously_seen_collection_ids": [],
    "precheckout_bundle_search_info": None, "total_items_offset": 0, "total_ads_previously_blended": 0,
    "vertical_title": None, "multi_store_entities": [], "last_seen_item_ids": [],
    "last_inserted_row_index": None, "cursorVersion": "FACET_CONTENT_OFFSET", "pageId": "",
    "pageType": "NOT_APPLICABLE",
}


def make_cursor(offset: int) -> str:
    payload = dict(_CURSOR_TEMPLATE, offset=offset)
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.b64encode(raw).decode()


def graphql_category_page(session: requests.Session, store_id: str, category_slug: str, subcat_slug: str | None, offset: int, limit: int = 50):
    """One page of the real categorySearch GraphQL pagination. Returns (products, has_next_page) or (None, None) on failure."""
    variables = {
        "storeId": store_id,
        "categoryId": category_slug,
        "sortBysList": ["UNSPECIFIED"],
        "cursor": make_cursor(offset),
        "limit": limit,
        "filterQuery": "",
        "filterKeysList": [],
        "aggregateStoreIds": [],
    }
    if subcat_slug:
        variables["subCategoryId"] = subcat_slug
    body = {"operationName": "categorySearch", "variables": variables, "query": CATEGORY_SEARCH_QUERY}
    try:
        resp = session.post(
            "https://www.doordash.com/graphql/categorySearch?operation=categorySearch",
            json=body,
            timeout=30,
        )
    except requests.RequestException:
        return None, None
    if resp.status_code != 200:
        return None, None
    try:
        data = resp.json()["data"]["retailStoreCategoryFeed"]
    except (KeyError, TypeError, ValueError):
        return None, None
    return data.get("products") or [], bool(data.get("pageInfo", {}).get("hasNextPage"))


LABEL_RE = re.compile(r'"label":"([^"]+)","priority_level":"[^"]+","value":"((?:[^"\\]|\\.)*)"')
SALE_FROM_RE = re.compile(r"^\$([\d.]+)(?: on sale from \$([\d.]+))?$")
OZ_RE = re.compile(r"([\d.]+)\s*oz", re.I)
EXPIRES_PREFIX = "Expires Soon "


def cents_display(cents: str) -> str:
    if not cents:
        return ""
    try:
        return f"${int(cents) / 100:.2f}"
    except ValueError:
        return ""


def usd_amount(cents: str) -> str:
    if not cents:
        return ""
    try:
        return f"{int(cents) / 100:.2f}"
    except ValueError:
        return ""


def unit_fields(name: str, sold_as: str, price_usd: str) -> tuple[str, str]:
    size = (sold_as or "").strip()
    if "•" in size:
        left, _, right = size.partition("•")
        return left.strip(), right.strip()
    if not size:
        m = re.search(r"\(([^)]+)\)\s*$", name)
        size = m.group(1) if m else ""
    unit_price = ""
    oz = OZ_RE.search(size)
    if oz and price_usd:
        try:
            unit_price = f"${float(price_usd) / float(oz.group(1)):.2f}/oz"
        except ValueError:
            pass
    return size, unit_price


def parse_item_fields(raw: dict) -> dict:
    """Normalize list-card / GraphQL fields into the CSV shape."""
    name = unescape(raw.get("item_name") or "")
    expires_soon = "yes" if name.startswith(EXPIRES_PREFIX) else ""
    if name.startswith(EXPIRES_PREFIX):
        name = name[len(EXPIRES_PREFIX) :]

    labels = raw.get("labels") or {}
    badge_texts = list(raw.get("badge_texts") or [])
    for v in labels.get("badge") or []:
        if v and v not in badge_texts:
            badge_texts.append(v)

    price_display = raw.get("price_display") or ""
    unit_amount = raw.get("unit_amount") or ""
    original_display = cents_display(raw.get("non_discount_cents") or "")
    original_usd = usd_amount(raw.get("non_discount_cents") or "")

    item_prices = labels.get("item_price") or []
    a11y_price = unescape(item_prices[0] if item_prices else "")
    sale_m = SALE_FROM_RE.match(a11y_price)
    if sale_m:
        if not price_display:
            price_display = f"${sale_m.group(1)}"
        if not unit_amount:
            try:
                unit_amount = str(int(round(float(sale_m.group(1)) * 100)))
            except ValueError:
                pass
        if sale_m.group(2) and not original_display:
            original_display = f"${sale_m.group(2)}"
            try:
                original_usd = f"{float(sale_m.group(2)):.2f}"
            except ValueError:
                pass

    discount = next((b for b in badge_texts if "% off" in b.lower()), "")
    best_by = ""
    for b in badge_texts:
        if b.lower().startswith("best by "):
            best_by = b[8:].strip()
            break
    recently_sold = next((b for b in badge_texts if "recently sold" in b.lower()), "")
    snap = "yes" if any(b.strip().upper() == "SNAP" for b in badge_texts) else ""

    stock_badge = raw.get("badge") or ""
    if not stock_badge:
        stock_badge = next((b for b in badge_texts if "in stock" in b.lower() or b.lower() == "out of stock"), "")
    if not stock_badge and raw.get("item_limit"):
        stock_badge = f"{raw['item_limit']} in stock"

    price_usd = usd_amount(unit_amount)
    unit_size, unit_price = unit_fields(name, unescape(raw.get("sold_as") or ""), price_usd)
    rating_val, rating_count = parse_rating(raw.get("rating") or "")

    return {
        "category": raw.get("category") or "",
        "subcat": raw.get("subcat") or "",
        "item_id": raw.get("item_id") or "",
        "item_name": name,
        "expires_soon": expires_soon,
        "best_by": best_by,
        "price_display": price_display,
        "unit_amount": unit_amount,
        "original_display": original_display,
        "original_usd": original_usd,
        "discount": discount,
        "unit_size": unit_size,
        "unit_price": unit_price,
        "image": unescape(raw.get("image") or ""),
        "badge": stock_badge,
        "rating": raw.get("rating") or "",
        "recently_sold": recently_sold,
        "snap": snap,
        "rating_val": rating_val,
        "rating_count": rating_count,
        "price_usd": price_usd,
    }


def graphql_products_to_items(products: list, category: str, subcat: str) -> list:
    items = []
    for p in products:
        price = p.get("price") or {}
        ratings = p.get("ratings") or {}
        rating_text = ""
        if ratings.get("averageRating") is not None:
            rating_text = f"average rating of {ratings['averageRating']} stars, {ratings.get('displayNumRatings', '')}"
        item_limit = p.get("itemLimit")
        badges = p.get("badges") or []
        badge_texts = [b.get("text") or "" for b in badges if isinstance(b, dict)]
        logging = p.get("logging") or {}
        non_discount = ""
        if isinstance(logging, dict) and logging.get("non_discount_price") is not None:
            non_discount = str(logging["non_discount_price"])
        sold_as = p.get("soldAsInfoShortText") or p.get("soldAsInfoLongText") or ""
        meta = ((p.get("metadata") or {}).get("soldAsInfo") or {})
        meas_price = ((meta.get("measurementPrice") or {}).get("displayString") or "")
        meas_unit = meta.get("measurementUnit") or ""
        factor = meta.get("measurementFactor") or {}
        if not sold_as and meas_unit and factor.get("unitAmount") is not None:
            amt = int(factor["unitAmount"]) / (10 ** int(factor.get("decimalPlaces") or 0))
            sold_as = f"{amt:g} {meas_unit}".strip()
            if meas_price:
                sold_as = f"{sold_as} • {meas_price}"
        items.append(
            parse_item_fields(
                {
                    "category": category,
                    "subcat": subcat,
                    "item_id": str(p.get("id", "")),
                    "item_name": p.get("name", "") or "",
                    "price_display": price.get("displayString", ""),
                    "unit_amount": str(price.get("unitAmount", "")) if price.get("unitAmount") is not None else "",
                    "image": p.get("imageUrl", "") or "",
                    "badge": f"{item_limit} in stock" if item_limit is not None else "",
                    "rating": rating_text,
                    "sold_as": sold_as,
                    "badge_texts": badge_texts,
                    "non_discount_cents": non_discount,
                    "item_limit": str(item_limit) if item_limit is not None else "",
                }
            )
        )
    return [it for it in items if it["item_id"] and it["item_id"] != "None"]


def paginate_category_graphql(
    session: requests.Session,
    store_id: str,
    category_slug: str,
    subcat_slug: str | None,
    category_name: str,
    subcat_name: str,
    start_offset: int = 50,
    limit: int = 50,
    max_pages: int = 15,
    delay: float = 3.0,
):
    """Continue past the SSR page's initial batch using the real load-more endpoint.
    Sequential and conservative on purpose - this endpoint's rate limit is much
    stricter than the plain page fetches. Gives up quietly on repeated failure
    rather than retrying hard, so one blocked page never derails the run."""
    all_items = []
    offset = start_offset
    consecutive_failures = 0
    for _ in range(max_pages):
        products, has_next = graphql_category_page(session, store_id, category_slug, subcat_slug, offset, limit)
        if products is None:
            consecutive_failures += 1
            if consecutive_failures >= 2:
                break
            time.sleep(delay * 3)
            continue
        consecutive_failures = 0
        if not products:
            break
        all_items.extend(graphql_products_to_items(products, category_name, subcat_name))
        if not has_next:
            break
        offset += limit
        time.sleep(delay)
    return all_items


def extract_flight(html: str) -> str:
    """Concatenate every Next.js RSC flight-payload string embedded in the page."""
    combined_parts = []
    for chunk in html.split("<script>")[1:]:
        chunk = chunk.split("</script>", 1)[0]
        if not chunk.startswith("self.__next_f.push("):
            continue
        inner = chunk[len("self.__next_f.push(") : chunk.rfind(")")]
        try:
            arr = json.loads(inner)
        except json.JSONDecodeError:
            continue
        if len(arr) > 1 and isinstance(arr[1], str):
            combined_parts.append(arr[1])
    return "".join(combined_parts)


_FIELD_CACHE = {}


def _get(text: str, pattern: str):
    rx = _FIELD_CACHE.get(pattern)
    if rx is None:
        rx = _FIELD_CACHE[pattern] = re.compile(pattern)
    m = rx.search(text)
    return m.group(1) if m else ""


def extract_items(combined: str, category: str, subcat: str) -> list:
    """Pull item records out of a concatenated flight-payload string."""
    items = []
    marker = '"item_data":{'
    idx = 0
    while True:
        idx = combined.find(marker, idx)
        if idx == -1:
            break
        before = combined[max(0, idx - 900) : idx]
        win = combined[idx : idx + 4000]

        item_id = _get(win, r'"item_id":"(\d+)"')
        item_name = _get(win, r'"item_name":"((?:[^"\\]|\\.)*)"')
        price_display = _get(win, r'"price":\{[^}]*?"display_string":"((?:[^"\\]|\\.)*)"')
        unit_amount = _get(win, r'"unit_amount":(\d+)')
        image = _get(before, r'"uri":"((?:[^"\\]|\\.)*)"\}\}')
        rating = _get(before, r'"value":"(average rating[^"]*)"')
        item_limit = _get(win, r'"item_limit_data":\{"limit":"(\d+)"')
        non_discount_cents = _get(win, r'"non_discount_price":(\d+)')
        sold_as = _get(win, r'"sold_as_info_short_string":"((?:[^"\\]|\\.)*)"')

        labels = {}
        for label, value in LABEL_RE.findall(before):
            labels.setdefault(label, []).append(value)
        badge_texts = [m.group(1) for m in re.finditer(r'"badgeText":"((?:[^"\\]|\\.)*)"', win) if m.group(1)]
        for v in labels.get("badge") or []:
            if v and v not in badge_texts:
                badge_texts.append(v)

        if item_id:
            items.append(
                parse_item_fields(
                    {
                        "category": category,
                        "subcat": subcat,
                        "item_id": item_id,
                        "item_name": item_name,
                        "price_display": price_display,
                        "unit_amount": unit_amount,
                        "image": image,
                        "badge": next((b for b in badge_texts if "in stock" in b.lower()), ""),
                        "rating": rating,
                        "sold_as": sold_as,
                        "badge_texts": badge_texts,
                        "non_discount_cents": non_discount_cents,
                        "item_limit": item_limit,
                        "labels": labels,
                    }
                )
            )
        idx += len(marker)
    return items


class Pacer:
    """Shared request pacing across every worker thread.

    Two jobs: (1) space out request *dispatch* so `concurrency` workers don't
    all fire at the same instant (a fixed minimum gap between dispatches,
    enforced under one lock), and (2) when any worker sees a 429, put every
    worker on hold until a shared cooldown clears, instead of each thread
    independently retrying back into the same rate limit.
    """

    def __init__(self, min_interval: float = 0.15):
        self.min_interval = min_interval
        self._lock = Lock()
        self._next_ok = 0.0
        self._cooldown_until = 0.0

    def wait(self) -> None:
        # A worker can reserve a dispatch slot, release the lock, and sleep --
        # during which another worker's 429 pushes _cooldown_until further
        # out. Without rechecking after waking, the first worker would still
        # dispatch at its stale reserved time, defeating the cooldown. So
        # loop: reserve, sleep, then confirm the cooldown hasn't since moved
        # past "now" before actually returning.
        while True:
            with self._lock:
                now = time.monotonic()
                target = max(self._next_ok, self._cooldown_until, now)
                self._next_ok = target + self.min_interval
            remaining = target - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            with self._lock:
                if self._cooldown_until <= time.monotonic():
                    return

    def trigger_cooldown(self, seconds: float) -> None:
        with self._lock:
            self._cooldown_until = max(self._cooldown_until, time.monotonic() + seconds)


def backoff_delay(attempt: int, retry_after: float | None) -> float:
    """Exponential backoff with jitter; a server-supplied Retry-After wins outright.

    Jitter (a random component, not just a growing fixed delay) matters here
    specifically because requests are fired from a thread pool: without it,
    every worker that got 429'd in the same instant would sleep the exact
    same duration and then retry in the exact same instant again.
    """
    if retry_after is not None:
        return retry_after + random.uniform(0, 1.0)
    base = min(30.0, 2.0 ** attempt)
    return base + random.uniform(0, base * 0.5)


def retry_after_seconds(resp: "requests.Response | None") -> float | None:
    if resp is None:
        return None
    header = resp.headers.get("Retry-After")
    if not header:
        return None
    try:
        return float(header)
    except ValueError:
        return None


def fetch(session: requests.Session, url: str, pacer: Pacer, max_attempts: int = 5) -> tuple:
    """GET url with retries. Returns (response_or_None, log).

    `log["attempts"]` is the full per-attempt history (status/error/elapsed/
    size for each try), not just the last one -- a request that failed twice
    on 429 and then succeeded used to leave no trace of those first two
    failures once it returned. `log["status"]`/`log["error"]` are convenience
    copies of the *final* attempt's outcome, for callers that just want a
    one-line summary.
    """
    log = {"url": url, "attempts": [], "status": None, "error": None}
    resp = None
    for attempt in range(max_attempts):
        pacer.wait()
        start = time.monotonic()
        try:
            resp = session.get(url, timeout=30)
        except requests.RequestException as exc:
            elapsed = time.monotonic() - start
            log["attempts"].append({"n": attempt + 1, "status": None, "error": type(exc).__name__, "elapsed": elapsed, "size": 0})
            resp = None
        else:
            elapsed = time.monotonic() - start
            size = len(resp.content or b"")
            log["attempts"].append({"n": attempt + 1, "status": resp.status_code, "error": None, "elapsed": elapsed, "size": size})
            if resp.status_code < 400:
                log["status"] = resp.status_code
                return resp, log
            if resp.status_code not in (429, 500, 502, 503, 504):
                log["status"] = resp.status_code
                return resp, log  # a real error (404 etc.) - don't retry
            if resp.status_code == 429:
                pacer.trigger_cooldown(retry_after_seconds(resp) or 15.0)
        if attempt < max_attempts - 1:
            time.sleep(backoff_delay(attempt, retry_after_seconds(resp)))
    last = log["attempts"][-1]
    log["status"], log["error"] = last["status"], last["error"]
    return resp, log


def discover_categories(session: requests.Session, store_id: str, pacer: Pacer) -> list:
    """Fetch the store home page and regex out every /category/{slug} link."""
    url = f"https://www.doordash.com/convenience/store/{store_id}/"
    resp, log = fetch(session, url, pacer)
    if resp is None or resp.status_code >= 400:
        raise RuntimeError(f"Could not load store home page (status={log['status']} error={log['error']})")
    slugs = sorted(set(re.findall(rf"/convenience/store/{store_id}/category/([a-zA-Z0-9%\-]+)", resp.text)))
    slugs = [s for s in slugs if s != "deals"]  # deals duplicates other categories, no unique SKUs
    return slugs


def discover_subcategories(session: requests.Session, store_id: str, cat_slug: str, pacer: Pacer) -> tuple:
    """Returns (subcat_slugs, failure_log_or_None). A failure here means the
    category's subcategories are unknown, not just that this one page failed
    -- silently returning [] would leave whole subcategory pages undiscovered
    without any record of it."""
    url = f"https://www.doordash.com/convenience/store/{store_id}/category/{cat_slug}"
    resp, log = fetch(session, url, pacer)
    if resp is None or resp.status_code >= 400:
        return [], {"category": cat_slug, **log}
    return sorted(set(re.findall(r"sub-category/([a-zA-Z0-9%\-]+)", resp.text))), None


def category_display_name(slug: str) -> str:
    name = urllib.parse.unquote_plus(slug)
    name = re.sub(r"-\d+$", "", name)
    return name.replace("&", "&").strip().title()


def process_job(session: requests.Session, store_id: str, category_slug: str, subcat_slug: str | None, pacer: Pacer):
    if subcat_slug:
        url = f"https://www.doordash.com/convenience/store/{store_id}/category/{category_slug}/sub-category/{subcat_slug}"
        subcat_name = category_display_name(subcat_slug)
    else:
        url = f"https://www.doordash.com/convenience/store/{store_id}/category/{category_slug}"
        subcat_name = ""
    resp, log = fetch(session, url, pacer)
    if resp is None or resp.status_code >= 400:
        return [], {"category": category_slug, "subcat": subcat_slug, **log}
    combined = extract_flight(resp.text)
    items = extract_items(combined, category_display_name(category_slug), subcat_name)
    return items, None


STOCK_RE = re.compile(r"(\d+)\s+in stock")
RATING_RE = re.compile(r"average rating of ([\d.]+) stars,\s*(.+)")


def stock_status(badge: str) -> str:
    if not badge:
        return ""
    if "20+" in badge:
        return "In stock (20+)"
    m = STOCK_RE.match(badge)
    if m:
        n = int(m.group(1))
        return f"In stock ({n})" if n > 0 else "Out of stock"
    return badge


def parse_rating(rating: str):
    if not rating:
        return "", ""
    m = RATING_RE.match(rating)
    if m:
        return m.group(1), m.group(2)
    return "", ""


def merge_item(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if v and not dst.get(k):
            dst[k] = v


PDP_BEST_RE = re.compile(r"Best by ([0-9]{1,2}/[0-9]{1,2})")
PDP_SOLD_RE = re.compile(r"([\d.]+k?\+? recently sold)", re.I)
PDP_UNIT_RE = re.compile(r"(\d[\d.]* oz)\s*[•·]\s*(\$[\d.]+/oz)")


def extract_pdp_details(html: str) -> dict:
    """Pull PDP-only badges (Best by, recently sold, $/oz) out of a product-page response."""
    out = {}
    m = PDP_BEST_RE.search(html)
    if m:
        out["best_by"] = m.group(1)
    m = re.search(r'data-testid="best_by:Best by ([^"]+)"', html)
    if m:
        out["best_by"] = m.group(1)
    m = PDP_SOLD_RE.search(html)
    if m:
        out["recently_sold"] = m.group(1)
    m = re.search(r'data-testid="recently_bought:([^"]+)"', html)
    if m:
        out["recently_sold"] = m.group(1)
    m = PDP_UNIT_RE.search(html)
    if m:
        out["unit_size"] = m.group(1)
        out["unit_price"] = m.group(2)
    if '"type":"snap"' in html or ">SNAP<" in html:
        out["snap"] = "yes"
    return out


def extract_mosaic_details(payload: dict) -> dict:
    """Pull price / unit-price strings out of the item-page mosaic JSON."""
    out = {}
    texts = []

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in (
                    "props.per-unit-price-string",
                    "props.strikethrough-price",
                    "props.price-row-accessibility-text",
                    "title.content",
                ) and isinstance(v, str) and v:
                    texts.append((k, v))
                else:
                    walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(payload)
    for k, v in texts:
        if k == "props.per-unit-price-string" and "•" in v:
            left, _, right = v.partition("•")
            out["unit_size"] = left.strip()
            out["unit_price"] = right.strip()
        elif k == "props.strikethrough-price" and v.startswith("$"):
            out["original_display"] = v
            try:
                out["original_usd"] = f"{float(v[1:]):.2f}"
            except ValueError:
                pass
        elif k == "props.price-row-accessibility-text":
            m = re.match(r"\$([\d.]+)(?:, was \$([\d.]+))?", v)
            if m and m.group(2) and not out.get("original_display"):
                out["original_display"] = f"${m.group(2)}"
                out["original_usd"] = f"{float(m.group(2)):.2f}"
    out.update(extract_pdp_details(json.dumps(payload)))
    return {k: v for k, v in out.items() if v}


def fetch_item_details(session: requests.Session, store_id: str, item_id: str, pacer: "Pacer") -> dict:
    url = f"https://www.doordash.com/unified-gateway-dash/cx/v1/items/{item_id}"
    pacer.wait()
    try:
        resp = session.post(
            url,
            json={"store_id": store_id},
            headers={
                "content-type": "application/json",
                "x-unified-gateway-generated-source": "v1",
                "origin": "https://www.doordash.com",
                "referer": f"https://www.doordash.com/convenience/store/{store_id}/",
            },
            timeout=30,
        )
    except requests.RequestException:
        resp = None
    if resp is not None and resp.status_code == 200:
        try:
            extra = extract_mosaic_details(resp.json())
            if extra:
                return extra
        except ValueError:
            pass
    html_url = (
        f"https://www.doordash.com/convenience/store/{store_id}"
        f"?origin_page=item&product_id={item_id}&store_id={store_id}"
    )
    html_resp, _log = fetch(session, html_url, pacer)
    if html_resp is None or html_resp.status_code >= 400:
        return {}
    return extract_pdp_details(html_resp.text)


def unescape(s: str) -> str:
    if not s:
        return ""
    return (
        s.replace('\\"', '"')
        .replace("\\\\", "\\")
        .replace("\\/", "/")
        .replace("\\n", " ")
        .replace("\\u0026", "&")
    )


def append_csv(out_path, rows, fieldnames):
    """Append rows to a CSV. Write a header only when the file is new.

    If an existing file has a different schema (e.g. no scraped_at), rewrite it
    to match so later analysis can treat the file as one aligned table.
    """
    file_exists = os.path.isfile(out_path) and os.path.getsize(out_path) > 0
    if file_exists:
        with open(out_path, newline="", encoding="utf-8") as f:
            existing_fields = csv.DictReader(f).fieldnames or []
        if list(existing_fields) != list(fieldnames):
            with open(out_path, newline="", encoding="utf-8") as f:
                old_rows = list(csv.DictReader(f))
            legacy_ts = datetime.fromtimestamp(
                os.path.getmtime(out_path), tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                for row in old_rows:
                    if not row.get("scraped_at"):
                        row["scraped_at"] = legacy_ts
                    writer.writerow({k: row.get(k, "") for k in fieldnames})
        mode = "a"
        write_header = False
    else:
        mode = "w"
        write_header = True

    with open(out_path, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Scrape every item from a DoorDash DashMart/convenience store.")
    parser.add_argument("store_id", help="Store ID from the URL, e.g. 1042759")
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output CSV path (default: doordash_store_<id>_items.csv). Appends each run.",
    )
    parser.add_argument("-c", "--concurrency", type=int, default=6, help="Concurrent requests (default 6)")
    parser.add_argument(
        "-n", "--name", default=None, help="Display name for console/report output (default: the store ID)"
    )
    parser.add_argument(
        "--min-interval",
        type=float,
        default=0.15,
        help="Minimum seconds between request dispatches, shared across all workers (default 0.15)",
    )
    parser.add_argument(
        "--paginate",
        action="store_true",
        help="Also call the real load-more endpoint per page to go past the SSR batch "
        "(slower, sequential, more complete; see module docstring)",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="Also POST each item's product-page API (slow). List pages already "
        "have sale/original price, discount, stock, and unit size; Best by / "
        "recently sold are not in that API either.",
    )
    args = parser.parse_args()

    store_id = args.store_id
    display_name = args.name or store_id
    out_path = args.output or f"doordash_store_{store_id}_items.csv"
    pacer = Pacer(min_interval=args.min_interval)
    run_start = time.monotonic()

    session = requests.Session()
    session.headers.update(BASE_HEADERS)

    print(f"Discovering categories for store {store_id}...")
    cat_slugs = discover_categories(session, store_id, pacer)
    print(f"  found {len(cat_slugs)} categories")

    print("Discovering sub-categories...")
    jobs = []  # (category_slug, subcat_slug or None)
    discovery_failures = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(discover_subcategories, session, store_id, slug, pacer): slug for slug in cat_slugs}
        for fut in as_completed(futures):
            slug = futures[fut]
            subs, fail = fut.result()
            if fail:
                discovery_failures.append(fail)
            jobs.append((slug, None))
            for sub in subs:
                jobs.append((slug, sub))
    if discovery_failures:
        print(
            f"  {len(jobs)} total pages to crawl (categories + sub-categories); "
            f"WARNING: {len(discovery_failures)} categories' sub-category lists failed to load "
            "-- their sub-category pages are not in this crawl at all"
        )
    else:
        print(f"  {len(jobs)} total pages to crawl (categories + sub-categories)")

    item_map = {}
    errors = []  # full failure-log dicts, not just (url, status) tuples
    # A page that returns HTTP 200 but parses zero items is currently treated
    # as a plain success -- which is right for a legitimately empty
    # sub-category, but identical to what an unexpected page shape / broken
    # parser would also produce. Tracking these separately doesn't fix that
    # ambiguity, but it stops it from being invisible.
    empty_pages = []
    lock = Lock()
    done = [0]

    def worker(cat_slug, sub_slug):
        items, err = process_job(session, store_id, cat_slug, sub_slug, pacer)
        with lock:
            for it in items:
                existing = item_map.get(it["item_id"])
                if existing is None:
                    item_map[it["item_id"]] = it
                else:
                    merge_item(existing, it)
            if err:
                errors.append(err)
            elif not items:
                empty_pages.append({"category": cat_slug, "subcat": sub_slug})
            done[0] += 1
            if done[0] % 20 == 0 or done[0] == len(jobs):
                print(f"  {done[0]}/{len(jobs)} pages done, {len(item_map)} unique items so far")

    print(f"Crawling with concurrency={args.concurrency}, min_interval={args.min_interval}s (retries on 429 with backoff)...")
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(worker, c, s) for c, s in jobs]
        for fut in as_completed(futures):
            fut.result()

    first_pass_failures = len(errors)
    still_failed = []
    if errors:
        print(f"\n{len(errors)} pages failed even after retries; retrying once more slowly...")
        retry_session = requests.Session()
        retry_session.headers.update(BASE_HEADERS)
        for err in errors:
            items, err2 = process_job(retry_session, store_id, err["category"], err["subcat"], pacer)
            for it in items:
                existing = item_map.get(it["item_id"])
                if existing is None:
                    item_map[it["item_id"]] = it
                else:
                    merge_item(existing, it)
            if err2:
                still_failed.append(err2)
            elif not items:
                empty_pages.append({"category": err["category"], "subcat": err["subcat"]})
            time.sleep(1)
        recovered = first_pass_failures - len(still_failed)
        print(f"  after retry: {len(item_map)} unique items ({recovered} pages recovered, {len(still_failed)} still failed)")

    print(f"\nTotal unique items after page crawl: {len(item_map)}")

    if args.paginate:
        print(
            f"\nPagination pass: calling the real load-more endpoint for all {len(jobs)} pages "
            "(sequential, ~3s between calls - this endpoint rate-limits hard, so this is slow "
            "by design; it gives up quietly per-page on failure instead of hammering it)."
        )
        gql_session = requests.Session()
        gql_session.headers.update(BASE_HEADERS)
        gql_session.headers.update(GRAPHQL_HEADERS)
        added = 0
        for i, (cat_slug, sub_slug) in enumerate(jobs, 1):
            cat_name = category_display_name(cat_slug)
            sub_name = category_display_name(sub_slug) if sub_slug else ""
            gql_session.headers["referer"] = (
                f"https://www.doordash.com/convenience/store/{store_id}/category/{cat_slug}"
                + (f"/sub-category/{sub_slug}" if sub_slug else "")
            )
            new_items = paginate_category_graphql(gql_session, store_id, cat_slug, sub_slug, cat_name, sub_name)
            for it in new_items:
                existing = item_map.get(it["item_id"])
                if existing is None:
                    item_map[it["item_id"]] = it
                    added += 1
                else:
                    merge_item(existing, it)
            if i % 10 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)} pages paginated, {added} new items found, {len(item_map)} unique total")
        print(f"Pagination pass added {added} items. Total unique items: {len(item_map)}")

    detail_ids = list(item_map) if args.details else []
    if detail_ids:
        print(
            f"\nProduct-page pass: {len(detail_ids)} items via item API"
        )
        detail_done = [0]
        filled = [0]

        def detail_worker(item_id):
            extra = fetch_item_details(session, store_id, item_id, pacer)
            with lock:
                if extra:
                    for k, v in extra.items():
                        if v:
                            item_map[item_id][k] = v
                    filled[0] += 1
                detail_done[0] += 1
                if detail_done[0] % 20 == 0 or detail_done[0] == len(detail_ids):
                    print(f"  {detail_done[0]}/{len(detail_ids)} product pages, {filled[0]} with extra fields")

        with ThreadPoolExecutor(max_workers=min(args.concurrency, 4)) as pool:
            futures = [pool.submit(detail_worker, iid) for iid in detail_ids]
            for fut in as_completed(futures):
                fut.result()

    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []
    for it in item_map.values():
        rows.append(
            {
                "scraped_at": scraped_at,
                "category": it.get("category", ""),
                "subcategory": it.get("subcat", ""),
                "item_id": it.get("item_id", ""),
                "item_name": it.get("item_name", ""),
                "expires_soon": it.get("expires_soon", ""),
                "best_by": it.get("best_by", ""),
                "price": it.get("price_display", ""),
                "price_usd": it.get("price_usd", ""),
                "original_price": it.get("original_display", ""),
                "original_price_usd": it.get("original_usd", ""),
                "discount": it.get("discount", ""),
                "unit_size": it.get("unit_size", ""),
                "unit_price": it.get("unit_price", ""),
                "stock_status": stock_status(it.get("badge") or ""),
                "recently_sold": it.get("recently_sold", ""),
                "snap": it.get("snap", ""),
                "rating": it.get("rating_val", ""),
                "rating_count": it.get("rating_count", ""),
                "image_url": it.get("image", ""),
            }
        )
    rows.sort(key=lambda r: (r["category"], r["item_name"]))

    fieldnames = [
        "scraped_at",
        "category",
        "subcategory",
        "item_id",
        "item_name",
        "expires_soon",
        "best_by",
        "price",
        "price_usd",
        "original_price",
        "original_price_usd",
        "discount",
        "unit_size",
        "unit_price",
        "stock_status",
        "recently_sold",
        "snap",
        "rating",
        "rating_count",
        "image_url",
    ]
    append_csv(out_path, rows, fieldnames)

    print(f"Appended {len(rows)} rows ({scraped_at}) to {out_path}")

    # --- Coverage summary ---------------------------------------------------
    # A run with zero failed pages still only means "every discovered page was
    # fetched" -- individual category/subcategory pages can under-render
    # relative to DoorDash's own reported per-category totals (see module
    # docstring), and that's a separate, still-unmeasured gap. So "complete"
    # here is scoped narrowly to page-fetch success, not full catalog recall.
    complete = not still_failed and not discovery_failures
    elapsed_seconds = round(time.monotonic() - run_start, 1)
    summary = {
        "store_id": store_id,
        "name": display_name,
        "scraped_at": scraped_at,
        "settings": {
            "concurrency": args.concurrency,
            "min_interval": args.min_interval,
            "paginate": args.paginate,
            "details": args.details,
        },
        "elapsed_seconds": elapsed_seconds,
        "pages_discovered": len(jobs),
        "first_pass_failures": first_pass_failures,
        "recovered_on_retry": first_pass_failures - len(still_failed),
        "still_failed": len(still_failed),
        "discovery_failures": len(discovery_failures),
        "pages_with_zero_items": len(empty_pages),
        "products_saved": len(item_map),
        "complete": complete,
    }

    out_stem = Path(out_path)
    summary_path = out_stem.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2))

    lines = [
        f"{display_name} — {'COMPLETE' if complete else 'INCOMPLETE'}",
        f"Elapsed:             {elapsed_seconds:>8.1f}s  (concurrency={args.concurrency}, min_interval={args.min_interval}s)",
        f"Discovered pages:    {len(jobs):>8}",
        f"First-pass failures: {first_pass_failures:>8}",
        f"Recovered on retry:  {first_pass_failures - len(still_failed):>8}",
        f"Still failed:        {len(still_failed):>8}",
        f"Discovery failures:  {len(discovery_failures):>8}",
        f"Zero-item pages:     {len(empty_pages):>8}  (HTTP success but nothing parsed -- may be a genuinely empty page or a parser miss; not distinguished)",
        f"Products saved:      {len(item_map):>8}",
    ]
    if errors or still_failed or discovery_failures or empty_pages:
        failed_path = out_stem.with_suffix(".failed_pages.json")
        failed_path.write_text(
            json.dumps(
                {
                    # every page that failed at least once, even if the retry
                    # pass fixed it -- needed to see *why* pages failed (429 vs.
                    # timeout vs. something else), which a pure recovery count erases
                    "first_pass_failures": errors,
                    "still_failed": still_failed,
                    "discovery_failures": discovery_failures,
                    "zero_item_pages": empty_pages,
                },
                indent=2,
            )
        )
        lines.append(f"Failure details:     {failed_path.name}")
    lines.append(
        "Note: COMPLETE means every discovered page was fetched, not that every "
        "product on the site was found -- per-category SSR truncation is separate "
        "and not measured here."
    )
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
