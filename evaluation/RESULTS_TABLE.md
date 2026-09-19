# Checkpoint 3 baseline metrics (E5)

## tfidf

### dev (n=90, answerable n=77)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 (n pools) |
|---|---|---|---|---|
| conservative | 83.12% (64/77) | 92.21% (71/77) | 0.859 | 72.45% (85 pools, 5 N/A) |
| practical | 83.12% (64/77) | 92.21% (71/77) | 0.859 | 71.00% (86 pools, 4 N/A) |

Return coverage: 100.00% (90/90). False return on unanswerable: 1.0. False abstention: 0.0.

### test (n=30, answerable n=20)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 (n pools) |
|---|---|---|---|---|
| conservative | 90.00% (18/20) | 95.00% (19/20) | 0.925 | 73.50% (24 pools, 6 N/A) |
| practical | 90.00% (18/20) | 95.00% (19/20) | 0.925 | 71.70% (25 pools, 5 N/A) |

Return coverage: 100.00% (30/30). False return on unanswerable: 1.0. False abstention: 0.0.

### validation (n=30, answerable n=25)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 (n pools) |
|---|---|---|---|---|
| conservative | 76.00% (19/25) | 88.00% (22/25) | 0.798 | 76.27% (28 pools, 2 N/A) |
| practical | 76.00% (19/25) | 88.00% (22/25) | 0.798 | 75.36% (29 pools, 1 N/A) |

Return coverage: 100.00% (30/30). False return on unanswerable: 1.0. False abstention: 0.0.

## tfidf_dimension_filter

### dev (n=90, answerable n=77)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 (n pools) |
|---|---|---|---|---|
| conservative | 77.92% (60/77) | 88.31% (68/77) | 0.810 | 64.67% (85 pools, 5 N/A) |
| practical | 77.92% (60/77) | 88.31% (68/77) | 0.810 | 63.81% (86 pools, 4 N/A) |

Return coverage: 87.78% (79/90). False return on unanswerable: 0.38461538461538464. False abstention: 0.03896103896103896.

### test (n=30, answerable n=20)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 (n pools) |
|---|---|---|---|---|
| conservative | 95.00% (19/20) | 95.00% (19/20) | 0.950 | 68.29% (24 pools, 6 N/A) |
| practical | 95.00% (19/20) | 95.00% (19/20) | 0.950 | 66.70% (25 pools, 5 N/A) |

Return coverage: 76.67% (23/30). False return on unanswerable: 0.3. False abstention: 0.0.

### validation (n=30, answerable n=25)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 (n pools) |
|---|---|---|---|---|
| conservative | 76.00% (19/25) | 92.00% (23/25) | 0.811 | 68.57% (28 pools, 2 N/A) |
| practical | 76.00% (19/25) | 92.00% (23/25) | 0.811 | 65.34% (29 pools, 1 N/A) |

Return coverage: 90.00% (27/30). False return on unanswerable: 0.4. False abstention: 0.0.

## tfidf_dimension_filter_threshold

### dev (n=90, answerable n=77)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 (n pools) |
|---|---|---|---|---|
| conservative | 68.83% (53/77) | 72.73% (56/77) | 0.700 | 54.56% (85 pools, 5 N/A) |
| practical | 68.83% (53/77) | 72.73% (56/77) | 0.700 | 53.92% (86 pools, 4 N/A) |

Return coverage: 65.56% (59/90). False return on unanswerable: 0.07692307692307693. False abstention: 0.24675324675324675.

### test (n=30, answerable n=20)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 (n pools) |
|---|---|---|---|---|
| conservative | 85.00% (17/20) | 85.00% (17/20) | 0.850 | 61.00% (24 pools, 6 N/A) |
| practical | 85.00% (17/20) | 85.00% (17/20) | 0.850 | 58.56% (25 pools, 5 N/A) |

Return coverage: 56.67% (17/30). False return on unanswerable: 0.0. False abstention: 0.15.

### validation (n=30, answerable n=25)

| view | Success@1 | Hit@5 | MRR@5 | Pool Recall@5 (n pools) |
|---|---|---|---|---|
| conservative | 72.00% (18/25) | 80.00% (20/25) | 0.738 | 61.07% (28 pools, 2 N/A) |
| practical | 72.00% (18/25) | 80.00% (20/25) | 0.738 | 58.10% (29 pools, 1 N/A) |

Return coverage: 73.33% (22/30). False return on unanswerable: 0.4. False abstention: 0.2.
