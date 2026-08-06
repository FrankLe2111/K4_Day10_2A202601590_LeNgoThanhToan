# Group Report — Day 10: Data Pipeline & Data Observability

> Dùng mẫu này cho báo cáo chung của nhóm 3–5 thành viên. Thay toàn bộ nội dung trong dấu `[ ]` bằng thông tin và kết quả thực tế. Xóa các dòng hướng dẫn không còn cần thiết trước khi nộp.

## 1. Thông tin bài nộp

| Thông tin         | Nội dung                  |
| ------------------ | -------------------------- |
| Khóa/Lớp         | [K4]              |
| Tên nhóm         | [VinCourse]     |
| Repository         | [https://github.com/FrankLe2111/K4_Day10_2A202601590_LeNgoThanhToan] |
| Ngày hoàn thành | [2026-08-06]               |

### Thành viên và phân công

| STT | Họ và tên | MSSV | Vai trò chính | Module/deliverable sở hữu |
| --: | --- | --- | --- | --- |
| 1 | Nguyễn Đức Hưng | 2A202601936 | Role 1 - Source owner | `src/ingestion/crossref.py`; raw response, raw records và schema đầu vào |
| 2 | Giang Trung Quân | 2A202601098 | Role 2 - Data model & evaluation-set owner | `src/ingestion/cleaning.py`, `src/evaluation/testset.py`; cleaned dataset, `text_for_embedding` và evaluation set |
| 3 | Lê Ngô Thanh Toàn | 2A202601590 | Role 3 - Observability owner | `src/observability/quality.py`, `src/observability/reporting.py`; quality checks, freshness và Markdown reports |
| 4 | Tạ Thị Thu Huyền | 2A202601782 | Role 4 - Corruption & integration owner | `src/ingestion/corruption.py`, `src/pipelines/phase1.py`, `src/pipelines/corruption_flow.py`; baseline/corrupted/repaired flow và metrics so sánh |

## 2. Tóm tắt kết quả

Viết từ 150–250 từ, trả lời ngắn gọn:

- Nhóm đã hoàn thành những phần nào?
- Baseline pipeline đã tạo ra các artifact nào?
- Corruption nào ảnh hưởng rõ nhất đến data quality hoặc agent?
- Repair đã phục hồi được chỉ số nào?
- Blocker hoặc giới hạn quan trọng nhất còn lại là gì?

**Tóm tắt của nhóm:**

[Viết phần tóm tắt tại đây.]

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

Điều chỉnh sơ đồ dưới đây nếu cách triển khai thực tế của nhóm khác starter:

```text
Crossref API
    -> raw response/raw records
    -> cleaning và data modeling
    -> embedding + ChromaDB index
    -> evaluation baseline
    -> quality/freshness reports
    -> corruption
    -> re-index và re-evaluate
    -> repair từ dữ liệu nguồn
    -> comparison report
```

### Trách nhiệm của từng khối

| Khối             | Input          | Xử lý chính             | Output/artifact          | Owner          |
| ----------------- | -------------- | -------------------------- | ------------------------ | -------------- |
| Ingestion         | Crossref API | Fetch, retry, parse payload, lưu raw response/raw records | `data/raw/` | Nguyễn Đức Hưng |
| Cleaning          | Raw records trong `data/raw/` | Chuẩn hóa schema, loại record lỗi, deduplicate, tạo `text_for_embedding`, tính `age_days` | `data/clean/` | Giang Trung Quân |
| Embedding/index   | Cleaned dataset | Dùng MiniLM và ChromaDB để tạo vector index | `data/embeddings/` | Tạ Thị Thu Huyền |
| Evaluation        | Cleaned dataset và vector index | Tạo test set, chạy evaluator và tính metrics | `data/eval/`, `data/results/` | Giang Trung Quân, Tạ Thị Thu Huyền |
| Observability     | Clean/corrupted/repaired datasets và metrics | Quality checks, freshness monitoring, tạo Markdown reports | `data/quality/`, `data/reports/` | Lê Ngô Thanh Toàn |
| Corruption/repair | Baseline cleaned dataset và raw records | Tạo data corruption, rebuild index, evaluate, repair từ raw/source và so sánh | `data/results/corruption_log.json`, corrupted/repaired metrics, comparison report | Tạ Thị Thu Huyền |
| Orchestration     | Output của tất cả module | Ghép `phase1.py`, `corruption_flow.py`, chạy entrypoint và kiểm tra artifact | `data/reports/phase1_report.md`, `data/reports/corruption_report.md` | Tạ Thị Thu Huyền |

### Contract checkpoint 1 cần chốt

Tại thời điểm checkpoint 1, nhóm mới bắt đầu triển khai nên các schema dưới đây là contract dự kiến để các role cùng bám theo. Nhóm sẽ cập nhật lại nếu code thực tế hoặc dữ liệu Crossref yêu cầu thay đổi.

| Contract | Quy ước dự kiến |
| --- | --- |
| Raw schema | Mỗi paper record có `paper_id`, `title`, `summary`, `authors`, `categories`, `primary_category`, `published`, `published_source`, `published_date_precision`, `updated`, `updated_source`, `updated_date_precision`, `abs_url`, `pdf_url`, `comment` |
| Clean schema | Giữ các trường chính từ raw, chuẩn hóa kiểu dữ liệu, thêm `text_for_embedding`, `age_days`, các cờ tracking như `published_valid`, `published_missing`, `published_in_future`; loại record không có `paper_id` hoặc `title` |
| Document identity | Dùng `paper_id` từ Crossref DOI làm document ID chính; không tự tạo ID từ title/date nếu thiếu DOI ở bước ingestion hiện tại |
| Evaluation set | Mỗi sample có `question`, `ground_truth`, `ground_truth_doc_ids`, `question_type`; tất cả `ground_truth_doc_ids` phải tồn tại trong cleaned dataset |
| Artifact paths | Dùng đúng paths trong `src/core/config.py`: `data/raw/`, `data/clean/`, `data/eval/`, `data/results/`, `data/quality/`, `data/reports/` |
| Metrics | Giữ cùng `retrieval_hit_rate`, `mean_token_f1`, `judge_accuracy`, `mean_judge_score` cho baseline/corrupted/repaired |
| Repair | Repair bằng cách rebuild từ raw records/source đáng tin cậy, không sửa tay metrics hoặc answers |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình             | Giá trị sử dụng |
| ---------------------------- | ------------------- |
| `LLM_PROVIDER`             | [Giá trị]         |
| `LLM_MODEL`                | [Giá trị]         |
| Embedding model              | [Giá trị]         |
| Số lượng Crossref records | [Giá trị]         |
| Retrieval`top_k`           | [Giá trị]         |
| Freshness threshold          | [Giá trị]         |
| Random seed, nếu có        | [Giá trị]         |

Không dán nội dung API key hoặc file `.env` vào báo cáo.

### Lệnh cài đặt

Chỉ giữ lại cách nhóm đã dùng.

```bash
uv sync
```

Hoặc:

```bash
python -m pip install -e .
```

### Lệnh chạy

Baseline:

```bash
uv run python script/run_phase1.py
```

Hoặc với môi trường `pip` đã kích hoạt:

```bash
python script/run_phase1.py
```

Corruption flow:

```bash
uv run python script/run_corruption_flow.py
```

Hoặc với môi trường `pip` đã kích hoạt:

```bash
python script/run_corruption_flow.py
```

### Kết quả tái hiện

| Lệnh             | Trạng thái                                    | Thời điểm chạy gần nhất | Bằng chứng                         |
| ----------------- | ----------------------------------------------- | ----------------------------- | ------------------------------------ |
| Baseline pipeline | [Thành công/Thất bại một phần/Thất bại] | [Thời gian]                  | [Artifact hoặc log đã che secret] |
| Corruption flow   | [Thành công/Thất bại một phần/Thất bại] | [Thời gian]                  | [Artifact hoặc log đã che secret] |

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính                | Giá trị                             |
| --------------------------- | ------------------------------------- |
| Source                      | [Crossref endpoint/dataset thực tế] |
| Query/filter                | [Query hoặc filter]                  |
| Thời điểm lấy dữ liệu | [Timestamp]                           |
| Số record nhận được    | [Số lượng]                         |
| Cơ chế retry/backoff      | [Mô tả ngắn]                       |

### Raw và clean schema

| Trường        | Kiểu dữ liệu | Bắt buộc?  | Ý nghĩa   | Xử lý khi thiếu/sai |
| --------------- | --------------- | ------------ | ----------- | ---------------------- |
| [Tên trường] | [Kiểu]         | [Có/Không] | [Ý nghĩa] | [Cách xử lý]        |
| [Tên trường] | [Kiểu]         | [Có/Không] | [Ý nghĩa] | [Cách xử lý]        |

### Quy tắc cleaning

| Quy tắc                                 | Quality dimension liên quan | Số record bị tác động | Cách xác minh      |
| ---------------------------------------- | ---------------------------- | -------------------------: | -------------------- |
| [Ví dụ: loại record không có title] | [Completeness/Validity/...]  |              [Số lượng] | [Artifact/kiểm tra] |
| [Quy tắc thực tế]                     | [Dimension]                  |              [Số lượng] | [Artifact/kiểm tra] |

Giải thích cách nhóm tạo `text_for_embedding`, document ID và `age_days`:

[Mô tả tại đây.]

## 6. Evaluation setup

| Thành phần                             | Cấu hình thực tế          |
| ---------------------------------------- | ----------------------------- |
| Số câu hỏi                            | [Số lượng]                 |
| Các`question_type`                    | [Danh sách]                  |
| Ground-truth document ID                 | [Cách tạo/đối chiếu]     |
| Embedding model                          | [Tên model]                  |
| Vector store/collection                  | [Tên/config]                 |
| Retrieval`top_k`                       | [Giá trị]                   |
| LLM provider/model                       | [Giá trị]                   |
| Test set dùng chung cho ba trạng thái | [Đường dẫn hoặc ID/hash] |

Giải thích vì sao test set được giữ nguyên khi đánh giá baseline, corrupted và repaired:

[Giải thích tại đây.]

## 7. Kết quả baseline

### Artifact checklist

| Artifact                 | Đường dẫn thực tế                | Trạng thái | Ghi chú   |
| ------------------------ | -------------------------------------- | ------------ | ---------- |
| Raw response/records     | `data/raw/`                          | [Có/Thiếu] | [Ghi chú] |
| Cleaned dataset          | `data/clean/`                        | [Có/Thiếu] | [Ghi chú] |
| Embedding manifest/index | `data/embeddings/`                   | [Có/Thiếu] | [Ghi chú] |
| Evaluation set           | `data/eval/`                         | [Có/Thiếu] | [Ghi chú] |
| Baseline metrics         | `data/results/baseline_metrics.json` | [Có/Thiếu] | [Ghi chú] |
| Quality/freshness        | `data/quality/`                      | [Có/Thiếu] | [Ghi chú] |
| Baseline report          | `data/reports/phase1_report.md`      | [Có/Thiếu] | [Ghi chú] |

### Baseline metrics

| Metric                 |       Giá trị | Diễn giải                             |
| ---------------------- | --------------: | --------------------------------------- |
| `retrieval_hit_rate` |     [Giá trị] | [Ý nghĩa trong kết quả của nhóm]  |
| `mean_token_f1`      |     [Giá trị] | [Diễn giải]                           |
| `judge_accuracy`     |     [Giá trị] | [Diễn giải]                           |
| `mean_judge_score`   |     [Giá trị] | [Diễn giải]                           |
| Ragas, nếu có        | [Giá trị/N/A] | [Diễn giải hoặc lý do không chạy] |

## 8. Data quality và freshness

### Quality checks

| Check        | Quality dimension | Ngưỡng/kỳ vọng | Kết quả baseline      | Bằng chứng |
| ------------ | ----------------- | ------------------ | ----------------------- | ------------ |
| [Tên check] | [Dimension]       | [Ngưỡng]         | [Pass/Fail + giá trị] | [Artifact]   |
| [Tên check] | [Dimension]       | [Ngưỡng]         | [Pass/Fail + giá trị] | [Artifact]   |

### Freshness

| Thuộc tính               | Giá trị                           |
| -------------------------- | ----------------------------------- |
| Freshness được đo tại | [Dataset/index/artifact]            |
| Timestamp mới nhất       | [Giá trị]                         |
| Ngưỡng freshness         | [Giá trị]                         |
| Trạng thái baseline      | [Fresh/Stale/Unknown]               |
| Lý do                     | [Giải thích dựa trên số liệu] |

## 9. Corruption scenarios và repair

| Corruption         | Cách tạo | Record bị tác động | Quality signal kỳ vọng | Tác động thực tế | Cách repair   |
| ------------------ | ---------- | ---------------------: | ------------------------ | --------------------- | -------------- |
| [Loại corruption] | [Mô tả]  |          [Số lượng] | [Kỳ vọng]              | [Artifact/metric]     | [Cách repair] |
| [Loại corruption] | [Mô tả]  |          [Số lượng] | [Kỳ vọng]              | [Artifact/metric]     | [Cách repair] |

Corruption log:

- Đường dẫn: `data/results/corruption_log.json`
- Trạng thái: [Có/Thiếu]
- Nhận xét: [Log có đủ loại corruption, record bị tác động và tham số hay không?]

Giải thích cách repair đảm bảo dữ liệu được phục hồi từ nguồn đáng tin cậy thay vì chỉ che kết quả lỗi:

[Giải thích tại đây.]

## 10. So sánh baseline, corrupted và repaired

| Metric/signal            | Baseline | Corrupted | Repaired | Thay đổi do corruption | Mức phục hồi | Nhận xét   |
| ------------------------ | -------: | --------: | -------: | -----------------------: | --------------: | ------------ |
| `retrieval_hit_rate`   |      [ ] |       [ ] |      [ ] |                      [ ] |             [ ] | [Nhận xét] |
| `mean_token_f1`        |      [ ] |       [ ] |      [ ] |                      [ ] |             [ ] | [Nhận xét] |
| `judge_accuracy`       |      [ ] |       [ ] |      [ ] |                      [ ] |             [ ] | [Nhận xét] |
| `mean_judge_score`     |      [ ] |       [ ] |      [ ] |                      [ ] |             [ ] | [Nhận xét] |
| Quality checks pass/fail |      [ ] |       [ ] |      [ ] |                      [ ] |             [ ] | [Nhận xét] |
| Freshness status         |      [ ] |       [ ] |      [ ] |                      [ ] |             [ ] | [Nhận xét] |

Nêu ít nhất hai kết luận có quan hệ nhân quả được hỗ trợ bởi artifacts:

1. [Corruption/data change] → [quality/freshness signal] → [retrieval/answer metric].
2. [Repair action] → [quality/freshness recovery] → [agent metric recovery hoặc lý do chưa recovery].

Không kết luận corruption “có tác động” nếu số liệu không cho thấy thay đổi. Nếu kết quả khác kỳ vọng, mô tả giả thuyết và cách nhóm đã kiểm tra.

## 11. Vấn đề tích hợp quan trọng

Mô tả một vấn đề phát sinh khi ghép các module trong pipeline và cách nhóm xử lý:

- **Triệu chứng:** [Lỗi hoặc kết quả sai.]
- **Nguyên nhân:** [Root cause.]
- **Cách xử lý:** [Thay đổi đã thực hiện.]
- **Cách xác minh:** [Lệnh và artifact.]

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại | Ảnh hưởng   | Hướng cải thiện có thể kiểm chứng |
| --------------------- | -------------- | ----------------------------------------- |
| [Giới hạn]          | [Ảnh hưởng] | [Đề xuất]                              |
| [Giới hạn]          | [Ảnh hưởng] | [Đề xuất]                              |

## 13. Checklist trước khi nộp

- [ ] Thông tin nhóm và repository chính xác.
- [ ] Phân công khớp với module, artifact và kết quả thực tế.
- [ ] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp.
- [ ] Baseline, corrupted và repaired dùng cùng evaluation set.
- [ ] Bảng metrics khớp với các file trong `data/results/`.
- [ ] Quality/freshness conclusions khớp với `data/quality/`.
- [ ] Các đường dẫn báo cáo và artifact truy cập được.
- [ ] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng.
- [ ] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh.
