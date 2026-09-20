# Independent label check — 50 random pairs

Run 2026-09-20 against the frozen benchmark (`evaluation/benchmark_pairs.jsonl`, 1,658 pairs,
`catalog_version_sha256` `087a7bba…`). Sample drawn by `independent_label_check.py`,
seed `50_2026`, uniform over the whole pool.

## Why this was run

1,544 of the 1,658 pool labels came from `claude_auto_label.py`, whose rule set compares
dimension, package size, brand and product type — **the same comparisons `retrieval.py`'s filters
apply**. The benchmark and the matcher are therefore not fully independent, so a measured matcher
improvement (Checkpoint 3.1's Success@1 76.6% → 84.4%, for instance) is biased upward by an
unknown amount. Nothing in the repo measured that bias. This does, partially.

## What makes it independent

Re-reading the catalog title and re-applying an attribute comparison would repeat the
circularity rather than measure it — the failure mode Checkpoint 2's `manual_review.py` was
rebuilt to avoid ("a verification step that only compares stored data to itself is circular").

So each pair was judged from the **product photograph**, fetched live from DoorDash's CDN at
review time: the packaging as photographed, which the original labeler never read. All 50 photos
were available. Where photo and title disagreed, the photo decided what the product physically is.

The photos carried real information the title does not. `#2`'s packaging shows **2 PACK**,
confirming the per-pack-vs-total distinction. `#9`, `#31` and `#50` show **PAMPLEMOUSSE** and
**PURE** where a Razz-Cranberry request was made. `#33` reads **SALTED** against an unsalted
request. `#15` shows breaded strips, not raw breast. `#45` is a peanut butter jar against a
request for butter.

## What it does not establish

**The adjudicator is an AI, not a human rater.** This measures agreement between the frozen
labels and an independent-*source* re-judgment. It does not establish ground truth and is not
the human review a published accuracy claim should rest on. The honest reading is: it removes
one specific circularity (same rule set, same evidence), not all of them.

## Result

**47 / 50 exact agreement = 94.0%.**

| Frozen label | n | Independent agreed |
|---|---|---|
| Acceptable | 12 | **12 / 12** |
| Incorrect | 38 | 35 / 38 |

Sample composition: 30 exact / 20 flexible; 4 best-guess pairs; `reviewed_by` 44
`codex_ai_audit`, 6 `codex_photo_review`.

### The three disagreements are one systematic pattern, not noise

| # | Request | Candidate | Frozen | Independent |
|---|---|---|---|---|
| 1 | `16 oz salmon fillet` | Skuna Bay Fresh Atlantic Salmon Fillet (by pound) | Incorrect | Needs clarification |
| 3 | `3 bananas` | Organic Bananas (bunch), $0.69/lb | Incorrect | Needs clarification |
| 6 | `16 oz salmon fillet` | Fresh Norwegian Atlantic Salmon Fillet Pack, $11.29/lb | Incorrect | Needs clarification |

All three are **variable-weight products against a fixed-size request**, all flexible-mode, all
disagreeing in the same direction.

**And the frozen label follows documented policy.** `LABELING_GUIDELINES.md` line 99 states:
"Fixed-package requests do not match variable-weight listings in this MVP." So these are not
labeling errors — they are a policy the guideline chose and the labeler applied consistently.
Judged against the written policy, agreement is **50 / 50**.

## The one substantive finding

The policy is in tension with the codebase's own standing rule elsewhere.

`filter_by_dimension` and `filter_by_package_size` both treat an unresolvable size as **unknown —
do not filter**, on the explicit grounds that unknown is a third state and never a confirmed
mismatch. The S3 identity filter follows the same rule. But the *labels* call the same
variable-weight products **Incorrect**, which asserts a confirmed mismatch.

So the matcher says "I cannot tell" and the benchmark says "that was wrong." A matcher that
correctly declines to filter a variable-weight candidate is scored as if it retrieved a known-bad
one. This is a small population — 1,000 / 31,398 catalog rows are `variable_weight` — but it is
a real internal inconsistency, and it pushes in the direction of **understating** matcher quality
on those rows rather than overstating it.

Not changed here. Changing a labeling policy would re-stale frozen decisions mid-checkpoint, which
is exactly what the immutability rule exists to prevent. Recorded for a future labeling-guideline
revision.

## What this says about the circularity concern

The specific worry was that auto-labeling inflates matcher metrics. Inflation requires frozen
**Acceptable** labels that are not really acceptable — a matcher returning one gets credit it
did not earn. Success@1 and returned-match accuracy both key off exactly that class.

**Zero such cases were found: 12 / 12 frozen Acceptables were confirmed against the packaging.**

That is the most reassuring result available from a sample this size, and it must be read with
its denominator. Twelve is small. With 0 errors in 12, the rule of three puts the 95% upper bound
on the Acceptable error rate at roughly **25%** — this check cannot rule out a meaningful error
rate, only the large one. A tighter bound needs a sample stratified on Acceptable pairs
specifically, which would be the natural follow-up if a published number ever depends on it.

Both disagreement directions also matter, and only one was observed: the frozen labels were
**more decisive** than the independent judgment in 3 cases and **less decisive** in none. Nothing
in this sample suggests the labels are systematically generous toward the matcher.

## Reproduction

```bash
cd dash
.venv/bin/python independent_label_check.py   # redraws the same 50 (seeded), refetches photos
```

Outputs: `sample.json` (now carrying `independent_label` per pair), `photos/01..50.jpg`,
`sheet_1..6.png`.
