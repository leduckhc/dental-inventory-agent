"""FAISS vector index over med_info.txt documents.

Built once at agent startup. Uses BAAI/bge-base-en-v1.5 for local embeddings.
No OpenAI API key required.
"""

from functools import lru_cache
from typing import List, Tuple

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from app.rag.loader import load_med_documents

EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"
TOP_K = 3
SIMILARITY_THRESHOLD = 0.4  # below this score → agent should admit it doesn't know


@lru_cache(maxsize=1)
def get_index() -> FAISS:
    """Build and cache the FAISS index (called once at startup)."""
    docs = load_med_documents()
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
    return FAISS.from_documents(docs, embeddings)


def query_knowledge_base(query: str, k: int = TOP_K) -> Tuple[str, float]:
    """Return (context_text, best_similarity_score).

    The caller (tool) should instruct the LLM to admit ignorance when
    best_score < SIMILARITY_THRESHOLD.
    """
    index = get_index()
    results: List[Tuple[Document, float]] = index.similarity_search_with_score(query, k=k)

    if not results:
        return "", 0.0

    # FAISS returns L2 distance; lower = more similar.
    # Convert to a 0–1 similarity score: sim = 1 / (1 + distance)
    docs_and_scores = [(doc, 1.0 / (1.0 + dist)) for doc, dist in results]
    docs_and_scores.sort(key=lambda x: x[1], reverse=True)

    best_score = docs_and_scores[0][1]
    context = "\n\n---\n\n".join(doc.page_content for doc, _ in docs_and_scores)

    return context, best_score
