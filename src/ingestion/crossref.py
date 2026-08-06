import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    published_source: str
    published_date_precision: str
    updated: str
    updated_source: str
    updated_date_precision: str
    abs_url: str
    pdf_url: str
    comment: str

def _clean_xml_tags(text: str) -> str:
    # Xoá các thẻ XML/HML như <jats:p> và chuẩn hóa khoảng trắng.
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    return normalize_whitespace(cleaned)

def _extract_date(date_struct: dict[str, Any] | None) -> tuple[str, str]:
    # Trích xuất chuỗi ngày dạng YYYY-MM-DD từ dict date-parts của Crossref.
    # Không tự gán ngày hiện tại khi nguồn thiếu/sai ngày, vì freshness phải
    # truy vết được dữ liệu thật thay vì dữ liệu fallback bị bịa.
    if not date_struct or not isinstance(date_struct, dict) or "date-parts" not in date_struct:
        return "", "missing"

    date_parts = date_struct.get("date-parts", [[]])
    if not isinstance(date_parts, list) or not date_parts or not isinstance(date_parts[0], list) or not date_parts[0]:
        return "", "missing"

    parts = date_parts[0]
    try:
        if len(parts) == 0 or parts[0] is None:
            return "", "missing"
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 and parts[1] is not None else 1
        day = int(parts[2]) if len(parts) > 2 and parts[2] is not None else 1
        precision = "day" if len(parts) >= 3 else "month" if len(parts) == 2 else "year"
        return f"{year:04d}-{month:02d}-{day:02d}", precision
    except (ValueError, TypeError):
        return "", "invalid"


def _choose_date(item: dict[str, Any], field_names: list[str]) -> tuple[str, str, str]:
    for field_name in field_names:
        value = item.get(field_name)
        date_value, precision = _extract_date(value if isinstance(value, dict) else None)
        if date_value:
            return date_value, field_name, precision
        if precision == "invalid":
            return "", field_name, precision
    return "", "missing", "missing"


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    # Edge Case 1: Payload không phải dict hoặc None
    if not isinstance(payload, dict):
        return []

    items = payload.get("message", {}).get("items", [])
    if not isinstance(items, list):
        return []

    records: list[PaperRecord] = []

    for item in items:
        # Edge Case 2: Phần tử item bị None hoặc không phải dict
        if not isinstance(item, dict):
            continue

        doi = str(item.get("DOI", "") or "").strip()
        title_raw = item.get("title", [])

        # Edge Case 3: Title dạng list chứa None hoặc rỗng
        if isinstance(title_raw, list) and title_raw:
            first_title = title_raw[0]
            title = _clean_xml_tags(str(first_title)) if first_title else ""
        else:
            title = _clean_xml_tags(str(title_raw or ""))

        if not doi or not title or title.lower() == "none":
            continue

        summary = _clean_xml_tags(str(item.get("abstract", "") or ""))

        # Edge Case 4: Mảng author chứa phần tử non-dict hoặc None
        author_list = item.get("author", [])
        authors: list[str] = []
        if isinstance(author_list, list):
            for author in author_list:
                if not isinstance(author, dict):
                    continue
                given = str(author.get("given", "") or "").strip()
                family = str(author.get("family", "") or "").strip()
                name = f"{given} {family}".strip() if given and family else (family or given)
                if name:
                    authors.append(name)
        if not authors:
            authors = ["Anonymous"]

        subjects = item.get("subject", [])
        categories = [normalize_whitespace(str(s)) for s in subjects if s] if isinstance(subjects, list) else []
        if not categories:
            categories = ["General"]
        primary_category = categories[0]

        published, published_source, published_precision = _choose_date(
            item,
            ["published-online", "published-print", "issued"],
        )
        updated, updated_source, updated_precision = _choose_date(
            item,
            ["deposited", "indexed", "published-online", "published-print", "issued"],
        )

        abs_url = str(item.get("URL", "") or f"https://doi.org/{doi}")

        pdf_url = ""
        link_list = item.get("link", [])
        if isinstance(link_list, list):
            for link in link_list:
                if isinstance(link, dict) and link.get("content-type") == "application/pdf":
                    pdf_url = str(link.get("URL", "") or "")
                    break

        container_title = item.get("container-title", [])
        if isinstance(container_title, list) and container_title:
            comment = str(container_title[0] or "")
        else:
            comment = str(container_title or "")

        records.append(
            PaperRecord(
                paper_id=doi,
                title=title,
                summary=summary,
                authors=authors,
                categories=categories,
                primary_category=primary_category,
                published=published,
                published_source=published_source,
                published_date_precision=published_precision,
                updated=updated,
                updated_source=updated_source,
                updated_date_precision=updated_precision,
                abs_url=abs_url,
                pdf_url=pdf_url,
                comment=comment,
            )
        )

    return records



def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """TODO(student): goi source API, luu raw response, parse thanh records.

    Pseudo-code:
    1. Tao params tu `settings.source_query`, `settings.source_filter`, `settings.max_results`.
    2. Goi API voi retry cho cac status code nhu 429/503.
    3. Luu raw response vao `settings.paths.raw_api_response`.
    4. Parse payload bang `parse_crossref_payload`.
    5. Luu records vao `settings.paths.raw_records_json`.
    """
    url = "https://api.crossref.org/works"
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
    }
    headers = {
        "User-Agent": "Day10DataObservabilityLab/1.0 (mailto:student@example.com)",
    }

    max_retries = 4
    backoff = 1.0
    payload: dict[str, Any] = {}

    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=15)
            if response.status_code in {429, 503, 502, 504}:
                time.sleep(backoff)
                backoff *= 2
                continue
            response.raise_for_status()
            payload = response.json()
            break
        except requests.RequestException as exc:
            if attempt == max_retries - 1:
                raise RuntimeError(f"Failed to fetch Crossref records: {exc}") from exc
            time.sleep(backoff)
            backoff *= 2

    # Lưu Raw API Response JSON
    write_json(settings.paths.raw_api_response, payload)

    # Parse sang danh sách PaperRecord
    records = parse_crossref_payload(payload)

    # Lưu Raw Records JSON
    raw_records_data = [asdict(record) for record in records]
    write_json(settings.paths.raw_records_json, raw_records_data)

    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """TODO(student): doc JSON snapshot va map thanh `PaperRecord`."""
    raw_data = read_json(path)
    records: list[PaperRecord] = []
    for item in raw_data:
        records.append(
            PaperRecord(
                paper_id=item["paper_id"],
                title=item["title"],
                summary=item["summary"],
                authors=item.get("authors", []),
                categories=item.get("categories", []),
                primary_category=item.get("primary_category", "General"),
                published=item.get("published", ""),
                published_source=item.get("published_source", ""),
                published_date_precision=item.get("published_date_precision", ""),
                updated=item.get("updated", ""),
                updated_source=item.get("updated_source", ""),
                updated_date_precision=item.get("updated_date_precision", ""),
                abs_url=item.get("abs_url", ""),
                pdf_url=item.get("pdf_url", ""),
                comment=item.get("comment", ""),
            )
        )
    return records
