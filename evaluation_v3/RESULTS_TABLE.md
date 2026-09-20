# Checkpoint 4 S4 metrics -- embedding baselines

Same frozen catalog, requests, pool and splits as v1/v2. Embedding scores are not comparable to TF-IDF scores; only these metrics are.


## `embed`

Full-catalog latency: median 263.4 ms, p95 364.4 ms (n=150).

### dev (n=90, answerable n=77)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 |
|---|---|---|---|---|
| conservative | 71.4% (55/77) | 89.6% (69/77) | 0.781 | 72.9% |
| practical | 71.4% (55/77) | 89.6% (69/77) | 0.781 | 73.4% |

Return coverage 100.0% · false return on unanswerable 1.0 · false abstention 0.0

Success@1 by mode (practical): exact 90.7% (39/43) · flexible 47.1% (16/34)

### test (n=30, answerable n=20)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 |
|---|---|---|---|---|
| conservative | 80.0% (16/20) | 95.0% (19/20) | 0.860 | 75.3% |
| practical | 80.0% (16/20) | 95.0% (19/20) | 0.860 | 75.2% |

Return coverage 100.0% · false return on unanswerable 1.0 · false abstention 0.0

Success@1 by mode (practical): exact 100.0% (12/12) · flexible 50.0% (4/8)

### validation (n=30, answerable n=25)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 |
|---|---|---|---|---|
| conservative | 72.0% (18/25) | 84.0% (21/25) | 0.780 | 75.8% |
| practical | 72.0% (18/25) | 84.0% (21/25) | 0.780 | 74.9% |

Return coverage 100.0% · false return on unanswerable 1.0 · false abstention 0.0

Success@1 by mode (practical): exact 100.0% (14/14) · flexible 36.4% (4/11)

## `embed_dimension_size_filter`

Full-catalog latency: median 234.1 ms, p95 259.1 ms (n=150).

### dev (n=90, answerable n=77)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 |
|---|---|---|---|---|
| conservative | 87.0% (67/77) | 92.2% (71/77) | 0.894 | 80.3% |
| practical | 87.0% (67/77) | 92.2% (71/77) | 0.894 | 79.2% |

Return coverage 82.2% · false return on unanswerable 0.23076923076923078 · false abstention 0.07792207792207792

Success@1 by mode (practical): exact 90.7% (39/43) · flexible 82.4% (28/34)

### test (n=30, answerable n=20)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 |
|---|---|---|---|---|
| conservative | 95.0% (19/20) | 100.0% (20/20) | 0.967 | 75.0% |
| practical | 95.0% (19/20) | 100.0% (20/20) | 0.967 | 72.6% |

Return coverage 70.0% · false return on unanswerable 0.1 · false abstention 0.0

Success@1 by mode (practical): exact 100.0% (12/12) · flexible 87.5% (7/8)

### validation (n=30, answerable n=25)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 |
|---|---|---|---|---|
| conservative | 92.0% (23/25) | 92.0% (23/25) | 0.920 | 81.3% |
| practical | 92.0% (23/25) | 92.0% (23/25) | 0.920 | 77.6% |

Return coverage 80.0% · false return on unanswerable 0.2 · false abstention 0.08

Success@1 by mode (practical): exact 100.0% (14/14) · flexible 81.8% (9/11)
