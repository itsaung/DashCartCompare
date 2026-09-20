# Checkpoint 4 — Semantic matching and evaluation

Status: implementation plan only. Prepared 2026-09-20 against the current repository.
Tactical breakdown for `PROJECT_PLAN.md` Checkpoint 4, in the same form `EVALUATION_PLAN.md`
gives Checkpoint 3 (E1–E7). Sub-checkpoints here are numbered **S1–S7**.

## Outcome

Decide, on measured evidence, whether an embedding or hybrid matcher beats the frozen lexical
baselines on this benchmark; implement exact-mode identity matching, which no baseline currently
does; and produce an acceptance threshold **and** a review band whose costs are declared before
any number is seen. Finish this before basket arithmetic (Checkpoint 5) or the Streamlit demo
(Checkpoint 6).

Like Checkpoint 3, this is a portfolio-scale evaluation of a frozen, AI-adjudicated catalog
benchmark. It does not establish live stock availability, cheapest-basket accuracy, or
independent human ground truth.

## What this inherits

- **Frozen catalog:** `benchmark_catalog_frozen.csv`, 31,398 rows, 5 stores.
- **Frozen benchmark:** 150 requests (79 exact / 71 flexible; 122 answerable, 17
  needs_clarification, 11 no_acceptable_match), 1,658 pool pairs + 153 (v1) + 94 (v2) additional
  judgments.
- **Frozen splits:** `evaluation/splits.json` — dev 90 / validation 30 / test 30. Dev is
  47 exact / 43 flexible; validation 16/14; test 16/14.
- **Frozen v1 report** (`evaluation/`, three TF-IDF baselines) and **frozen v2 report**
  (`evaluation_v2/`, `tfidf_dimension_size_filter`). Both directories are immutable.
- **Current best to beat** — `tfidf_dimension_size_filter`, full-catalog search, practical view:
  Success@1 84.4% (65/77) dev, 88.0% (22/25) validation, 100.0% (20/20) test; returned-match
  accuracy 87.8% dev, 84.6% validation, 90.9% test; return coverage 82.2% dev, 86.7% validation,
  73.3% test; latency median 1,919.5 ms / p95 2,690.1 ms.
- **Machinery to build on, not replace:** `retrieval.py` (filters + baseline functions),
  `tfidf_baseline.py` (named baseline wrappers), `evaluation_metrics.py` (pure metric functions),
  `evaluation_metrics_v2.py` (the "new baseline, same metrics, new directory" pattern),
  `run_experiments_v2.py`, `tune_threshold.py`, `build_splits.py`, `benchmark_config.py`.
- **Test suite:** 331 tests passing via `.venv/bin/pytest -q`. Every new pure function in this
  checkpoint arrives with hand-calculated fixtures, matching the E5/E6 convention.

## Out of scope for Checkpoint 4

- Basket arithmetic, package-count rounding, cost ranking (Checkpoint 5). Flexible mode's
  "rank acceptable choices by actual purchase cost" is a Checkpoint 5 step; Checkpoint 4 ranks by
  match quality only and says so in the report.
- Any Streamlit/UI work (Checkpoint 6).
- Re-scraping, re-labeling the existing pool, regenerating `normalized_catalog.csv`'s size fields,
  or any change to `evaluation/` or `evaluation_v2/`.
- Fine-tuning, training, or distilling an embedding model. The model is pretrained and pinned
  (S1); `PROJECT_PLAN.md` §4 explicitly defers custom model training.
- Latency optimization as a goal. It is measured and reported here; the profiling/fix is a
  Checkpoint 6 prerequisite (see Risks).
- A new catalog-completeness push. Closed as NO — see "Resolved open questions" below.

All Checkpoint 4 outputs go to a new directory, **`evaluation_v3/`**, following the v1→v2 pattern.
Nothing in `evaluation/` or `evaluation_v2/` is read-write; both are read-only inputs.

---

## S1 — Pin the environment and the embedding model

**Inputs:** `.venv` (Python 3.14.3, scikit-learn 1.9.1, numpy 2.5.3, pandas 3.0.5); no
`sentence-transformers` / `torch` installed.

**Method**

1. Install into `.venv` with `.venv/bin/python -m pip install` (the `pip` console script's shebang
   is stale — never invoke `.venv/bin/pip` directly).
2. **Recommended model: `sentence-transformers/all-MiniLM-L6-v2`**, pinned by its Hugging Face
   commit revision, not by tag or by "latest".
   - Why: 6 transformer layers, 22.7M parameters, 384-dimensional output, ~90 MB fp32 on disk —
     the smallest widely-used general sentence encoder with a long track record on short-text
     semantic similarity, which is exactly this task's shape (product titles of 3–12 tokens).
     It is CPU-only by construction; no CUDA, no MPS dependency. A one-off encode of all 31,398
     catalog titles is a single batched forward pass over ~31k short sequences, cached to disk,
     and the query-time cost is one forward pass over one short string plus a dense
     31,398 × 384 matrix-vector product. *Expectation, not a measurement:* both should be well
     under the current ~1.5 s per-query lexical path. S4 measures it; do not quote this
     paragraph as a result.
   - Documented alternative, recorded but not run unless S1 forces it:
     `BAAI/bge-small-en-v1.5` (33M params, also 384-dim, ~130 MB). Marginally stronger on public
     retrieval benchmarks, requires a query instruction prefix, and is a heavier install. Picking
     between two models on benchmark scores would be model selection against the benchmark, which
     this checkpoint forbids before S6/S7 — so the choice is made here, up front, on footprint and
     task-shape grounds alone, and is not revisited because a score came out low.
3. **Python 3.14 compatibility is unverified and is S1's real risk.** Attempt, in this order, and
   stop at the first that works:
   a. `sentence-transformers` + `torch` wheels for CPython 3.14.
   b. `onnxruntime` + `tokenizers` running an exported ONNX version of the same pinned model
      (no torch at inference).
   c. If neither installs, **stop and report**. Do not switch to a different, larger,
      easier-to-install model to get unblocked, and do not rebuild `.venv` on an older Python —
      that would invalidate the 331-test suite's environment. Escalate as an open question.
4. Record, in `evaluation_v3/model_manifest.json`: model id, HF revision SHA, embedding
   dimension, normalization convention (L2-normalized, so cosine == dot product), max sequence
   length and truncation behavior, installed package versions, Python version, machine
   description, and the SHA-256 of the catalog the embeddings were computed against.
5. Compute and cache the catalog embedding matrix once: `evaluation_v3/catalog_embeddings.npy`
   plus `evaluation_v3/catalog_embeddings_key.json`, keyed the same way `retrieval._cache_key`
   keys the TF-IDF cache — catalog hash, **row order**, text-construction version, model id +
   revision, library versions. A stale key means refit, never silent reuse.

**Outputs:** `evaluation_v3/model_manifest.json`, `evaluation_v3/catalog_embeddings.npy`,
`evaluation_v3/catalog_embeddings_key.json`, an updated dependency lockfile.

**Pass criteria:** the model loads and encodes offline from the pinned revision; re-running the
embed step against the unchanged catalog reproduces a byte-identical `.npy`; changing any element
of the cache key invalidates the cache (hand-tested); `.venv/bin/pytest -q` still passes all 331
pre-existing tests after the install.

**Guardrails / anti-goals**

- Do not choose or change the model based on any benchmark score, on any split, at any point after
  S1. Checkpoint 7 requires a pinned model version; a model re-picked after seeing dev numbers is
  a tuned hyperparameter, and must be disclosed as one if it ever happens.
- Do not add a GPU/`device` branch. CPU-only, so reported latency is the latency a reviewer
  reproduces.
- Do not embed anything beyond the catalog text fields S2 defines. No price, no store, no label.

---

## S2 — Brand and variant extraction (catalog side and query side)

This is a **prerequisite for S3**, not an independent goal. `normalized_catalog.csv` /
`benchmark_catalog_frozen.csv` carry `brand` and `variant` columns that are explicit nulls on every
row — `build_normalized_catalog.py` writes `None` deliberately and `PARSING_AUDIT.md` (§ on
deferred fields) records that full extraction was deferred to Checkpoint 4. `parse_shopping_line`
likewise emits no brand or variant field; its `product_type` for `"12 oz Barissimo French Vanilla
ground coffee"` is the whole string `"barissimo french vanilla ground coffee"`. Exact mode cannot
be implemented until both sides produce a comparable brand and variant.

**Inputs:** `benchmark_catalog_frozen.csv` (`raw_title`, `raw_category`), the 150 request texts,
`normalize.py`, `parse_query.py`.

**Method**

1. **New module `product_identity.py`.** Do not modify `build_normalized_catalog.py` or the frozen
   catalog CSV. Extraction is a derived, side-car artifact computed over the frozen catalog:
   `evaluation_v3/catalog_identity.csv`, keyed `(store_id, product_id)`, columns
   `brand`, `brand_confidence`, `variant_tokens`, `identity_status`.
2. **Brand, catalog side — deterministic, evidence-first, no invention.** Two sources, in order:
   a. A brand lexicon induced from the catalog itself: leading title n-grams (n = 1–3) that recur
      across ≥ K distinct `product_id`s within a store and across ≥ 2 `raw_category` values.
      `K` is declared before looking at any evaluation score (proposed K = 5) and recorded in
      `checkpoint4_config.py`. Add the five store/private-label names known from the catalog
      (e.g. ALDI's own lines) by explicit listing, not inference.
   b. Position: the matched lexicon entry must occur as a title prefix or immediately before the
      product-type noun. A lexicon hit anywhere in the string is not sufficient.
   Anything that does not satisfy both is `brand = None, identity_status = "brand_unknown"` —
   explicitly unknown, never a guess. This mirrors the project's standing rule that unknown is a
   third state, not a mismatch.
3. **Variant, catalog side.** Variant is the set of residual descriptor tokens after removing
   brand, product-type head noun, and size tokens, intersected with a declared descriptor
   vocabulary (flavor words, fat-percentage forms, `organic`, `unsweetened`, `whole`, `low fat`,
   `frozen`, `original`, colors, etc.), reusing `normalize.py`'s existing modifier handling where
   it already exists. Tokens outside the vocabulary are dropped, not invented into a variant.
   Output is a normalized token set, not a free-text string, so comparison is set-based and
   spelling/word-order differences do not create false conflicts (`LABELING_GUIDELINES.md` v2:
   "Word order, intervening descriptors and obvious spelling errors do not establish a conflict").
4. **Query side.** Add `brand`, `brand_confidence`, `variant_tokens` to `parse_shopping_line`'s
   output dict via the same `product_identity.py` functions over the raw request text. Additive
   only: every existing key keeps its current value and meaning, so the 331 existing tests and
   both frozen reports stay valid. If a request's brand cannot be resolved, the field is `None`
   and S3 treats that as "identity attribute missing".
5. **Sanity audit, not tuning.** Hand-check a stratified sample of 100 catalog rows and all 150
   request texts against the extractor, and publish the agreement rate with numerator and
   denominator in `evaluation_v3/IDENTITY_EXTRACTION_AUDIT.md`. The audit sample may include dev
   requests; it must **not** consult any label, any prediction, or any validation/test metric.
   `expected.brand` / `expected.variant` in `benchmark_requests.json` are hidden ground truth and
   **must not** be read by `product_identity.py`, by the audit, or by anything in the matcher path
   — the same structural rule `retrieval.py`'s docstring already states.

**Outputs:** `product_identity.py`, `test_product_identity.py`,
`evaluation_v3/catalog_identity.csv`, `evaluation_v3/IDENTITY_EXTRACTION_AUDIT.md`,
additive fields on `parse_shopping_line`.

**Pass criteria:** hand-calculated tests cover brand-prefix hit, mid-string lexicon hit that must
*not* count, private-label brand, unknown brand, variant token set equality under reordering,
variant conflict (`whole` vs `2%`), variant-absent-on-candidate (unknown, not conflict), and
size tokens never leaking into `variant_tokens`. The 331 pre-existing tests still pass unchanged.
The audit reports counts, not a target.

**Guardrails / anti-goals**

- Do not write to `benchmark_catalog_frozen.csv`, `normalized_catalog.csv`, or any file under
  `evaluation/` or `evaluation_v2/`.
- Do not use an LLM call at inference time to extract brand. The matcher must be deterministic and
  reproducible from a clean checkout; `PROJECT_PLAN.md` §4 defers LLM agents.
- Do not tune `K`, the descriptor vocabulary, or the lexicon against any evaluation metric. If a
  later sub-checkpoint's failure analysis suggests a change, that change makes every subsequent
  number exploratory and must be labeled as such.
- Do not let "brand unknown" silently become "brand matches".

---

## S3 — Exact-mode identity matching

**Inputs:** S2's identity fields (both sides), `retrieval.filter_by_dimension`,
`retrieval.filter_by_package_size`, the benchmark's per-request `matching_mode` (already carried,
already broken out by `evaluation_metrics.py`'s `by_matching_mode`).

`matching_mode` is request metadata the user supplies in the real product (`PROJECT_PLAN.md` §1:
the shopper picks exact or flexible per line), not a hidden label — so the matcher may read it.
Everything else under `expected` stays hidden.

**Method**

1. New `retrieval.filter_by_identity(candidates, identity_df, structured, mode)`:
   - **exact mode** requires brand match **and** variant compatibility **and** package-size
     identity (S3 reuses `filter_by_package_size` unchanged for the size half — it is already
     total-vs-total and already unit-equivalent-only).
   - A **confirmed conflict** on brand or variant (a specific different value present on both
     sides) → candidate dropped.
   - A **missing identity attribute** on either side (request has no brand, or candidate's brand
     is `brand_unknown`) → the candidate is not dropped and not accepted; the request's response
     becomes `needs_clarification`. `PROJECT_PLAN.md` Checkpoint 4: "If key identity attributes are
     missing, request review." This is the one place the identity gate can *raise* the abstention
     rate, and that is the intended behavior.
   - **flexible mode**: brand is not required unless the request states one; variant and product
     type still enforced. Package size may differ — but Checkpoint 4 does **not** yet do the
     quantity arithmetic that `PROJECT_PLAN.md` requires before allowing a size change
     ("Allow package-size changes only when quantity can be calculated"), so flexible mode in
     Checkpoint 4 keeps `filter_by_package_size`'s current same-total rule and the report states
     explicitly that size-flexible matching lands in Checkpoint 5 with the basket engine.
2. New response state handling: exact-mode requests never fall through to a substitute. If the
   identity gate empties the candidate list, the response is `no_acceptable_match` or
   `needs_clarification` (per the rule above) — never a best-effort return. Add an explicit test
   asserting that for an exact request with an unmatched brand, no result is returned at any
   threshold, including threshold 0.0.
3. New named baseline in `tfidf_baseline.py`: `tfidf_identity_filter` =
   `tfidf_dimension_size_filter` + `filter_by_identity`. Separate function, not a modification of
   `attribute_and_size_filter_baseline` — the v1/v2 baselines stay byte-identical, same rule
   Checkpoint 3.1 followed.
4. Score it through the existing pipeline into `evaluation_v3/` (S4's runner covers this; S3 only
   needs the matcher and its tests).

**Outputs:** `retrieval.filter_by_identity`, `tfidf_baseline.run_identity_baseline`,
tests in `test_retrieval.py` / `test_tfidf_baseline.py`.

**Pass criteria:** hand-calculated tests for: exact + brand conflict → dropped; exact + brand
unknown on candidate → `needs_clarification`, zero results; exact + brand match + variant conflict
→ dropped; exact + all three identity attributes match → retained; flexible + different brand →
retained; flexible + stated brand + different brand → dropped; exact request that would have
returned a plausible substitute under `tfidf_dimension_size_filter` returns nothing instead.
No test asserts a metric value; all assertions are on matcher behavior.

**Guardrails / anti-goals**

- Never downgrade an exact request to a substitute, at any threshold, for any coverage benefit.
  If exact-mode coverage collapses, that is the finding and it gets reported as one.
- Do not read `expected.brand` / `expected.variant` / `reference_product_ids` anywhere in the
  matcher path.
- Do not reuse `claude_auto_label.py`'s 3% `SIZE_MISMATCH_TOLERANCE`. The unit-equivalent-only
  comparison (`PACKAGE_SIZE_ROUNDING_TOLERANCE = 0.01`, already in `retrieval.py`) is the one in
  force, per `LABELING_GUIDELINES.md` v2 and the 2026-09-19 size-tolerance audit.

---

## S4 — Embedding similarity baseline

**Inputs:** S1's pinned model and cached catalog embeddings; S2/S3's identity machinery
(available but **not** applied in this sub-checkpoint's headline baseline — see below).

**Method**

1. `embedding_retrieval.py`: `embedding_search(query_text, embeddings, catalog_df, top_k)` —
   L2-normalized cosine over the full 31,398-row matrix, the same deterministic tie-break
   `benchmark_config.tie_break_key` (`-score, store_id, product_id`), the same
   "score > 0 to be ranked" convention and the same explicit empty-result behavior as
   `retrieval._ranked`.
2. Two named baselines, so the embedding's own contribution is separable from the filters':
   - `embed` — raw embedding ranking, no gate, no filter, no threshold. The direct counterpart of
     v1's `tfidf`.
   - `embed_dimension_size_filter` — the same gates as `tfidf_dimension_size_filter`
     (parser-clarification gate, dimension filter, package-size filter), floor 0.0. The direct
     counterpart of v2's current best, differing only in the retriever.
   Each uses the same candidate prefilter depth `max(top_k * 4, 20)` as the lexical baselines, so
   depth is not a confound.
3. Run E4's two experiments (pool ranking + full-catalog search) through a
   `run_experiments_v3.py` modeled on `run_experiments_v2.py`, reusing `find_new_candidates` and
   the union-of-already-labeled logic. Any newly surfaced top-5 pair goes to
   `evaluation_v3/new_candidates_to_review.json` and is adjudicated by the same rules
   (`apply_new_candidate_review_v3.py`, reusing `apply_new_candidate_review.py`'s corrected checks
   — product-type confirmation, known-variant shadowing, false-friend list, unit-equivalent-only
   size), never merged back into v1's or v2's decisions.
4. Metrics via `evaluation_metrics_v3.py`, importing `evaluation_metrics.py`'s pure functions
   unchanged (the v2 pattern), with the label lookup merged across four sources: v1 pool, v1
   additional, v2 additional, v3 additional.
5. Measure warm query median and p95 and cold model-load/encode time separately, as in E5.

**Outputs:** `embedding_retrieval.py`, `run_experiments_v3.py`,
`apply_new_candidate_review_v3.py`, `evaluation_metrics_v3.py`,
`evaluation_v3/predictions.jsonl`, `evaluation_v3/new_candidates_to_review.json`,
`evaluation_v3/additional_judgments.json`, `evaluation_v3/metrics.json`,
`evaluation_v3/RESULTS_TABLE.md`.

**Pass criteria:** predictions written before any label is consulted; zero unjudged top-5 results
before any final number is quoted (preliminary tables must disclose judgment coverage, per E4);
re-running reproduces identical predictions; deterministic behavior on tied scores and empty
queries covered by hand-calculated tests.

**Guardrails / anti-goals**

- Do not tune the prefilter depth, `top_k`, or the text-construction fields to improve a score.
- Do not treat cosine similarity as a probability or a calibrated confidence. It is a ranking
  score; `PROJECT_PLAN.md` says so explicitly and the v1 report already honors it.
- Do not drop or re-label an unjudged result to improve a number. Unjudged is a separate state.
- Do not compare embedding scores to TF-IDF scores numerically. The two similarity scales are not
  commensurable; only the *metrics* are comparable, and only on the same split.

---

## S5 — Hybrid baseline

**Inputs:** S3's identity filter, S4's embedding retrieval, the existing TF-IDF retrieval.

**Method**

1. `hybrid_retrieval.py`: union the lexical top-N and the embedding top-N (N declared up front,
   proposed N = 50 each), then fuse. Use **reciprocal rank fusion** with a declared constant
   (`RRF_K = 60`, the standard value, fixed before any run), not a weighted score blend —
   RRF needs no cross-scale calibration between a TF-IDF cosine and an embedding cosine, and it has
   no free weight to tune on dev. If a weighted blend is used instead, the weight is a tuned
   hyperparameter, must be swept on dev only under S6's discipline, and must be disclosed as one.
2. Apply the constraint stack in one fixed order after fusion: parser-clarification gate →
   dimension filter → package-size filter → identity filter (S3). Retrieve, then constrain —
   the order `PROJECT_PLAN.md` Checkpoint 4 specifies.
3. Name: `hybrid_identity_filter`. Floor 0.0 at this stage; thresholds are S6's job.
4. Run through the same S4 pipeline (same runner, same review queue, same metrics module, same
   directory).

**Outputs:** `hybrid_retrieval.py`, `test_hybrid_retrieval.py`, additional records in
`evaluation_v3/predictions.jsonl`, extended `evaluation_v3/metrics.json` and `RESULTS_TABLE.md`.

**Pass criteria:** hand-calculated RRF fixtures (a candidate ranked 1 lexically and 40 semantically
vs. one ranked 5 and 5 — the expected fused order computed by hand, not by running the code);
fusion is deterministic under ties; a candidate appearing in only one retriever's list is handled
explicitly and tested; the constraint stack applies in the declared order and each filter's effect
is separately observable.

**Guardrails / anti-goals**

- Do not add a third retriever, a reranker, or a cross-encoder. `PROJECT_PLAN.md` asks for three
  approaches; the comparison is the deliverable, not a leaderboard climb.
- Do not tune `N` or `RRF_K` after seeing results. They are declared in `checkpoint4_config.py`
  before S5 runs.
- "Simplest method with the best validation tradeoff" is the selection rule (`PROJECT_PLAN.md`).
  If hybrid ties the embedding baseline or the lexical baseline on validation, the simpler one
  wins. Write that down before S7, not after.

---

## S6 — Acceptance threshold and review band, tuned on dev only

E6 gives the methodology for a single threshold. Checkpoint 4 needs **two** cut points.

**Inputs:** S4/S5 dev-split predictions at floor 0.0, `evaluation_metrics.py`'s label lookup,
`build_benchmark.NO_MATCH_AUDIT`.

**Method**

1. **New constants, in a new module `checkpoint4_config.py`.** Do not touch, reuse, or overwrite
   `benchmark_config.MIN_SIMILARITY = 0.65`. That value is frozen for v1's
   `tfidf_dimension_filter_threshold` and is on a TF-IDF cosine scale that has no meaning for an
   embedding or an RRF score. The new constants are `ACCEPT_THRESHOLD` and `REVIEW_FLOOR`, one
   pair per baseline family, each `None` until this sub-checkpoint sets it — and, following
   `tfidf_baseline.py`'s existing convention, calling a thresholded baseline before S6 has run
   **raises** rather than falling back to a guessed value.
2. **Three-way outcome.** For the top-1 score `s`:
   - `s >= ACCEPT_THRESHOLD` → automatic match.
   - `REVIEW_FLOOR <= s < ACCEPT_THRESHOLD` → **review band**: surfaced to the user with
     candidates, explicitly not an automatic answer.
   - `s < REVIEW_FLOOR` → no match.
   The identity gate (S3) and the parser gate can route a request to review *independently of
   score*; a missing identity attribute is a review outcome at any score.
3. **Predeclared grid.** Both cut points swept jointly over a declared grid with the constraint
   `REVIEW_FLOOR <= ACCEPT_THRESHOLD`. Scale-appropriate per family (an embedding cosine over
   short product titles concentrates in a narrower band than a TF-IDF cosine, so a 0.00–0.80 /
   0.05 grid copied from E6 may be the wrong resolution): declare each family's grid in
   `checkpoint4_config.py` **from the dev score distribution's quantiles alone, before any cost is
   computed**, and record the grid in the output. Declaring a grid from dev scores is itself a use
   of dev data; that is permitted (dev is the tuning split) and must be stated in the report.
4. **Cost function — extends E6's, with a new outcome.** Per dev request, averaged:
   - **0** — appropriate acceptable automatic match (true answerable, returned, top-1's
     *conservative* label Acceptable), or correct abstention on a true-unanswerable request.
   - **0.5** — **deferred to review.** A review outcome is not free: it costs the user attention
     and it is a match the system could not make. It is strictly cheaper than a confident wrong
     answer and strictly cheaper than a silent abstention on an answerable request, because the
     user is shown candidates and can resolve it in one step. Applied to a review-band outcome on
     *any* request, answerable or not — deferring on a genuinely unanswerable request is
     mildly wasteful rather than correct, which is why it is not 0.
   - **1** — abstaining outright on a true-answerable request (false abstention).
   - **2** — an incorrect automatic match, an automatic match on a true-unanswerable request, or
     an unresolved top-1 under conservative labels.
   The 0.5 value is a **declared design preference, not an estimate of anything measured.** It
   encodes: one wrong automatic grocery match costs about four review deferrals. It is written into
   `checkpoint4_config.py` with this justification before the sweep runs, and the sweep is **also**
   run at 0.25 and 0.75 as a declared sensitivity check, with all three chosen `(ACCEPT_THRESHOLD,
   REVIEW_FLOOR)` pairs reported. If the choice of 0.5 changes the selected pair, that fact is
   reported; the 0.5 run remains the one that selects, chosen in advance.
5. **Exclusions.** Same as E6: dev `no_acceptable_match` requests whose `NO_MATCH_AUDIT` confidence
   is not in `{"confirmed", "confirmed by construction"}` (r052, r129) are excluded from tuning and
   the count disclosed.
6. **Tie-break.** Lowest cost; ties broken by greater confirmed-correct automatic-match count, then
   by lower review-band width (`ACCEPT_THRESHOLD - REVIEW_FLOOR`), then by lower
   `ACCEPT_THRESHOLD`. Declared before the sweep.
7. Save the complete dev cost surface, not just the argmin.

**Outputs:** `tune_threshold_v3.py`, `test_tune_threshold_v3.py`,
`evaluation_v3/threshold_selection.json` (grid, full cost surface, chosen pair, tie-break trail,
excluded request ids, sensitivity runs), frozen constants in `checkpoint4_config.py`,
optionally a dev precision/coverage/review-rate plot.

**Pass criteria:** hand-calculated fixtures for every cost branch including the new 0.5 branch and
the `REVIEW_FLOOR == ACCEPT_THRESHOLD` degenerate case (which must reduce exactly to E6's
two-outcome behavior); no validation or test label enters selection, asserted by a test that the
tuning function is never given a non-dev record; re-running reproduces the identical chosen pair.

**Guardrails / anti-goals**

- Do not touch `benchmark_config.MIN_SIMILARITY`.
- Do not adjust the cost function after seeing which threshold it picks. If the cost function is
  revised, the revision and its reason are documented and every number after it is exploratory.
- If the optimum defers or abstains nearly everywhere, report that honestly as a weak matcher. Do
  not widen the grid, soften the cost, or reach for validation to rescue it.
- The review band is not a place to hide errors. Review rate is reported with the same prominence
  as precision and coverage, with numerator and denominator.

---

## S7 — Final evaluation, model selection, and writeup

**Inputs:** everything above; `evaluation/splits.json` (unchanged).

**Method — strict order, no step revisited**

1. **Dev**, all baselines, all variants. All analysis, all error inspection, all iteration happens
   here and stops here.
2. **Freeze.** Write `evaluation_v3/frozen_config.json`: the selected method (one of
   `tfidf_dimension_size_filter` [the incumbent], `embed_dimension_size_filter`,
   `hybrid_identity_filter`, `tfidf_identity_filter`), the pinned model revision, both cut points,
   the fusion constants, the identity-extraction version, and the code SHA. Commit it.
3. **Validation, inspected once.** Model/threshold selection uses validation, per the hard
   constraint. If validation prompts a configuration change, the revision is documented, the
   configuration is re-frozen, and the validation inspection is disclosed as having happened more
   than once — the test split still stays untouched.
4. **Test, run once, after step 3 is final.** A test result may be corrected only for an evaluator
   bug, transparently. Using a test error to change the matcher makes every subsequent number
   exploratory and must be labeled so.
5. Full-split-by-split reporting: dev / validation / test separately, exact and flexible broken out
   separately (`by_matching_mode` already exists), conservative bounds and practical view both,
   every rate with its numerator and denominator, and every sample size shown. With 16 exact / 14
   flexible per held-out split, no single-split difference of a few points is interpretable —
   state that inline, as v1's report does.
6. Failure analysis of 10–15 representative real cases, grouped by brand, variant, size, dietary
   attribute, ambiguity, and retrieval miss, using actual queries and actual catalog products —
   no invented scores.
7. Latency: warm median and p95 per baseline; cold model load and catalog-encode time separately;
   the measured hardware named.

**The 95% automatic-match-precision criterion — exactly how it is measured**

- **Definition.** Automatic-match precision = (requests whose response is an *automatic match*,
  whose ground-truth answerability is `answerable`, and whose returned top-1 candidate's label is
  `Acceptable`) ÷ (all requests receiving an *automatic match*). Review-band outcomes are excluded
  from **both** numerator and denominator — they are not automatic matches. Abstentions are
  excluded from both. A return on a `needs_clarification` or `no_acceptable_match` request counts
  against the numerator, never for it, even when the candidate looks compatible — this is
  `evaluation_metrics.returned_match_accuracy`'s existing response-policy rule, reused unchanged.
- **Which label view.** The headline number is reported in **both** views: practical (binary
  best-guess labels) and conservative (best guesses revert to `Needs clarification`, giving a
  lower and an upper bound). The 95% criterion is judged against the **conservative lower bound**.
  Clearing it on the practical view only is reported as exactly that, not as clearing it.
- **Which split.** Validation selects; **test** is the reported criterion check, run once. Dev is
  reported for completeness and is not the criterion.
- **Coverage is reported alongside, always.** `PROJECT_PLAN.md`: "Report coverage alongside
  precision so rejecting everything cannot look successful." Report automatic-match rate, review
  rate, and abstention rate as a three-way partition summing to 1, with counts.
- **Constraint-violation check.** Separately assert: zero automatic matches on the test split
  violate an explicit hard constraint (confirmed brand conflict, confirmed variant conflict,
  confirmed size conflict, dimension conflict). This is a distinct pass criterion from the 95%
  number and is checked by an explicit script, not by eye.

**If 95% is not met — the pre-declared honorable outcome.** `PROJECT_PLAN.md` Checkpoint 4 states:
"If embeddings do not improve performance, retain the baseline and explain the finding." That is
declared here, in advance, as a legitimate completion of this checkpoint, not a failure:

- Retain `tfidf_dimension_size_filter` (or whichever configuration validation actually preferred)
  as the shipped matcher.
- Publish the measured numbers as they are, with denominators.
- Publish the precision/coverage/review-rate curve so a reader can see what threshold *would* reach
  95% and at what coverage cost — and state plainly whether that coverage is usable.
- Name the specific mechanisms blocking it, drawn from the failure analysis.
- Do **not** raise the threshold until the automatic-match denominator is small enough to hit 95%
  and report that as success. A precision number on a tiny denominator is reported with its
  denominator and is not a pass.
- Do **not** change the benchmark, the labels, or the splits to reach the number.
- Checkpoint 4 is complete when the comparison is honest, reproducible and documented. No score
  target is required for checkpoint completion — the same rule E7 already operates under.

**Outputs:** `evaluation_v3/SEMANTIC_RESULTS.md`, `evaluation_v3/frozen_config.json`,
`evaluation_v3/metrics.json`, `evaluation_v3/RESULTS_TABLE.md`,
`evaluation_v3/constraint_violation_check.json`, updated `PROJECT_PLAN.md` Appendix A.

**Pass criteria:** a fresh run on the same inputs reproduces predictions and metric values; zero
unjudged top-5 results anywhere in the final report; the test split was scored exactly once after
`frozen_config.json` was committed (visible in git history); the constraint-violation check is
zero on test; coverage, review rate and precision are all reported with counts.

**Guardrails / anti-goals**

- Do not modify `evaluation/` or `evaluation_v2/`.
- Do not re-run test to "confirm" a number.
- Do not report a percentage without its numerator and denominator.
- Do not describe cosine similarity as a confidence percentage anywhere in the writeup.

---

## Risks

1. **Overfitting to dev.** Dev is 90 requests, 77 answerable, and its 50 pilot requests shaped
   `LABELING_GUIDELINES.md` itself. Every decision in S2 (lexicon threshold K, descriptor
   vocabulary), S5 (N, RRF_K), and S6 (grid, cost weights) is a knob. Mitigation: all of them
   declared in `checkpoint4_config.py` before their first run, with the declaration committed; the
   report lists every knob and when it was set. Residual risk is real and should be stated in the
   writeup, not claimed away.
2. **The frozen test split.** 30 requests, 20 answerable, 16 exact / 14 flexible. The incumbent
   already scores 100.0% (20/20) Success@1 on it — there is no headroom to demonstrate there, and a
   single request is 5 percentage points. Test is a sanity check on the selection, not evidence of
   a difference between methods. Any claim of one method beating another must rest on dev and
   validation, with sample sizes shown. The temptation to peek after a disappointing validation
   number is the specific failure mode; `frozen_config.json` committed before the test run is the
   control.
3. **Latency — deferred twice, now a live blocker for Checkpoint 6.** Current full-catalog search
   is ~1,520 ms median / ~1,947 ms p95 for `tfidf_dimension_filter` and ~1,920 / ~2,690 ms for
   `tfidf_dimension_size_filter`, against Checkpoint 6's sub-3-second target *for a whole 10-item
   list*. At ~1.9 s/query a 10-item list is ~19 s — roughly 6x over target before any embedding
   work. v1's §5 already found the distribution bimodal and pointed at per-query overhead
   (`parse_shopping_line` and/or `vectorizer.transform`) rather than the 31k-row sparse cosine.
   Adding a transformer forward pass and a second constraint pass will not help. Two things the
   plan does about it: (a) S4 measures embedding query time and catalog-encode time separately, so
   the report says which stage costs what instead of guessing again; (b) this plan states
   explicitly that a profiling pass is a **prerequisite for Checkpoint 6**, not an optional
   follow-up, and that Checkpoint 6 cannot claim its own pass criterion until it happens. It is
   deliberately *not* folded into Checkpoint 4 — mixing optimization into a measurement checkpoint
   changes what is being measured mid-flight. Third deferral, now with an explicit owner.
4. **Benchmark labeling limitations.** Every label — the 1,658 pool pairs, the 95-photo review, the
   153 v1 additional judgments, the 94 v2 additional judgments — is AI adjudication from frozen
   catalog text and images, not independent human review or live product-page verification. 56 pool
   labels are explicit best guesses. Request-level answerability for r052 and r129 is
   "pattern-consistent, not independently re-searched." A measured improvement here is an
   improvement against *this adjudication*, and the writeup must say so in those words. S4's new
   candidates inherit the same limitation and the same review rules.
5. **S2 is the plan's largest unknown.** Brand/variant extraction from raw titles across five
   stores with inconsistent conventions is a real parsing problem, and its quality caps S3's exact
   mode entirely. If the S2 audit shows weak extraction, S3's identity filter will mostly emit
   "identity attribute missing → review", which will show up as a coverage collapse in exact mode.
   That outcome is correct behavior and a reportable finding — but it is also the most likely way
   this checkpoint produces a disappointing headline number. Sequencing S2 before S3 and auditing
   S2 on its own terms (not through a downstream metric) is the mitigation.
6. **Python 3.14 dependency availability** (S1). If neither torch nor ONNX Runtime installs, S4 and
   S5 cannot run at all and the checkpoint reduces to S2/S3 plus a negative finding about the
   environment. Detected in S1, before any other work is built on it.
7. **Model download requires network access and an unpinned upstream.** A Hugging Face repository
   can change; pinning to a revision SHA and caching the weights locally is the control, and the
   SHA goes in `model_manifest.json` so Checkpoint 7's reproducibility claim is checkable.

---

## Resolved open questions

### Should Checkpoint 4 divert to catalog data completeness instead of matcher work? — **No.**

A read-only audit of catalog size-parse failures was run on 2026-09-20 (measurement, not estimate):

- 28,276 / 31,398 catalog rows (90.06%) have a resolvable canonical package size.
- Of the 3,122 that do not: 1,830 missing size, 1,000 genuinely priced by weight (a correct
  exclusion by design, per Checkpoint 2), 222 unrecognized format, 70 non-size labels.
- 80.8% of the unresolved non-variable-weight rows are **non-grocery**: Household 990,
  Personal Care 302, Baby 117, Flowers 93, Beauty 55, Gift Cards 50, and others.
- Restricted to food categories and excluding variable-weight rows: **406 / 20,291 = 2.00%** of
  grocery rows fail to resolve a size. Of those, 300 are a missing source field (a catalog data
  gap) and 106 are a parser gap.

The two residual evaluation failures previously discussed together are two different things:

- "Deli Fresh Turkey Breast Mega Pack" (Ralphs) has a **blank `raw_size`** — a genuine catalog data
  gap, fixable only by better source data.
- "Organic Honeycrisp Apples (each)" is `$3.99/lb`, `variable_weight` — **working as designed**.
  Checkpoint 2 deliberately excludes variable-weight products from automatic basket calculation.
  No parser change and no better catalog data fixes this, because there is nothing to fix.

**Conclusion.** A full catalog-completeness push buys back at most 300 food rows (300/20,291 =
1.5%); a parser fix at most 106 (106/20,291 = 0.5%). Catalog completeness is not the bottleneck,
so the Checkpoint 3.1 §6 suggestion that "catalog data completeness, not matcher logic, is the real
bottleneck for this slice" is **not supported by the measurement** and is closed. Checkpoint 4
proceeds on the matcher, as originally planned.

Note carefully what this measurement does and does not establish: it establishes that catalog size
completeness has little headroom. It does **not** establish that the matcher has headroom. Whether
the matcher does is precisely what S4–S7 measure, and a null result there is a legitimate outcome.

### The two small parser gaps — **deferred, recorded, not a Checkpoint 4 sub-task.**

Two real parser gaps were found: `bunch` / `1 bunch` (46 rows, a legitimate produce unit) and
compound size forms (`12 x 12 fl oz`, `8 ct, 12 oz`, `25 pk`). Together these are a subset of the
106 parser-gap food rows — at most 0.5% of grocery rows, and no residual evaluation failure in
`evaluation_v2/SIZE_BASELINE_RESULTS.md` §4 is attributed to either. Fixing them would change the
frozen catalog's derived size fields, which would invalidate the TF-IDF cache key, the embedding
cache key, and the direct comparability of v1/v2/v3 results against the same frozen inputs — a
disproportionate cost for a sub-1% data gain, in the middle of the checkpoint whose entire purpose
is a controlled comparison. **Decision: defer to a scoped post-Checkpoint-4 task**, recorded in
`PROJECT_PLAN.md` Appendix A with these numbers so the reason is retrievable. If it is ever done,
it needs its own catalog re-freeze and its own report directory.

### `parse_shopping_line`'s "pack of" dimension gap — **deferred, unchanged.**

`"a 12 fl oz x 12 ct pack of ..."` (r142) parses as dimension `count`, so volume candidates are
filtered out before size matching runs. Affects v1 and v2 identically. It is a `parse_query.py`
bug, not a matcher bug, and fixing it mid-checkpoint would change the request-side inputs that
v1/v2/v3 are being compared on. Carried forward unchanged; noted in S7's writeup so a reader does
not mistake it for a Checkpoint 4 regression.

---

## Open questions (unresolved from the repository)

1. **Do `torch` / `sentence-transformers` / `onnxruntime` wheels exist for CPython 3.14.3 on this
   machine's platform?** Not checked — checking would require installing, which is out of scope for
   a read-only planning pass. S1 resolves it first, with a declared fallback ladder and a declared
   stop condition.
2. **What is the actual per-query embedding latency here?** Unmeasured. The expectation stated in
   S1 (well under the current ~1.5 s) is an expectation from operation counts, not a finding, and
   must not be quoted as one. S4 measures it.
3. **How good is brand/variant extraction achievable from these titles?** Unknown until S2's audit
   runs. No prior measurement exists in the repo — `PARSING_AUDIT.md` records only that the fields
   were deliberately left null.
4. **Is the exact/flexible benchmark split large enough to support a per-mode conclusion?**
   Dev has 47 exact / 43 flexible; validation and test have 16/14 each. Per-mode held-out rates on
   n=14–16 are very noisy. This plan reports them with counts and declines to draw per-mode
   conclusions from the held-out splits; whether that is too conservative is a judgment call left
   open.
5. **Should the review band's 0.5 cost be something else?** There is no measured basis for any
   particular value — it is a declared design preference. The sensitivity runs at 0.25 and 0.75
   expose how much the choice matters, but they do not determine the right value. Left explicitly
   unresolved.
6. **Does the frozen test split have enough signal to check the 95% criterion at all?** With 20
   answerable test requests and an incumbent already at 100.0% (20/20) Success@1, the
   automatic-match denominator on test may be well under 20, at which point a 95% precision figure
   is a statement about ~15 requests. The plan reports the denominator prominently; whether a
   criterion this coarse should be treated as a gate is a question for the writeup rather than
   something this plan can settle.
7. **What should happen if validation prefers a different method than dev does?** The declared rule
   is "simplest method with the best validation tradeoff" (S5), but "simplest" between an embedding
   baseline and a hybrid one is a judgment. Pre-declaring a full tie-break order across four
   candidate configurations is left open; it should be written down in `frozen_config.json` before
   validation is inspected, not after.
