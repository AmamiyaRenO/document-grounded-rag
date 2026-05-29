"""Thin retrieval layer over the vector store.

Holds a single lazily-built ``VectorStore`` so the index (and the embedding model)
are constructed once per process and reused across requests.
"""

from __future__ import annotations

from .config import settings
from .vector_store import RetrievedChunk, VectorStore

_store: VectorStore | None = None


def get_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore.from_docs()
    return _store


def warmup() -> VectorStore:
    """Eagerly build the index (called on app startup)."""
    return get_store()


def retrieve(question: str, top_k: int | None = None) -> list[RetrievedChunk]:
    k = top_k if top_k is not None else settings.top_k
    return get_store().search(question, k)
