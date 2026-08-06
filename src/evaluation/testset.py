from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import pandas as pd

# Allow this helper to be run directly from any working directory.
src_dir = Path(__file__).resolve().parents[1]
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from core.utils import write_json, first_sentence


def _cell_text(value: object) -> str:
    """Convert a dataframe cell to text without leaking pandas NaN."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Build an evaluation set from the cleaned dataframe.

    Pseudo-code:
    1. Kiem tra so luong document toi thieu.
    2. Chon mot so paper dai dien.
    3. Tao nhieu loai cau hoi:
       - summary
       - authors
       - date
       - categories
    4. Moi row can co:
       - id
       - question_type
       - question
       - ground_truth
       - ground_truth_doc_ids
    5. Ghi file JSON vao output_path.
    """
    if df.empty:
        raise ValueError("Cannot build an evaluation set from an empty dataframe.")
    samples = []
    for _, row in df.head(min(6, len(df))).iterrows():
        pid, title = _cell_text(row["paper_id"]), _cell_text(row["title"])
        summary = _cell_text(row["summary"])
        authors = _cell_text(row["authors_joined"])
        published = _cell_text(row["published"])
        categories = _cell_text(row["categories_joined"])
        questions = [
            ("summary", f"What is the main contribution of '{title}'?", first_sentence(summary)),
            ("authors", f"Who authored '{title}'?", authors),
            ("date", f"When was '{title}' published?", published),
            ("categories", f"What categories describe '{title}'?", categories),
        ]
        for question_type, question, ground_truth in questions:
            if ground_truth.strip():
                samples.append({
                    "id": f"{pid}::{question_type}",
                    "question_type": question_type,
                    "question": question,
                    "ground_truth": ground_truth,
                    "ground_truth_doc_ids": [pid],
                })
    write_json(output_path, samples)
    return samples

if __name__ == "__main__":
    project_dir = Path(__file__).resolve().parents[2]
    df = pd.read_csv(project_dir / "data/clean/papers_clean.csv")
    output_path = project_dir / "data/eval/test_set.json"
    build_test_set(df, output_path)
    print(f"Wrote {len(df)} source records to {output_path}")
