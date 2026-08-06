from __future__ import annotations

from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import load_settings
from core.utils import read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from pipelines.phase1 import (
    _artifact_sha256,
    _dataframe_records,
    _load_and_validate_test_set,
    _pipeline_config,
    _require_artifact,
    _validate_clean_dataframe,
    _validate_evaluation_bundle,
    _validate_metrics,
    _validate_output_isolation,
)
from retrieval.index import LocalEmbeddingIndex


def _load_json_dataframe(path: Path, label: str) -> pd.DataFrame:
    """Load records from JSON so nested authors/categories remain real lists."""
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    payload = read_json(path)
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"{label} must be a non-empty JSON list: {path}")
    invalid_rows = [index for index, row in enumerate(payload) if not isinstance(row, dict)]
    if invalid_rows:
        raise ValueError(f"{label} contains non-object rows at indexes: {invalid_rows[:5]}")
    return pd.DataFrame(payload)


def _load_pipeline_config(metrics: dict[str, Any]) -> tuple[dict[str, Any], date]:
    config = metrics.get("pipeline_config")
    if not isinstance(config, dict):
        raise RuntimeError(
            "Baseline metrics do not contain pipeline_config. Re-run script/run_phase1.py "
            "before starting corruption/repair."
        )
    try:
        clean_run_date = date.fromisoformat(str(config["clean_run_date"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(
            "Baseline pipeline_config has an invalid clean_run_date; re-run phase 1."
        ) from exc
    return config, clean_run_date


def _config_differences(
    recorded: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    keys = sorted(set(recorded) | set(current))
    return {
        key: {"baseline": recorded.get(key), "current": current.get(key)}
        for key in keys
        if recorded.get(key) != current.get(key)
    }


def _validate_baseline_manifest(path: Path, expected_collection: str) -> None:
    manifest = read_json(path)
    if not isinstance(manifest, dict):
        raise ValueError(f"Baseline embedding manifest must be a JSON object: {path}")
    actual_collection = manifest.get("collection_name")
    if actual_collection != expected_collection:
        raise RuntimeError(
            "Baseline embedding manifest uses collection "
            f"{actual_collection!r}; expected {expected_collection!r}. Re-run phase 1."
        )


def _validate_corruption_log(path: Path) -> list[dict[str, Any]]:
    _require_artifact(path, "Corruption log")
    payload = read_json(path)
    # Current Role 4 corruption code writes an envelope with audit metadata;
    # accepting the earlier bare-list form keeps orchestration compatible with
    # snapshots created before that contract was tightened.
    operations = payload.get("operations") if isinstance(payload, dict) else payload
    if (
        not isinstance(operations, list)
        or not operations
        or any(not isinstance(entry, dict) for entry in operations)
    ):
        raise ValueError(f"Corruption log must contain a non-empty operations list: {path}")
    if isinstance(payload, dict):
        declared_count = payload.get("operation_count")
        if declared_count is not None and declared_count != len(operations):
            raise ValueError(
                f"Corruption log declares {declared_count!r} operations but contains {len(operations)}."
            )
    return operations


def _assert_repaired_ids_match(
    baseline_df: pd.DataFrame,
    repaired_df: pd.DataFrame,
) -> None:
    baseline_ids = baseline_df["paper_id"].astype(str).tolist()
    repaired_ids = repaired_df["paper_id"].astype(str).tolist()
    if baseline_ids == repaired_ids:
        return

    baseline_set = set(baseline_ids)
    repaired_set = set(repaired_ids)
    raise RuntimeError(
        "Repair from the raw snapshot did not restore the baseline document identities. "
        f"Missing={sorted(baseline_set - repaired_set)[:10]}, "
        f"unexpected={sorted(repaired_set - baseline_set)[:10]}, "
        f"baseline_rows={len(baseline_ids)}, repaired_rows={len(repaired_ids)}."
    )


def main() -> None:
    """Run corruption and exact raw-snapshot repair with one immutable test set."""
    settings = load_settings()
    _validate_output_isolation(settings)
    if settings.refresh_source or settings.refresh_test_set:
        raise RuntimeError(
            "Corruption flow must reuse phase-one artifacts. Unset REFRESH_SOURCE and "
            "REFRESH_TEST_SET, then run this flow again."
        )

    baseline_artifacts = {
        "Parsed raw records snapshot": settings.paths.raw_records_json,
        "Baseline clean CSV": settings.paths.clean_csv,
        "Baseline clean JSON": settings.paths.clean_json,
        "Baseline embedding manifest": settings.paths.embeddings_json,
        "Stable evaluation set": settings.paths.eval_testset,
        "Baseline metrics": settings.paths.baseline_metrics,
        "Baseline answers": settings.paths.baseline_answers,
        "Baseline quality report": settings.paths.quality_dir / "baseline_quality.json",
        "Baseline freshness report": settings.paths.freshness_report,
        "Baseline Markdown report": settings.paths.baseline_report,
    }
    for label, path in baseline_artifacts.items():
        _require_artifact(path, label)

    baseline_df = _load_json_dataframe(settings.paths.clean_json, "Baseline clean dataset")
    _validate_clean_dataframe(baseline_df, "baseline")
    baseline_ids = set(baseline_df["paper_id"].astype(str))
    test_set = _load_and_validate_test_set(settings.paths.eval_testset, baseline_ids)

    raw_snapshot_hash = _artifact_sha256(settings.paths.raw_records_json)
    baseline_clean_hash = _artifact_sha256(settings.paths.clean_json)
    test_set_hash = _artifact_sha256(settings.paths.eval_testset)
    baseline_metrics = read_json(settings.paths.baseline_metrics)
    _validate_metrics(baseline_metrics, len(test_set), "baseline")
    recorded_config, clean_run_date = _load_pipeline_config(baseline_metrics)
    current_config = _pipeline_config(
        settings,
        raw_snapshot_sha256=raw_snapshot_hash,
        baseline_clean_sha256=baseline_clean_hash,
        test_set_sha256=test_set_hash,
        clean_run_date=clean_run_date,
    )
    differences = _config_differences(recorded_config, current_config)
    if differences:
        raise RuntimeError(
            "Corruption flow configuration or baseline artifacts differ from phase 1. "
            f"Re-run phase 1 with the intended configuration. Differences: {differences}"
        )
    _validate_baseline_manifest(
        settings.paths.embeddings_json,
        settings.baseline_collection_name,
    )

    corrupted_df = corrupt_clean_dataframe(baseline_df, settings.paths.corruption_log)
    _validate_clean_dataframe(corrupted_df, "corrupted", require_unique_ids=False)
    corruption_log = _validate_corruption_log(settings.paths.corruption_log)
    write_csv(corrupted_df, settings.paths.corrupted_clean_csv)
    write_json(settings.paths.corrupted_clean_json, _dataframe_records(corrupted_df))

    corrupted_index = LocalEmbeddingIndex.build(
        corrupted_df,
        settings,
        settings.paths.corrupted_embeddings_json,
    )
    if corrupted_index.collection_name != settings.corrupted_collection_name:
        raise RuntimeError(
            "Corrupted index used an unexpected collection: "
            f"{corrupted_index.collection_name!r} instead of {settings.corrupted_collection_name!r}."
        )
    corrupted_bundle = evaluate_pipeline(
        settings,
        corrupted_index,
        settings.paths.eval_testset,
        settings.paths.corrupted_metrics,
        settings.paths.corrupted_answers,
    )
    _validate_evaluation_bundle(corrupted_bundle, len(test_set), "corrupted")
    corrupted_bundle.summary["pipeline_config"] = current_config
    write_json(settings.paths.corrupted_metrics, corrupted_bundle.summary)
    corrupted_quality = run_data_quality_checks(corrupted_df, settings, "corrupted")
    corrupted_freshness_path = settings.paths.quality_dir / "corrupted_freshness_report.json"
    corrupted_freshness = build_freshness_report(
        corrupted_df,
        settings,
        corrupted_freshness_path,
    )

    if _artifact_sha256(settings.paths.raw_records_json) != raw_snapshot_hash:
        raise RuntimeError("The raw records snapshot changed during corruption; repair was aborted.")
    if _artifact_sha256(settings.paths.eval_testset) != test_set_hash:
        raise RuntimeError("The stable evaluation set changed during corrupted evaluation.")

    raw_records = load_raw_records(settings.paths.raw_records_json)
    if not raw_records:
        raise RuntimeError("The raw records snapshot contains zero records; repair cannot continue.")
    repair_at = datetime.combine(clean_run_date, time.min, tzinfo=UTC)
    repaired_df = build_clean_dataframe(raw_records, repair_at)
    _validate_clean_dataframe(repaired_df, "repaired")
    _assert_repaired_ids_match(baseline_df, repaired_df)
    _load_and_validate_test_set(
        settings.paths.eval_testset,
        set(repaired_df["paper_id"].astype(str)),
    )
    write_csv(repaired_df, settings.paths.repaired_clean_csv)
    write_json(settings.paths.repaired_clean_json, _dataframe_records(repaired_df))
    repaired_clean_hash = _artifact_sha256(settings.paths.repaired_clean_json)
    if repaired_clean_hash != baseline_clean_hash:
        raise RuntimeError(
            "Repair rebuilt from the exact raw snapshot but did not reproduce the baseline clean JSON. "
            "The cleaning code or baseline artifact changed; re-run phase 1 before comparing metrics."
        )

    repaired_index = LocalEmbeddingIndex.build(
        repaired_df,
        settings,
        settings.paths.repaired_embeddings_json,
    )
    if repaired_index.collection_name != settings.repaired_collection_name:
        raise RuntimeError(
            "Repaired index used an unexpected collection: "
            f"{repaired_index.collection_name!r} instead of {settings.repaired_collection_name!r}."
        )
    repaired_bundle = evaluate_pipeline(
        settings,
        repaired_index,
        settings.paths.eval_testset,
        settings.paths.repaired_metrics,
        settings.paths.repaired_answers,
    )
    _validate_evaluation_bundle(repaired_bundle, len(test_set), "repaired")
    repaired_bundle.summary["pipeline_config"] = current_config
    write_json(settings.paths.repaired_metrics, repaired_bundle.summary)
    repaired_quality = run_data_quality_checks(repaired_df, settings, "repaired")
    repaired_freshness_path = settings.paths.quality_dir / "repaired_freshness_report.json"
    repaired_freshness = build_freshness_report(
        repaired_df,
        settings,
        repaired_freshness_path,
    )

    if _artifact_sha256(settings.paths.raw_records_json) != raw_snapshot_hash:
        raise RuntimeError("The raw records snapshot changed during repair/evaluation.")
    if _artifact_sha256(settings.paths.eval_testset) != test_set_hash:
        raise RuntimeError("The stable evaluation set changed during repaired evaluation.")

    generate_corruption_report(
        settings.paths.comparison_report,
        baseline_metrics,
        corrupted_bundle.summary,
        repaired_bundle.summary,
        corrupted_quality,
        repaired_quality,
        corrupted_freshness,
        repaired_freshness,
    )

    expected_artifacts = {
        "Corrupted clean CSV": settings.paths.corrupted_clean_csv,
        "Corrupted clean JSON": settings.paths.corrupted_clean_json,
        "Corrupted embedding manifest": settings.paths.corrupted_embeddings_json,
        "Corrupted metrics": settings.paths.corrupted_metrics,
        "Corrupted answers": settings.paths.corrupted_answers,
        "Corrupted quality report": settings.paths.quality_dir / "corrupted_quality.json",
        "Corrupted freshness report": corrupted_freshness_path,
        "Repaired clean CSV": settings.paths.repaired_clean_csv,
        "Repaired clean JSON": settings.paths.repaired_clean_json,
        "Repaired embedding manifest": settings.paths.repaired_embeddings_json,
        "Repaired metrics": settings.paths.repaired_metrics,
        "Repaired answers": settings.paths.repaired_answers,
        "Repaired quality report": settings.paths.quality_dir / "repaired_quality.json",
        "Repaired freshness report": repaired_freshness_path,
        "Comparison report": settings.paths.comparison_report,
    }
    for label, path in expected_artifacts.items():
        _require_artifact(path, label)

    print(
        "Corruption flow complete: "
        f"baseline={len(baseline_df)}, corrupted={len(corrupted_df)}, "
        f"repaired={len(repaired_df)}, operations={len(corruption_log)}, "
        f"test_set_sha256={test_set_hash[:12]}"
    )


if __name__ == "__main__":
    main()
