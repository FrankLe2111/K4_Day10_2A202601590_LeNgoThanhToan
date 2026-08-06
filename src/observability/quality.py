from __future__ import annotations

import argparse
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import write_json


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Run data quality checks and persist the result.

    Pseudo-code:
    1. Check row count.
    2. Check `paper_id` not null va unique.
    3. Check `title` not null.
    4. Check do dai `summary`.
    5. Check freshness bang `age_days`.
    6. Ghi ket qua vao `data/quality/`.
    """
    checks = []
    def add(name: str, passed: bool, details: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "details": details})
    add("row_count", len(df) > 0, {"value": int(len(df)), "minimum": 1})
    id_nulls = int(df["paper_id"].isna().sum()) if "paper_id" in df else len(df)
    duplicates = int(df["paper_id"].duplicated().sum()) if "paper_id" in df else len(df)
    add("paper_id_not_null", id_nulls == 0, {"null_rows": id_nulls})
    add("paper_id_unique", duplicates == 0, {"duplicate_rows": duplicates})
    title_nulls = int(df["title"].fillna("").astype(str).str.strip().eq("").sum()) if "title" in df else len(df)
    add("title_not_blank", title_nulls == 0, {"blank_rows": title_nulls})
    short_summary = int(df["summary"].fillna("").astype(str).str.len().lt(100).sum()) if "summary" in df else len(df)
    add("summary_has_content", short_summary == 0, {"short_or_blank_rows": short_summary, "minimum_chars": 100})
    stale = int(df["age_days"].fillna(settings.freshness_threshold_days + 1).gt(settings.freshness_threshold_days).sum()) if "age_days" in df else len(df)
    add("freshness", stale == 0, {"stale_rows": stale, "threshold_days": settings.freshness_threshold_days})
    payload = {"report_name": report_name, "total_rows": int(len(df)), "passed": all(x["passed"] for x in checks), "checks": checks}
    write_json(settings.paths.quality_dir / f"{report_name}_quality.json", payload)
    return payload


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Build and persist a freshness report.

    Pseudo-code:
    1. Tim latest va oldest published date.
    2. Dem so dong stale.
    3. Tao payload:
       - latest_published
       - oldest_published
       - stale_rows
       - total_rows
       - is_fresh
    4. Ghi JSON report.
    """
    dates = pd.to_datetime(df.get("published", pd.Series(dtype=str)), errors="coerce").dropna()
    latest = dates.max().date().isoformat() if not dates.empty else ""
    oldest = dates.min().date().isoformat() if not dates.empty else ""
    age = pd.to_numeric(df.get("age_days", pd.Series(dtype=float)), errors="coerce")
    stale_rows = int(age.gt(settings.freshness_threshold_days).sum())
    payload = {
        "latest_published": latest,
        "oldest_published": oldest,
        "stale_rows": stale_rows,
        "total_rows": int(len(df)),
        "threshold_days": settings.freshness_threshold_days,
        "is_fresh": bool(len(df) > 0 and stale_rows == 0),
    }
    write_json(report_path, payload)
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run data quality and freshness checks.")
    parser.add_argument(
        "--state",
        choices=("baseline", "corrupted", "repaired"),
        default="corrupted",
        help="Dataset state to inspect (default: corrupted).",
    )
    args = parser.parse_args()

    from core.config import load_settings

    settings = load_settings()
    csv_paths = {
        "baseline": settings.paths.clean_csv,
        "corrupted": settings.paths.corrupted_clean_csv,
        "repaired": settings.paths.repaired_clean_csv,
    }
    freshness_paths = {
        "baseline": settings.paths.freshness_report,
        "corrupted": settings.paths.quality_dir / "corrupted_freshness_report.json",
        "repaired": settings.paths.quality_dir / "repaired_freshness_report.json",
    }
    csv_path = csv_paths[args.state]
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Missing {csv_path}. Run the corresponding pipeline before checking {args.state}."
        )
    dataframe = pd.read_csv(csv_path)
    quality_result = run_data_quality_checks(dataframe, settings, args.state)
    freshness_result = build_freshness_report(dataframe, settings, freshness_paths[args.state])
    print(f"State: {args.state}")
    print(f"Rows: {len(dataframe)}")
    print(f"Quality: {'PASS' if quality_result['passed'] else 'FAIL'}")
    print(f"Freshness: {'PASS' if freshness_result['is_fresh'] else 'FAIL'}")
    for check in quality_result["checks"]:
        print(f"- {check['name']}: {'PASS' if check['passed'] else 'FAIL'} ({check['details']})")

if __name__ == "__main__":
    from core.config import load_settings
    settings = load_settings()
    df = pd.read_json(settings.paths.clean_json)
    run_data_quality_checks(df, settings, "baseline")
    build_freshness_report(df, settings, settings.paths.freshness_report)
