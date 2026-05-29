"""Local embedding model wrapper (sentence-transformers).

Embeddings are computed locally so retrieval requires no API key. Vectors are
L2-normalized, which lets a FAISS inner-product index act as a cosine-similarity index.
The model is loaded lazily and cached so the (slow) first load happens once.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from .config import settings


@lru_cache(maxsize=1)
def _get_model():
    # Imported lazily so importing this module (e.g. in unit tests that don't embed)
    # does not pay the sentence-transformers/torch import cost.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model)


def embed(texts: list[str]) -> np.ndarray:
    """Return an ``(n, dim)`` float32 array of L2-normalized embeddings."""
    model = _get_model()
    vectors = model.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(vectors, dtype="float32")


def embed_one(text: str) -> np.ndarray:
    """Embed a single string and return a 1-D vector."""
    return embed([text])[0]
