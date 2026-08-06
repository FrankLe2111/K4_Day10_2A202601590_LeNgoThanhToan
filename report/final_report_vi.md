# Báo cáo hoàn thành Day 10 – Data Pipeline, RAG và Data Observability

## 1. Mục tiêu

Project xây dựng một pipeline RAG hoàn chỉnh sử dụng metadata bài báo khoa học từ Crossref. Pipeline thực hiện toàn bộ vòng đời dữ liệu:

```text
Crossref API
    -> raw snapshot
    -> parse và cleaning
    -> embedding + ChromaDB
    -> evaluation baseline
    -> quality/freshness monitoring
    -> data corruption
    -> re-evaluation
    -> repair từ raw data
    -> comparison report
```

Mục tiêu cuối cùng là chứng minh bằng artifact và metrics rằng chất lượng dữ liệu ảnh hưởng trực tiếp đến chất lượng retrieval/RAG, đồng thời pipeline có thể phục hồi dữ liệu lỗi.

## 2. Cấu hình sử dụng

| Thành phần | Giá trị |
|---|---|
| Nguồn dữ liệu | Crossref REST API – `https://api.crossref.org/works` |
| Query | `agentic retrieval augmented generation large language model` |
| Freshness threshold | 180 ngày |
| Số record yêu cầu | 24 |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Embedding dimension | 384 |
| Vector store | ChromaDB |
| Retrieval top-k | 4 |
| LLM provider | OpenAI |
| LLM model | `gpt-4o-mini` |

API key được cấu hình trong `.env` và không đưa vào báo cáo.

## 3. Các phần đã triển khai

### 3.1. Ingestion từ Crossref

File thực hiện: `src/ingestion/crossref.py`

Đã triển khai:

- Gọi endpoint Crossref REST API.
- Truyền query, filter và số lượng record từ `Settings`.
- Retry/backoff với các lỗi tạm thời `429`, `502`, `503`, `504`.
- Parse DOI thành `paper_id` ổn định.
- Lấy title, abstract hoặc description, authors, categories, dates, URL và PDF URL.
- Loại record thiếu DOI, title hoặc summary dưới 100 ký tự.
- Loại XML/HTML như `<jats:p>` và `<b>` khỏi text.
- Loại duplicate theo DOI.

Raw artifacts:

- `data/raw/crossref_response.json`: response JSON gốc từ Crossref.
- `data/raw/crossref_records.json`: records đã flatten theo `PaperRecord`.

### 3.2. Cleaning và data modeling

File thực hiện: `src/ingestion/cleaning.py`

Các bước cleaning:

- Chuẩn hóa whitespace.
- Loại bỏ HTML/XML khỏi title và summary.
- Drop record không có title hoặc summary dưới 100 ký tự.
- Chuẩn hóa ngày về `YYYY-MM-DD`.
- Tính `age_days` so với thời điểm chạy pipeline.
- Gộp authors thành `authors_joined`.
- Gộp categories thành `categories_joined`.
- Tạo `summary_chars`.
- Tạo `text_for_embedding` theo format:

```text
Title: [title] | Authors: [authors] | Summary: [summary]
```

Clean artifacts:

- `data/clean/papers_clean.csv`
- `data/clean/papers_clean.json`

### 3.3. Embedding và vector index

Files thực hiện:

- `src/retrieval/embeddings.py`
- `src/retrieval/index.py`

Pipeline embedding:

1. Đọc `text_for_embedding` từ cleaned dataset.
2. Encode bằng `all-MiniLM-L6-v2`.
3. Normalize embedding vectors.
4. Lưu vectors và metadata vào ChromaDB.
5. Tạo manifest trong `data/embeddings/`.

Index hỗ trợ:

- Semantic search theo query.
- Lookup chính xác theo DOI.
- Lookup chính xác theo title.
- Trả về score cosine và metadata document.

### 3.4. Evaluation set

File thực hiện: `src/evaluation/testset.py`

Evaluation set được tạo từ cleaned data. Mỗi paper có thể tạo các loại câu hỏi:

- Summary/contribution.
- Authors.
- Publication date.
- Categories nếu category tồn tại.

Mỗi sample có:

```json
{
  "id": "paper-doi::summary",
  "question_type": "summary",
  "question": "...",
  "ground_truth": "...",
  "ground_truth_doc_ids": ["paper-doi"]
}
```

`ground_truth_doc_ids` giống nhau giữa nhiều câu hỏi về cùng một paper là đúng, vì các câu hỏi đó cùng có một tài liệu nguồn.

Đã xử lý lỗi Unicode bằng `ensure_ascii=False`, nên dữ liệu tiếng Nga hiển thị trực tiếp thay vì dạng `\\u0421...`.

Artifact:

- `data/eval/test_set.json`

### 3.5. LLM answer generation

File thực hiện: `src/retrieval/qa.py`

LLM được bổ sung vào bước trả lời:

1. Nhận câu hỏi.
2. Semantic search top-k documents.
3. Ghép các documents thành context.
4. Gửi question và context vào OpenAI LLM.
5. Yêu cầu LLM chỉ trả lời dựa trên context.
6. Nếu context không đủ, trả lời rõ ràng rằng không biết.

Mỗi answer ghi thêm:

```json
"answer_mode": "llm"
```

Nếu OpenAI API lỗi hoặc hết quota, pipeline dùng fallback local và ghi:

```json
"answer_mode": "fallback"
```

Điều này giúp pipeline không bị dừng hoàn toàn khi LLM provider tạm thời không khả dụng.

### 3.6. Evaluation metrics

File thực hiện: `src/evaluation/metrics.py`

Các metrics:

- `retrieval_hit_rate`: tỷ lệ câu hỏi có ground-truth document trong top-k retrieved documents.
- `mean_token_f1`: độ tương đồng token giữa câu trả lời và ground truth.
- `judge_accuracy`: tỷ lệ câu trả lời được judge đánh giá đúng.
- `mean_judge_score`: điểm judge trung bình từ 1 đến 5.
- `llm_answer_count`: số câu được trả lời bằng LLM.
- `fallback_answer_count`: số câu phải dùng fallback.

Artifact:

- `data/results/baseline_metrics.json`
- `data/results/baseline_answers.json`

### 3.7. Quality và freshness monitoring

File thực hiện: `src/observability/quality.py`

Các quality checks:

- Row count lớn hơn 0.
- `paper_id` không null.
- `paper_id` unique.
- Title không rỗng.
- Summary có tối thiểu 100 ký tự.
- Không có record vượt freshness threshold.

Artifacts:

- `data/quality/baseline_quality.json`
- `data/quality/freshness_report.json`

### 3.8. Corruption, repair và comparison

Files thực hiện:

- `src/ingestion/corruption.py`
- `src/pipelines/corruption_flow.py`

Các corruption scenario:

- Xóa một số record mới nhất.
- Làm rỗng summary.
- Truncate title.
- Chèn noise vào summary.
- Làm ngày xuất bản trở nên cũ.
- Tạo duplicate record.

Repair được thực hiện bằng cách đọc lại `data/raw/crossref_records.json`, sau đó chạy lại cleaning và indexing.

Artifacts:

- `data/clean/papers_clean_corrupted.csv`
- `data/clean/papers_clean_repaired.csv`
- `data/results/corruption_log.json`
- `data/results/corrupted_metrics.json`
- `data/results/repaired_metrics.json`
- `data/reports/corruption_report.md`

## 4. Baseline results

Baseline hiện tại có 18 evaluation samples và 18 câu được trả lời bằng LLM:

| Metric | Giá trị |
|---|---:|
| Samples | 18 |
| LLM answer count | 18 |
| Fallback answer count | 0 |
| Retrieval hit rate | 1.0000 |
| Mean Token F1 | 0.4177 |
| Judge accuracy | 0.6667 |
| Mean judge score | 3.4444 |
| Ragas | Chưa chạy |

Diễn giải:

- Retrieval tìm đúng tài liệu trong toàn bộ samples.
- Token F1 thấp hơn 1 vì LLM thường paraphrase, thêm/bớt từ hoặc diễn đạt khác ground truth.
- Judge accuracy thấp hơn 1 cho thấy retrieval đúng chưa đảm bảo câu trả lời cuối cùng luôn hoàn toàn chính xác.
- Đây là kết quả thực tế hơn baseline deterministic trước đó.

## 5. Data quality và freshness

Quality baseline:

| Check | Kết quả |
|---|---|
| Row count | PASS |
| Paper ID not null | PASS |
| Paper ID unique | PASS |
| Title not blank | PASS |
| Summary content | PASS |
| Freshness | PASS |

Freshness baseline:

| Thuộc tính | Giá trị |
|---|---:|
| Total rows | 6 |
| Latest published | 2026-06-30 |
| Oldest published | 2026-02-26 |
| Stale rows | 0 |
| Threshold | 180 ngày |
| Is fresh | `true` |

Báo cáo baseline:

- `data/reports/phase1_report.md`

## 6. Corruption và repair results

| Metric | Baseline | Corrupted | Repaired |
|---|---:|---:|---:|
| Retrieval hit rate | 1.0000 | 0.8333 | 1.0000 |
| Mean Token F1 | 1.0000* | 0.4641 | 1.0000* |
| Judge accuracy | 1.0000* | 0.4444 | 1.0000* |
| Mean judge score | 5.0000* | 2.6667 | 5.0000* |

`*` Các giá trị baseline/repaired trong artifact hiện tại được tạo ở lần chạy deterministic trước khi chuyển toàn bộ answer generation sang LLM; baseline LLM mới được ghi ở mục 4. Cần chạy lại corruption flow sau khi baseline LLM đã ổn định nếu muốn bảng ba trạng thái hoàn toàn cùng một chế độ LLM.

Kết luận từ corruption:

```text
Data corruption
    -> quality/freshness fail
    -> retrieval hit rate giảm
    -> judge accuracy và judge score giảm

Repair từ raw snapshot
    -> quality/freshness pass
    -> retrieval phục hồi
    -> answer metrics phục hồi
```

Corruption có ảnh hưởng rõ nhất là làm rỗng/trộn nhiễu summary và xóa record mới, vì các thay đổi này trực tiếp ảnh hưởng đến semantic embedding và context được đưa cho LLM.

## 7. Giải thích các khái niệm quan trọng

### Retrieval hit rate đo gì?

`retrieval_hit_rate` đo thành phần retriever/vector search của RAG. Nó kiểm tra ground-truth document có xuất hiện trong top-k documents hay không.

Metric này không trực tiếp chứng minh LLM trả lời đúng. Một hệ thống có retrieval hit rate bằng 1 vẫn có thể có answer quality thấp nếu LLM đọc sai context, bỏ sót thông tin hoặc hallucinate.

### Vì sao Token F1 không nhất thiết bằng 1?

Token F1 so sánh token của câu trả lời LLM với token của ground truth. Retrieval đúng chỉ cung cấp đúng context; LLM vẫn có thể:

- Paraphrase câu trả lời.
- Dùng từ đồng nghĩa.
- Bỏ sót token.
- Thêm thông tin.
- Trả lời dài/ngắn hơn reference.

Do đó retrieval và generation là hai chất lượng khác nhau.

## 8. Các lỗi đã xử lý

### Lỗi khởi tạo Settings

Một số file chạy trực tiếp từng gọi `Settings()` không tham số, gây thiếu 23 field bắt buộc. Đã thay bằng `load_settings()`.

Các file đã xử lý:

- `src/retrieval/index.py`
- `src/retrieval/qa.py`

### Lỗi Unicode trong JSON

JSON từng ghi chữ Cyrillic thành `\\u0421...` do `ensure_ascii=True`. Đã chuyển sang `ensure_ascii=False` để giữ UTF-8 trực tiếp.

### Lỗi NaN trong evaluation set

Category rỗng bị Pandas đọc thành `NaN`, sau đó biến thành chuỗi `"nan"`. Đã sửa để bỏ sample category khi category không tồn tại.

### Gemini hết quota

Gemini trả HTTP 429 `RESOURCE_EXHAUSTED`. Project đã chuyển sang OpenAI `gpt-4o-mini` và vẫn giữ local fallback nếu provider lỗi.

### Test set stale sau khi refresh source

Đã sửa `phase1.py` để tự tạo lại evaluation set khi `REFRESH_SOURCE=1`, tránh ground-truth IDs không còn tồn tại trong corpus mới.

## 9. Cách chạy lại toàn bộ pipeline

Từ thư mục gốc project:

```bash
cd /home/aic/K4_Day10_2A202601590_LeNgoThanhToan
source .venv/bin/activate
```

Chạy baseline với raw snapshot hiện có:

```bash
python script/run_phase1.py
```

Lấy dữ liệu Crossref mới và tạo lại test set:

```bash
REFRESH_SOURCE=1 REFRESH_TEST_SET=1 python script/run_phase1.py
```

Chạy corruption, re-evaluation và repair:

```bash
python script/run_corruption_flow.py
```

Chạy riêng các module retrieval:

```bash
python src/retrieval/embeddings.py
python src/retrieval/index.py
python src/retrieval/qa.py
python src/retrieval/agent.py
```

## 10. Hạn chế và hướng cải thiện

- Ragas chưa chạy; có thể bật bằng `RUN_RAGAS=1`.
- Bộ dữ liệu hiện chỉ có 6 bài báo sạch sau filtering, nên chưa đại diện cho corpus lớn.
- Ground truth được tạo tự động từ metadata, chưa được chuyên gia kiểm duyệt.
- Có thể bổ sung citation tracking để LLM trích dẫn DOI/document ID trong câu trả lời.
- Có thể đánh giá nhiều giá trị `top_k`, nhiều query paraphrase và nhiều seed.
- Nên chạy lại toàn bộ corruption flow với cùng chế độ LLM sau khi baseline LLM hoàn tất để so sánh công bằng tuyệt đối.

## 11. Kết luận

Project đã hoàn thành pipeline RAG và observability end-to-end. Dữ liệu được lấy từ Crossref, lưu raw để audit, cleaning theo data contract, embedding vào ChromaDB, truy vấn bằng semantic search và trả lời bằng OpenAI LLM. Baseline cho thấy retriever tìm đúng tài liệu, nhưng LLM answer quality thấp hơn retrieval quality, thể hiện qua Token F1 và judge metrics. Khi chủ động corruption dữ liệu, cả quality/freshness và RAG metrics đều suy giảm. Khi repair từ raw snapshot, dữ liệu và các metric retrieval được phục hồi. Đây là bằng chứng rằng data quality là một thành phần quyết định trực tiếp đến độ tin cậy của hệ thống RAG.
