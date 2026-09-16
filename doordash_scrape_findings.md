# DoorDash DashMart Scrape — Findings & Methodology

Target: `https://www.doordash.com/convenience/store/1042759/` (DashMart, 1022 West Morena Boulevard, San Diego)
Output: [doordash_dashmart_1042759_items.csv](doordash_dashmart_1042759_items.csv) — 3,152 unique items across 22 categories

## Site structure

- The store has 23 top-level categories (Snacks, Household, Pantry, …), each with its own URL:
  `/convenience/store/1042759/category/{slug}-{id}`
- Each category page reports a `results` count (e.g. Snacks = 652, Household = 483) that is **much larger** than what actually loads server-side on first render (~50 items).
- Categories break down further into **subcategory chips** (e.g. Household → Cleaning, Laundry, Storage, Electronics, …), each with its own URL:
  `/convenience/store/1042759/category/{cat-slug}/sub-category/{sub-slug}`
  These subcategory slugs are not exposed as visible links in the DOM — they only appear embedded in the page's raw HTML as `sub-category/{slug}` substrings, discoverable via a plain regex over the fetched page text (no clicking required).

## Data source: Next.js RSC "flight" payloads

The site is server-rendered with Next.js App Router. Every page ships its full data as an array of escaped JSON strings inside repeated tags:

```html
<script>self.__next_f.push([1,"11:[\"$\",\"div\",...,{\"item_data\":{\"item_id\":\"...\",\"item_name\":\"...\",\"price\":{\"display_string\":\"$2.99\",\"unit_amount\":299}}}]"])</script>
```

Extraction method:
1. Split the raw HTML on `<script>...</script>`, keep chunks starting with `self.__next_f.push(`.
2. `JSON.parse` each `[index, "string"]` array literal — this unescapes the embedded JSON string in one step.
3. Concatenate all unescaped strings into one big text blob per page.
4. Regex-extract item records anchored on the literal `"item_data":{` marker, pulling `item_id`, `item_name`, `price.display_string`, `price.unit_amount` from the ~1200 chars *after* the anchor, and `image.remote.uri` / stock badge / rating from the ~700 chars *before* it (accessibility labels precede `item_data` in the object).
5. Dedupe by `item_id` into a `Map` across every page fetched.

This required zero DOM parsing and zero page rendering — plain string/regex work on fetched HTML text.

## The pagination wall

Category pages never fired a "load more" network request under scroll, click, or key-press automation during early testing (confirmed by: scrolling to the literal bottom of a 483-result category page kept `document.body.scrollHeight` constant and triggered no new requests). Two contributing issues:

- **Flaky browser automation**: the automated browser repeatedly reported `document.hidden = true` even when frontmost, `window.innerWidth/innerHeight` occasionally collapsed to `0`, and scripted scroll actions reliably timed out after 30s regardless of tab state. Real key/mouse events (`Page_Down`, `left_click`) worked but triggered minimal scroll distance.
- **No accessible cursor endpoint found**: a `cursor` field *does* exist in this app (spotted in a `retailCollectionsFeed` GraphQL response for a "similar items" carousel — a base64-encoded blob of `{offset, content_ids, item_ids, ...}`), strongly suggesting the main grid uses the same cursor-pagination mechanism. But the actual request that would apply that cursor to load *more* of the main item grid was never captured, because it only fires on a genuine, browser-native scroll-intersection event that proved hard to reproduce with scripted automation.

**Workaround — subcategory decomposition**: rather than paginating one large category, fetch every subcategory chip's own page (each is a separate SSR with its own ~50–80 item batch). Household's 483 items are spread across 17 subcategories; summed, this recovers most — not all — of the catalog. This turned "23 huge pages" into "~240 small pages," each individually complete or near-complete.

Residual gap: some individual **subcategories** still exceed their own SSR batch (e.g. "Chips" under Snacks reports 142 results, only ~82 unique items were extractable) — the same unsolved cursor-pagination problem, just at smaller scale.

## Rate limiting

- Fetching all ~240 category/subcategory URLs concurrently (6–12 in flight) reliably triggered HTTP 429 from DoorDash after roughly 100–150 requests in quick succession.
- 429 responses had tiny bodies (Cloudflare challenge stub) and **no thrown exception** — `fetch()` doesn't throw on non-2xx, so the first crawl pass silently produced zero items for ~16 categories until this was noticed and checked explicitly.
- Fix: treat `status === 429 || status >= 500` as retryable, with exponential backoff (`2000ms × attempt`, up to 5 attempts) inside each worker.
- Recovery pattern that worked twice: run the full crawl once (accept some failures), then re-run *only the failed URLs* at low concurrency (2) after a short cooldown — this cleared 100% of remaining failures both times, typically within 1–2 minutes of cooldown.

## Result

- **3,152 unique items**, 22 categories (Deals excluded — it's a pure aggregation view of items already counted elsewhere, no unique SKUs of its own).
- Estimated completeness: **55–90% of DoorDash's own reported per-category totals**, varying by category size. Smaller categories (Produce, Meat, Vitamins, etc.) are likely at or near 100%; large categories with big subcategories (Snacks, Household, Candy) are undercounted by 30–45%.

## Follow-up: the real load-more endpoint, found for real

A later pass cracked the pagination endpoint that the section above says was never captured. Two things unlocked it:

1. **Switching to a real, actually-rendering Chrome instance.** The sandboxed automated browser used for the initial testing above had a persistent, unfixable bug (see above) where synthetic scroll events never triggered the load-more fetch. A real Chrome instance fixed nothing at first either — but confirmed the underlying `categorySearch` GraphQL operation *does* fire on genuine scroll, visible in the network panel.
2. **Reading the JS bundles directly, instead of relying on live network capture.** Live capture kept failing (automation flakiness, then a self-inflicted IP rate-limit from too much trial and error). So instead: fetched all ~223 Next.js JS chunk files referenced by the page (`requests`, no browser), grepped them for `categorySearch`, and found the *exact* GraphQL query text and every fragment it depends on, hardcoded in the (minified but unobfuscated-string) source:

   ```graphql
   query categorySearch($storeId: ID!, $categoryId: ID!, $subCategoryId: ID, $limit: Int,
                         $cursor: String, $sortBysList: [RetailSortByOption!]!, ...) {
     retailStoreCategoryFeed(storeId: $storeId, l1CategoryId: $categoryId, l2CategoryId: $subCategoryId,
                              limit: $limit, cursor: $cursor, sortBysList: $sortBysList, ...) {
       totalItemCount
       products { ...RetailItemDetailsFragment }
       pageInfo { cursor hasNextPage }
     }
   }
   ```

   This is real cursor-based pagination via Apollo's `fetchMore` — `pageInfo.hasNextPage` / `pageInfo.cursor` are genuine, not a dead end.

3. **The `cursor` is self-constructible.** It's base64 of a large, mostly-static JSON object (offset, empty arrays, `"cursorVersion":"FACET_CONTENT_OFFSET"`, etc.) where the *only* field that changes across pages is `offset`. No need to round-trip a server-issued cursor — `offset=0, 50, 100, …` can be generated directly. Confirmed byte-for-byte against a real captured request.

4. **A syntactically valid query still returned `products: []`.** Calling it with `requests` (correct query, correct variables) got a 200 with the right `totalItemCount` but an empty product list — for a while this looked like a missing delivery-address/market context (the `dd_market_id` cookie stays `-1` in a plain session). Testing that theory required adding a **Playwright** dependency to bootstrap a real browser session and harvest its cookies. That turned out to be a red herring: fresh cookies from an actual headless Chrome session didn't fix it either, and calling the endpoint via `page.evaluate(fetch(...))` **from inside that same authenticated browser context** still returned empty products.

5. **The real fix: missing headers, not missing cookies.** Captured a genuine successful request via Playwright's `page.on("request")` during real `mouse.wheel()` scrolling and diffed it against what we'd been sending. The gap was several DoorDash-specific headers our requests never included: `apollographql-client-name`, `apollographql-client-version`, `x-csrftoken`, `x-channel-id`, `x-experience-id`. The backend appears to accept the query from any client but only return real product data to requests carrying these — a plausible, deliberate anti-scraping measure (return a valid-looking empty result rather than an error) rather than any address/session gate.

6. **Verification is incomplete.** After finding the correct headers, further live testing to confirm non-empty `products` come back triggered a harder, longer-lived 403 block on this specific endpoint (separate from, and stricter than, the ~1-2 minute 429s on plain page fetches — this one didn't clear within several minutes of waiting). The header set and cursor format are confirmed correct (matched a real successful request exactly), but full end-to-end confirmation that the fix produces non-empty results is still pending a live retest once the block clears.

**Where this landed:** [doordash_dashmart_scraper.py](doordash_dashmart_scraper.py) got an opt-in `--paginate` flag implementing all of the above — sequential, ~3s between calls (this endpoint's rate limit is much stricter than the page-fetch one), gives up quietly per-page on failure so one blocked page never derails the run. Ships with high confidence but not a fully-verified live run; retest with `--paginate` once the endpoint is unblocked.

## Answering: can the API/network layer be inspected without ever opening a browser?

**Yes — and for a task like this, it would have been faster.** What actually unblocked this scrape (calling `fetch()` directly from page context, bypassing rendering entirely) is a special case of a more general, better workflow:

1. **Capture once with a real browser, then go fully headless.**
   Open DevTools → Network tab, manually do the interesting thing once (scroll a category to trigger "load more," click a filter chip), then either:
   - Right-click the relevant request → **"Copy as cURL"** — gives you a ready-to-run, fully-authenticated command line call.
   - Or **Network tab → "Export HAR"** — captures every request/response/header/cookie from the whole session into one file you can `grep`/`jq` offline, no re-browsing needed.

   From that point on, every subsequent call is a plain `curl` / Python `requests`/`httpx` call — no page rendering, no DOM, no viewport, no "hidden tab" flakiness like we hit repeatedly during testing. This is strictly faster and more reliable once the request shape is known, and it's how the actual pagination cursor request (still unfound here) would have been fastest to identify — passive capture beats scripting clicks/scrolls blind.

2. **A dedicated intercepting proxy (mitmproxy / Charles / Proxyman)** works even better for this — route any browser (or DoorDash's mobile app) through it once, and every API call — including ones triggered by gestures hard to script, like momentum-scroll infinite loading — gets logged automatically with full bodies, with no automation code required at all.

3. **For this particular site, "the API" is arguably unnecessary** — the RSC flight payload trick means a plain `curl '<category-url>' -b cookies.txt | grep item_data` already returns the same item data extracted here, no JavaScript execution required. The browser was only load-bearing for two one-time costs: (a) discovering this embedded-JSON data shape in the first place, and (b) obtaining a valid, geo-located session cookie. Both are one-time setup steps — the cookie jar could be exported and reused in plain `curl` calls indefinitely, until it expires.

**Takeaway for next time:** reconnaissance (find the request shape once, via DevTools/HAR/proxy) and execution (replay it at scale via plain HTTP) are separable, and only the first needs a browser at all. That split happened late here — the breakthrough came only after a lot of time spent fighting the automated browser's scroll/viewport behavior. Starting with a HAR capture or "Copy as cURL" instead of scripting UI interactions would have reached the same `fetch()`-based approach in a fraction of the time.
