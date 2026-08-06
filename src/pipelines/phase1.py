from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
import os
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex


_CLEAN_REQUIRED_COLUMNS = frozenset(
    {
        "paper_id",
        "title",
        "summary",
        "authors",
        "authors_joined",
        "categories",
        "categories_joined",
        "published",
        "age_days",
        "abs_url",
        "pdf_url",
        "text_for_embedding",
    }
)
_TEST_SET_REQUIRED_FIELDS = frozenset(
    {"id", "question_type", "question", "ground_truth", "ground_truth_doc_ids"}
)
_METRIC_KEYS = (
    "retrieval_hit_rate",
    "mean_token_f1",
    "judge_accuracy",
    "mean_judge_score",
)


def _artifact_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_safe(value: Any) -> Any:
    """Convert pandas/numpy scalar values while preserving real list columns."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is None:
        return None

    try:
        missing = pd.isna(value)
        if not isinstance(missing, (list, tuple)) and bool(missing):
            return None
    except (TypeError, ValueError):
        pass

    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _dataframe_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [_json_safe(record) for record in df.to_dict(orient="records")]


def _require_artifact(path: Path, label: str) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"{label} was not created or is empty: {path}")


def _validate_output_isolation(settings: Settings) -> None:
    path_groups = {
        "clean JSON": (
            settings.paths.clean_json,
            settings.paths.corrupted_clean_json,
            settings.paths.repaired_clean_json,
        ),
        "clean CSV": (
            settings.paths.clean_csv,
            settings.paths.corrupted_clean_csv,
            settings.paths.repaired_clean_csv,
        ),
        "embedding manifests": (
            settings.paths.embeddings_json,
            settings.paths.corrupted_embeddings_json,
            settings.paths.repaired_embeddings_json,
        ),
        "metrics": (
            settings.paths.baseline_metrics,
            settings.paths.corrupted_metrics,
            settings.paths.repaired_metrics,
        ),
        "answers": (
            settings.paths.baseline_answers,
            settings.paths.corrupted_answers,
            settings.paths.repaired_answers,
        ),
        "quality reports": (
            settings.paths.quality_dir / "baseline_quality.json",
            settings.paths.quality_dir / "corrupted_quality.json",
            settings.paths.quality_dir / "repaired_quality.json",
        ),
        "freshness reports": (
            settings.paths.freshness_report,
            settings.paths.quality_dir / "corrupted_freshness_report.json",
            settings.paths.quality_dir / "repaired_freshness_report.json",
        ),
        "Markdown reports": (
            settings.paths.baseline_report,
            settings.paths.comparison_report,
        ),
    }
    for label, paths in path_groups.items():
        resolved = [str(Path(path).resolve()).casefold() for path in paths]
        if len(set(resolved)) != len(resolved):
            raise ValueError(f"Configured {label} paths must be distinct: {paths}")

    collections = [
        str(settings.baseline_collection_name).strip(),
        str(settings.corrupted_collection_name).strip(),
        str(settings.repaired_collection_name).strip(),
    ]
    if any(not name for name in collections) or len({name.casefold() for name in collections}) != 3:
        raise ValueError(
            "Baseline, corrupted, and repaired Chroma collection names must be non-empty and distinct."
        )


def _validate_clean_dataframe(
    df: pd.DataFrame,
    state: str,
    *,
    require_unique_ids: bool = True,
) -> None:
    if df.empty:
        raise RuntimeError(f"{state} cleaning produced zero records.")

    missing_columns = sorted(_CLEAN_REQUIRED_COLUMNS - set(df.columns))
    if missing_columns:
        raise ValueError(f"{state} dataframe is missing required columns: {missing_columns}")

    paper_ids = df["paper_id"].fillna("").astype(str).str.strip()
    blank_ids = int(paper_ids.eq("").sum())
    if blank_ids:
        raise ValueError(f"{state} dataframe contains {blank_ids} blank paper_id value(s).")
    if require_unique_ids:
        duplicate_ids = int(paper_ids.str.casefold().duplicated().sum())
        if duplicate_ids:
            raise ValueError(f"{state} dataframe contains {duplicate_ids} duplicate paper_id value(s).")

    for column in ("title", "text_for_embedding"):
        blank_values = int(df[column].fillna("").astype(str).str.strip().eq("").sum())
        if blank_values:
            raise ValueError(f"{state} dataframe contains {blank_values} blank {column} value(s).")

    for column in ("authors", "categories"):
        invalid_rows = [index for index, value in df[column].items() if not isinstance(value, list)]
        if invalid_rows:
            preview = invalid_rows[:5]
            raise ValueError(
                f"{state} dataframe must preserve {column} as lists; invalid row indexes: {preview}"
            )


def _load_and_validate_test_set(
    path: Path,
    available_document_ids: set[str],
) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Evaluation set is missing: {path}")
    payload = read_json(path)
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"Evaluation set must be a non-empty JSON list: {path}")

    sample_ids: set[str] = set()
    referenced_ids: set[str] = set()
    for position, sample in enumerate(payload):
        if not isinstance(sample, dict):
            raise ValueError(f"Evaluation sample {position} is not a JSON object.")
        missing_fields = sorted(_TEST_SET_REQUIRED_FIELDS - set(sample))
        if missing_fields:
            raise ValueError(f"Evaluation sample {position} is missing fields: {missing_fields}")

        for field in ("id", "question_type", "question", "ground_truth"):
            if not isinstance(sample[field], str) or not sample[field].strip():
                raise ValueError(f"Evaluation sample {position} has an invalid {field!r} value.")
        sample_id = sample["id"].strip()
        if sample_id in sample_ids:
            raise ValueError(f"Evaluation set contains duplicate sample id: {sample_id}")
        sample_ids.add(sample_id)

        document_ids = sample["ground_truth_doc_ids"]
        if (
            not isinstance(document_ids, list)
            or not document_ids
            or any(not isinstance(item, str) or not item.strip() for item in document_ids)
        ):
            raise ValueError(
                f"Evaluation sample {position} must have non-empty string ground_truth_doc_ids."
            )
        referenced_ids.update(item.strip() for item in document_ids)

    orphan_ids = sorted(referenced_ids - available_document_ids)
    if orphan_ids:
        raise ValueError(
            "Evaluation set references documents that are absent from the baseline clean dataset: "
            f"{orphan_ids[:10]}. Re-run phase 1 with REFRESH_TEST_SET=1."
        )
    return payload


def _validate_metrics(metrics: Any, expected_samples: int, state: str) -> None:
    if not isinstance(metrics, dict):
        raise TypeError(f"{state} metrics must be a JSON object/dictionary.")
    missing_metrics = [key for key in _METRIC_KEYS if key not in metrics]
    if missing_metrics:
        raise ValueError(f"{state} metrics are missing required keys: {missing_metrics}")
    if metrics.get("samples") != expected_samples:
        raise ValueError(
            f"{state} metrics report {metrics.get('samples')!r} samples; expected {expected_samples}."
        )


def _validate_evaluation_bundle(bundle: Any, expected_samples: int, state: str) -> None:
    summary = getattr(bundle, "summary", None)
    answers = getattr(bundle, "answers", None)
    _validate_metrics(summary, expected_samples, state)
    if not isinstance(answers, list) or len(answers) != expected_samples:
        actual = len(answers) if isinstance(answers, list) else type(answers).__name__
        raise ValueError(f"{state} evaluation produced {actual} answers; expected {expected_samples}.")


def _env_flag(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes"}


def _pipeline_config(
    settings: Settings,
    *,
    raw_snapshot_sha256: str,
    baseline_clean_sha256: str,
    test_set_sha256: str,
    clean_run_date: date,
) -> dict[str, Any]:
    """Configuration persisted with every metric file for fair comparisons."""
    return {
        "embedding_model": settings.embedding_model,
        "top_k": settings.top_k,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.model_name,
        "use_llm_eval": _env_flag("USE_LLM_EVAL", True),
        "run_ragas": _env_flag("RUN_RAGAS", False),
        "freshness_threshold_days": settings.freshness_threshold_days,
        "raw_snapshot_sha256": raw_snapshot_sha256,
        "baseline_clean_sha256": baseline_clean_sha256,
        "test_set_sha256": test_set_sha256,
        "clean_run_date": clean_run_date.isoformat(),
    }


def main() -> None:
    """Run the reproducible baseline pipeline and persist all phase-one artifacts."""
    settings = load_settings()
    _validate_output_isolation(settings)

    raw_path = settings.paths.raw_records_json
    source_refreshed = bool(settings.refresh_source or not raw_path.is_file())
    records = fetch_source_records(settings) if source_refreshed else load_raw_records(raw_path)
    if not records:
        raise RuntimeError("Raw ingestion produced zero records; baseline pipeline stopped.")
    _require_artifact(settings.paths.raw_api_response, "Raw Crossref response")
    _require_artifact(raw_path, "Parsed raw records snapshot")
    raw_snapshot_hash = _artifact_sha256(raw_path)

    run_at = now_utc()
    clean_df = build_clean_dataframe(records, run_at)
    _validate_clean_dataframe(clean_df, "baseline")
    write_csv(clean_df, settings.paths.clean_csv)
    write_json(settings.paths.clean_json, _dataframe_records(clean_df))
    baseline_clean_hash = _artifact_sha256(settings.paths.clean_json)

    baseline_index = LocalEmbeddingIndex.build(
        clean_df,
        settings,
        settings.paths.embeddings_json,
    )
    if baseline_index.collection_name != settings.baseline_collection_name:
        raise RuntimeError(
            "Baseline index used an unexpected collection: "
            f"{baseline_index.collection_name!r} instead of {settings.baseline_collection_name!r}."
        )

    rebuild_test_set = bool(
        source_refreshed or settings.refresh_test_set or not settings.paths.eval_testset.is_file()
    )
    if rebuild_test_set:
        build_test_set(clean_df, settings.paths.eval_testset)
    clean_ids = set(clean_df["paper_id"].astype(str))
    test_set = _load_and_validate_test_set(settings.paths.eval_testset, clean_ids)
    test_set_hash = _artifact_sha256(settings.paths.eval_testset)

    baseline_bundle = evaluate_pipeline(
        settings,
        baseline_index,
        settings.paths.eval_testset,
        settings.paths.baseline_metrics,
        settings.paths.baseline_answers,
    )
    if _artifact_sha256(settings.paths.eval_testset) != test_set_hash:
        raise RuntimeError("Evaluation unexpectedly modified the stable evaluation set.")
    _validate_evaluation_bundle(baseline_bundle, len(test_set), "baseline")

    experiment_config = _pipeline_config(
        settings,
        raw_snapshot_sha256=raw_snapshot_hash,
        baseline_clean_sha256=baseline_clean_hash,
        test_set_sha256=test_set_hash,
        clean_run_date=run_at.date(),
    )
    baseline_bundle.summary["pipeline_config"] = experiment_config
    write_json(settings.paths.baseline_metrics, baseline_bundle.summary)

    quality = run_data_quality_checks(clean_df, settings, "baseline")
    freshness = build_freshness_report(clean_df, settings, settings.paths.freshness_report)
    source_summary = {
        "source_api": settings.source_api,
        "query": settings.source_query,
        "filter": settings.source_filter,
        "source_refreshed": source_refreshed,
        "raw_records": len(records),
        "clean_records": len(clean_df),
        "clean_run_date": run_at.date().isoformat(),
        "raw_snapshot_sha256": raw_snapshot_hash,
        "test_set_samples": len(test_set),
        "test_set_sha256": test_set_hash,
    }
    generate_phase1_report(
        settings.paths.baseline_report,
        source_summary,
        baseline_bundle.summary,
        quality,
        freshness,
    )

    expected_artifacts = {
        "Clean CSV": settings.paths.clean_csv,
        "Clean JSON": settings.paths.clean_json,
        "Baseline embedding manifest": settings.paths.embeddings_json,
        "Evaluation set": settings.paths.eval_testset,
        "Baseline metrics": settings.paths.baseline_metrics,
        "Baseline answers": settings.paths.baseline_answers,
        "Baseline quality report": settings.paths.quality_dir / "baseline_quality.json",
        "Baseline freshness report": settings.paths.freshness_report,
        "Baseline Markdown report": settings.paths.baseline_report,
    }
    for label, path in expected_artifacts.items():
        _require_artifact(path, label)

    print(
        "Baseline complete: "
        f"raw={len(records)}, clean={len(clean_df)}, eval_samples={len(test_set)}, "
        f"test_set_sha256={test_set_hash[:12]}"
    )


if __name__ == "__main__":
    main()
