from __future__ import annotations

import json

import pandas as pd
import pytest

# Importing the real pipeline module also imports the retrieval/evaluation
# stack. A partial developer environment can still run the corruption unit
# tests; these integration-oriented helper tests run once project dependencies
# have been installed with ``pip install -e .`` or ``uv sync``.
pytest.importorskip("langchain")
pytest.importorskip("datasets")
pytest.importorskip("chromadb")

from core.utils import write_json
from pipelines.corruption_flow import (
    _assert_repaired_ids_match,
    _load_json_dataframe,
    _validate_corruption_log,
)
from pipelines.phase1 import _dataframe_records, _load_and_validate_test_set


def test_dataframe_json_records_preserve_lists_and_normalize_nan() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "paper_id": "paper-1",
                "authors": ["Ada", "Grace"],
                "categories": ["RAG"],
                "age_days": float("nan"),
            }
        ]
    )

    records = _dataframe_records(dataframe)

    assert records[0]["authors"] == ["Ada", "Grace"]
    assert records[0]["categories"] == ["RAG"]
    assert records[0]["age_days"] is None


def test_test_set_validation_rejects_orphan_ground_truth_id(tmp_path) -> None:
    test_set_path = tmp_path / "test_set.json"
    write_json(
        test_set_path,
        [
            {
                "id": "q001",
                "question_type": "summary",
                "question": "What does this paper contribute?",
                "ground_truth": "A grounded answer.",
                "ground_truth_doc_ids": ["missing-paper"],
            }
        ],
    )

    with pytest.raises(ValueError, match="absent from the baseline"):
        _load_and_validate_test_set(test_set_path, {"paper-1"})


def test_json_dataframe_loader_preserves_nested_list_schema(tmp_path) -> None:
    clean_path = tmp_path / "clean.json"
    write_json(
        clean_path,
        [
            {
                "paper_id": "paper-1",
                "authors": ["Ada", "Grace"],
                "categories": ["RAG", "Evaluation"],
            }
        ],
    )

    dataframe = _load_json_dataframe(clean_path, "clean fixture")

    assert dataframe.at[0, "authors"] == ["Ada", "Grace"]
    assert dataframe.at[0, "categories"] == ["RAG", "Evaluation"]


def test_corruption_log_envelope_and_exact_repair_id_validation(tmp_path) -> None:
    log_path = tmp_path / "corruption_log.json"
    log_path.write_text(
        json.dumps(
            {
                "operation_count": 1,
                "operations": [
                    {
                        "operation": "blank_summary",
                        "paper_ids": ["paper-1"],
                        "changes": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert len(_validate_corruption_log(log_path)) == 1

    baseline = pd.DataFrame({"paper_id": ["paper-1", "paper-2"]})
    repaired = pd.DataFrame({"paper_id": ["paper-1", "paper-3"]})
    with pytest.raises(RuntimeError, match="did not restore"):
        _assert_repaired_ids_match(baseline, repaired)
