from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import first_sentence, write_json


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"1", "true", "yes"}


def _non_empty(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _add_sample(
    samples: list[dict[str, Any]],
    *,
    question_type: str,
    question: str,
    ground_truth: str,
    paper_id: str,
) -> None:
    if not question.strip() or not ground_truth.strip() or not paper_id.strip():
        return
    samples.append(
        {
            "id": f"q{len(samples) + 1:03d}",
            "question_type": question_type,
            "question": question,
            "ground_truth": ground_truth,
            "ground_truth_doc_ids": [paper_id],
        }
    )


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Build an evidence-backed evaluation set from cleaned records.

    Questions are created only when the source field is present and valid. This
    keeps evaluation from rewarding answers to fabricated or fallback data.
    """
    required_columns = {"paper_id", "title", "summary", "authors_joined", "categories_joined", "published"}
    missing_columns = sorted(required_columns - set(df.columns))
    if missing_columns:
        raise ValueError(f"Clean dataframe is missing required columns: {missing_columns}")

    if df.empty:
        raise ValueError("Cannot build an evaluation set from an empty dataframe.")

    samples: list[dict[str, Any]] = []
    selected = df.head(8).to_dict(orient="records")

    for row in selected:
        paper_id = _non_empty(row.get("paper_id"))
        title = _non_empty(row.get("title"))
        summary = _non_empty(row.get("summary"))
        authors = _non_empty(row.get("authors_joined"))
        categories = _non_empty(row.get("categories_joined"))
        published = _non_empty(row.get("published"))
        published_valid = _as_bool(row.get("published_valid", bool(published)))

        if summary:
            _add_sample(
                samples,
                question_type="summary",
                question=f"What is the main idea of the paper titled '{title}'?",
                ground_truth=first_sentence(summary),
                paper_id=paper_id,
            )
        if authors:
            _add_sample(
                samples,
                question_type="authors",
                question=f"Who authored the paper titled '{title}'?",
                ground_truth=authors,
                paper_id=paper_id,
            )
        if published and published_valid:
            _add_sample(
                samples,
                question_type="date",
                question=f"When was the paper titled '{title}' published?",
                ground_truth=published,
                paper_id=paper_id,
            )
        if categories:
            _add_sample(
                samples,
                question_type="categories",
                question=f"What categories are assigned to the paper titled '{title}'?",
                ground_truth=categories,
                paper_id=paper_id,
            )

    if len(samples) < 4:
        raise ValueError(
            "Evaluation set is too small. Need at least 4 evidence-backed questions from the cleaned dataset."
        )

    write_json(Path(output_path), samples)
    return samples
