from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return normalize_whitespace(str(value))


def _normalize_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _normalize_text(value)
        key = item.lower()
        if item and key not in seen:
            normalized.append(item)
            seen.add(key)
    return normalized


def _parse_date(value: Any) -> tuple[str, date | None, bool, str]:
    """Return normalized date, parsed date, validity flag, and precision.

    Missing or invalid dates stay empty. We do not invent dates because freshness
    and age-based corruption checks must remain traceable to source data.
    """
    text = _normalize_text(value)
    if not text:
        return "", None, False, "missing"

    for fmt, precision in (
        ("%Y-%m-%d", "day"),
        ("%Y-%m", "month"),
        ("%Y", "year"),
    ):
        try:
            parsed = datetime.strptime(text, fmt).date()
            normalized = parsed.isoformat()
            return normalized, parsed, True, precision
        except ValueError:
            continue
    return "", None, False, "invalid"


def _age_days(published_date: date | None, run_date: datetime) -> int | None:
    if published_date is None:
        return None
    return (run_date.date() - published_date).days


def _embedding_text(row: dict[str, Any]) -> str:
    parts = [
        f"Title: {row['title']}",
        f"Summary: {row['summary']}" if row["summary"] else "",
        f"Authors: {row['authors_joined']}" if row["authors_joined"] else "",
        f"Categories: {row['categories_joined']}" if row["categories_joined"] else "",
        f"Venue: {row['comment']}" if row["comment"] else "",
        f"Published: {row['published']}" if row["published_valid"] else "",
    ]
    return "\n".join(part for part in parts if part)


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw records into a dataframe ready for embedding.

    The cleaning contract favors accuracy over convenience:
    - records missing `paper_id` or `title` are removed because downstream
      retrieval needs a stable document identity and a meaningful label;
    - missing optional fields stay empty and get explicit tracking flags;
    - missing/invalid dates are not replaced with synthetic dates.
    """
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for record in records:
        paper_id = _normalize_text(record.paper_id)
        title = _normalize_text(record.title)
        if not paper_id or not title:
            continue

        paper_id_key = paper_id.lower()
        if paper_id_key in seen_ids:
            continue
        seen_ids.add(paper_id_key)

        summary = _normalize_text(record.summary)
        authors = _normalize_list(record.authors)
        categories = _normalize_list(record.categories)
        primary_category = _normalize_text(record.primary_category)
        if not primary_category and categories:
            primary_category = categories[0]

        published_original = _normalize_text(record.published)
        updated_original = _normalize_text(record.updated)
        published, published_date, published_valid, published_precision = _parse_date(published_original)
        updated, _, updated_valid, updated_precision = _parse_date(updated_original)
        source_published_precision = _normalize_text(getattr(record, "published_date_precision", ""))
        source_updated_precision = _normalize_text(getattr(record, "updated_date_precision", ""))
        age = _age_days(published_date, run_date)

        row: dict[str, Any] = {
            "paper_id": paper_id,
            "title": title,
            "summary": summary,
            "authors": authors,
            "authors_joined": compact_join(authors),
            "categories": categories,
            "categories_joined": compact_join(categories),
            "primary_category": primary_category,
            "published": published,
            "published_original": published_original,
            "published_valid": published_valid,
            "published_source": _normalize_text(getattr(record, "published_source", "")),
            "published_date_precision": source_published_precision or published_precision,
            "published_missing": not bool(published_original),
            "published_in_future": bool(age is not None and age < 0),
            "updated": updated,
            "updated_original": updated_original,
            "updated_valid": updated_valid,
            "updated_source": _normalize_text(getattr(record, "updated_source", "")),
            "updated_date_precision": source_updated_precision or updated_precision,
            "abs_url": _normalize_text(record.abs_url),
            "pdf_url": _normalize_text(record.pdf_url),
            "comment": _normalize_text(record.comment),
            "summary_missing": not bool(summary),
            "authors_missing": not bool(authors),
            "categories_missing": not bool(categories),
            "summary_chars": len(summary),
            "age_days": age,
        }
        row["text_for_embedding"] = _embedding_text(row)
        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    return df.sort_values(["published", "paper_id"], ascending=[False, True], na_position="last").reset_index(drop=True)
