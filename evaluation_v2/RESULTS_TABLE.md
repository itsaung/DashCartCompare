# Checkpoint 3.1 metrics -- tfidf_dimension_size_filter


## dev (n=90, answerable n=77)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 (n pools) |
|---|---|---|---|---|
| conservative | 84.42% (65/77) | 90.91% (70/77) | 0.871 | 79.82% (85 pools, 5 N/A) |
| practical | 84.42% (65/77) | 90.91% (70/77) | 0.871 | 78.75% (86 pools, 4 N/A) |

Return coverage: 82.22%. False return on unanswerable: 0.15384615384615385. False abstention: 0.06493506493506493.

## test (n=30, answerable n=20)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 (n pools) |
|---|---|---|---|---|
| conservative | 100.00% (20/20) | 100.00% (20/20) | 1.000 | 74.31% (24 pools, 6 N/A) |
| practical | 100.00% (20/20) | 100.00% (20/20) | 1.000 | 71.90% (25 pools, 5 N/A) |

Return coverage: 73.33%. False return on unanswerable: 0.2. False abstention: 0.0.

## validation (n=30, answerable n=25)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 (n pools) |
|---|---|---|---|---|
| conservative | 88.00% (22/25) | 96.00% (24/25) | 0.913 | 81.31% (28 pools, 2 N/A) |
| practical | 88.00% (22/25) | 96.00% (24/25) | 0.913 | 77.64% (29 pools, 1 N/A) |

Return coverage: 86.67%. False return on unanswerable: 0.2. False abstention: 0.0.