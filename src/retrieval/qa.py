from __future__ import annotations

from dataclasses import dataclass
import re

from core.config import Settings, load_settings
from core.utils import first_sentence
from retrieval.index import LocalEmbeddingIndex, SearchResult
from retrieval.llm import build_llm


@dataclass(frozen=True)
class AnswerResult:
    question: str
    answer: str
    retrieved_doc_ids: list[str]
    retrieved_contexts: list[str]
    retrieved_titles: list[str]
    answer_mode: str


def _extract_answer(question: str, top_result: SearchResult) -> str:
    lowered = question.lower()
    metadata = top_result.metadata
    if "who authored" in lowered or "list the authors" in lowered:
        return metadata["authors_joined"]
    if "when was" in lowered or "publication date" in lowered or "published on" in lowered:
        return metadata["published"]
    if "what categories" in lowered:
        return metadata["categories_joined"]
    return first_sentence(metadata["summary"])


def _generate_llm_answer(question: str, retrieved: list[SearchResult], settings: Settings) -> str:
    context = "\n\n".join(
        f"Document {index + 1}\nTitle: {item.title}\n{item.content}"
        for index, item in enumerate(retrieved)
    )
    prompt = (
        "Answer the question using only the scholarly paper context below.\n"
        "If the context does not contain the answer, say: I don't know from the indexed corpus.\n"
        "Be concise and do not invent facts. Return only the answer, without analysis.\n\n"
        f"Question: {question}\n\nContext:\n{context}"
    )
    response = build_llm(settings=settings, temperature=0.0).invoke(prompt)
    content = response.content if hasattr(response, "content") else str(response)
    if isinstance(content, list):
        content = " ".join(
            str(part.get("text", part)) if isinstance(part, dict) else str(part)
            for part in content
        )
    answer = str(content).strip()
    if not answer:
        raise ValueError("LLM returned an empty answer.")
    return answer


def answer_question(
    question: str,
    settings: Settings,
    index: LocalEmbeddingIndex,
    top_k: int | None = None,
    use_llm: bool = True,
) -> AnswerResult:
    title_match = re.search(r"'([^']+)'", question)
    exact = index.lookup(title_match.group(1)) if title_match else None
    retrieved = index.search(question, top_k=top_k)
    if exact:
        exact_result = SearchResult(
            paper_id=exact["paper_id"],
            title=exact["title"],
            score=1.0,
            content=exact["content"],
            metadata=exact["metadata"],
        )
        deduped = [exact_result] + [item for item in retrieved if item.paper_id != exact_result.paper_id]
        retrieved = deduped[: (top_k or settings.top_k)]
    answer_mode = "fallback"
    if not retrieved:
        answer = "I don't know from the indexed corpus."
    elif use_llm:
        try:
            answer = _generate_llm_answer(question, retrieved, settings)
            answer_mode = "llm"
        except Exception:
            answer = _extract_answer(question, retrieved[0])
    else:
        answer = _extract_answer(question, retrieved[0])
    return AnswerResult(
        question=question,
        answer=answer,
        retrieved_doc_ids=[item.paper_id for item in retrieved],
        retrieved_contexts=[item.content for item in retrieved],
        retrieved_titles=[item.title for item in retrieved],
        answer_mode=answer_mode,
    )

if __name__ == "__main__":
    settings = load_settings()
    index = LocalEmbeddingIndex.load(settings, settings.paths.embeddings_json)
    question = "What is the main contribution of 'Retrieval-Augmented Large Language Model Agents for Automated Scientific Literature Review Generation'?"
    result = answer_question(question, settings, index)
    print(f"Question: {result.question}")
    print(f"Answer: {result.answer}")
    print(f"Retrieved doc IDs: {result.retrieved_doc_ids}")
    print(f"Retrieved titles: {result.retrieved_titles}")
