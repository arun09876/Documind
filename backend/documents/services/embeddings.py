"""Text embeddings.

Default: BAAI/bge-small-en-v1.5 via fastembed (ONNX, CPU, ~70 MB download on
first use, no API key). If the model can't be loaded (for example offline),
a feature-hashing embedder keeps the app working: weaker semantically, but
hybrid search still has BM25 for exact terms.

Every chunk stores the name of the model that embedded it, so switching models
never mixes incompatible vectors in one search.
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
from functools import lru_cache

import numpy as np
from django.conf import settings

log = logging.getLogger(__name__)

_WORD = re.compile(r"[a-z0-9]+")


class Embedder:
    name: str
    dim: int

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError

    def embed_query(self, text: str) -> np.ndarray:
        raise NotImplementedError


def _normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


class LocalEmbedder(Embedder):
    """BGE small via fastembed. Queries get BGE's retrieval instruction prefix."""

    def __init__(self, model_name: str):
        from fastembed import TextEmbedding  # imported lazily: optional heavy dependency

        self._model = TextEmbedding(model_name=model_name)
        self._lock = threading.Lock()  # ONNX session: serialize calls from worker threads
        self.name = model_name
        self.dim = len(next(iter(self._model.embed(["probe"]))))

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        with self._lock:
            vectors = list(self._model.passage_embed(texts, batch_size=32))
        return _normalize(np.array(vectors, dtype=np.float32))

    def embed_query(self, text: str) -> np.ndarray:
        with self._lock:
            vector = next(iter(self._model.query_embed(text)))
        return _normalize(np.array([vector], dtype=np.float32))[0]


class HashingEmbedder(Embedder):
    """Deterministic feature hashing of words and word bigrams (offline fallback)."""

    def __init__(self, dim: int = 384):
        self.name = f"hashing-{dim}"
        self.dim = dim

    def _vector(self, text: str) -> np.ndarray:
        words = _WORD.findall(text.lower())
        features = words + [f"{a}_{b}" for a, b in zip(words, words[1:])]
        v = np.zeros(self.dim, dtype=np.float32)
        for f in features:
            h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "little")
            v[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        return v

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return _normalize(np.stack([self._vector(t) for t in texts]))

    def embed_query(self, text: str) -> np.ndarray:
        return _normalize(self._vector(text)[None, :])[0]


_lock = threading.Lock()


@lru_cache(maxsize=1)
def _build() -> Embedder:
    backend = settings.EMBEDDING_BACKEND.lower()
    if backend == "hash":
        return HashingEmbedder()
    try:
        embedder = LocalEmbedder(settings.EMBEDDING_MODEL)
        log.info("Embeddings: %s (%d dims, local ONNX)", embedder.name, embedder.dim)
        return embedder
    except Exception as exc:  # noqa: BLE001 - download/ONNX failures of many kinds
        if backend == "local":
            raise
        log.warning("Could not load %s (%s); falling back to hashing embeddings", settings.EMBEDDING_MODEL, exc)
        return HashingEmbedder()


def get_embedder() -> Embedder:
    with _lock:
        return _build()
