"""In-memory FAISS vector store over the document chunks.

The corpus is tiny, so we build a flat inner-product index at startup. Because the
embeddings are L2-normalized, inner product equals cosine similarity directly.
"""

from __future__ import annotations

from dataclasses import dataclass

import faiss
import numpy as np

from .embeddings import embed, embed_one
from .ingest import Chunk, load_chunks


@dataclass
class RetrievedChunk:
    chunk: Chunk
    similarity_score: float


class VectorStore:
    def __init__(self, chunks: list[Chunk]):
        if not chunks:
            raise ValueError("Cannot build a vector store from zero chunks.")
        self.chunks = chunks
        matrix = embed([c.text for c in chunks])
        self.dim = matrix.shape[1]
        self.index = faiss.IndexFlatIP(self.dim)
        self.index.add(matrix)

    @classmethod
    def from_docs(cls) -> "VectorStore":
        return cls(load_chunks())

    def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        query_vec = embed_one(query).reshape(1, -1)
        k = min(top_k, len(self.chunks))
        scores, indices = self.index.search(query_vec, k)
        results: list[RetrievedChunk] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:  # FAISS pads with -1 when fewer than k results exist
                continue
            results.append(
                RetrievedChunk(
                    chunk=self.chunks[int(idx)],
                    similarity_score=round(float(score), 4),
                )
            )
        return results
