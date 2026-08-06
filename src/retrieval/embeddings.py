from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer


@lru_cache(maxsize=4)
def _load_model(model_name: str) -> SentenceTransformer:
    return SentenceTransformer(model_name)


class MiniLMEmbeddings(Embeddings):
    def __init__(self, model_name: str):
        self.model = _load_model(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        embedding = self.model.encode([text], normalize_embeddings=True)
        return embedding[0].tolist()

if __name__ == "__main__":
    model_name = "sentence-transformers/all-MiniLM-L6-v2"
    embeddings = MiniLMEmbeddings(model_name)
    project_dir = Path(__file__).resolve().parents[2]
    clean_path = project_dir / "data" / "clean" / "papers_clean.csv"
    df = pd.read_csv(clean_path)
    texts = df["text_for_embedding"].fillna("").astype(str).tolist()
    vectors = embeddings.embed_documents(texts)
    print(f"Loaded documents: {len(texts)}")
    print(f"Embedding dimension: {len(vectors[0]) if vectors else 0}")
    print(f"Clean data source: {clean_path}")
