from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import time

import requests

from core.config import Settings


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _clean_text(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def _parse_date(value: dict) -> str:
    parts = value.get("date-parts", [[]])[0] if isinstance(value, dict) else []
    if not parts:
        return ""
    year = int(parts[0])
    month = int(parts[1]) if len(parts) > 1 else 1
    day = int(parts[2]) if len(parts) > 2 else 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse a Crossref payload into normalized paper records."""
    items = payload.get("message", {}).get("items", [])
    records: list[PaperRecord] = []
    seen_ids: set[str] = set()
    for item in items if isinstance(items, list) else []:
        paper_id = _clean_text(item.get("DOI"))
        titles = item.get("title", []) or []
        title = _clean_text(titles[0] if titles else "")
        summary = _clean_text(item.get("abstract") or item.get("description"))
        if not paper_id or not title or len(summary) < 100 or paper_id.lower() in seen_ids:
            continue

        authors = []
        for author in item.get("author", []) or []:
            name = " ".join(
                part for part in (_clean_text(author.get("given")), _clean_text(author.get("family"))) if part
            )
            if name:
                authors.append(name)
        categories = [_clean_text(x) for x in item.get("subject", []) or [] if _clean_text(x)]
        published = _parse_date(item.get("published", {}))
        updated = (
            _parse_date(item.get("updated", {}))
            or _parse_date(item.get("issued", {}))
            or _parse_date(item.get("created", {}))
        )
        pdf_url = ""
        for link in item.get("link", []) or []:
            if link.get("content-type") == "application/pdf":
                pdf_url = _clean_text(link.get("URL"))
                break
        records.append(PaperRecord(
            paper_id=paper_id,
            title=title,
            summary=summary,
            authors=authors,
            categories=categories,
            primary_category=categories[0] if categories else "",
            published=published,
            updated=updated,
            abs_url=_clean_text(item.get("URL") or f"https://doi.org/{paper_id}"),
            pdf_url=pdf_url,
            comment=_clean_text(item.get("comment")),
        ))
        seen_ids.add(paper_id.lower())
    return records


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Fetch, snapshot, and parse records from the Crossref API."""
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
    }
    headers = {"User-Agent": "day10-data-pipeline/1.0 (mailto:crossref@example.com)"}
    response = None
    for attempt in range(3):
        response = requests.get("https://api.crossref.org/works", params=params, headers=headers, timeout=30)
        if response.status_code not in {429, 502, 503, 504} or attempt == 2:
            break
        time.sleep(2**attempt)
    assert response is not None
    response.raise_for_status()
    payload = response.json()
    settings.paths.raw_api_response.parent.mkdir(parents=True, exist_ok=True)
    settings.paths.raw_api_response.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    records = parse_crossref_payload(payload)
    settings.paths.raw_records_json.parent.mkdir(parents=True, exist_ok=True)
    settings.paths.raw_records_json.write_text(
        json.dumps([record.__dict__ for record in records], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Load a JSON snapshot and map it to ``PaperRecord`` objects."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected a list of records in {path}")
    return [PaperRecord(**item) for item in payload]
