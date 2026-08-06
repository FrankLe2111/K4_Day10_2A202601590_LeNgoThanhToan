from __future__ import annotations

import json

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

from ingestion.corruption import corrupt_clean_dataframe


def _embedding_text(row: dict) -> str:
    return "\n".join(
        (
            f"Title: {row['title']}",
            f"Summary: {row['summary']}",
            f"Authors: {row['authors_joined']}",
            f"Categories: {row['categories_joined']}",
            f"Venue: {row['comment']}",
            f"Published: {row['published']}",
        )
    )


def _clean_dataframe() -> pd.DataFrame:
    rows = []
    for number in range(8):
        row = {
            "paper_id": f"paper-{number}",
            "title": f"A deliberately long scholarly paper title number {number}",
            "summary": f"Summary for paper {number}. " + ("Useful evidence. " * 10),
            # These two fields intentionally mimic values after a CSV round trip.
            "authors": "['Ada Lovelace', 'Grace Hopper']",
            "authors_joined": "Ada Lovelace, Grace Hopper",
            "authors_missing": False,
            "categories": "['RAG', 'Evaluation']",
            "categories_joined": "RAG, Evaluation",
            "categories_missing": False,
            "primary_category": "RAG",
            "published": (pd.Timestamp("2026-08-01") - pd.Timedelta(days=number)).date().isoformat(),
            "published_original": (pd.Timestamp("2026-08-01") - pd.Timedelta(days=number)).date().isoformat(),
            "published_valid": True,
            "published_source": "published-online",
            "published_date_precision": "day",
            "published_missing": False,
            "published_in_future": False,
            "updated": "2026-08-01",
            "updated_original": "2026-08-01",
            "updated_valid": True,
            "updated_source": "deposited",
            "updated_date_precision": "day",
            "abs_url": f"https://doi.org/paper-{number}",
            "pdf_url": "",
            "comment": "Test Journal",
            "summary_missing": False,
            "summary_chars": 0,
            "age_days": number + 5,
        }
        row["summary_chars"] = len(row["summary"])
        row["text_for_embedding"] = _embedding_text(row)
        rows.append(row)

    # The newest record is deliberately not first. Selection must use dates,
    # not incidental dataframe order.
    return pd.DataFrame(rows).iloc[[3, 5, 0, 6, 2, 7, 1, 4]].reset_index(drop=True)


def _operation(log: dict, name: str) -> dict:
    return next(item for item in log["operations"] if item["operation"] == name)


def test_corruption_is_deterministic_auditable_and_does_not_mutate_input(tmp_path) -> None:
    clean = _clean_dataframe()
    original = clean.copy(deep=True)

    first = corrupt_clean_dataframe(clean, tmp_path / "first.json")
    second = corrupt_clean_dataframe(clean, tmp_path / "second.json")
    first_log = json.loads((tmp_path / "first.json").read_text(encoding="utf-8"))
    second_log = json.loads((tmp_path / "second.json").read_text(encoding="utf-8"))

    assert_frame_equal(clean, original)
    assert_frame_equal(first, second)
    assert first_log == second_log
    assert list(first.columns) == list(clean.columns)
    assert first_log["deterministic"] is True
    assert first_log["operation_count"] == 6
    assert [item["operation"] for item in first_log["operations"]] == [
        "drop_latest_records",
        "blank_summary",
        "truncate_title",
        "inject_summary_noise",
        "make_date_stale",
        "add_duplicate",
    ]
    assert all(item["count"] == len(item["paper_ids"]) == len(item["changes"]) for item in first_log["operations"])
    assert all("before" in change and "after" in change for item in first_log["operations"] for change in item["changes"])

    dropped = _operation(first_log, "drop_latest_records")
    assert dropped["paper_ids"] == ["paper-0"]
    assert "paper-0" not in set(first["paper_id"])

    blank = _operation(first_log, "blank_summary")
    blank_row = first[first["paper_id"] == blank["paper_ids"][0]].iloc[0]
    assert blank_row["summary"] == ""
    assert blank_row["summary_chars"] == 0
    assert bool(blank_row["summary_missing"]) is True
    assert "Summary:" not in blank_row["text_for_embedding"]

    truncated = _operation(first_log, "truncate_title")
    truncated_row = first[first["paper_id"] == truncated["paper_ids"][0]].iloc[0]
    assert 0 < len(truncated_row["title"]) <= 35
    assert truncated_row["title"] != truncated["changes"][0]["before"]["title"]
    assert truncated_row["text_for_embedding"].startswith(f"Title: {truncated_row['title']}")

    noise = _operation(first_log, "inject_summary_noise")
    noise_row = first[first["paper_id"] == noise["paper_ids"][0]].iloc[0]
    assert noise_row["summary"].startswith("[[CORRUPTED_NOISE]] ")
    assert noise_row["summary_chars"] == len(noise_row["summary"])
    assert bool(noise_row["summary_missing"]) is False
    assert noise_row["summary"] in noise_row["text_for_embedding"]

    stale = _operation(first_log, "make_date_stale")
    stale_row = first[first["paper_id"] == stale["paper_ids"][0]].iloc[0]
    assert stale_row["age_days"] >= 3650
    assert bool(stale_row["published_valid"]) is True
    assert bool(stale_row["published_missing"]) is False
    assert bool(stale_row["published_in_future"]) is False
    assert f"Published: {stale_row['published']}" in stale_row["text_for_embedding"]

    duplicate = _operation(first_log, "add_duplicate")
    duplicate_rows = first[first["paper_id"] == duplicate["paper_ids"][0]].reset_index(drop=True)
    assert len(duplicate_rows) == 2
    assert_series_equal(duplicate_rows.iloc[0], duplicate_rows.iloc[1], check_names=False)

    # The raw list-like CSV fields and their clean joined counterparts must be
    # identical for every surviving record, including the duplicate.
    for _, row in first.iterrows():
        source = original[original["paper_id"] == row["paper_id"]].iloc[0]
        assert row["authors"] == source["authors"]
        assert row["authors_joined"] == source["authors_joined"]
        assert row["categories"] == source["categories"]
        assert row["categories_joined"] == source["categories_joined"]

    changed_ids = {
        blank["paper_ids"][0],
        truncated["paper_ids"][0],
        noise["paper_ids"][0],
        stale["paper_ids"][0],
    }
    for paper_id in set(original["paper_id"]).difference(dropped["paper_ids"], changed_ids):
        source = original[original["paper_id"] == paper_id].iloc[0]
        surviving = first[first["paper_id"] == paper_id]
        # The duplicate target has two copies; both must still equal its clean
        # source row. Every other untouched record has exactly one copy.
        for _, row in surviving.iterrows():
            assert_series_equal(row, source, check_names=False)


@pytest.mark.parametrize("row_count", [0, 5])
def test_corruption_rejects_inputs_that_cannot_hold_all_scenarios(tmp_path, row_count: int) -> None:
    clean = _clean_dataframe().head(row_count)

    with pytest.raises(ValueError):
        corrupt_clean_dataframe(clean, tmp_path / "log.json")

    assert not (tmp_path / "log.json").exists()
