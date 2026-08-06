# Báo cáo cá nhân — Day 10: Data Pipeline & Data Observability

<!--
File này tổng hợp vai trò, phần việc và kết quả cá nhân của Tạ Thị Thu Huyền.
Báo cáo tập trung vào quá trình tạo corruption, điều phối repair flow và kiểm thử tích hợp.
Các số liệu và artifact được dùng làm bằng chứng cho khả năng phục hồi của pipeline.
-->

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
|---|---|
| Họ và tên | Tạ Thị Thu Huyền |
| MSSV | 2A202601782 |
| Khóa/Lớp | K4 |
| Tên nhóm | Nhóm 4 người — Day 10 |
| Vai trò chính | Corruption & Integration Owner (Thành viên 4) |
| Repository | https://github.com/FrankLe2111/K4_Day10_2A202601590_LeNgoThanhToan |
| Nhánh thực hiện | `feat/corruption-repair-flow` |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
|---|---|---|---|---|
| Corruption có kiểm soát | `src/ingestion/corruption.py` — `corrupt_clean_dataframe` | Cleaned DataFrame của baseline | Corrupted DataFrame và corruption log có before/after | Hoàn thành |
| Baseline orchestration | `src/pipelines/phase1.py` | Raw snapshot, cấu hình pipeline và các module Role 1–3 | Clean artifacts, test set, baseline index, metrics, quality/freshness và report | Hoàn thành |
| Corruption/repair orchestration | `src/pipelines/corruption_flow.py` | Baseline artifacts và raw snapshot đã khóa | Corrupted/repaired artifacts, ba collection và comparison report | Hoàn thành |
| Kiểm thử tích hợp | `tests/test_corruption.py`, `tests/test_pipelines.py` | Các contract corruption/pipeline | 8 test tự động, kiểm tra schema, log, repair và delta report | Hoàn thành |

Phần việc này nhận raw/clean schema, evaluation set, retrieval, evaluator và observability từ các vai trò trước. Output của tôi là hai flow có thể chạy lại end-to-end và bộ bằng chứng baseline–corrupted–repaired.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
|---|---|---|
| Bổ sung comparison delta | `src/observability/reporting.py` | Report có thêm `Corrupted - baseline` và `Repaired - baseline`, kèm test chống hồi quy |
| Kiểm tra contract liên module | Cleaning, test set, retrieval và evaluation | Phát hiện sớm sai schema, ID ground truth không tồn tại, sai collection/path hoặc thay đổi test set |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
|---|---|---|---|
| Tạo sáu corruption có chủ đích | `src/ingestion/corruption.py`, `data/results/corruption_log.json` | Drop 2 bản ghi mới nhất; blank summary; truncate title; inject noise; làm stale date; thêm duplicate | Đọc `operation_count`, `paper_ids`, `parameters`, `before/after` trong log |
| Chạy baseline có validation | `src/pipelines/phase1.py`, `data/results/baseline_metrics.json` | 24 clean records, 32 evaluation samples, quality/freshness PASS | `python script/run_phase1.py` và đối chiếu artifact |
| Đo impact corruption | `data/results/corrupted_metrics.json`, `data/quality/corrupted_quality.json` | 23 records; retrieval hit rate còn 0.75; quality và freshness FAIL | `python script/run_corruption_flow.py` |
| Repair từ raw snapshot | `data/clean/papers_clean_repaired.json`, `data/results/repaired_metrics.json` | Phục hồi 24 records, IDs/hash clean và metrics về baseline | Validation trong `corruption_flow.py` và comparison report |
| Tạo báo cáo so sánh | `data/reports/corruption_report.md` | Bảng ba trạng thái và delta rõ ràng | Đối chiếu ba metrics JSON với report |

Output tiêu biểu là `data/results/corruption_log.json`. Artifact này ghi input 24 dòng, output 23 dòng, net delta -1 và sáu thao tác có ID cụ thể. Nhờ đó có thể truy vết chính xác dữ liệu nào bị thay đổi và kiểm tra repair thay vì chỉ dựa vào terminal báo thành công.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Pipeline cần chứng minh dữ liệu xấu tác động đến RAG và dữ liệu có thể được phục hồi đúng cách. Phép so sánh chỉ có ý nghĩa nếu baseline, corrupted và repaired dùng cùng test set, evaluator, embedding model, `top_k` và raw snapshot; đồng thời không trạng thái nào ghi đè trạng thái khác.

### Cách triển khai

`corrupt_clean_dataframe` tạo bản sao sâu của clean DataFrame và chọn record theo thứ tự xác định để kết quả tái lập. Hàm áp dụng sáu corruption riêng biệt, cập nhật lại các cột dẫn xuất như `summary_missing`, `age_days` và `text_for_embedding`, rồi ghi đầy đủ before/after vào log.

`phase1.py` điều phối raw → clean → index → test set → evaluate → quality/freshness → report. Flow kiểm tra schema, uniqueness của `paper_id`, ground-truth IDs, số answers/metrics, collection name và hash các artifact quan trọng.

`corruption_flow.py` chỉ chạy khi baseline artifacts hợp lệ. Flow đọc baseline clean JSON để bảo toàn kiểu list, dùng lại test set cũ, build collection corrupted riêng, đánh giá, sau đó chạy cleaning lại từ đúng raw snapshot để tạo repaired dataset. Repair chỉ được chấp nhận khi tập ID và hash JSON clean repaired khớp baseline.

### Input, output và contract

| Thành phần | Mô tả |
|---|---|
| Input | Raw records JSON; baseline clean JSON; test set gồm `id`, `question_type`, `question`, `ground_truth`, `ground_truth_doc_ids`; cấu hình model/top-k |
| Output | Clean/corrupted/repaired CSV và JSON; ba Chroma collection; answers, metrics, quality/freshness, corruption log và Markdown reports |
| Module phụ thuộc | `ingestion.cleaning`, `retrieval.index`, `evaluation.qa`, `evaluation.metrics`, `observability.quality`, `observability.reporting` |
| Module sử dụng output | Script entrypoints, UI evaluation, group/individual report và phần demo |
| Điều kiện lỗi cần xử lý | Thiếu baseline artifact; sai schema; orphan ground-truth ID; dùng trùng path/collection; test set/config/hash thay đổi; raw snapshot bị mutate; repaired IDs/hash không khớp baseline |

### Cách xác minh

```powershell
$env:USE_LLM_EVAL='false'
.\.venv\Scripts\python.exe script\run_phase1.py
.\.venv\Scripts\python.exe script\run_corruption_flow.py
.\.venv\Scripts\python.exe -m pytest -q
```

- **Kết quả mong đợi:** Hai flow exit code 0; corrupted khác baseline đúng theo log; repaired phục hồi baseline; report khớp JSON.
- **Kết quả thực tế:** `baseline=24`, `corrupted=23`, `repaired=24`, `operations=6`; 8 test passed.
- **Artifact/log:** `data/results/corruption_log.json`, ba file metrics trong `data/results/`, quality/freshness trong `data/quality/` và `data/reports/corruption_report.md`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Repair có thể được làm bằng cách sửa/copy trực tiếp corrupted hoặc baseline clean data, nhưng cách này không chứng minh pipeline có khả năng phục hồi từ nguồn đáng tin.
- **Các phương án đã cân nhắc:** (1) copy baseline clean làm repaired; (2) sửa tay corrupted rows; (3) chạy cleaning lại từ raw snapshot đã dùng cho baseline.
- **Phương án đã chọn:** Chạy lại cleaning từ đúng raw snapshot, cùng `clean_run_date`, sau đó đối chiếu tập `paper_id` và hash JSON với baseline.
- **Lý do:** Phương án này bảo toàn lineage, tái lập được và không che lỗi bằng cách sửa metrics hoặc answers. Chi phí chạy lại cao hơn nhưng correctness và auditability tốt hơn.
- **Bằng chứng:** Repaired có 24/24 records, quality PASS, freshness PASS và bốn metrics trở về đúng baseline; hash raw và test set giữ nguyên trong `pipeline_config`.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** Khi load baseline clean qua CSV, các trường `authors` và `categories` dạng list có thể trở thành chuỗi biểu diễn list, làm schema repaired và embedding text không còn tương đương baseline.
- **Bước tái hiện:** Đọc clean CSV bằng pandas rồi kiểm tra kiểu dữ liệu của `authors`/`categories`.
- **Nguyên nhân gốc:** CSV không bảo toàn nested/list types; round-trip tạo ra string thay vì list.
- **Cách xử lý:** Corruption flow dùng baseline clean JSON làm nguồn clean chuẩn và loader kiểm tra list schema; quá trình ghi JSON chuẩn hóa NaN thành `null` nhưng giữ list.
- **Cách xác minh:** Test `test_json_dataframe_loader_preserves_nested_list_schema` và `test_dataframe_json_records_preserve_lists_and_normalize_nan` đều pass.
- **Điều học được:** Artifact format là một phần của data contract; chọn sai định dạng trung gian có thể tạo corruption ngoài ý muốn và làm phép so sánh mất công bằng.

## 7. Hiểu biết về luồng end-to-end

Crossref trả raw response, sau đó payload được parse thành raw records có `paper_id` ổn định và được lưu thành snapshot. Cleaning chuẩn hóa title, summary, authors, categories và published date; deduplicate theo ID; tính `age_days` và tạo `text_for_embedding`. Clean records được embedding bằng MiniLM và đưa vào Chroma collection.

Evaluation set được tạo từ clean data và giữ `ground_truth_doc_ids` trỏ tới `paper_id` thật. Retriever/agent trả answer và retrieved IDs; evaluator dùng IDs để đo retrieval hit, đồng thời so answer với ground truth để tính token F1 và judge metrics.

Quality checks kiểm tra cấu trúc và tính hợp lệ của dữ liệu như thiếu trường, duplicate và uniqueness. Freshness tập trung vào thời gian xuất bản, số row stale và ngưỡng ngày. Hai nhóm signal bổ sung cho nhau nhưng không thay thế nhau.

Ba trạng thái phải dùng cùng test set, evaluator và `top_k` để metric delta phản ánh thay đổi dữ liệu thay vì thay đổi đề kiểm tra/cấu hình. Repair được coi là thành công khi rebuilt từ raw snapshot, khôi phục IDs/hash/schema, quality/freshness và metrics; không chỉ vì script exit code 0.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét cá nhân |
|---|---:|---:|---:|---|
| `retrieval_hit_rate` | 1.0 | 0.75 | 1.0 | Corruption làm giảm 0.25; repair phục hồi hoàn toàn |
| `mean_token_f1` | 1.0 | 0.7579 | 1.0 | Answer quality giảm khoảng 0.2421 rồi phục hồi |
| `judge_accuracy` | 1.0 | 0.75 | 1.0 | Giảm cùng retrieval hit rate và phục hồi về baseline |
| `mean_judge_score` | 5 | 4 | 5 | Giảm 1 điểm rồi phục hồi |
| Quality checks | PASS | FAIL | PASS | Missing summary/duplicate làm corrupted không đạt contract |
| Freshness status | PASS | FAIL | PASS | Một row bị làm cũ 3.650 ngày khiến freshness fail |

Các số liệu trên được tạo với `USE_LLM_EVAL=false`: cả 32 samples ở ba trạng thái dùng cùng fallback evaluator, `llm_answer_count=0`. Vì vậy đây là so sánh nhất quán trong chế độ local/fallback, không phải bằng chứng về chất lượng của OpenAI LLM.

### Kết luận từ số liệu

1. Drop latest records cùng các lỗi nội dung/duplicate/stale date → quality và freshness từ PASS thành FAIL → retrieval hit rate giảm `1.0 → 0.75`, token F1 giảm `1.0 → 0.7579`.
2. Re-clean từ raw snapshot → 24 records, quality/freshness trở lại PASS → toàn bộ metric repaired trở về baseline.

Corruption ảnh hưởng rõ nhất đến RAG là xóa hai latest records vì ground-truth documents không còn trong corrupted collection, tạo retrieval miss trực tiếp. Blank summary và truncate title cũng làm embedding context kém hơn. Corruption stale date thể hiện rõ nhất ở observability với `stale_rows=1`, còn duplicate làm quality contract thất bại.

Điểm khác kỳ vọng là không phải mọi corruption đều làm từng metric giảm độc lập; metrics tổng hợp giảm 25%, trong khi quality/freshness phát hiện nhiều loại lỗi hơn. Điều này cho thấy observability cần đo cả data signals và agent metrics, vì một lỗi dữ liệu có thể chưa xuất hiện trong tập câu hỏi hiện tại.

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Pipeline đáng tin cần lineage, artifact hash và validation ở ranh giới module, không chỉ cần các hàm chạy được riêng lẻ.
2. Corruption phải xác định, có log before/after và có signal kỳ vọng thì mới đo được tác động và repair.
3. Retrieval/answer quality phụ thuộc trực tiếp vào completeness và nội dung của dữ liệu; quality/freshness giúp phát hiện rủi ro mà evaluation set có thể chưa bao phủ.

### Nếu có thêm thời gian

Tôi sẽ chạy lại cả ba trạng thái với cùng LLM evaluator và bật Ragas, đồng thời mở rộng test set bằng paraphrase và nhiều seed. Cải thiện được đo bằng độ ổn định của metric delta qua nhiều lần chạy, thay vì chỉ dựa trên một test set và fallback evaluator.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Tạ Thị Thu Huyền
**Ngày xác nhận:** 2026-08-06
