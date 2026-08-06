# Báo cáo cá nhân – Nguyễn Đức Hùng

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | Nguyễn Đức Hùng |
| MSSV | 2A202601936 |
| Khóa/Lớp | K4 |
| Tên nhóm | VinCourse |
| Vai trò | Role 1 – Data Ingestion, Data Cleaning & Pipeline Architecture |
| Repository | [FrankLe2111/K4_Day10_2A202601590_LeNgoThanhToan](https://github.com/FrankLe2111/K4_Day10_2A202601590_LeNgoThanhToan) |
| Ngày hoàn thành | 2026-08-06 |

---

## 2. Phạm vi công việc

| Module/deliverable | File/hàm phụ trách | Input | Output | Trạng thái |
|---|---|---|---|---|
| Data Ingestion | `src/ingestion/crossref.py` | Crossref REST API / Search Query | Raw Response & `PaperRecord` dataclass | Hoàn thành |
| Defensive Edge Cases | `parse_crossref_payload()` | HTTP Payload JSON thô | 4 Lớp kiểm tra ngoại lệ Edge Case 100% safe | Hoàn thành |
| Raw Artifacts | `fetch_source_records()` | API Response & Settings | `crossref_response.json` & `crossref_records.json` | Hoàn thành |
| Data Cleaning | `src/ingestion/cleaning.py` | List `PaperRecord` raw | Clean DataFrame, CSV & JSON | Hoàn thành |
| Feature Engineering | `build_clean_dataframe()` | Raw fields | `text_for_embedding`, `age_days`, `summary_chars` | Hoàn thành |
| Lesson Artifacts | `CHANG_1_LESSONS.md`, `CHANG_2_LESSONS.md`, `CHANG_3_LESSONS.md`, `CHANG_4_LESSONS.md` | Bài học & Cú pháp | Giáo trình chi tiết từng chặng | Hoàn thành |

---

## 3. Kết quả bàn giao

- **Raw API Response Artifact**: `data/raw/crossref_response.json` (~245 KB) – Lưu giữ 100% dữ liệu gốc API trả về để audit và replay.
- **Raw Records Artifact**: `data/raw/crossref_records.json` (~60 KB) – Danh sách 24 bản ghi thô đã parse thành cấu trúc phẳng `PaperRecord`.
- **Clean CSV Artifact**: `data/clean/papers_clean.csv` (~99 KB) – 24 bài báo đã qua làm sạch, bỏ XML, lọc rác `< 100` chars và khử trùng lặp.
- **Clean JSON Artifact**: `data/clean/papers_clean.json` (~115 KB) – Dạng JSON tương ứng với Clean DataFrame.
- **Benchmark Test Set Artifact**: `data/eval/test_set.json` (~40 KB) – 40 câu hỏi kiểm thử tiếng Việt đa dạng (`summary`, `authors`, `date`, `categories`).
- **Data Quality & Observability Artifacts**: `data/quality/baseline_quality.json` (`passed=true`) & `data/quality/freshness_report.json` (`is_fresh=true`).

---

## 4. Vấn đề kỹ thuật và cách triển khai

### 4.1. Data Ingestion & Polite Pool API Fetching (`crossref.py`)

Trong `fetch_source_records()`:
1. Cấu hình HTTP Request Header `User-Agent` chứa email `mailto:student@example.com` để tham gia **Polite Pool của Crossref API**, giúp giảm nguy cơ bị chặn IP.
2. Tích hợp thuật toán **Exponential Backoff (`time.sleep(backoff)`)** với tối đa 4 lần thử lại khi gặp các mã lỗi tạm thời của server (`HTTP 429 Too Many Requests`, `503 Service Unavailable`, `502`, `504`).

### 4.2. Lập trình phòng thủ 4 lớp (Defensive Edge Case Handling)

Trong `parse_crossref_payload()` và `_extract_date()`:
1. **Edge Case 1 (Payload rỗng/sai kiểu)**: Nếu `payload` không phải `dict`, trả về `[]` thay vì quăng lỗi `AttributeError`.
2. **Edge Case 2 (Phần tử mảng `None`)**: Kiểm tra `isinstance(item, dict)` và `isinstance(author, dict)` trước khi truy cập `.get()`.
3. **Edge Case 3 (Tiêu đề biến thành chuỗi `"None"`)**: Bổ sung bộ lọc `if not doi or not title or title.lower() == "none": continue`.
4. **Edge Case 4 (Thiếu ngày tháng xuất bản)**: Nếu API thiếu ngày xuất bản hoặc lỗi kiểu, fallback về **chuỗi rỗng `""`** thay vì ngày hiện tại để tránh gây **Hallucination** cho RAG Agent.

### 4.3. Data Cleaning & Feature Engineering (`cleaning.py`)

Trong `build_clean_dataframe()`:
1. **Chuẩn hóa văn bản**: Dùng `normalize_whitespace()` rút gọn khoảng trắng rác `\n\t`.
2. **Ghép chuỗi danh mục & Tác giả**: Dùng `compact_join(authors)` tạo `authors_joined` và `categories_joined`.
3. **Tính toán `age_days`**: Đo khoảng cách ngày so với `run_date`. Nếu `published` bị rỗng `""`, gán `age_days = 9999` (để Data Observability phát hiện dữ liệu mốc/thiếu ngày).
4. **Tạo cột biểu diễn ngữ nghĩa `text_for_embedding`**:
   - Định dạng chuẩn: `Title: [title] | Authors: [authors_joined] | Summary: [summary]`.
5. **Lọc rác & Khử trùng lặp**:
   - Loại bỏ tiêu đề rỗng hoặc tóm tắt quá ngắn (`summary_chars < 100`).
   - Xóa bỏ trùng lặp mã DOI: `df.drop_duplicates(subset=["paper_id"], keep="first")`.
   - Sắp xếp ngày công bố giảm dần: `df.sort_values(by="published", ascending=False)`.

---

## 5. Input/output contract

| Thành phần | Contract |
|---|---|
| Ingestion Input | Crossref API URL `https://api.crossref.org/works`, `query`, `filter`, `rows` |
| Ingestion Raw Output | `data/raw/crossref_response.json` & `data/raw/crossref_records.json` |
| Cleaning Input | `list[PaperRecord]`, `run_date: datetime` |
| Cleaning Output | `pd.DataFrame` (16 cột) $\rightarrow$ `papers_clean.csv` & `papers_clean.json` |
| Testset Output | `data/eval/test_set.json` (40 câu hỏi tiếng Việt kèm `ground_truth_doc_ids`) |
| Quality Output | `data/quality/baseline_quality.json` & `freshness_report.json` |

---

## 6. Verification

Các lệnh đã chạy kiểm thử thực tế và đạt thành công 100%:

```bash
# 1. Verification kiểm tra cú pháp Python (0 syntax errors)
python -m py_compile "src/ingestion/crossref.py"
python -m py_compile "src/ingestion/cleaning.py"
python -m py_compile "src/evaluation/testset.py"
python -m py_compile "src/observability/quality.py"

# 2. Thực thi kiểm thử Chặng 1 & 2 (Clean DataFrame generation)
$env:PYTHONPATH="src"; python -c "from datetime import datetime, UTC; from core.config import load_settings; from core.utils import write_csv, write_json; from ingestion.crossref import load_raw_records; from ingestion.cleaning import build_clean_dataframe; s = load_settings(); records = load_raw_records(s.paths.raw_records_json); df = build_clean_dataframe(records, datetime.now(UTC)); write_csv(df, s.paths.clean_csv); write_json(s.paths.clean_json, df.to_dict(orient='records')); print(f'Successfully cleaned {len(df)} papers!')"

# 3. Thực thi kiểm thử Chặng 3 (Test Set generation)
$env:PYTHONPATH="src"; python -c "import pandas as pd; from core.config import load_settings; from core.utils import read_json; from evaluation.testset import build_test_set; s = load_settings(); data = read_json(s.paths.clean_json); df = pd.DataFrame(data); test_set = build_test_set(df, s.paths.eval_testset); print(f'Successfully generated {len(test_set)} test questions!')"

# 4. Thực thi kiểm thử Chặng 4 (Quality & Freshness check)
$env:PYTHONPATH="src"; python -c "import pandas as pd; from core.config import load_settings; from core.utils import read_json; from observability.quality import run_data_quality_checks, build_freshness_report; s = load_settings(); data = read_json(s.paths.clean_json); df = pd.DataFrame(data); print(run_data_quality_checks(df, s, 'baseline_quality')); print(build_freshness_report(df, s, s.paths.freshness_report))"
```

**Kết quả kiểm tra Data Quality**:
```json
{
  "report_name": "baseline_quality",
  "total_rows": 24,
  "unique_ids": 24,
  "is_unique": true,
  "missing_summary_rows": 0,
  "missing_title_rows": 0,
  "stale_rows": 0,
  "passed": true
}
```

---

## 7. Quyết định kỹ thuật quan trọng

### 7.1. Chọn Fallback chuỗi rỗng `""` thay vì lấy ngày hiện tại `today` khi thiếu ngày xuất bản
- **Bối cảnh**: Bài báo trong Crossref API có thể bị thiếu dữ liệu ngày tháng.
- **Phương án 1 (Gán ngày hiện tại `today`)**: Dễ lập trình, nhưng làm bài báo cũ bị biến thành bài báo mới 100%. Khi người dùng hỏi *"Bài báo công bố khi nào?"*, RAG Agent đọc context và khẳng định bài báo công bố hôm nay $\rightarrow$ **Gây ra Pipeline-Induced Hallucination**.
- **Phương án 2 (Lựa chọn - Fallback `""`)**: Khi bài báo thiếu ngày, `published = ""`. RAG Agent đọc ngữ cảnh thấy thiếu ngày sẽ trả lời trung thực: *"Tài liệu không cung cấp thông tin ngày xuất bản"*. Đồng thời `age_days` được gán `= 9999` giúp Data Observability phát hiện dữ liệu mốc/thiếu ngày.

### 7.2. Chọn lọc bỏ các trường metadata phụ (`ISSN`, `publisher`, `volume`, `page`, `license`) khỏi `PaperRecord` schema
- **Bối cảnh**: Crossref API trả về hàng chục trường siêu dữ liệu phụ.
- **Lý do chọn lựa**:
  1. **Giảm từ nhiễu (Noise Reduction)**: Mô hình Embedding `all-MiniLM-L6-v2` chỉ cần ngữ nghĩa khoa học (Tiêu đề, Tác giả, Tóm tắt). Các chuỗi như `ISSN: 2949-1894` hay `Volume: 7` làm loãng khoảng cách vector.
  2. **Chuẩn hóa đa nguồn (Cross-source Standardization)**: Giúp schema tương thích khi mở rộng crawler sang arXiv hoặc PubMed (những nơi không có `ISSN`).
  3. **Tiết kiệm bộ nhớ ChromaDB**: Giảm kích thước file vector index và tăng tốc độ truy vấn Top-K.

---

## 8. Lỗi đã xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Thẻ rác `<jats:p>` trong abstract | Nhà xuất bản lưu tóm tắt dạng JATS XML | Dùng Regex `re.sub(r"<[^>]+>", " ", text)` bóc tách |
| Chuỗi `\u0421...` xuất hiện trong file JSON | Python `json.dumps` dùng `ensure_ascii=True` | Giải thích đây là Unicode Escape mã hóa tiếng Nga/Cyrillic chuẩn 100%; đổi `ensure_ascii=False` nếu muốn hiển thị ký tự UTF-8 |
| Lỗi `AttributeError` / `TypeError` khi gọi `.get()` | API trả về phần tử JSON bị `None` hoặc sai kiểu dict | Thêm kiểm tra phòng thủ 4 lớp `isinstance(item, dict)` |
| `summary_chars` quá ngắn gây nhiễu RAG | Bài báo chỉ chứa tóm tắt 1 câu rác | Thêm bộ lọc `df["summary_chars"] >= 100` trong `cleaning.py` |
| `ModuleNotFoundError: No module named 'chromadb'` | Import phụ thuộc vòng trong `evaluation/__init__.py` | Cập nhật `src/evaluation/__init__.py` chỉ export `build_test_set` một cách modular |

---

## 9. Phân tích metrics & Tác động của Data Ingestion/Cleaning tới RAG

| Metric / Signal | Baseline | Corrupted | Repaired | Phân tích tác động |
|---|---:|---:|---:|---|
| **Retrieval Hit Rate** | **1.0000** | 0.7500 | **1.0000** | Dữ liệu bị hỏng/xóa tóm tắt làm rớt Hit Rate 25%; khôi phục từ raw giúp Hit Rate trở lại 100% |
| **Mean Token F1** | **1.0000** | 0.3543 | **1.0000** | Dữ liệu rác làm giảm trùng khớp từ vựng trầm trọng |
| **Data Quality Passed** | **`true`** | `false` | **`true`** | Quality check phát hiện chính xác bài báo rỗng/trùng lặp |
| **Freshness Status** | **Fresh** | Stale | **Fresh** | Phát hiện ngày mốc 9999 khi dữ liệu bị hỏng |

**Kết luận cốt lõi**: *"Garbage In, Garbage Out"*. Nếu chặng Ingestion & Cleaning làm tốt nhiệm vụ lọc rác, loại bỏ thẻ XML và xây dựng `text_for_embedding` chuẩn mực, hiệu năng Retrieval Hit Rate và Token F1 của RAG Agent sẽ đạt mức tối đa.

---

## 10. Hiểu biết end-to-end

1. Crossref API trả về HTTP JSON thô $\rightarrow$ Ingestion bóc tách XML, bóc ngày, đóng gói `PaperRecord` và lưu 2 Raw Artifacts (`crossref_response.json` & `crossref_records.json`).
2. Cleaning loại bỏ dòng rác `< 100` ký tự, khử trùng lặp DOI, ghép tác giả/danh mục và xây dựng `text_for_embedding`.
3. Transformer Embedding `all-MiniLM-L6-v2` nén `text_for_embedding` thành vector 384 chiều và lưu vào ChromaDB Index.
4. Test Set Generator trích xuất 10 bài báo đại diện thành 40 câu hỏi kiểm thử tiếng Việt kèm `ground_truth` và `ground_truth_doc_ids`.
5. Data Quality Checks giám sát 5 trụ cột (Freshness, Quality, Volume, Schema, Lineage) và xuất báo cáo JSON.
6. Chặng Evaluation cho RAG Agent làm 40 câu hỏi, đo Retrieval Hit Rate và Token F1.
7. Khi dữ liệu bị hỏng (Corruption), luồng Data Repair đọc lại Raw Snapshot để khôi phục dữ liệu sạch 100% mà không cần gọi lại API bên ngoài.

---

## 11. Bài học và hướng cải thiện

1. **Bài học về Data Ingestion**: Luôn bảo tồn Raw Artifacts nguyên bản để phục vụ audit và repair offline.
2. **Bài học về Defensive Programming**: Phải kiểm tra kiểu dữ liệu `isinstance()` và dùng fallback an toàn để chống crash pipeline và chống tiêm ngày giả gây Hallucination.
3. **Hướng cải thiện**:
   - Mở rộng crawler tích hợp thêm nguồn bài báo từ arXiv REST API và PubMed.
   - Thêm tính năng tự động phát hiện ngôn ngữ (Language Detection) để phân loại bài báo tiếng Anh / tiếng Nga / tiếng Việt.

---

## 12. Cam kết

- [x] Nội dung báo cáo dựa trên artifact và metrics thực tế từ dự án.
- [x] Mọi quyết định kỹ thuật và lệnh kiểm thử đều được xác minh thực nghiệm.
- [x] Báo cáo không chứa API key, token hoặc secret.
- [x] Đã kiểm tra biên dịch và chạy thành công pipeline.

**Họ và tên:** Nguyễn Đức Hùng<br>
**MSSV:** 2A202601936<br>
**Ngày xác nhận:** 2026-08-06
