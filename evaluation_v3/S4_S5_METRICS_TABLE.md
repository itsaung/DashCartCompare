# Checkpoint 4 S4 metrics -- embedding baselines

Same frozen catalog, requests, pool and splits as v1/v2. Embedding scores are not comparable to TF-IDF scores; only these metrics are.


## `embed`

Full-catalog latency: median 567.3 ms, p95 1401.0 ms (n=150).

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

Full-catalog latency: median 421.4 ms, p95 578.1 ms (n=150).

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

## `hybrid_dimension_size_filter`

Full-catalog latency: median 4904.4 ms, p95 6308.9 ms (n=150).

### dev (n=90, answerable n=77)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 |
|---|---|---|---|---|
| conservative | 92.2% (71/77) | 92.2% (71/77) | 0.922 | 80.4% |
| practical | 92.2% (71/77) | 92.2% (71/77) | 0.922 | 79.3% |

Return coverage 82.2% · false return on unanswerable 0.15384615384615385 · false abstention 0.06493506493506493

Success@1 by mode (practical): exact 90.7% (39/43) · flexible 94.1% (32/34)

### test (n=30, answerable n=20)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 |
|---|---|---|---|---|
| conservative | 100.0% (20/20) | 100.0% (20/20) | 1.000 | 74.3% |
| practical | 100.0% (20/20) | 100.0% (20/20) | 1.000 | 71.9% |

Return coverage 70.0% · false return on unanswerable 0.1 · false abstention 0.0

Success@1 by mode (practical): exact 100.0% (12/12) · flexible 100.0% (8/8)

### validation (n=30, answerable n=25)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 |
|---|---|---|---|---|
| conservative | 92.0% (23/25) | 92.0% (23/25) | 0.920 | 81.3% |
| practical | 92.0% (23/25) | 92.0% (23/25) | 0.920 | 77.6% |

Return coverage 80.0% · false return on unanswerable 0.2 · false abstention 0.08

Success@1 by mode (practical): exact 100.0% (14/14) · flexible 81.8% (9/11)

## `hybrid_identity_filter`

Full-catalog latency: median 5262.4 ms, p95 6254.7 ms (n=150).

### dev (n=90, answerable n=77)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 |
|---|---|---|---|---|
| conservative | 80.5% (62/77) | 81.8% (63/77) | 0.808 | 69.0% |
| practical | 80.5% (62/77) | 81.8% (63/77) | 0.808 | 68.1% |

Return coverage 71.1% · false return on unanswerable 0.07692307692307693 · false abstention 0.18181818181818182

Success@1 by mode (practical): exact 69.8% (30/43) · flexible 94.1% (32/34)

### test (n=30, answerable n=20)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 |
|---|---|---|---|---|
| conservative | 65.0% (13/20) | 65.0% (13/20) | 0.650 | 45.1% |
| practical | 65.0% (13/20) | 65.0% (13/20) | 0.650 | 43.3% |

Return coverage 46.7% · false return on unanswerable 0.0 · false abstention 0.3

Success@1 by mode (practical): exact 41.7% (5/12) · flexible 100.0% (8/8)

### validation (n=30, answerable n=25)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 |
|---|---|---|---|---|
| conservative | 84.0% (21/25) | 84.0% (21/25) | 0.840 | 74.2% |
| practical | 84.0% (21/25) | 84.0% (21/25) | 0.840 | 70.7% |

Return coverage 76.7% · false return on unanswerable 0.2 · false abstention 0.12

Success@1 by mode (practical): exact 85.7% (12/14) · flexible 81.8% (9/11)
