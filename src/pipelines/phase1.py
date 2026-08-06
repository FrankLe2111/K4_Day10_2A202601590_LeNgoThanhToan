from __future__ import annotations

from core.config import load_settings
from core.utils import now_utc, write_csv, write_json
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex


def main() -> None:
    """Run the baseline pipeline end-to-end.

    Pseudo-code:
    1. Load settings.
    2. Load hoac fetch raw records.
    3. Clean data.
    4. Save clean CSV/JSON.
    5. Build Chroma index.
    6. Tao hoac load evaluation set.
    7. Evaluate.
    8. Run quality checks va freshness report.
    9. Tao markdown report.
    10. Co the demo agent tren vai sample question.
    """
    settings = load_settings()
    raw_path = settings.paths.raw_records_json
    if settings.refresh_source or not raw_path.exists():
        records = fetch_source_records(settings)
    else:
        records = load_raw_records(raw_path)
    df = build_clean_dataframe(records, now_utc())
    if df.empty:
        raise RuntimeError("Cleaning produced zero records; stop before building the vector index.")
    write_csv(df, settings.paths.clean_csv)
    write_json(settings.paths.clean_json, df.to_dict(orient="records"))
    index = LocalEmbeddingIndex.build(df, settings, settings.paths.embeddings_json)
    if settings.refresh_source or settings.refresh_test_set or not settings.paths.eval_testset.exists():
        build_test_set(df, settings.paths.eval_testset)
    bundle = evaluate_pipeline(settings, index, settings.paths.eval_testset, settings.paths.baseline_metrics, settings.paths.baseline_answers)
    quality = run_data_quality_checks(df, settings, "baseline")
    freshness = build_freshness_report(df, settings, settings.paths.freshness_report)
    source_summary = {"source_api": settings.source_api, "query": settings.source_query, "filter": settings.source_filter, "raw_records": len(records), "clean_records": len(df)}
    generate_phase1_report(settings.paths.baseline_report, source_summary, bundle.summary, quality, freshness)
    print(f"Baseline complete: {len(df)} clean records")

if __name__ == "__main__":
    main()
