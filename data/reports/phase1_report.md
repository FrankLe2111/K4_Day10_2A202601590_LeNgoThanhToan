# Phase 1 Baseline Report

## Source

- `source_api`: Crossref REST API
- `query`: agentic retrieval augmented generation large language model
- `filter`: from-pub-date:2026-02-07
- `source_refreshed`: False
- `raw_records`: 24
- `clean_records`: 24
- `clean_run_date`: 2026-08-06
- `raw_snapshot_sha256`: 1b7968d4ff39b2523ecfdfb5f776586a0a116a6048ec5133443e6f930c01115b
- `test_set_samples`: 32
- `test_set_sha256`: c3eb850f3c8cc4d5108c72bcbe1d9e5655bb28854917196c513fe0152b921d75

## Evaluation metrics

- `retrieval_hit_rate`: 1.0
- `mean_token_f1`: 1.0
- `judge_accuracy`: 1.0
- `mean_judge_score`: 5
- `llm_answer_count`: 0
- `fallback_answer_count`: 32

## Data quality

- Status: **PASS**
- Rows: 24

## Freshness

- `latest_published`: 2026-08-05
- `oldest_published`: 2026-02-12
- `stale_rows`: 0
- `total_rows`: 24
- `threshold_days`: 180
- `is_fresh`: True
