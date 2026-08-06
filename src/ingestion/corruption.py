from __future__ import annotations

import pandas as pd
import json
from pathlib import Path


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Simulate several data corruption scenarios.

    Pseudo-code:
    1. Drop mot so latest records.
    2. Blank summary o mot so dong.
    3. Inject noise vao text.
    4. Lam title bi truncate.
    5. Lam published date cu di.
    6. Add duplicate rows.
    7. Rebuild `text_for_embedding`.
    8. Ghi corruption log vao output_log_path.
    """
    if df.empty:
        raise ValueError("Cannot corrupt an empty dataframe.")
    corrupted = df.copy(deep=True)
    log = []
    n = len(corrupted)
    latest_count = max(1, min(2, n // 5))
    dropped_ids = corrupted.head(latest_count)["paper_id"].tolist()
    corrupted = corrupted.iloc[latest_count:].copy()
    log.append({"operation": "drop_latest_records", "paper_ids": dropped_ids})
    if not corrupted.empty:
        idx = corrupted.index[0]
        corrupted.loc[idx, "summary"] = ""
        corrupted.loc[idx, "summary_chars"] = 0
        log.append({"operation": "blank_summary", "paper_ids": [corrupted.loc[idx, "paper_id"]]})
    if len(corrupted) > 1:
        idx = corrupted.index[1]
        corrupted.loc[idx, "title"] = str(corrupted.loc[idx, "title"])[:35]
        log.append({"operation": "truncate_title", "paper_ids": [corrupted.loc[idx, "paper_id"]]})
    if len(corrupted) > 2:
        idx = corrupted.index[2]
        corrupted.loc[idx, "summary"] = "NOISE ERROR corrupted_text " + str(corrupted.loc[idx, "summary"])
        corrupted.loc[idx, "summary_chars"] = len(corrupted.loc[idx, "summary"])
        log.append({"operation": "inject_summary_noise", "paper_ids": [corrupted.loc[idx, "paper_id"]]})
    if len(corrupted) > 3:
        idx = corrupted.index[3]
        corrupted.loc[idx, "published"] = "2000-01-01"
        corrupted.loc[idx, "age_days"] = 9999
        log.append({"operation": "make_date_stale", "paper_ids": [corrupted.loc[idx, "paper_id"]]})
    if len(corrupted) > 4:
        duplicate = corrupted.iloc[[4]].copy()
        corrupted = pd.concat([corrupted, duplicate], ignore_index=True)
        log.append({"operation": "add_duplicate", "paper_ids": [str(duplicate.iloc[0]["paper_id"])]})
    corrupted["authors_joined"] = corrupted["authors"].apply(lambda x: ", ".join(x) if isinstance(x, list) else str(x or ""))
    corrupted["categories_joined"] = corrupted["categories"].apply(lambda x: ", ".join(x) if isinstance(x, list) else str(x or ""))
    corrupted["text_for_embedding"] = corrupted.apply(
        lambda row: f"Title: {row['title']} | Authors: {row['authors_joined']} | Summary: {row['summary']}", axis=1
    )
    path = Path(output_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    return corrupted.reset_index(drop=True)

if __name__ == "__main__":
    project_dir = Path(__file__).resolve().parents[2]
    clean_csv_path = project_dir / "data/clean/papers_clean.csv"
    corrupted_csv_path = project_dir / "data/corrupted/papers_corrupted.csv"
    log_path = project_dir / "data/corrupted/corruption_log.json"
    df_clean = pd.read_csv(clean_csv_path)
    df_corrupted = corrupt_clean_dataframe(df_clean, log_path)
    df_corrupted.to_csv(corrupted_csv_path, index=False)
    print(f"Wrote {len(df_corrupted)} corrupted records to {corrupted_csv_path}")