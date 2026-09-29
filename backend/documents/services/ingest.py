"""Ingestion pipeline: PDF → page texts → chunks → embeddings → stored, searchable.

Runs on a small background thread pool so uploads return immediately; the UI
polls the document's status. (A bigger deployment would move this to Celery or
RQ; the function below is already a self-contained unit of work.)
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from documents.models import Chunk, Document

from . import retrieval
from .chunking import chunk_pages
from .embeddings import get_embedder
from .pdf import PdfError, extract_pages

log = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ingest")


def schedule(document_id: int) -> None:
    """Process after the current transaction commits (so the worker sees the row)."""
    if settings.INGEST_SYNC:
        transaction.on_commit(lambda: process(document_id))
    else:
        transaction.on_commit(lambda: _pool.submit(_run_in_thread, document_id))


def _run_in_thread(document_id: int) -> None:
    close_old_connections()
    try:
        process(document_id)
    finally:
        close_old_connections()


def process(document_id: int) -> None:
    doc = Document.objects.get(pk=document_id)
    try:
        with doc.file.open("rb") as f:
            data = f.read()
        pages, meta = extract_pages(data, settings.MAX_PDF_PAGES)
        pieces = chunk_pages(pages, settings.CHUNK_TARGET_CHARS, settings.CHUNK_OVERLAP_CHARS)
        embedder = get_embedder()
        vectors = embedder.embed_passages([p.text for p in pieces])

        with transaction.atomic():
            doc.chunks.all().delete()
            Chunk.objects.bulk_create(
                [
                    Chunk(document=doc, index=p.index, text=p.text, page_start=p.page_start, page_end=p.page_end,
                          embedding=vectors[i].tobytes(), embedding_model=embedder.name)
                    for i, p in enumerate(pieces)
                ],
                batch_size=500,
            )
            if meta.get("title") and doc.title == doc.filename.rsplit(".", 1)[0]:
                doc.title = meta["title"][:255]
            doc.page_count = meta["page_count"]
            doc.chunk_count = len(pieces)
            doc.embedding_model = embedder.name
            doc.status = Document.Status.READY
            doc.error = ""
            doc.processed_at = timezone.now()
            doc.save()
        log.info("Ingested %s: %d pages, %d chunks", doc.filename, doc.page_count, doc.chunk_count)
    except PdfError as exc:
        _fail(doc, str(exc))
    except Exception:  # noqa: BLE001 - record the failure instead of leaving the doc "processing" forever
        log.exception("Ingestion failed for document %s", document_id)
        _fail(doc, "Something went wrong while processing this file.")
    finally:
        retrieval.invalidate(doc.user_id)


def _fail(doc: Document, message: str) -> None:
    Document.objects.filter(pk=doc.pk).update(status=Document.Status.FAILED, error=message[:300], processed_at=timezone.now())
