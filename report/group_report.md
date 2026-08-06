# Báo cáo nhóm – Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Trường | Nội dung |
|---|---|
| Khóa/Lớp | K4 |
| Nhóm | VinCourse |
| Repository | [FrankLe2111/K4_Day10_2A202601590_LeNgoThanhToan](https://github.com/FrankLe2111/K4_Day10_2A202601590_LeNgoThanhToan) |
| Ngày hoàn thành | 2026-08-06 |

| Thành viên | MSSV | Vai trò |
|---|---|---|
| Nguyễn Đức Hưng | 2A202601936 | Crossref ingestion, raw data |
| Giang Trung Quân | 2A202601098 | Cleaning, data model, evaluation set |
| Lê Ngô Thanh Toàn | 2A202601590 | Observability, reports, integration |
| Tạ Thị Thu Huyền | 2A202601782 | Retrieval, corruption, repair |

## 2. Tóm tắt

Nhóm đã hoàn thành pipeline RAG end-to-end trên metadata bài báo khoa học từ Crossref. Pipeline gọi API có retry/backoff, lưu raw response để audit, parse về `PaperRecord`, làm sạch dữ liệu, tạo embedding bằng `all-MiniLM-L6-v2`, lưu index ChromaDB, đánh giá retrieval/answer quality và tạo quality/freshness reports. Baseline hiện có 24 documents sạch và 32 evaluation samples. Tất cả quality checks baseline đều PASS: không thiếu ID, không duplicate, title hợp lệ, summary tối thiểu 100 ký tự và không có record stale. Khi inject corruption, quality chuyển FAIL và metrics giảm: retrieval hit rate từ 1.0 xuống 0.75, Token F1 từ 1.0 xuống 0.3543, judge accuracy từ 1.0 xuống 0.3125. Repair bằng cách rebuild từ raw snapshot phục hồi toàn bộ các metrics về baseline. Artifact reproducible hiện dùng local fallback (`USE_LLM_EVAL=0`) vì OpenAI API không ổn định; limitation này được ghi rõ, không coi fallback là kết quả LLM thật.

## 3. Kiến trúc và luồng dữ liệu

```text
Crossref API -> raw response/records -> cleaning -> clean CSV/JSON
    -> MiniLM embeddings + ChromaDB -> evaluation -> quality/freshness
    -> corruption -> corrupted evaluation -> repair from raw
    -> repaired evaluation -> comparison report
```

| Khối | Xử lý | Artifact | Owner |
|---|---|---|---|
| Ingestion | Query, filter, retry, parse DOI/title/abstract/authors/dates | `data/raw/` | Nguyễn Đức Hưng |
| Cleaning | Remove XML, validate, deduplicate, build semantic text | `data/clean/` | Giang Trung Quân |
| Embedding/index | MiniLM 384 chiều, Chroma cosine search, top-k=4 | `data/embeddings/` | Tạ Thị Thu Huyền |
| Evaluation | Test set, retrieval hit, Token F1, judge | `data/eval/`, `data/results/` | Giang Trung Quân, Lê Ngô Thanh Toàn |
| Observability | Completeness, uniqueness, summary validity, freshness | `data/quality/` | Lê Ngô Thanh Toàn |
| Corruption/repair | Inject lỗi, re-index, rebuild từ raw, compare | `data/results/`, `data/reports/` | Tạ Thị Thu Huyền |
| UI | Overview, search, Ask RAG, evaluation, data explorer | `app.py` | Lê Ngô Thanh Toàn |

## 4. Cấu hình và tái hiện

| Thành phần | Giá trị |
|---|---|
| Source | `https://api.crossref.org/works` |
| Query | `agentic retrieval augmented generation large language model` |
| Max results | 24 |
| Embedding | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector store | ChromaDB, cosine |
| `top_k` | 4 |
| Freshness threshold | 180 ngày |
| LLM | OpenAI `gpt-4o-mini` |
| Artifact run | `USE_LLM_EVAL=0` local fallback |

Không ghi API key vào report. Lệnh chạy:

```bash
cd /home/aic/K4_Day10_2A202601590_LeNgoThanhToan
source .venv/bin/activate
python -m pip install -e .
USE_LLM_EVAL=0 python script/run_phase1.py
USE_LLM_EVAL=0 python script/run_corruption_flow.py
streamlit run app.py
```

## 5. Ingestion và cleaning contract

`paper_id` là DOI ổn định và là document ID. Record thiếu DOI/title hoặc summary sau cleaning dưới 100 ký tự bị loại. Abstract ưu tiên `abstract`, fallback `description`. XML/HTML bị loại khỏi text. Authors/categories được flatten thành `authors_joined`/`categories_joined`. Published date chuyển thành `YYYY-MM-DD`; `age_days` được tính từ ngày chạy pipeline.

`text_for_embedding`:

```text
Title: [title] | Authors: [authors_joined] | Summary: [summary]
```

Crossref retry các status `429`, `502`, `503`, `504` bằng exponential backoff. Raw response được lưu trước khi parse để có thể audit/repair.

## 6. Evaluation setup

| Thành phần | Cấu hình |
|---|---|
| Clean documents | 24 |
| Evaluation samples | 32 |
| Question types | `summary`, `authors`, `date`, `categories` |
| Ground truth | DOI trong `ground_truth_doc_ids` |
| Test set | `data/eval/test_set.json` |
| Retrieval | ChromaDB, top-k 4 |
| Answer mode hiện tại | local deterministic fallback |
| Ragas | Chưa chạy; bật bằng `RUN_RAGAS=1` |

Cùng một test set được dùng ở cả ba state để chênh lệch metrics chỉ phản ánh chất lượng dữ liệu/index, không phản ánh thay đổi câu hỏi.

## 7. Artifact checklist

| Artifact | Trạng thái |
|---|---|
| Raw response/records | Có – `data/raw/` |
| Clean CSV/JSON | Có – `data/clean/` |
| Embedding manifest | Có – `data/embeddings/papers_embeddings.json` |
| Evaluation set | Có – `data/eval/test_set.json` |
| Baseline metrics/answers | Có – `data/results/baseline_*.json` |
| Corrupted metrics/answers | Có – `data/results/corrupted_*.json` |
| Repaired metrics/answers | Có – `data/results/repaired_*.json` |
| Quality/freshness | Có – `data/quality/` |
| Reports | Có – `data/reports/` |
| Demo UI | Có – `app.py` |

## 8. Baseline metrics

| Metric | Giá trị | Ý nghĩa |
|---|---:|---|
| Samples | 32 | Số evaluation samples |
| `llm_answer_count` | 0 | Run reproducible không gọi API |
| `fallback_answer_count` | 32 | Local fallback |
| `retrieval_hit_rate` | 1.0000 | Ground truth luôn nằm trong top-k |
| `mean_token_f1` | 1.0000 | Fallback khớp reference metadata |
| `judge_accuracy` | 1.0000 | Heuristic judge |
| `mean_judge_score` | 5.0000 | Heuristic judge |
| Ragas | Skipped | Chưa bật |

> Baseline 1.0 là kết quả fallback deterministic, không phải bằng chứng LLM đạt tuyệt đối. Chạy `USE_LLM_EVAL=1` khi provider sẵn sàng để đánh giá generation thật.

## 9. Quality và freshness

Baseline: 24 rows, 0 null IDs, 0 duplicate IDs, 0 blank titles, 0 summary dưới 100 chars, 0 stale rows; tất cả checks PASS. Freshness: latest `2026-08-05`, oldest `2026-02-12`, threshold 180 ngày, `is_fresh=true`.

| State | Rows | Quality | Freshness | Chi tiết |
|---|---:|---|---|---|
| Baseline | 24 | PASS | Fresh | Tất cả checks đạt |
| Corrupted | 23 | FAIL | Stale | duplicate=1, short summary=1, stale=1 |
| Repaired | 24 | PASS | Fresh | Tất cả checks phục hồi |

## 10. Corruption và repair

| Corruption | Quality signal | Repair |
|---|---|---|
| Drop latest records | Row count giảm, freshness đổi | Rebuild từ raw |
| Blank summary | `summary_has_content` FAIL | Lấy summary raw |
| Truncate title | Mất thông tin title/context | Lấy title raw |
| Inject summary noise | Semantic/answer quality giảm | Rebuild text + embedding |
| Stale date `2000-01-01` | Freshness FAIL | Lấy published raw |
| Duplicate row | `paper_id_unique` FAIL | Deduplicate lại |

Repair không sửa metrics bằng tay; nó đọc `data/raw/crossref_records.json`, chạy lại cleaning và build index.

## 11. Comparison và kết luận nhân quả

| Metric | Baseline | Corrupted | Repaired |
|---|---:|---:|---:|
| `retrieval_hit_rate` | 1.0000 | 0.7500 | 1.0000 |
| `mean_token_f1` | 1.0000 | 0.3543 | 1.0000 |
| `judge_accuracy` | 1.0000 | 0.3125 | 1.0000 |
| `mean_judge_score` | 5.0000 | 2.1875 | 5.0000 |
| Quality | PASS | FAIL | PASS |
| Freshness | Fresh | Stale | Fresh |

1. Corruption làm duplicate/summary/date lỗi → quality và freshness FAIL → retrieval hit giảm 25 điểm phần trăm, judge accuracy giảm 68.75 điểm phần trăm.
2. Repair từ raw snapshot → uniqueness, summary và freshness PASS → retrieval và answer metrics phục hồi hoàn toàn.

## 12. Lỗi tích hợp đã xử lý

- `Settings()` thiếu arguments: thay bằng `load_settings()`.
- JSON Unicode dạng `\\u0421...`: dùng `ensure_ascii=False`.
- Category rỗng thành `"nan"`: lọc NaN khi tạo test set.
- Test set stale sau refresh: rebuild khi `REFRESH_SOURCE=1`.
- Gemini/OpenAI quota: thêm OpenAI config và fallback `USE_LLM_EVAL=0`.
- UI thiếu Chroma binary: tự rebuild index từ clean CSV.

## 13. Giới hạn và hướng cải thiện

Dataset hiện có 24 papers nên chưa đại diện corpus lớn; ground truth sinh tự động chưa được chuyên gia kiểm duyệt; Ragas chưa chạy; artifact metrics hiện là fallback. Cải thiện tiếp theo là tăng số papers, review test set, chạy `RUN_RAGAS=1`, chạy lại với `USE_LLM_EVAL=1` và thêm citation DOI vào câu trả lời LLM.

## 14. Kết luận

Pipeline đã hoàn thành ingestion, cleaning, indexing, retrieval, evaluation, observability, corruption, repair và UI. Baseline đạt quality/freshness PASS; corruption làm cả data checks và RAG metrics suy giảm; repair từ raw snapshot phục hồi chúng. Kết quả chứng minh data quality là yếu tố trực tiếp quyết định độ tin cậy của RAG.
