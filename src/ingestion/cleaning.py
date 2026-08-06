from __future__ import annotations

from datetime import datetime
import re
import pandas as pd

from ingestion.crossref import PaperRecord


def _clean_text(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"<[^>]*>", " ", text)
    return " ".join(text.split()).strip()


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw records into a dataframe ready for embedding.

    Pseudo-code:
    1. Normalize title, summary, authors, categories.
    2. Parse published/updated date.
    3. Tinh age_days.
    4. Tao cot helper:
       - authors_joined
       - categories_joined
       - summary_chars
       - text_for_embedding
    5. Drop duplicates va filter row xau.
    6. Sort dataframe va return.
    """
    rows = []
    run_date = run_date.replace(tzinfo=None)
    for record in records:
        title = _clean_text(record.title)
        summary = _clean_text(record.summary)
        paper_id = str(record.paper_id or "").strip()
        if not paper_id or not title or len(summary) < 100:
            continue
        authors = [" ".join(str(x).split()) for x in (record.authors or []) if str(x).strip()]
        categories = [" ".join(str(x).split()) for x in (record.categories or []) if str(x).strip()]
        published = pd.to_datetime(record.published, errors="coerce")
        updated = pd.to_datetime(record.updated, errors="coerce")
        age_days = int((run_date - published.to_pydatetime().replace(tzinfo=None)).days) if pd.notna(published) else None
        rows.append({
            "paper_id": paper_id,
            "title": title,
            "summary": summary,
            "authors": authors,
            "categories": categories,
            "primary_category": record.primary_category or (categories[0] if categories else ""),
            "published": published.date().isoformat() if pd.notna(published) else "",
            "updated": updated.date().isoformat() if pd.notna(updated) else "",
            "abs_url": record.abs_url or f"https://doi.org/{paper_id}",
            "pdf_url": record.pdf_url or "",
            "comment": record.comment or "",
            "authors_joined": ", ".join(authors),
            "categories_joined": ", ".join(categories),
            "summary_chars": len(summary),
            "age_days": age_days,
            "text_for_embedding": f"Title: {title} | Authors: {', '.join(authors)} | Summary: {summary}",
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.drop_duplicates(subset=["paper_id"], keep="first")
    df = df[df["title"].str.len() > 0]
    df = df[df["summary"].str.len() >= 100]
    return df.sort_values(["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)
