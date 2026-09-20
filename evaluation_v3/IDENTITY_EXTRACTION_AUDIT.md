# S2 identity extraction audit

Checkpoint 4, S2. Audited 2026-09-20 against `evaluation_v3/catalog_identity.csv`
(`identity_version` v1), built from the frozen 31,398-row catalog.

This audit judges the extractor against the **raw product titles**, which are the source the
extractor reads — not against `expected.brand`/`expected.variant` in the benchmark, which are
hidden ground truth and were not consulted. It is a single-reviewer judgment call on each row,
not an independent multi-rater measurement, and should be read as such.

## 1. Coverage on the full catalog

| | count | share |
|---|---|---|
| Brand resolved | 26,562 / 31,398 | 84.6% |
| Brand unknown (explicit) | 4,836 / 31,398 | 15.4% |
| At least one variant token | 17,080 / 31,398 | 54.4% |

Lexicon: 3,242 induced entries, plus 47 explicitly listed store/private-label brands.

## 2. Hand-checked sample: 100 rows, 20 per store

Seeded (`random.seed(42)`), stratified by store, drawn before any row was inspected.

**Brand asserted on 84 of 100 rows. Of those 84, 69 were judged correct — 82.1% (69/84).**
The 15 errors split into two kinds, neither of which is a wrong *brand identity*:

**Truncated (10/84).** The lexicon's frequency floor stops the n-gram short:
`International` for International Harvest, `Sour` for Sour Punch, `Nature's` for Nature's Truth,
`Blue` for Blue Buffalo, `Country` for Country Crock, `Three` for Three Wishes, `Sweet` for
Sweet Loren's, `True` for True Dates, `Little` for Little Salad Bar, `Mrs.` for Mrs. Butterworth's.

**Over-extended (5/84).** `Liquid I.V. Hydration` for Liquid I.V., `Fre Alcohol-Removed` for Fre,
`Khloud Popcorn` for Khloud, and — the one genuine false positive — **`USDA Choice Beef` on two
rows, which is a grade descriptor, not a brand at all.**

**Brand unknown on 16 of 100 rows.** Of those, 2 are genuinely unbranded (`Celery Pack`,
`Spiral Multicolor Pastel Birthday Candles`) and **14 are real brands the frequency floor missed**
— Franz, Mila, Waiakea, Mack's, Medinatura, Supernatural, Theraneem, Boka, Aonic, Oxiclean,
La Terra Fina, Cordzilla, Simply Lemonade, Tajin. All sell too few products in this catalog to
clear `MIN_BRAND_PRODUCTS = 5`.

So on this sample: 69 right, 15 imprecise-but-consistent, 14 missed, 2 correctly unknown.

## 3. Why truncation and over-extension are less damaging than they look

Both are **symmetric**: the catalog side and the query side run the identical functions over the
identical lexicon, so a title and a request phrased the same way truncate the same way. An
exact-mode comparison of "Nature's Truth Ceylon Cinnamon" against a catalog row of the same
product compares `Nature's` to `Nature's`, and agrees.

They break only when the two sides are phrased differently enough to truncate differently, or
when two *different* brands truncate to the same prefix. The second is the real risk and this
audit did not measure its rate — a targeted check of collision rate among truncated prefixes is
worth doing before exact mode's results are quoted. **Recorded as unmeasured, not as absent.**

The `USDA Choice Beef` case is different in kind: a descriptor promoted to a brand, which S3 would
treat as a real identity attribute. It is rare in this sample (2/100) but it is the failure mode
that can produce a confident wrong answer rather than a conservative one.

## 4. Query side

All 150 benchmark requests were run through `extract_request_identity`. **69 of 150 resolved a
brand.** Spot-checking against matching mode:

- Exact-mode requests resolve a brand as intended — `Barissimo`, `Countryside Creamery`, `Oatly`,
  `Clancy's`, `Kerrygold`, `Simply Nature`, `Cinnamon Toast Crunch`, `Califia Farms`.
- Flexible-mode requests correctly resolve **no** brand: "2 lb Honeycrisp Apples", "12 oz ground
  coffee", "0.5 gal almond milk, any brand" all return `None`, which is what flexible mode needs.

That split is the useful signal here: the extractor is not inventing brands for generic requests.

## 5. Deviations from CHECKPOINT_4_PLAN.md S2, and why

**The plan's ">= 2 distinct `raw_category` values" requirement was dropped.** Measured against the
real catalog, it discards **2,059** legitimate single-category brands — A&W, Advil, Afrin, A.1.,
3M among them — because plenty of real brands sell into exactly one department. Keeping it would
have traded a large, systematic false-negative rate for a small false-positive gain. The position
requirement (leading n-grams only) and the frequency floor are kept.

**A dominant-continuation rule was added**, which the plan did not specify. Three rules were
checked against real data before settling:

1. *Longest lexicon match* — overreached: `Signature Select Double`, `Sprouts Angus Grass-Fed`,
   `Birds Eye Steamfresh`.
2. *Shortest match with >= D distinct continuations* — under-reached the opposite way:
   `Signature` for Signature Select, `Sun` for Sun Luck, and it lost Salonpas and Birds Eye to
   unknown entirely.
3. *Extend while the longer form holds >= 50% of the shorter form's products* — the rule shipped.
   Correct on all four of the cases the first two rules got wrong.

The ratio was measured **insensitive across 0.40–0.75** on the real catalog (identical 84.6%
coverage at every value tested), so 0.50 is a declared midpoint, not a tuned optimum. Worth
knowing that it is not doing fine-grained work.

**Trailing generic words are trimmed off a matched brand** (`Clancy's Original` → `Clancy's`,
variant gains `original`). Without this the same word lands on both the brand and the variant side
and an exact-mode brand comparison starts depending on phrasing.

## 6. Known limitations

1. **The frequency floor is the dominant error source** — 14 of 16 unknowns in the sample are real
   brands below it. Lowering `MIN_BRAND_PRODUCTS` would recover them and admit more junk; the
   trade was not swept, because sweeping it against anything that touches the benchmark would make
   it a tuned hyperparameter. It stays at the pre-declared 5.
2. **Prefix-collision rate among truncated brands is unmeasured** (§3).
3. **A descriptor can be promoted to a brand** (`USDA Choice Beef`), 2/100 in this sample.
4. **Brand over-extends when every product of a brand shares a leading word** — the dominance
   ratio is 1.0 and frequency alone cannot separate them (`Birds Eye Steamfresh`). Asserted as a
   test in `test_product_identity.py` so it stays visible.
5. **The variant vocabulary is a closed list.** A descriptor outside it is silently dropped rather
   than becoming a variant. That is the intended direction of failure (unknown, not invented), but
   it means variant absence never proves a product lacks the attribute.
6. **Single reviewer, single pass, 100 rows.** The per-store cell is 20 rows, far too small for a
   per-store accuracy claim; none is made.

## 7. What this means for S3

Exact mode requires brand, variant and package size. On this evidence it can expect a brand on
roughly 85% of catalog rows and 46% of requests (69/150 — appropriately concentrated in
exact-mode requests). The remaining rows route to review rather than to a wrong answer, which is
S3's declared behavior and is correct, but it does mean **exact-mode coverage is capped by
extraction quality, not by the matcher** — the outcome `CHECKPOINT_4_PLAN.md` Risk 5 anticipated.
