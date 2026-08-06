# Báo cáo cá nhân - Giang Trung Quân

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | Giang Trung Quân |
| MSSV | 2A202601098 |
| Khóa/Lớp | K4 |
| Tên nhóm | VinCourse |
| Vai trò | Role 2 - Data Modeling, Cleaning Contract & Evaluation Set |
| Repository | https://github.com/FrankLe2111/K4_Day10_2A202601590_LeNgoThanhToan |
| Ngày hoàn thành | 2026-08-06 |

---

## 2. Phạm vi công việc

| Module/deliverable | File/hàm phụ trách | Input | Output | Trạng thái |
|---|---|---|---|---|
| Data modeling | `src/ingestion/cleaning.py` | `list[PaperRecord]`, `run_date` | Clean DataFrame có schema ổn định | Hoàn thành |
| Text normalization | `_normalize_text()`, `_normalize_list()` | Raw title, summary, authors, categories | Chuỗi/lists đã chuẩn hóa, loại trùng theo lowercase | Hoàn thành |
| Date contract | `_parse_date()`, `_age_days()` | Date từ Crossref | `published`, `published_valid`, `published_date_precision`, `age_days` | Hoàn thành |
| Embedding text | `_embedding_text()` | Clean row | `text_for_embedding` dùng cho Chroma/vector search | Hoàn thành |
| Evaluation set | `src/evaluation/testset.py`, `build_test_set()` | Clean DataFrame | `data/eval/test_set.json` gồm câu hỏi có ground truth | Hoàn thành |
| Evidence contract | `_add_sample()`, `_non_empty()`, `_as_bool()` | Field sạch và hợp lệ | Sample chỉ được tạo khi có bằng chứng từ dữ liệu | Hoàn thành |

---

## 3. Kết quả bàn giao

- Clean dataset: `data/clean/papers_clean.csv` và `data/clean/papers_clean.json` gồm 24 paper hợp lệ.
- Clean schema phục vụ các bước sau: `paper_id`, `title`, `summary`, `authors_joined`, `categories_joined`, `published`, `published_valid`, `age_days`, `text_for_embedding`.
- Evaluation set: `data/eval/test_set.json` gồm 32 samples, sinh từ 8 paper đầu; mỗi paper tối đa 4 loại câu hỏi: `summary`, `authors`, `date`, `categories`.
- Baseline quality: `data/quality/baseline_quality.json` đạt `passed=true`, 24 rows, 24 unique IDs, không thiếu title/summary, không stale row.
- Baseline metrics: `retrieval_hit_rate=1.0000`, `mean_token_f1=1.0000`, `judge_accuracy=1.0000`, `mean_judge_score=5.0000`.
- Corrupted metrics giảm còn `retrieval_hit_rate=0.7500`, `mean_token_f1=0.3543`, `judge_accuracy=0.3125`, chứng minh evaluation set có thể phản ánh tác động của dữ liệu lỗi.

---

## 4. Vấn đề kỹ thuật và cách triển khai

### 4.1. Cleaning contract trong `cleaning.py`

`build_clean_dataframe()` nhận danh sách `PaperRecord` từ ingestion và chuyển thành DataFrame sạch. Contract chính:

1. Bỏ record thiếu `paper_id` hoặc `title` vì downstream cần document identity ổn định.
2. Khử trùng DOI theo lowercase để tránh cùng một paper xuất hiện nhiều lần trong index.
3. Chuẩn hóa `authors` và `categories` thành list không rỗng, không trùng lặp.
4. Giữ field optional ở dạng rỗng hoặc flag rõ ràng thay vì tự bịa dữ liệu.
5. Tạo thêm các cột theo dõi chất lượng như `summary_missing`, `authors_missing`, `categories_missing`, `summary_chars`, `published_missing`, `published_in_future`.

Điểm quan trọng là cleaning không chỉ làm đẹp dữ liệu, mà còn tạo contract cho retrieval, evaluation và observability.

### 4.2. Xử lý ngày xuất bản

`_parse_date()` hỗ trợ ba độ chính xác:

- `%Y-%m-%d` -> `day`
- `%Y-%m` -> `month`
- `%Y` -> `year`

Nếu ngày bị thiếu hoặc sai định dạng, hàm trả về `published=""`, `published_valid=false`, precision tương ứng là `missing` hoặc `invalid`. Nhóm không gán ngày hiện tại cho dữ liệu thiếu vì điều đó làm freshness report sai và có thể khiến RAG trả lời nhầm rằng paper mới hơn thực tế.

### 4.3. Tạo `text_for_embedding`

`_embedding_text()` ghép các field giàu ngữ nghĩa:

```text
Title: ...
Summary: ...
Authors: ...
Categories: ...
Venue: ...
Published: ...
```

Các phần rỗng được bỏ qua. Cách này giúp vector index nhận được context đủ rõ nhưng không bị nhiễu bởi metadata không cần thiết. `Published` chỉ được đưa vào khi `published_valid=true`, tránh embedding dữ liệu ngày không đáng tin.

### 4.4. Evaluation set có bằng chứng

`build_test_set()` chỉ tạo câu hỏi khi field nguồn thật sự tồn tại:

- Có `summary` mới tạo câu hỏi `summary`.
- Có `authors_joined` mới tạo câu hỏi `authors`.
- Có `published` và `published_valid=true` mới tạo câu hỏi `date`.
- Có `categories_joined` mới tạo câu hỏi `categories`.

Mỗi sample chứa `question`, `ground_truth` và `ground_truth_doc_ids`. Nhờ vậy retrieval metric có thể kiểm tra document đúng có nằm trong top-k hay không, còn answer metric có ground truth rõ ràng để so sánh.

---

## 5. Input/output contract

| Thành phần | Contract |
|---|---|
| Cleaning input | `list[PaperRecord]` từ `src/ingestion/crossref.py` |
| Cleaning output | `pd.DataFrame` đã chuẩn hóa, sắp xếp theo `published` giảm dần và `paper_id` tăng dần |
| Required fields cho eval | `paper_id`, `title`, `summary`, `authors_joined`, `categories_joined`, `published` |
| Evaluation output | `data/eval/test_set.json` |
| Evaluation sample schema | `id`, `question_type`, `question`, `ground_truth`, `ground_truth_doc_ids` |
| Downstream consumers | `src/retrieval/index.py`, `src/evaluation/metrics.py`, `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py` |

---

## 6. Verification

Các artifact hiện tại xác nhận phần Role 2 hoạt động đúng:

```json
{
  "baseline_samples": 32,
  "baseline_retrieval_hit_rate": 1.0,
  "baseline_mean_token_f1": 1.0,
  "baseline_judge_accuracy": 1.0,
  "baseline_mean_judge_score": 5,
  "clean_rows": 24,
  "unique_ids": 24,
  "baseline_quality_passed": true,
  "freshness_is_fresh": true
}
```

Các lệnh kiểm tra phù hợp với phần việc:

```bash
python -m compileall -q src script app.py
USE_LLM_EVAL=0 python script/run_phase1.py
USE_LLM_EVAL=0 python script/run_corruption_flow.py
```

Lưu ý: metrics hiện tại dùng fallback local (`llm_answer_count=0`, `fallback_answer_count=32`) để đảm bảo pipeline reproducible khi API LLM không sẵn sàng. Vì vậy baseline 1.0 là kết quả kiểm tra pipeline/evidence contract, không được claim là chất lượng generation thật của LLM.

---

## 7. Quyết định kỹ thuật quan trọng

### 7.1. Không tạo evaluation question từ dữ liệu thiếu

Nếu test set sinh câu hỏi cho field thiếu, hệ thống có thể được thưởng vì đoán đúng dữ liệu không có thật. Vì vậy `build_test_set()` dùng `_non_empty()` và `_as_bool()` để chỉ tạo sample từ dữ liệu có bằng chứng. Quyết định này làm số lượng câu hỏi phụ thuộc vào chất lượng clean data, nhưng đổi lại metric trung thực hơn.

### 7.2. Dùng first sentence làm ground truth cho summary

Với câu hỏi summary, `ground_truth` lấy từ `first_sentence(summary)`. Cách này giúp ground truth ngắn, dễ so sánh bằng token F1, và vẫn bám vào nội dung thật của paper. Nếu dùng toàn bộ abstract dài, metric dễ bị phạt vì answer ngắn hơn dù đúng ý chính.

### 7.3. Giữ `ground_truth_doc_ids` theo DOI

Mỗi sample giữ `ground_truth_doc_ids` là `paper_id`/DOI. Đây là cầu nối giữa test set và retriever: retrieval hit rate không chỉ đo câu trả lời, mà còn kiểm tra xem hệ thống có lấy đúng tài liệu nguồn hay không.

---

## 8. Lỗi đã xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Evaluation set có thể quá nhỏ | Clean data thiếu field cần thiết | `build_test_set()` raise `ValueError` nếu có dưới 4 samples |
| Câu hỏi date dùng ngày không hợp lệ | Raw date thiếu hoặc sai format | Chỉ tạo date question khi `published_valid=true` |
| `NaN` bị biến thành chuỗi `"nan"` | Pandas lưu giá trị thiếu dưới dạng float NaN | `_non_empty()` và `_as_bool()` xử lý NaN trước khi convert |
| Duplicate paper làm lệch index/eval | DOI lặp trong raw hoặc corrupted data | Cleaning dùng `seen_ids` theo lowercase để giữ document identity duy nhất |
| Embedding bị nhiễu field rỗng | Metadata optional không phải paper nào cũng có | `_embedding_text()` chỉ ghép phần có nội dung |

---

## 9. Phân tích metrics

| Metric / Signal | Baseline | Corrupted | Repaired | Phân tích |
|---|---:|---:|---:|---|
| `samples` | 32 | 32 | 32 | Cùng test set được dùng để so sánh công bằng |
| `retrieval_hit_rate` | 1.0000 | 0.7500 | 1.0000 | Corruption làm mất hoặc nhiễu context; repair khôi phục document match |
| `mean_token_f1` | 1.0000 | 0.3543 | 1.0000 | Khi summary/date/identity bị lỗi, answer lệch ground truth |
| `judge_accuracy` | 1.0000 | 0.3125 | 1.0000 | Judge phản ánh chất lượng answer giảm mạnh sau corruption |
| Quality | PASS | FAIL | PASS | Clean contract và quality checks phát hiện duplicate, summary ngắn, stale date |
| Freshness | Fresh | Stale | Fresh | Date contract giúp phát hiện dữ liệu cũ bất thường |

Kết quả này cho thấy phần Role 2 ảnh hưởng trực tiếp đến độ tin cậy của RAG: schema sạch và evaluation set có bằng chứng giúp phát hiện rõ khi dữ liệu bị hỏng, đồng thời xác nhận repair đã đưa hệ thống về trạng thái baseline.

---

## 10. Hiểu biết end-to-end

1. Crossref ingestion tạo `PaperRecord` và raw artifacts.
2. Role 2 chuyển raw records thành clean DataFrame, chuẩn hóa text/list/date, tạo `text_for_embedding`.
3. Clean dataset được lưu thành CSV/JSON và được dùng để build embedding, Chroma index và test set.
4. Test set giữ câu hỏi, ground truth và DOI nguồn để evaluation đo cả retrieval lẫn answer quality.
5. Observability đọc clean/corrupted/repaired data để kiểm tra row count, uniqueness, summary length và freshness.
6. Corruption flow làm hỏng dữ liệu, chạy lại evaluation, sau đó repair từ raw snapshot.
7. Metrics baseline/corrupted/repaired chứng minh cùng một evaluation set có thể phát hiện degradation và xác nhận phục hồi.

---

## 11. Bài học và hướng cải thiện

- Evaluation tốt phải bắt đầu từ dữ liệu sạch và ground truth có nguồn rõ ràng.
- Không nên tự bịa fallback cho ngày tháng hoặc metadata vì có thể làm sai freshness và làm RAG hallucinate.
- `text_for_embedding` cần đủ ngữ nghĩa nhưng không nên nhồi quá nhiều metadata gây nhiễu vector search.
- Có thể mở rộng test set bằng cách chọn paper đa dạng hơn thay vì chỉ `df.head(8)`.
- Nên thêm câu hỏi kiểm tra DOI/citation và câu hỏi multi-hop để đánh giá RAG sâu hơn.
- Khi có quota LLM ổn định, nên chạy lại với `USE_LLM_EVAL=1` và `RUN_RAGAS=1` để đo faithfulness/context precision.

---

## 12. Cam kết

- [x] Nội dung báo cáo dựa trên code và artifact hiện có trong repository.
- [x] Báo cáo mô tả đúng phạm vi Role 2, không nhận nhầm ownership của ingestion API, observability hay pipeline integration.
- [x] Số liệu baseline/corrupted/repaired lấy từ artifact thực tế.
- [x] Không đưa API key, token hoặc secret vào report.
- [x] Hiểu luồng end-to-end và vai trò của clean schema/evaluation set trong RAG observability.

**Họ và tên:** Giang Trung Quân<br>
**MSSV:** 2A202601098<br>
**Ngày xác nhận:** 2026-08-06
