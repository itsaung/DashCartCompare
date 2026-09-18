# Labeling guidelines — Checkpoint 3 benchmark

**Version: v1** (pilot). Bump this version on any meaningful rule change; a
decision recorded under an older version is stale once the version bumps,
even if the request/catalog didn't change (`build_benchmark.py` enforces
this via each decision's stamped `labeling_guideline_version`).

## The three labels

- **Acceptable** — this candidate genuinely satisfies the request as a
  reasonable shopper would read it.
- **Needs clarification** — genuinely uncertain, not confidently right or
  wrong. This is not a dumping ground for "not obviously incorrect" — see
  the specific triggers below.
- **Incorrect** — clearly does not satisfy the request (wrong product type,
  wrong flavor/variant when one was specified, wrong dimension, wrong brand
  when brand was specified and not substitutable, or — for a
  `no_acceptable_match` request — the closest thing the catalog has, which is
  still not an acceptable answer).

**Needs clarification never counts as Acceptable** for any metric
(`tfidf_baseline.py`'s Precision@1/accuracy-among-returned-matches). It's a
distinct outcome, not a softened Incorrect either.

## Explicit rules

1. **`dimension_review_flag=True` candidates are Needs clarification by
   default, not auto-Incorrect**, even when the literal parsed dimension
   disagrees with the request (e.g. a beverage recorded as bare "oz" —
   weight — against a "fl oz" request). The flag exists specifically because
   `build_normalized_catalog.py` can't tell if that's a real product-category
   error or a true weight-sold item; don't resolve that uncertainty by
   guessing. Only label it Incorrect if another `expected` field
   (brand/variant) independently rules it out regardless of dimension.

2. **A request's `reference_product_ids` are not automatically Acceptable.**
   They're the author's best-effort answer, but the reviewer's own read of
   the candidate against `expected` is what actually counts. If a reference
   turns out wrong on review, label it what it actually is and note why —
   don't silently trust the draft.

3. **`allowed_substitutions` governs brand/variant judgment calls.** If
   `expected.allowed_substitutions` says `{"brand": "any"}`, a different
   brand satisfying every other attribute is Acceptable, not Incorrect. If it
   says nothing about flavor/variant, a stated flavor/variant must actually
   match (or be unconfirmable from the title, in which case Needs
   clarification, not a guessed Incorrect).

4. **Multiple simultaneously-Acceptable candidates are expected and
   correct, not a labeling error** — especially for `flexible` requests. A
   generic "greek yogurt" request with six different acceptable flavors in
   the pool is not a sign something went wrong.

5. **An `answerability = "no_acceptable_match"` request can still have every
   candidate in its pool be Incorrect** (or Needs clarification) — that's the
   expected outcome, not a bug in the pool. E.g. "2 lb chicken breast": every
   real candidate is a variable-weight product with no fixed 2 lb package,
   so none of them are actually a satisfying answer regardless of how
   similar their title looks.

6. **An `answerability = "needs_clarification"` request** (parser genuinely
   can't tell what's meant, or the product's normal selling unit doesn't
   match what was asked) doesn't require every candidate to be labeled
   Incorrect — grade each candidate on its own merits against `expected`;
   the *request's* answerability and a *candidate's* label are different
   judgments.

7. **Size/quantity mismatches**: a candidate whose package size doesn't
   match `expected.size` (when specified and not substitutable) is
   Incorrect, not Needs clarification — this is a hard, checkable fact once
   the label reviewer looks at `raw_size`/`pkg_canonical_total`, not a
   genuine ambiguity.

## Review process notes

- The review UI shows `expected` and the candidate's real attributes but
  hides the draft label, retrieval source, and similarity score until after
  you submit your own decision. Decide first, reveal after (optional) — the
  reveal is for calibration logging, never a substitute for your own call.
- Requests are queued grouped by `paraphrase_group` so related requests are
  reviewed near each other.

## Pilot notes (from the 50-request review pass)

The pilot's 574 candidate pairs ended up reviewed in three passes: an
initial human pass (partial), an automated pass (`claude_auto_label.py`,
explicit rules over brand/variant/dimension/size) for the remainder, and
then an independent human audit that caught 42 mislabeled pairs the
automated pass got wrong. Two real, systematic gaps came out of that audit
-- both relevant to how the remaining 100 requests get pooled and reviewed,
not just one-off mistakes:

1. **Retrieval noise can surface a candidate with no real connection to the
   request at all** — e.g. a "Dozen Roses" listing turned up as a candidate
   for a dozen-eggs request, purely because `synonym_assisted_search` matched
   the literal word "dozen" with no product-type sanity check at all. This
   is a retrieval-quality limitation (`retrieval.py`), not a labeling-rule
   gap — no attribute-comparison rule would "almost" get this right, since
   the candidate isn't a near-miss on any axis, it's simply an unrelated
   product category. Reviewers (human or automated) need to check basic
   product-type plausibility first, before getting into brand/size/variant
   detail — an Incorrect label here is about category, not attributes.

2. **The automated labeler only checks brand/variant/dimension/size against
   `expected` — it never confirms the candidate is even the right *product
   type*.** This under-flagged real mismatches as Acceptable in the pilot:
   corn snacks labeled Acceptable against a yogurt request, candy against a
   chips request. Both happened because nothing in `expected` explicitly
   states "must be a yogurt" or "must be a chip" — that's implicit in the
   request text itself, which `auto_label` doesn't check against the
   candidate's `raw_category`/title at all. This is a real gap in
   `claude_auto_label.py`'s rule set, not just noisy retrieval; before the
   full 150-request benchmark's automated pass, `auto_label` should add an
   explicit product-type/category sanity check (e.g. comparing the
   request's parsed `product_type` head noun against `raw_category`, in
   addition to the existing brand/variant/dimension/size checks), and any
   automated-labeled batch should still get an independent human audit
   pass like this one rather than being trusted outright.

No new labeling *rule* (in the numbered list above) needed to change — the
three-label semantics held up. What changed is the process: automated
labeling at this pool-construction quality needs a real audit pass, not
just spot-checking, and that audit should specifically target "is this
candidate even the right kind of product" before getting into finer-grained
attribute checks.
