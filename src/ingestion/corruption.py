from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

from core.utils import write_json


_MINIMUM_ROWS = 6
_MAX_DROPPED_ROWS = 2
_TITLE_MAX_CHARS = 35
_NOISE_PREFIX = "[[CORRUPTED_NOISE]] "
_MINIMUM_STALE_AGE_DAYS = 3650
_REQUIRED_COLUMNS = {
    "paper_id",
    "title",
    "summary",
    "published",
    "age_days",
    "summary_chars",
    "summary_missing",
    "published_valid",
    "published_missing",
    "published_in_future",
    "text_for_embedding",
}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        # List-like cells make ``pd.isna`` return an array. Such a cell is not
        # missing, and, importantly, must not be modified in place.
        return False


def _cell_text(value: Any) -> str:
    return "" if _is_missing(value) else str(value).strip()


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if _is_missing(value):
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no", ""}:
            return False
    return bool(value)


def _as_int(value: Any, *, field_name: str, paper_id: str) -> int:
    if _is_missing(value):
        raise ValueError(f"{field_name} is missing for paper_id={paper_id!r}.")
    try:
        return int(float(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{field_name} must be numeric for paper_id={paper_id!r}; got {value!r}."
        ) from exc


def _json_value(value: Any) -> Any:
    """Convert pandas/numpy scalar values to deterministic JSON values."""
    if _is_missing(value):
        return None
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, set):
        return sorted((_json_value(item) for item in value), key=str)
    if hasattr(value, "item"):
        value = value.item()
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value.isoformat()
    return value


def _row_snapshot(row: pd.Series, fields: Iterable[str]) -> dict[str, Any]:
    return {field: _json_value(row.get(field)) for field in fields}


def _embedding_text(row: pd.Series) -> str:
    """Mirror the clean-data embedding format without parsing list columns.

    CSV round-tripping turns ``authors`` and ``categories`` into strings such
    as ``"['Ada', 'Grace']"``. The already-normalized ``*_joined`` columns are
    therefore the source of truth here; the raw list columns remain untouched.
    """
    title = _cell_text(row.get("title"))
    summary = _cell_text(row.get("summary"))
    authors = _cell_text(row.get("authors_joined"))
    categories = _cell_text(row.get("categories_joined"))
    comment = _cell_text(row.get("comment"))
    published = _cell_text(row.get("published"))
    published_valid = _as_bool(row.get("published_valid"), default=bool(published))

    parts = [
        f"Title: {title}",
        f"Summary: {summary}" if summary else "",
        f"Authors: {authors}" if authors else "",
        f"Categories: {categories}" if categories else "",
        f"Venue: {comment}" if comment else "",
        f"Published: {published}" if published and published_valid else "",
    ]
    return "\n".join(part for part in parts if part)


def _refresh_embedding(df: pd.DataFrame, index: int) -> None:
    df.at[index, "text_for_embedding"] = _embedding_text(df.loc[index])


def _operation(
    name: str,
    changes: list[dict[str, Any]],
    **parameters: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "operation": name,
        "count": len(changes),
        "paper_ids": [change["paper_id"] for change in changes],
        "changes": changes,
    }
    if parameters:
        payload["parameters"] = {key: _json_value(value) for key, value in parameters.items()}
    return payload


def _validate_input(df: pd.DataFrame) -> None:
    if df.empty:
        raise ValueError("Cannot corrupt an empty dataframe.")
    missing_columns = sorted(_REQUIRED_COLUMNS.difference(df.columns))
    if missing_columns:
        raise ValueError(f"Clean dataframe is missing required columns: {missing_columns}")
    if len(df) < _MINIMUM_ROWS:
        raise ValueError(
            f"At least {_MINIMUM_ROWS} clean rows are required to apply all corruption scenarios; "
            f"got {len(df)}."
        )


def _latest_indices(df: pd.DataFrame, count: int) -> list[int]:
    candidates = pd.DataFrame(
        {
            "row_index": df.index,
            "published": pd.to_datetime(df["published"], errors="coerce"),
            "paper_id": df["paper_id"].map(_cell_text),
        }
    )
    ordered = candidates.sort_values(
        ["published", "paper_id", "row_index"],
        ascending=[False, True, True],
        na_position="last",
        kind="mergesort",
    )
    return [int(index) for index in ordered.head(count)["row_index"]]


def _truncated_title(title: str) -> str:
    if len(title) > _TITLE_MAX_CHARS:
        return title[:_TITLE_MAX_CHARS].rstrip()
    if len(title) > 1:
        return title[: max(1, len(title) // 2)].rstrip()
    return title


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Create a deterministic, auditable corrupted copy of a clean dataframe.

    Six controlled scenarios are applied to distinct records: latest-record
    removal, a blank summary, a truncated title, summary noise, a stale
    publication date, and a duplicate row. The input dataframe is never
    mutated. Every changed field, including derived flags and embedding text,
    is captured in the JSON log.
    """
    _validate_input(df)
    corrupted = df.copy(deep=True).reset_index(drop=True)
    input_row_count = len(corrupted)
    operations: list[dict[str, Any]] = []

    # Keep five distinct rows for the four field corruptions and one duplicate.
    drop_count = min(
        _MAX_DROPPED_ROWS,
        max(1, input_row_count // 5),
        input_row_count - 5,
    )
    dropped_indices = _latest_indices(corrupted, drop_count)
    drop_changes: list[dict[str, Any]] = []
    for index in dropped_indices:
        row = corrupted.loc[index]
        paper_id = _cell_text(row["paper_id"])
        drop_changes.append(
            {
                "paper_id": paper_id,
                "before": {
                    "row_present": True,
                    **_row_snapshot(row, ("published", "age_days")),
                },
                "after": {"row_present": False},
            }
        )
    corrupted = corrupted.drop(index=dropped_indices).reset_index(drop=True)
    operations.append(_operation("drop_latest_records", drop_changes))

    summary_fields = ("summary", "summary_chars", "summary_missing", "text_for_embedding")
    title_fields = ("title", "text_for_embedding")
    published_fields = (
        "published",
        "age_days",
        "published_valid",
        "published_missing",
        "published_in_future",
        "published_date_precision",
        "text_for_embedding",
    )

    # Blank one summary and keep all its derived fields consistent.
    blank_index = 0
    blank_id = _cell_text(corrupted.at[blank_index, "paper_id"])
    blank_before = _row_snapshot(corrupted.loc[blank_index], summary_fields)
    corrupted.at[blank_index, "summary"] = ""
    corrupted.at[blank_index, "summary_chars"] = 0
    corrupted.at[blank_index, "summary_missing"] = True
    _refresh_embedding(corrupted, blank_index)
    operations.append(
        _operation(
            "blank_summary",
            [
                {
                    "paper_id": blank_id,
                    "before": blank_before,
                    "after": _row_snapshot(corrupted.loc[blank_index], summary_fields),
                }
            ],
        )
    )

    # Truncate a different title. Short synthetic test titles are shortened by
    # half so the operation is still observable and deterministic.
    title_index = 1
    title_id = _cell_text(corrupted.at[title_index, "paper_id"])
    title_before = _row_snapshot(corrupted.loc[title_index], title_fields)
    original_title = _cell_text(corrupted.at[title_index, "title"])
    corrupted.at[title_index, "title"] = _truncated_title(original_title)
    _refresh_embedding(corrupted, title_index)
    operations.append(
        _operation(
            "truncate_title",
            [
                {
                    "paper_id": title_id,
                    "before": title_before,
                    "after": _row_snapshot(corrupted.loc[title_index], title_fields),
                }
            ],
            max_chars=_TITLE_MAX_CHARS,
        )
    )

    # Inject a stable marker into another summary.
    noise_index = 2
    noise_id = _cell_text(corrupted.at[noise_index, "paper_id"])
    noise_before = _row_snapshot(corrupted.loc[noise_index], summary_fields)
    noisy_summary = _NOISE_PREFIX + _cell_text(corrupted.at[noise_index, "summary"])
    corrupted.at[noise_index, "summary"] = noisy_summary
    corrupted.at[noise_index, "summary_chars"] = len(noisy_summary)
    corrupted.at[noise_index, "summary_missing"] = False
    _refresh_embedding(corrupted, noise_index)
    operations.append(
        _operation(
            "inject_summary_noise",
            [
                {
                    "paper_id": noise_id,
                    "before": noise_before,
                    "after": _row_snapshot(corrupted.loc[noise_index], summary_fields),
                }
            ],
            prefix=_NOISE_PREFIX,
        )
    )

    # Shift a valid publication date far enough into the past to guarantee a
    # stale age while preserving the original run-date relationship.
    stale_index = 3
    stale_id = _cell_text(corrupted.at[stale_index, "paper_id"])
    stale_before = _row_snapshot(corrupted.loc[stale_index], published_fields)
    original_published = pd.to_datetime(corrupted.at[stale_index, "published"], errors="coerce")
    if pd.isna(original_published):
        raise ValueError(f"published must be a valid date for paper_id={stale_id!r}.")
    original_age = _as_int(corrupted.at[stale_index, "age_days"], field_name="age_days", paper_id=stale_id)
    days_shifted = max(_MINIMUM_STALE_AGE_DAYS, _MINIMUM_STALE_AGE_DAYS - original_age)
    stale_date = original_published - pd.Timedelta(days=days_shifted)
    stale_age = original_age + days_shifted
    corrupted.at[stale_index, "published"] = stale_date.date().isoformat()
    corrupted.at[stale_index, "age_days"] = stale_age
    corrupted.at[stale_index, "published_valid"] = True
    corrupted.at[stale_index, "published_missing"] = False
    corrupted.at[stale_index, "published_in_future"] = stale_age < 0
    if "published_date_precision" in corrupted.columns:
        corrupted.at[stale_index, "published_date_precision"] = "day"
    _refresh_embedding(corrupted, stale_index)
    operations.append(
        _operation(
            "make_date_stale",
            [
                {
                    "paper_id": stale_id,
                    "before": stale_before,
                    "after": _row_snapshot(corrupted.loc[stale_index], published_fields),
                }
            ],
            days_shifted=days_shifted,
            minimum_age_days=_MINIMUM_STALE_AGE_DAYS,
        )
    )

    # Duplicate an otherwise untouched row so the duplicate operation remains
    # isolated from all content corruptions above.
    duplicate_index = 4
    duplicate_id = _cell_text(corrupted.at[duplicate_index, "paper_id"])
    occurrences_before = int(corrupted["paper_id"].map(_cell_text).eq(duplicate_id).sum())
    row_count_before = len(corrupted)
    duplicate = corrupted.iloc[[duplicate_index]].copy(deep=True)
    corrupted = pd.concat([corrupted, duplicate], ignore_index=True)
    occurrences_after = int(corrupted["paper_id"].map(_cell_text).eq(duplicate_id).sum())
    operations.append(
        _operation(
            "add_duplicate",
            [
                {
                    "paper_id": duplicate_id,
                    "before": {
                        "occurrences": occurrences_before,
                        "row_count": row_count_before,
                    },
                    "after": {
                        "occurrences": occurrences_after,
                        "row_count": len(corrupted),
                    },
                }
            ],
        )
    )

    log_payload = {
        "version": 1,
        "deterministic": True,
        "input_row_count": input_row_count,
        "output_row_count": len(corrupted),
        "net_row_delta": len(corrupted) - input_row_count,
        "operation_count": len(operations),
        "operations": operations,
    }
    write_json(output_log_path, log_payload)
    return corrupted


if __name__ == "__main__":
    from core.config import load_settings
    from core.utils import write_csv

    settings = load_settings()
    clean_df = pd.read_csv(settings.paths.clean_csv)
    corrupted_df = corrupt_clean_dataframe(clean_df, settings.paths.corruption_log)
    write_csv(corrupted_df, settings.paths.corrupted_clean_csv)
    print(f"Wrote {len(corrupted_df)} corrupted records to {settings.paths.corrupted_clean_csv}")
