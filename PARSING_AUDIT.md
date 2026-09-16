# Parsing Audit — Checkpoint 2

Two deterministic, vocabulary-based parsers, no ML:

- `normalize.py` / `parse_package_size()` — turns a product's `unit_size`
  field (e.g. `"4.8 oz x 8 ct"`) into a fixed size, or explicitly refuses to.
- `parse_query.py` / `parse_shopping_line()` — turns a shopping-list line
  (e.g. `"a dozen large eggs"`) into a structured request, or explicitly
  flags it for review.

Both follow the same rule: an unresolved case is reported as unresolved,
never silently guessed. This document records what fails, and why, against
real data and targeted test cases — not just what passes.

## A note on what "resolved" means

**90.1% resolved measures parser coverage, not correctness.** A row counts
as "resolved" if `parse_package_size()` produced a fixed size at all — it
says nothing about whether that size is the *right* one. A plausible but
wrong parse (say, a regex matching the wrong number in a title) would still
count as resolved here. Correctness is what the manual review sample below
(and eventually a labeled benchmark) checks; this stat only tells you
volume, not accuracy.

**Missing `unit_size` means the field is empty, not that no size exists
anywhere.** The scraper already has a fallback for this: when DoorDash's
own size field is empty, it extracts a size from a trailing `"(...)"` in
the product title (`unit_fields()` in `doordash_dashmart_scraper.py`). So
before trusting "missing" as final, this was checked directly: of the
1,830 rows with an empty `unit_size` in the current data, **zero** have an
uncaptured size-looking trailing parenthetical in the title. That's real
evidence for this specific pattern, not just an assumption — but it only
rules out that one pattern (a size in parens at the end of the title). A
size embedded elsewhere in the title, in a different format, would not be
caught by this check or by the scraper's fallback.

## Product normalization — full-corpus results

Run against the latest snapshot of all five stores. **This required a
fix first**: an earlier version of this corpus sweep (and of
`coverage_report.py`) included DashMart's *entire* accumulated CSV, which
contains rows from two different scrape dates. Deduping by `item_id` and
keeping the last-seen row per ID silently blended two runs' inventories —
304 products that only existed in the older run were counted as part of
the "current" catalog. Fixed by filtering to DashMart's single most recent
`scraped_at` value only (`latest_snapshot_only()` in `coverage_report.py`,
reused by both the corpus test and `build_normalized_catalog.py`). This
changed the total row count from 34,401 to the correct 31,398.

| Outcome | Count | % of total |
|---|---:|---:|
| Resolved to a fixed size | 28,276 | 90.1% |
| Missing size (DoorDash gave none, title had none either) | 1,830 | 5.8% |
| Priced by weight, no fixed size (produce/meat/deli) | 1,000 | 3.2% |
| Unrecognized format | 222 | 0.7% |
| Apparel/diaper/seasonal size label (not a package size) | 70 | 0.2% |

The middle two rows (missing size, priced by weight) are not parser
failures — they are correctly-identified cases where **no fixed size
exists to extract**. Per the project plan, priced-by-weight items are
excluded from automatic basket math in v1; this parser is what makes that
exclusion possible; it can't be fixed by a better regex.

### Representative remaining failures (222 "unrecognized format", corrected corpus)

| Raw string | Count | Why it fails | What it would take to fix |
|---|---:|---|---|
| `each` / `ea` | (now handled) | — | Fixed during this checkpoint: treated as a fixed count of 1 |
| `3 pk x 56 ct` | (now handled) | — | Fixed during this checkpoint: a second multipack pattern for pack-of-packs with no weight/volume unit |
| `bunch`, `1 bunch` (chard/cilantro) | 46 | No standard weight or count — a bunch of cilantro and a bunch of bananas are different sizes | Would need a per-product-type default, which is a guess, not a parse. Left unresolved deliberately. |
| `10 ft`, `4 in`, `9 in`, `3 ft`, `50 ft`, `75 ft` | ~19 | Length is a fourth dimension this module doesn't model (ribbon, tape, cord — non-food party/craft items) | Out of scope: these aren't comparable across a grocery basket anyway |
| `pack`, `25 pk`, `20 pk` (bare, no per-pack size) | ~9 | A pack count with no stated per-pack size | Genuinely ambiguous from the string alone; would need the product page, not just `unit_size` |
| bare digits (`1`, `9`, `7`, `10`, `8`) | ~21 | A number with no unit at all | Cannot assume a unit; leaving unresolved is correct, not a gap |
| `12 x 12 fl oz` | 3 | Count comes *before* the unit (reversed from the handled `12 fl oz x 12 ct` order) | A distinct, low-volume pattern; not worth a special case yet at 3 occurrences |
| `8 ct, 12 oz` | 3 | Two measurements joined by a comma — genuinely two numbers describing the same package | Would need to decide which one is "the" size, or represent both; not attempted |
| `1 pr` | 3 | "Pair" as a unit isn't in the vocabulary | Small, could be added if pairs show up more; not common enough yet to justify it |

### A fix made during this audit

`Large`, `Medium`, `Size 6`, `Size 6-10` etc. were initially falling into
the generic "unrecognized format" bucket. These are apparel/diaper size
labels that leaked into the `unit_size` field from non-comparable listings
(e.g. costumes, diapers sized by weight range rather than count). Added a
dedicated pattern so these get a specific, honest reason
("not a package size...") instead of being indistinguishable from a genuine
parsing gap. This didn't change how many rows are unresolved — it changed
whether the *reason* is informative.

## Shopping-list parsing — targeted cases

61 cases in `test_parse_query.py` (the plan's required 50, plus 11
regression cases added across two rounds of external review — see below),
all passing, grouped by what they exercise:

| Category | Example | Result |
|---|---|---|
| Plan's own worked examples | `"a dozen large eggs"`, `"organic strawberries, 1 lb"` | Resolved, matches the plan's stated interpretation exactly |
| Decimals / fractions | `"1.5 lb ground beef"`, `"1/2 gal milk"` | Resolved |
| Bare counts (no unit word) | `"3 apples"` | Resolved as a count of 3 |
| Word-form quantities | `"a dozen"`, `"two dozen"`, `"half a dozen"`, `"a couple of"` | Resolved (see bug found below) |
| Abbreviated units | `"2 lbs"`, `"12 fl oz"`, `"500 ml"`, `"2 kg"` | Resolved |
| Missing quantity | `"milk"`, `"chips"` (no number at all) | **Flagged for review**, no quantity invented |
| Vague quantity words | `"some apples"`, `"a few bananas"`, `"several onions"` | **Flagged for review** — these have no fixed number by definition |
| Ambiguous container units | `"2 boxes of cereal"`, `"3 cans of soup"`, `"1 bottle of olive oil"` | **Flagged for review** — box/can/bottle sizes vary by product, no default assumed |
| Modifiers preserved | `"1 gallon whole milk"` → modifier `whole` | Modifier extracted, not folded into product type |
| Unknown descriptive words | `"2 lb fancy tomatoes"` | `"fancy"` is not in the modifier vocabulary, so it stays in `product_type` rather than being dropped or misclassified |

### A real bug this audit caught

`"two dozen eggs"` initially parsed as quantity=2, product_type="dozen eggs"
— the word-quantity table only had `"a dozen"` / `"one dozen"` / `"dozen"`
as literal phrases, so `"two"` matched alone (as 2) and left the word
`"dozen"` stranded in the leftover text instead of combining with it. Fixed
by generating `"<number word> dozen"` combinations (`"two dozen"` → 24,
`"three dozen"` → 36, etc.) instead of hand-enumerating a couple of cases.
Caught by a test that specifically checks 24, not just that *a* number
came out.

## Issues found in external code review (first round)

A review of this checkpoint's work (not self-review) found five confidently
wrong parses in `parse_query.py` and three crashes plus a validation gap in
`normalize.py` — all fixed, all with regression tests now. Listed here
because "we found bugs and fixed them" is different from "we didn't look
hard enough the first time," and the difference only shows if the bugs are
actually named.

**`parse_query.py` — wrong answers with `needs_review: false`.** This
category is worse than a rejected line: downstream code has no way to know
the result is untrustworthy.

| Input | Was | Now |
|---|---|---|
| `"2 dozen eggs"` | quantity 2, product `"dozen eggs"` | quantity 24, product `"eggs"` |
| `"1 1/2 lb apples"` | quantity 1 (count), rest discarded | quantity 1.5 lb → 24 oz |
| `"1 GAL milk"` | unit not recognized (case-sensitive match) | resolves as 1 gal → 128 fl oz |
| `"2% milk"` | quantity 2, product `"% milk"` | `needs_review`, modifier `"2%"` preserved, product `"milk"` |
| `"1 milk"` | quantity 1 (count), no review | `needs_review`: milk isn't sold by the count |

Root causes: the leading-number regex used `\b` after the digits, which
doesn't fire between a digit and a letter (`"16oz"` never matched at all —
also fixed, and now tested), and separately didn't exclude a following `%`
(so `"2%"` got torn into a number and a stray `"%"`); the word-quantity
table only had `"a dozen"`/`"one dozen"`/`"dozen"` as literal phrases, with
no path for a *numeral* plus `"dozen"`; unit/container word matching wasn't
lowercased before the vocabulary lookup; and there was no vocabulary at all
for "this product is never sold as a bare count," so `"1 milk"` looked
identical to a legitimate `"1 apple"`.

**`normalize.py` — crashes on malformed input.**

| Input | Was | Now |
|---|---|---|
| `"1/0 oz"` | `ZeroDivisionError` | unresolved: invalid quantity |
| `"1..2 oz"` | `ValueError` from `float()` | unresolved: invalid quantity |
| `"1 quarts"` / `"1 pints"` | `TypeError` (regex accepted the plural, the unit table didn't have it) | resolves correctly (table now has both plurals) |
| `"0 oz"` | resolved as a valid zero-size package | unresolved: non-positive quantity |

All four fixed in `_to_float()` (now returns `None` instead of raising) and
a `_valid_positive_amount()` check added to every branch that builds a
resolved result, plus the missing plural entries in `_UNIT_TABLE`. Every
row above is now a regression test in `test_normalize.py`.

**The DashMart snapshot-mixing bug** (described above) was also found in
this review, not before it — `coverage_report.py`'s original
`dedupe_keep_last()` was a real bug, not a stylistic issue, and is now
`latest_snapshot_only()` with a regression test
(`test_build_normalized_catalog.py::test_dashmart_uses_single_snapshot_not_merged_history`).

**A test that didn't test what it said it did.** One `test_parse_query.py`
case was written as `"16oz yogurt".replace("oz", " oz")` — meant to note
"normalize the spacing," it actually replaced the input *before* parsing,
so the unspaced form was never exercised at all, and the `\b` bug above
went undetected by a test that looked like it covered exactly this case.
Fixed to test both `"16 oz yogurt"` and `"16oz yogurt"` as separate cases.

## Issues found in external code review (second round)

**Four more `parse_query.py` validation holes**, found the same way as the
first round: reproduced, fixed, regression-tested.

| Input | Was | Now |
|---|---|---|
| `"0 eggs"` | quantity 0, no review | needs review: non-positive quantity |
| `"1 loaf bread"` | product `"loaf bread"`, no review | `"loaf"` is an ambiguous container (like bag/box), product `"bread"`, needs review |
| `"1 gallon gluten-free milk"` | `"gluten-free"` stuck in the leftover text, not recognized as a modifier | modifier `"gluten free"` extracted; hyphens now normalized to spaces before modifier matching |
| `"12% milk"` | quantity **1** (!), from `\d+` backtracking down from "12" to dodge a `(?!%)` lookahead | no quantity at all; needs review |

The `"12% milk"` case is the sharpest one: the fix from the first round
added a `(?!%)` lookahead to stop `"2%"` from being torn into a number, but
regex backtracking defeats a lookahead placed right after a greedy
quantifier — the engine just tries a *shorter* digit match ("1") for which
the lookahead succeeds, rather than failing the whole thing. Fixed by
removing the lookahead and instead checking, after the full greedy match,
whether the very next character is `"%"` — checking the actual matched
text, not hoping backtracking won't find a way around a lookahead.

## Bare `oz` on likely-liquid products: flag, don't reinterpret

The review sample surfaced this directly: `Ripple ... Milk Bottle (48 oz)`,
`Modelo ... Cans (12 oz x 12 ct)`, and a `FocusAid ... Energy Drink Can (12
oz)` all parse as **weight** per the documented literal rule (bare `oz` is
always weight — see below). That's not wrong given the rule, but it has a
real consequence: a flexible-mode request in fluid ounces would never
match these, purely because of a dimension mismatch that has nothing to do
with whether the product actually fits the request.

The fix is a review flag, not a silent reinterpretation — converting these
to volume would just be a different silent guess, arguably worse since it
would look more "fixed." `build_normalized_catalog.py` (which sees
`raw_title`/`raw_category`, unlike `normalize.py`) adds
`dimension_review_flag` + `dimension_review_reason` columns. `normalize.py`
itself is untouched — it has no product context to make this call with,
and shouldn't be given any; that's a boundary worth keeping.

Getting the heuristic itself right took three iterations, each checked
against real data before moving to the next:

1. **First pass**: category (`Drinks`/`Alcohol`) or any of 16 liquid
   keywords appearing anywhere in the title. Flagged 1,568 rows — but
   checking a sample showed "milk" alone produced 340 hits, nearly all
   `"Milk Chocolate"` / `"Whole Milk Yogurt"` / `"Whole Milk Ricotta
   Cheese"` (an ingredient descriptor, not a drinkable product). `coffee`,
   `water`, `soda`, `tea`, `wine`, `cocktail`, `cider`, `seltzer`,
   `sparkling`, `lemonade`, and `smoothie` all had the same problem to
   varying degrees (ground coffee beans, tuna packed in water, baking
   soda, tea-tree shampoo, cooking wine, fruit cocktail, cider vinegar,
   Alka-Seltzer, sparkling toothpaste, lemonade candy, snack-pouch
   "smoothie melts").
2. **Second pass**: restrict each keyword to being the title's *head
   noun* — the last content word, or immediately followed by a container
   word (`bottle`, `carton`, `jug`, `can`). This alone cut the flag count
   from 1,568 to 656 and, checked again, showed `coffee`/`water`/`soda`/
   `tea`/`wine`/`cocktail` were *still* dominated by false positives even
   as head nouns (`"Ground Coffee"`, `"Tuna in Water"`, `"Baking Soda"`,
   `"Green Tea"` shampoo, `"Cooking Wine"`, `"Fruit Cocktail"`) — dropped
   entirely, since real beverages using those words are already caught by
   the category check. Kept only `milk`, `juice`, `broth`, `smoothie`,
   `kombucha`, which cleaned up well under the same check.
3. **Third pass**: excluded titles containing `dry`/`powder`/`powdered`
   (`"Dry Whole Milk Powder"`, `"Instant Dry Milk"` are genuinely solid) —
   down to 654 flagged. All three originally-cited products (Ripple,
   Modelo, FocusAid) remain flagged at every stage.

**Known remaining noise, documented rather than chased further**: 2 dry
milk products still get flagged because they're filed under the `Drinks`
category (the dry/powder exclusion only guards the keyword path, not the
category path); a handful of `"Rice Cooked in Bone Broth"` / `"Lip
Milk"` (a lip-balm product line) titles remain flagged too. These are
single-digit counts against 654 total flags and 31,398 rows — the
heuristic's job is to nominate candidates for review, not classify
perfectly, and each of these costs one reviewer glance, not a data
integrity problem.

## Known, deliberate limitations (not bugs)

- **Bare `oz` is always weight, never volume.** `"8 oz milk"` resolves as
  8 weight-ounces, not 8 fluid ounces, even though milk is a liquid. The
  plan requires keeping `oz` and `fl oz` distinct; this parser enforces that
  literally rather than trying to infer intent from the product name. A
  user must write `"8 fl oz milk"` for volume. This is a real gap for
  natural phrasing, recorded here rather than patched with a guess. (The
  dimension-review flag above is the mitigation for the catalog side of
  this same rule; shopping-list parsing doesn't have an equivalent yet.)
- **`product_type` is leftover text, not a grocery taxonomy.** After
  quantity, unit, and known modifiers are stripped out, whatever remains
  becomes the product type verbatim (e.g. `"almond milk"`, `"ground beef"`).
  There's no canonical list of product types and no plural/singular
  normalization (`"eggs"` stays `"eggs"`). Matching this against actual
  catalog products is Checkpoint 4's job (matching), not this one.
- **Ambiguous containers (bag/box/can/bottle/pack/jar/carton/loaf/loaves)
  always need review.** No attempt is made to guess a "typical" bag of
  chips or loaf of bread size — package sizes for the same container word
  vary by product and by store.

## Dataset deliverable: `normalized_catalog.csv`

Parsing functions alone aren't the Checkpoint 2 deliverable the plan asks
for — a reproducible table is. `build_normalized_catalog.py` produces
`normalized_catalog.csv` (31,398 rows, regenerable by re-running the
script) with, per row: explicit `store_id`/`store_name`/`snapshot_id`/
`product_id` (identity and provenance, not inferred from which file you
happened to load), `raw_title`/`raw_category`/`raw_size` alongside the
parsed `pkg_*` fields, `price_cents` as an integer (not a float, to avoid
rounding drift when summing basket totals later), `parsing_status` +
`parsing_reason`, and explicit `brand`/`variant` columns that are `None`
for every row right now — present in the schema, not silently omitted, but
not yet populated. Full brand/variant extraction is deferred to whenever
product matching (Checkpoint 4) actually needs it; getting identity,
provenance, and package size right was the bar for this checkpoint, not
brand parsing.

## Manual verification record

**First version of this was itself flagged as not good enough.** It sampled
20 products per store, wrote them to `MANUAL_REVIEW.md`, and defaulted
every row's review column to `"OK"` with a `"None"` discrepancies note —
regardless of whether anyone had actually looked. Re-running the script (to
pick up a new snapshot, say) silently regenerated the whole file, so even a
real discrepancy noted by hand would have been erased on the next run.
Neither problem is cosmetic: a plausibility skim ("does this look like a
real product") was being presented as equivalent to checking the scraper
against its actual source, which it isn't — comparing our own stored
`raw_title`/`raw_size` to itself can never catch the scraper having copied
something wrong in the first place.

Redesigned around three rules: (1) generation only ever creates rows in an
explicit `"unreviewed"` state — nothing defaults to a positive verdict; (2)
review decisions live in a separate file (`manual_review_decisions.json`),
keyed by store+product ID, and re-running generation preserves whatever's
already there rather than overwriting it (a fixed seed means the same
rows come back, so decisions stay matched to the right products); (3) every
row carries a `source_url` — the live DoorDash product page — so
"verified" means something was actually checked against a source
independent of this project's own CSV.

To exercise the mechanism for real rather than leave it as untested
infrastructure: 7 of the 100 rows (one from each remaining store, three
from ALDI) were checked against a fresh, independent re-fetch of their
live category page (not a re-read of `normalized_catalog.csv`) — title and
price matched exactly in all 7, recorded with `record_decision()` and a
note naming the category and date checked. The other 93 are honestly
`"unreviewed"` — not glossed over, not defaulted to OK. Extending this to
more of the sample (or automating the live-refetch step) is future work,
not represented as done here.

## What's still needed before Checkpoint 3

- No pandas yet in any module — everything works directly on
  `csv.DictReader` rows/dicts. Still a deliberate choice: nothing so far
  has needed a join or a groupby, and introducing a dependency without an
  operation that justifies it doesn't match this repo's own stated bias
  toward minimal scope. It'll get pulled in when building the cross-store
  product matching step, or the labeled benchmark in Checkpoint 3, where
  joins are real.
- The checks in this document (full-corpus sweep, manual review) were run
  once, by hand, after each fix. They are not yet wired into a single
  repeatable "regenerate everything and check it" command — `pytest`,
  `build_normalized_catalog.py`, and `manual_review.py` are separate
  invocations today.
- Only 7 of 100 manual-review rows are actually verified against a live,
  independent re-fetch; the other 93 are honestly `"unreviewed"`, not
  quietly treated as fine. Extending real verification to more of the
  sample (or automating the live-refetch step so it's cheap to run against
  all 100) is unstarted.
- Shopping-list parsing has no equivalent of the catalog's
  `dimension_review_flag` — a request like `"8 oz milk"` still resolves as
  weight with no review signal, even though the same ambiguity that
  motivated the catalog-side flag applies here too.
