# Báo cáo cá nhân – Lê Ngô Thanh Toàn

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | Lê Ngô Thanh Toàn |
| MSSV | 2A202601590 |
| Khóa/Lớp | K4 |
| Tên nhóm | VinCourse |
| Vai trò | Observability và pipeline integration |
| Repository | [FrankLe2111/K4_Day10_2A202601590_LeNgoThanhToan](https://github.com/FrankLe2111/K4_Day10_2A202601590_LeNgoThanhToan) |
| Ngày hoàn thành | 2026-08-06 |

## 2. Phạm vi công việc

| Module/deliverable | File/hàm | Input | Output | Trạng thái |
|---|---|---|---|---|
| Data quality | `src/observability/quality.py` | Clean/corrupted/repaired DataFrame | Quality JSON | Hoàn thành |
| Freshness | `build_freshness_report()` | `published`, `age_days` | Freshness JSON | Hoàn thành |
| Reporting | `src/observability/reporting.py` | Metrics, quality, freshness | Markdown reports | Hoàn thành |
| Baseline integration | `src/pipelines/phase1.py` | Settings, raw records | Clean/index/eval/report | Hoàn thành |
| Corruption integration | `src/pipelines/corruption_flow.py` | Clean data, raw snapshot | Corrupted/repaired comparison | Hoàn thành |
| UI demo | `app.py` | Project artifacts | Streamlit dashboard | Hoàn thành |

## 3. Kết quả bàn giao

- Baseline quality: `data/quality/baseline_quality.json` – tất cả checks PASS.
- Baseline freshness: `data/quality/freshness_report.json` – `is_fresh=true`.
- Corrupted quality: duplicate, short summary và stale date được phát hiện.
- Repaired quality: tất cả checks trở lại PASS.
- Baseline report: `data/reports/phase1_report.md`.
- Comparison report: `data/reports/corruption_report.md`.
- Dashboard: `app.py` với Overview, Search, Ask RAG, Evaluation và Clean Data.

## 4. Vấn đề kỹ thuật và cách triển khai

### 4.1. Quality checks

`run_data_quality_checks()` kiểm tra:

1. Row count > 0.
2. `paper_id` không null.
3. `paper_id` unique.
4. Title không rỗng.
5. Summary tối thiểu 100 ký tự.
6. Không có row quá freshness threshold.

Mỗi check trả về `name`, `passed` và `details`, giúp report có thể audit nguyên nhân PASS/FAIL thay vì chỉ có một boolean tổng hợp.

### 4.2. Freshness

`build_freshness_report()` tính:

- Published date mới nhất.
- Published date cũ nhất.
- Số stale rows.
- Tổng số rows.
- Threshold 180 ngày.
- `is_fresh`.

Baseline có latest `2026-08-05`, oldest `2026-02-12`, stale rows `0`. Corrupted có oldest `2000-01-01`, stale rows `1`, nên freshness FAIL. Repaired đọc lại ngày từ raw và trở lại FRESH.

### 4.3. Pipeline orchestration

Baseline flow:

```text
load_settings
    -> load/fetch raw records
    -> build_clean_dataframe
    -> save clean CSV/JSON
    -> build Chroma index
    -> create/load test set
    -> evaluate
    -> quality/freshness
    -> phase1 report
```

Corruption flow:

```text
load clean baseline
    -> corrupt dataframe
    -> evaluate corrupted
    -> quality/freshness corrupted
    -> rebuild clean dataframe from raw
    -> evaluate repaired
    -> quality/freshness repaired
    -> comparison report
```

Đã thêm guard để dừng pipeline nếu cleaning tạo zero records và tự rebuild evaluation set khi source được refresh, tránh test set chứa document ID không còn tồn tại.

## 5. Input/output contract

| Thành phần | Contract |
|---|---|
| Input raw | `data/raw/crossref_records.json` hoặc Crossref API |
| Clean input | `paper_id`, `title`, `summary`, `published`, `authors`, `categories` |
| Evaluation input | `data/eval/test_set.json`, cùng test set cho ba trạng thái |
| Metrics output | `baseline_metrics.json`, `corrupted_metrics.json`, `repaired_metrics.json` |
| Quality output | `<state>_quality.json` |
| Freshness output | `<state>_freshness_report.json` |
| Report output | `phase1_report.md`, `corruption_report.md` |

## 6. Verification

Các lệnh đã chạy:

```bash
USE_LLM_EVAL=0 python script/run_phase1.py
USE_LLM_EVAL=0 python script/run_corruption_flow.py
python src/observability/quality.py --state corrupted
python -m compileall -q src script app.py
streamlit run app.py
```

Kết quả quality corrupted:

```text
row_count: PASS
paper_id_not_null: PASS
paper_id_unique: FAIL (duplicate_rows=1)
title_not_blank: PASS
summary_has_content: FAIL (short_or_blank_rows=1)
freshness: FAIL (stale_rows=1)
```

## 7. Quyết định kỹ thuật quan trọng

### Chọn raw snapshot làm nguồn repair

Có hai cách sửa corrupted dataset:

1. Sửa trực tiếp các dòng lỗi trong corrupted CSV.
2. Đọc lại raw records rồi chạy lại cleaning.

Nhóm chọn cách 2 vì raw snapshot là nguồn có khả năng audit và không bị corruption. Cách này tránh việc repair chỉ che lỗi, đồng thời kiểm chứng được pipeline có thể tái tạo clean dataset. Bằng chứng là repaired có 24 rows, unique IDs, summary hợp lệ, freshness PASS và metrics trở về baseline.

### Chọn fallback khi LLM không khả dụng

OpenAI/Gemini có thể hết quota hoặc timeout. Nếu để pipeline phụ thuộc hoàn toàn vào API, không thể tạo artifacts reproducible. Vì vậy thêm `USE_LLM_EVAL=0`: answer lấy từ retrieved metadata và judge dùng heuristic. Báo cáo ghi rõ `llm_answer_count=0`, không claim đây là kết quả LLM thật. Khi provider sẵn sàng, chạy `USE_LLM_EVAL=1` để đánh giá generation thật.

## 8. Lỗi đã xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `Settings.__init__()` thiếu arguments | Gọi trực tiếp dataclass | Dùng `load_settings()` |
| `\\u0421...` trong test set | JSON escape Unicode | `ensure_ascii=False` |
| Category là `nan` | Pandas NaN bị cast thành string | `_cell_text()` bỏ NaN |
| Test set ID không khớp data mới | Không rebuild khi refresh source | Rebuild theo `refresh_source` |
| OpenAI/Gemini 429 hoặc timeout | Provider quota/network | Fallback evaluation |
| UI hiển thị metric `None` | Thiếu corrupted/repaired JSON | Chạy corruption flow và commit artifacts |

## 9. Phân tích metrics

| Metric | Baseline | Corrupted | Repaired | Phân tích |
|---|---:|---:|---:|---|
| `retrieval_hit_rate` | 1.0000 | 0.7500 | 1.0000 | Corruption làm mất/nhiễu context; repair phục hồi |
| `mean_token_f1` | 1.0000 | 0.3543 | 1.0000 | Context hỏng làm đáp án kém tương đồng |
| `judge_accuracy` | 1.0000 | 0.3125 | 1.0000 | Judge phản ánh answer quality giảm |
| `mean_judge_score` | 5.0000 | 2.1875 | 5.0000 | Giảm 2.8125 điểm rồi phục hồi |
| Quality | PASS | FAIL | PASS | Data checks phát hiện lỗi |
| Freshness | Fresh | Stale | Fresh | Stale date được phát hiện |

`retrieval_hit_rate` đo retriever/vector search: ground-truth document có nằm trong top-k hay không. Retrieval đúng không bảo đảm LLM trả lời đúng. Token F1 có thể thấp hơn 1 vì câu trả lời sinh ra có thể paraphrase, thêm/bớt từ hoặc khác reference.

Lưu ý: các artifact hiện tại dùng fallback local nên baseline đạt 1.0 không đại diện cho LLM generation. Đây là một điểm cần ghi rõ để báo cáo trung thực.

## 10. Hiểu biết end-to-end

1. Crossref trả metadata; ingestion lưu raw và flatten thành `PaperRecord`.
2. Cleaning validate title/summary, chuẩn hóa date/authors/categories và tạo semantic text.
3. MiniLM biến text thành vector; ChromaDB dùng vector để retrieve top-k documents.
4. Evaluation set giữ question, answer reference và ground-truth DOI. Retrieval hit kiểm tra document đúng có được lấy không; Token F1/judge kiểm tra answer.
5. Quality checks kiểm tra cấu trúc/nội dung dataset; freshness theo dõi tuổi published date. Hai nhóm signal khác nhau nhưng bổ trợ nhau.
6. Cùng một test set phải được dùng cho baseline/corrupted/repaired để comparison công bằng.
7. Repair thành công khi raw-derived clean data khôi phục quality/freshness và metrics về mức baseline.

## 11. Bài học và hướng cải thiện

- Data quality là một phần của correctness RAG, không chỉ là kiểm tra ETL.
- Raw snapshot giúp audit và repair deterministic.
- Retrieval hit cao nhưng answer quality vẫn cần đánh giá riêng.
- Cần chạy thêm `RUN_RAGAS=1` để đo faithfulness, context precision và context recall.
- Nên tăng dataset, review ground truth thủ công và chạy lại với `USE_LLM_EVAL=1` khi OpenAI ổn định.
- Có thể thêm citation DOI vào answer để tăng khả năng kiểm chứng.

## 12. Cam kết

- [x] Nội dung báo cáo dựa trên artifact và metrics thực tế.
- [x] Baseline/corrupted/repaired dùng cùng evaluation set.
- [x] Không đưa API key hoặc secret vào report.
- [x] Đã kiểm tra compile và chạy end-to-end pipeline.

**Họ và tên:** Lê Ngô Thanh Toàn<br>
**MSSV:** 2A202601590<br>
**Ngày xác nhận:** 2026-08-06
