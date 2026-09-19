# Checkpoint 3 — Evaluation pipeline and baseline results

Status: implementation plan only. Prepared 2026-09-18 against the current repository.

## Outcome

Produce a reproducible report showing whether TF-IDF retrieves suitable grocery products, how often the system should abstain, what the current dimension filter changes, and which errors deserve improvement next. Finish this before embeddings, basket optimization, or the app interface.

This is a portfolio-scale evaluation of a frozen, AI-adjudicated catalog benchmark. It does not establish live stock availability, cheapest basket accuracy, or independent human ground truth.

## Current inputs

- Frozen catalog: 31,398 products from five stores.
- Requests: 150; 122 answerable, 17 needing clarification, 11 marked no acceptable match.
- Candidate pairs: 1,658; 475 Acceptable and 1,183 Incorrect in the practical labels.
- Of these, 56 labels are explicitly best guesses. For conservative scoring, use `conservative_label` where present, otherwise `reviewer_label`.
- `retrieval.py` already fits/caches catalog TF-IDF and implements lexical retrieval and a dimension-filtered matcher.
- The current matcher checks parser clarification and package dimension; it does not enforce brand, flavor, numeric size, or multipack count. It retrieves at most `max(4*k, 20)` lexical candidates before filtering. Preserve and disclose these limitations in baseline v1.
- `MIN_SIMILARITY` is unset. Split construction, metrics, evaluation runner, and results reporting still need implementation.

## Checkpoint E1 — Validate and freeze benchmark v1

Implement `build_benchmark.py` to validate inputs and export evaluation-ready records. Do not regenerate requests, overwrite labels, refit normalization, or scrape during evaluation.

Validation must reject:

- Duplicate request IDs or duplicate `(store_id, product_id)` catalog identities.
- Missing products, missing current-pool decisions, invalid labels, or duplicate request/product pairs.
- Catalog, current-decision, candidate-pool, request-content, or guideline version/hash mismatches.
- Guessed labels without an explicit uncertainty flag and conservative interpretation.
- Conflicting labels for the same product within equivalent paraphrase groups.

The manifest contains historical audit hashes as well as the current hash. Validate against `current_decisions_sha256`, not the earlier pre-photo audit hash. Preserve historical provenance.

Export each pair with request ID, product identity, both label views, evidence provenance, and versions. Do not expose `expected`, references, labels, candidate sources, or audit notes to the matcher. Its input is raw request text and the catalog only.

Audit request-level answerability separately. Finding no acceptable candidate in a small pool does not prove catalog-wide absence. Check the 11 no-match assertions with targeted catalog searches; record evidence or mark the assertion uncertain. Also identify answerable requests with no known positive in their pool. Investigate rather than silently removing them or treating injected references as automatically correct.

Outputs: `evaluation/benchmark_pairs.jsonl`, `evaluation/benchmark_requests.json`, `evaluation/validation_report.json`.

Pass: every current pair accounted for; no unexplained integrity failures; request-level uncertainties explicitly documented.

## Checkpoint E2 — Freeze grouped development/validation/test splits

Aim for approximately 90/30/30 requests using the existing seed, but preserve groups over exact ratios.

1. Identify and store the actual original 50 pilot request IDs from the authored pilot section/history; do not assume IDs r001–r050 because IDs have gaps.
2. Pin all pilot requests and their paraphrases to development.
3. Audit additional equivalent-intent groups, including the same intended product described differently and duplicate listings across stores. Merge equivalent groups before assignment. A shared broad category alone is not sufficient to merge requests.
4. Document cross-group overlap where a broad request and an exact request share products; this catalog-known task does not claim generalization to unseen products.
5. Allocate remaining groups deterministically, balancing exact/flexible requests and answerability where feasible.
6. If pilot grouping makes 90/30/30 infeasible, report actual counts instead of splitting a group or silently moving pilot examples into test.

All existing examples have been inspected during labeling and some have influenced rule development. Describe this as a retrospective held-out split, not a pristine unseen test. Do not tune retrieval using validation/test scores after the split is locked. A small future set of newly authored, independently reviewed queries would strengthen the portfolio later; it is not required to finish this checkpoint.

Outputs: `evaluation/splits.json`, split summaries and hashes in `evaluation/run_manifest.json`.

Pass: groups are disjoint; pilot groups are development-only; repeat builds produce identical assignments.

## Checkpoint E3 — Define three small baselines

| Name | Behavior | Purpose |
|---|---|---|
| TF-IDF | Raw query against catalog titles; cosine ranking; no confidence threshold | Establish lexical retrieval performance |
| TF-IDF + dimension filter | Existing parser clarification gate and dimension filtering, with similarity floor zero | Measure the current guardrails |
| TF-IDF + dimension filter + threshold | Same matcher with one development-tuned minimum similarity | Measure the precision/coverage tradeoff |

Use identical catalog/vectorizer settings, deterministic ties `(-score, store_id, product_id)`, and explicit zero-score/empty-result behavior. Fit TF-IDF on the whole frozen catalog once; the catalog is the known searchable collection, not labeled training data. Include vectorizer settings, text construction, dependency versions and row ordering in cache validation, not just catalog content.

Before freezing v1, handle missing dimensions as unknown, not a confirmed mismatch caused by NaN truthiness. Keep existing substantive limitations, such as the top-20 prefilter depth and dimension-only checks, visible. Do not add embeddings or gold-intent constraints merely to improve the reported baseline.

Outputs: model configuration and per-query ranked results, response status, scores and elapsed times. Write results before consulting labels.

Pass: changing hidden expected fields or references cannot change the model's predictions; tied scores and empty queries behave reproducibly.

## Checkpoint E4 — Run two different experiments

### A. Ranking within the prepared pool

For each request, score every candidate in that request's fixed pool using the catalog-fitted vectorizer. Apply the baseline's gates/filters when applicable. Do not intersect the pool with a precomputed full-catalog top-20 list: that would confound pool ranking with retrieval.

Authored references and deliberate negatives remain in this experiment. Report it as ranking among supplied candidates, not evidence that the system can discover those products independently.

### B. End-to-end full-catalog search

Search all 31,398 catalog rows. Do not inject references or restrict search to the labeled pool. Preserve the dimension baseline's documented prefilter depth.

Before final scoring, collect the union of top-five results from all three frozen baseline configurations. For filtered variants, collect results before threshold rejection as well. This covers candidates that may become returned results during threshold tuning.

If any returned pair lacks a label, export it to `evaluation/new_candidates_to_review.json`. Review it against the same rules, recording uncertainty and evidence. Reviewers should see request/product details without model identity, score, or rank. Keep these additional judgments in `evaluation/additional_judgments.json`; do not change the original pool experiment by appending them there.

Unjudged is a separate state. Never treat an unjudged result as Incorrect or remove it to make the score look better. A final report requires all top-five results to be judged; preliminary reports must disclose judgment coverage.

Outputs: `evaluation/predictions.jsonl`, review queue and additional judgments.

Pass: predictions search the intended universe; zero unjudged top-five results in the final report; original pool membership remains unchanged.

## Checkpoint E5 — Metrics with explicit denominators

Report development, validation and test separately. Show counts as well as percentages. Use exact/flexible and answerability breakdowns; avoid drawing strong conclusions from very small slices.

For answerable requests, let N be the number evaluated. Abstention or an empty result contributes zero retrieval success.

- **Success@1:** requests whose first returned candidate is Acceptable / N.
- **Hit@5:** requests with at least one Acceptable candidate in the first five returned results / N.
- **MRR@5:** mean reciprocal rank of the first acceptable result, with zero for none or abstention. Useful but optional if it delays the core report.
- **Pool Recall@5:** retrieved acceptable candidates / all acceptable candidates in that fixed pool, averaged only over pools with at least one positive. Report the number of zero-positive pools separately as N/A. This is not catalog-wide recall.

For abstention behavior, evaluate all requests with sufficiently established request-level answerability:

- **Return coverage:** requests receiving at least one match / all evaluated requests.
- **Returned-match accuracy:** appropriate acceptable top-one answers / requests receiving a match. Return on a request requiring clarification or having no acceptable match is a response-policy error, even if the candidate is loosely compatible.
- **False-return rate on unanswerable requests:** requests needing clarification/no match that nevertheless receive a match / requests in those categories.
- **False-abstention rate:** answerable requests receiving no match / answerable requests.
- A three-way confusion table for `answerable`, `needs_clarification`, and `no_acceptable_match`. Candidate correctness and request-level response correctness are separate judgments.

Maintain two label views:

1. **Conservative:** the 56 best guesses revert to Needs clarification. Show confirmed-correct, confirmed-incorrect and unresolved top-one outcomes separately. Report Success@1 and Hit@5 lower/upper bounds: unresolved candidates are nonpositive for the lower bound and potentially acceptable for the upper bound. Do not call unresolved cases confirmed errors or remove them from denominators.
2. **Practical:** use the requested binary best-guess labels. Label these scores explicitly as including AI best guesses. Report how many scored predictions touch guessed labels, rather than citing only the dataset-wide count.

For conservative pool recall, use known positives only and name it “known-positive pool recall”; guessed positives are not an exhaustive relevance set. No full-catalog recall claim is justified by top-five judgments.

Latency: report warm query median and p95, excluding labeling and model fit; report cold fit/load separately. One fixed run is adequate initially. With roughly 30 test requests, always display the sample size and avoid overinterpreting tiny score differences.

Outputs: `evaluation/metrics.json`, an easy-to-read results table.

Pass: hand-calculated fixtures verify denominators, uncertainty bounds, abstention and N/A behavior. No claim of exhaustive catalog recall.

## Checkpoint E6 — Tune the threshold only on development

Predeclare a small grid, for example 0.00–0.80 in steps of 0.05. Cosine similarity is not a probability or a calibrated confidence percentage.

Use a simple explicit development cost, averaged across requests:

- 0: appropriate acceptable return, or correct abstention on an unanswerable request.
- 1: abstaining on an answerable request.
- 2: incorrect return, return on an unanswerable request, or unresolved top-one result under conservative labels.

This cost expresses a portfolio design preference that a wrong grocery match is worse than asking for clarification. Treating unresolved returns conservatively is a tuning policy, not a claim that their labels are wrong. Exclude requests with unresolved request-level answerability from tuning and disclose the count.

Choose the lowest-cost threshold; break ties by greater confirmed correct-return count, then lower threshold. Save the complete development curve. If the optimum abstains almost everywhere, report that honestly as a weak matcher—do not adjust the test or hide coverage.

Freeze the chosen threshold/configuration, inspect validation once, then run the final test report. If validation prompts changes, document the revision and keep the test untouched until the new configuration is fixed. Test failures due to evaluator bugs may be corrected transparently; using test errors to tune the matcher makes the next result exploratory.

Outputs: `evaluation/threshold_selection.json`, frozen run configuration, development precision/coverage plot if useful.

Pass: no validation/test labels enter threshold selection; configuration includes the objective, grid, tie-break and chosen value.

## Checkpoint E7 — Publish baseline findings

Generate `evaluation/BASELINE_RESULTS.md` with:

1. Dataset size, actual split counts, frozen versions and AI-labeling limitations.
2. Side-by-side results for all three baselines, separately for pool ranking and full-catalog search.
3. Conservative bounds, practical best-guess scores, returned-match accuracy, coverage and false returns.
4. A brief analysis of 10–15 representative failures: wrong product type, missed brand/variant, package/count error, parser error, retrieval miss, or uncertain source data.
5. Latency and exact reproduction instructions.
6. The next improvement justified by the evidence. Examples: fix package constraints if sizes dominate; consider semantic retrieval if wording variations dominate. Low scores are useful findings, not a failed portfolio project.

Include real query/product examples, not invented expected scores. Keep baseline v1 results immutable when a later model is evaluated. Evaluate future models on the same split and expand pooled judgments fairly when their new top results require review.

Pass: a fresh run on the same inputs reproduces predictions and metric values; no score target is required for checkpoint completion.

## Implementation order and tests

1. Benchmark validation/export and grouped splits.
2. Pure scoring functions with small hand-calculated tests.
3. Baseline runner and prediction serialization.
4. Full-catalog additional-judgment queue; complete review.
5. Development threshold selection and frozen configuration.
6. Validation/test report and error analysis.

Suggested files: `build_benchmark.py`, `evaluation_metrics.py`, `tfidf_baseline.py`, `test_benchmark.py`, `test_evaluation_metrics.py`, `test_tfidf_baseline.py`.

Required tests cover duplicate identity, stale hashes, split leakage, hidden-label independence, same-score ties, missing dimensions, zero-positive pools, short/empty result lists, guessed/unjudged labels, grouped splits and development-only threshold selection. All test writes must use temporary directories, including the existing manual-review tests.

Keep it small: Python, existing scikit-learn, JSON/Markdown outputs and pytest. No database, tracking server, dashboard or new scraping run is needed.
