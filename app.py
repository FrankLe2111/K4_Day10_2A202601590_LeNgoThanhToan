from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd
import streamlit as st

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.config import load_settings
from retrieval.index import LocalEmbeddingIndex
from retrieval.qa import answer_question


PROJECT_DIR = Path(__file__).resolve().parent

st.set_page_config(
    page_title="Crossref RAG Observatory",
    page_icon="📚",
    layout="wide",
)


@st.cache_resource
def get_settings():
    return load_settings(PROJECT_DIR)


@st.cache_resource
def get_index():
    settings = get_settings()
    if settings.paths.embeddings_json.exists():
        return LocalEmbeddingIndex.load(settings, settings.paths.embeddings_json)
    if not settings.paths.clean_csv.exists():
        raise FileNotFoundError("Chưa có clean dataset. Hãy chạy baseline pipeline trước.")
    clean_df = pd.read_csv(settings.paths.clean_csv)
    return LocalEmbeddingIndex.build(clean_df, settings, settings.paths.embeddings_json)


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def metric_card(label: str, value: object):
    st.metric(label, value)


def render_overview(settings):
    st.title("📚 Crossref RAG Observatory")
    st.caption("Demo end-to-end: Crossref → cleaning → embeddings → ChromaDB → LLM/RAG → observability")

    metrics = read_json(settings.paths.baseline_metrics, {})
    quality = read_json(settings.paths.quality_dir / "baseline_quality.json", {})
    freshness = read_json(settings.paths.freshness_report, {})
    clean_rows = 0
    if settings.paths.clean_csv.exists():
        clean_rows = len(pd.read_csv(settings.paths.clean_csv))

    cols = st.columns(5)
    with cols[0]:
        metric_card("Clean papers", clean_rows)
    with cols[1]:
        metric_card("Retrieval hit rate", f"{metrics.get('retrieval_hit_rate', 0):.2%}")
    with cols[2]:
        metric_card("Mean Token F1", f"{metrics.get('mean_token_f1', 0):.3f}")
    with cols[3]:
        metric_card("Judge accuracy", f"{metrics.get('judge_accuracy', 0):.2%}")
    with cols[4]:
        metric_card("Freshness", "PASS" if freshness.get("is_fresh") else "FAIL")

    st.subheader("Pipeline status")
    status_rows = {
        "Raw Crossref response": settings.paths.raw_api_response,
        "Parsed raw records": settings.paths.raw_records_json,
        "Clean CSV": settings.paths.clean_csv,
        "Clean JSON": settings.paths.clean_json,
        "Embedding manifest": settings.paths.embeddings_json,
        "Evaluation set": settings.paths.eval_testset,
        "Baseline metrics": settings.paths.baseline_metrics,
        "Quality report": settings.paths.quality_dir / "baseline_quality.json",
        "Phase 1 report": settings.paths.baseline_report,
    }
    table = [{"Artifact": name, "Status": "✅ Có" if path.exists() else "❌ Thiếu", "Path": str(path.relative_to(PROJECT_DIR))} for name, path in status_rows.items()]
    st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)

    left, right = st.columns(2)
    with left:
        st.subheader("Quality checks")
        checks = quality.get("checks", [])
        if checks:
            st.dataframe(pd.DataFrame(checks), use_container_width=True, hide_index=True)
        else:
            st.info("Chưa có quality report.")
    with right:
        st.subheader("Freshness")
        st.json(freshness if freshness else {"message": "Chưa có freshness report."})


def render_search(index, settings):
    st.title("🔎 Semantic Search")
    query = st.text_input("Nhập query", "retrieval augmented generation agents")
    top_k = st.slider("Top-k", 1, 10, settings.top_k)
    if st.button("Search", type="primary"):
        with st.spinner("Đang tìm kiếm trong ChromaDB..."):
            results = index.search(query, top_k=top_k)
        if not results:
            st.warning("Không tìm thấy document.")
        for rank, result in enumerate(results, 1):
            with st.expander(f"{rank}. {result.title}  ·  score={result.score:.4f}", expanded=rank == 1):
                st.write(f"**Paper ID:** `{result.paper_id}`")
                st.write(result.content)
                st.json(result.metadata)


def render_qa(index, settings):
    st.title("💬 Ask the RAG system")
    st.caption("LLM sẽ chỉ trả lời dựa trên các context được retrieve từ corpus local.")
    question = st.text_area(
        "Câu hỏi",
        "What is the main contribution of 'Retrieval-Augmented Large Language Model Agents for Automated Scientific Literature Review Generation'?",
        height=100,
    )
    use_llm = st.checkbox("Dùng OpenAI LLM", value=True, help="Bỏ chọn để chạy local deterministic fallback, không gọi API.")
    if st.button("Ask", type="primary"):
        with st.spinner("Đang retrieve context và sinh câu trả lời..."):
            result = answer_question(question, settings, index, use_llm=use_llm)
        st.success(f"Answer mode: {result.answer_mode}")
        st.markdown("### Answer")
        st.write(result.answer)
        st.markdown("### Retrieved documents")
        st.dataframe(
            pd.DataFrame({"paper_id": result.retrieved_doc_ids, "title": result.retrieved_titles}),
            use_container_width=True,
            hide_index=True,
        )
        with st.expander("Xem retrieved contexts"):
            for i, context in enumerate(result.retrieved_contexts, 1):
                st.markdown(f"**Context {i}**")
                st.write(context)


def render_evaluation(settings):
    st.title("📊 Evaluation & Reports")
    metrics = read_json(settings.paths.baseline_metrics, {})
    answers = read_json(settings.paths.baseline_answers, [])
    corrupted = read_json(settings.paths.corrupted_metrics, {})
    repaired = read_json(settings.paths.repaired_metrics, {})

    if metrics:
        st.subheader("Baseline / Corrupted / Repaired")
        keys = ["retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"]
        rows = []
        for key in keys:
            rows.append({"Metric": key, "Baseline": metrics.get(key), "Corrupted": corrupted.get(key), "Repaired": repaired.get(key)})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Chưa có baseline metrics. Hãy chạy script/run_phase1.py.")

    if answers:
        st.subheader("Baseline answers")
        answer_df = pd.DataFrame(answers)
        columns = [c for c in ["id", "question_type", "question", "answer", "answer_mode", "retrieval_hit", "token_f1"] if c in answer_df]
        st.dataframe(answer_df[columns], use_container_width=True, hide_index=True)

    for title, path in [("Phase 1 report", settings.paths.baseline_report), ("Corruption report", settings.paths.comparison_report)]:
        if path.exists():
            with st.expander(title):
                st.markdown(path.read_text(encoding="utf-8"))


def render_data(settings):
    st.title("🗂️ Clean data explorer")
    if not settings.paths.clean_csv.exists():
        st.warning("Chưa có papers_clean.csv.")
        return
    df = pd.read_csv(settings.paths.clean_csv)
    st.write(f"Rows: **{len(df)}** · Columns: **{len(df.columns)}**")
    search = st.text_input("Lọc theo title / paper_id")
    if search:
        mask = df["title"].fillna("").str.contains(search, case=False, regex=False) | df["paper_id"].fillna("").str.contains(search, case=False, regex=False)
        df = df[mask]
    st.dataframe(df, use_container_width=True, hide_index=True)


def main():
    settings = get_settings()
    try:
        index = get_index()
    except Exception as exc:
        st.error(str(exc))
        st.code("python script/run_phase1.py")
        st.stop()

    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Chọn màn hình", ["Overview", "Semantic Search", "Ask RAG", "Evaluation", "Clean Data"])
    st.sidebar.divider()
    st.sidebar.caption(f"Provider: {settings.llm_provider}")
    st.sidebar.caption(f"Model: {settings.model_name}")
    st.sidebar.caption(f"Embedding: {settings.embedding_model}")
    st.sidebar.caption(f"Collection: {index.collection_name}")

    if page == "Overview":
        render_overview(settings)
    elif page == "Semantic Search":
        render_search(index, settings)
    elif page == "Ask RAG":
        render_qa(index, settings)
    elif page == "Evaluation":
        render_evaluation(settings)
    else:
        render_data(settings)


if __name__ == "__main__":
    main()
