from __future__ import annotations

from typing import Any
from core.utils import write_text


def _metric_lines(metrics: dict[str, Any]) -> str:
    keys = (
        "retrieval_hit_rate",
        "mean_token_f1",
        "judge_accuracy",
        "mean_judge_score",
        "llm_answer_count",
        "fallback_answer_count",
    )
    return "\n".join(f"- `{key}`: {metrics.get(key, 'N/A')}" for key in keys)


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write the baseline phase markdown report.

    Pseudo-code:
    1. Gom source summary.
    2. In metrics retrieval/evaluation.
    3. In data quality va freshness.
    4. Ghi markdown vao report_path.
    """
    text = "# Phase 1 Baseline Report\n\n"
    text += "## Source\n\n" + "\n".join(f"- `{k}`: {v}" for k, v in source_summary.items()) + "\n\n"
    text += "## Evaluation metrics\n\n" + _metric_lines(metrics) + "\n\n"
    text += "## Data quality\n\n"
    text += f"- Status: **{'PASS' if quality.get('passed') else 'FAIL'}**\n- Rows: {quality.get('total_rows', 0)}\n\n"
    text += "## Freshness\n\n" + "\n".join(f"- `{k}`: {v}" for k, v in freshness.items()) + "\n"
    write_text(report_path, text)


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Write the baseline/corrupted/repaired comparison report."""
    metric_keys = ("retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score")
    lines = [
        "# Corruption and Repair Report",
        "",
        "## Metric comparison",
        "",
        "| Metric | Baseline | Corrupted | Repaired | Corrupted - baseline | Repaired - baseline |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key in metric_keys:
        baseline = baseline_metrics.get(key)
        corrupted = corrupted_metrics.get(key)
        repaired = repaired_metrics.get(key)
        corrupted_delta = corrupted - baseline if isinstance(baseline, (int, float)) and isinstance(corrupted, (int, float)) else "N/A"
        repaired_delta = repaired - baseline if isinstance(baseline, (int, float)) and isinstance(repaired, (int, float)) else "N/A"
        lines.append(
            f"| {key} | {baseline if baseline is not None else 'N/A'} | "
            f"{corrupted if corrupted is not None else 'N/A'} | "
            f"{repaired if repaired is not None else 'N/A'} | "
            f"{corrupted_delta} | {repaired_delta} |"
        )
    lines += ["", "## Quality and freshness", "", "| State | Quality | Fresh |", "|---|---|---|"]
    lines.append(f"| Corrupted | {corrupted_quality.get('passed')} | {corrupted_freshness.get('is_fresh')} |")
    lines.append(f"| Repaired | {repaired_quality.get('passed')} | {repaired_freshness.get('is_fresh')} |")
    lines += ["", "The repaired state is rebuilt from the raw records snapshot.", ""]
    write_text(report_path, "\n".join(lines))
