# Corruption and Repair Report

## Metric comparison

| Metric | Baseline | Corrupted | Repaired |
|---|---:|---:|---:|
| retrieval_hit_rate | 1.0 | 0.75 | 1.0 |
| mean_token_f1 | 1.0 | 0.7579196481812761 | 1.0 |
| judge_accuracy | 1.0 | 0.75 | 1.0 |
| mean_judge_score | 5 | 4 | 5 |

## Quality and freshness

| State | Quality | Fresh |
|---|---|---|
| Corrupted | False | False |
| Repaired | True | True |

The repaired state is rebuilt from the raw records snapshot.
