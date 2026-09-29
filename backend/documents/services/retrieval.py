"""Hybrid retrieval: dense vectors + BM25, merged with reciprocal rank fusion.

Why both: embeddings find paraphrases ("time off for a new baby" → parental
leave), while BM25 nails exact tokens that embeddings blur (policy codes,
product names, numbers). RRF combines the two rankings without having to
calibrate their very different score scales.

Each user's library is loaded into an in-memory matrix and cached until their
chunks change. Brute-force cosine over a normalized float32 matrix is exact and
fast for tens of thousands of chunks; a larger deployment would swap this class
for pgvector or a dedicated ANN index behind the same `search` interface.
"""
from __future__ import annotations

import math
import re
import threading
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from django.db.models import Count, Max

from documents.models import Chunk, Document

from .embeddings import get_embedder

RRF_K = 60
CANDIDATES = 30
_TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    "a an and are as at be but by can do does for from how i if in into is it its me my of on or our so "
    "that the their them then there these they this to up was we what when where which who why will with "
    "you your".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS]


class BM25:
    """Okapi BM25 over an inverted index (term -> [(chunk position, term frequency)])."""

    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.n = len(docs)
        self.len = np.array([len(d) for d in docs], dtype=np.float32)
        self.avg = float(self.len.mean()) if docs else 0.0
        self.postings: dict[str, list[tuple[int, int]]] = {}
        for i, d in enumerate(docs):
            for term, f in Counter(d).items():
                self.postings.setdefault(term, []).append((i, f))
        self.idf = {t: math.log(1 + (self.n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.postings.items()}

    def scores(self, query: list[str]) -> np.ndarray:
        out = np.zeros(self.n, dtype=np.float32)
        for term in set(query):
            for i, f in self.postings.get(term, ()):
                denom = f + self.k1 * (1 - self.b + self.b * self.len[i] / (self.avg or 1))
                out[i] += self.idf[term] * f * (self.k1 + 1) / denom
        return out


@dataclass
class _Library:
    version: tuple
    chunk_ids: list[int]
    doc_ids: np.ndarray
    matrix: np.ndarray
    bm25: BM25
    meta: dict[int, dict] = field(default_factory=dict)


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    document_id: int
    document_title: str
    text: str
    page_start: int
    page_end: int
    score: float
    vector_rank: int | None
    keyword_rank: int | None


_cache: dict[int, _Library] = {}
_cache_lock = threading.Lock()


def _version(user_id: int, model: str) -> tuple:
    agg = Chunk.objects.filter(document__user_id=user_id, document__status=Document.Status.READY, embedding_model=model).aggregate(
        n=Count("id"), last=Max("id"), docs=Count("document", distinct=True)
    )
    return (model, agg["n"], agg["last"], agg["docs"])


def _load(user_id: int) -> _Library:
    model = get_embedder().name
    version = _version(user_id, model)
    with _cache_lock:
        cached = _cache.get(user_id)
        if cached and cached.version == version:
            return cached

    rows = list(
        Chunk.objects.filter(document__user_id=user_id, document__status=Document.Status.READY, embedding_model=model)
        .select_related("document")
        .order_by("id")
    )
    dim = get_embedder().dim
    matrix = (
        np.frombuffer(b"".join(bytes(r.embedding) for r in rows), dtype=np.float32).reshape(len(rows), dim)
        if rows else np.zeros((0, dim), dtype=np.float32)
    )
    library = _Library(
        version=version,
        chunk_ids=[r.id for r in rows],
        doc_ids=np.array([r.document_id for r in rows], dtype=np.int64),
        matrix=matrix,
        bm25=BM25([tokenize(r.text) for r in rows]),
        meta={r.id: {"document_id": r.document_id, "title": r.document.title, "text": r.text,
                     "page_start": r.page_start, "page_end": r.page_end} for r in rows},
    )
    with _cache_lock:
        _cache[user_id] = library
    return library


def invalidate(user_id: int) -> None:
    with _cache_lock:
        _cache.pop(user_id, None)


def search(user_id: int, query: str, k: int = 6, document_ids: list[int] | None = None) -> list[Hit]:
    lib = _load(user_id)
    if not lib.chunk_ids or not query.strip():
        return []

    allowed = np.ones(len(lib.chunk_ids), dtype=bool)
    if document_ids:
        allowed = np.isin(lib.doc_ids, np.array(document_ids, dtype=np.int64))
    if not allowed.any():
        return []

    q = get_embedder().embed_query(query)
    dense = lib.matrix @ q
    dense[~allowed] = -np.inf
    sparse = lib.bm25.scores(tokenize(query))
    sparse[~allowed] = -np.inf

    dense_order = [i for i in np.argsort(-dense)[:CANDIDATES] if np.isfinite(dense[i])]
    sparse_order = [i for i in np.argsort(-sparse)[:CANDIDATES] if np.isfinite(sparse[i]) and sparse[i] > 0]

    fused: dict[int, float] = {}
    vector_rank: dict[int, int] = {}
    keyword_rank: dict[int, int] = {}
    for rank, i in enumerate(dense_order):
        fused[i] = fused.get(i, 0.0) + 1 / (RRF_K + rank + 1)
        vector_rank[i] = rank + 1
    for rank, i in enumerate(sparse_order):
        fused[i] = fused.get(i, 0.0) + 1 / (RRF_K + rank + 1)
        keyword_rank[i] = rank + 1

    best = sorted(fused, key=lambda i: -fused[i])[:k]
    hits = []
    for i in best:
        m = lib.meta[lib.chunk_ids[i]]
        hits.append(Hit(lib.chunk_ids[i], m["document_id"], m["title"], m["text"], m["page_start"], m["page_end"],
                        round(fused[i], 5), vector_rank.get(i), keyword_rank.get(i)))
    return hits
