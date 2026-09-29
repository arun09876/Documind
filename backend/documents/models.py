import uuid

from django.conf import settings
from django.db import models


def upload_path(instance: "Document", filename: str) -> str:
    # Random names: the original filename is kept in `filename`, never used on disk.
    return f"documents/{instance.user_id}/{uuid.uuid4().hex}.pdf"


class Document(models.Model):
    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=255)
    filename = models.CharField(max_length=255)
    file = models.FileField(upload_to=upload_path)
    size_bytes = models.PositiveBigIntegerField(default=0)
    page_count = models.PositiveIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROCESSING, db_index=True)
    error = models.CharField(max_length=300, blank=True)
    embedding_model = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class Chunk(models.Model):
    """A passage of a document plus its embedding (float32 bytes, L2-normalized)."""

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    index = models.PositiveIntegerField()
    text = models.TextField()
    page_start = models.PositiveIntegerField()
    page_end = models.PositiveIntegerField()
    embedding = models.BinaryField()
    embedding_model = models.CharField(max_length=80, db_index=True)

    class Meta:
        ordering = ["document", "index"]
        constraints = [models.UniqueConstraint(fields=["document", "index"], name="unique_chunk_index")]

    def __str__(self) -> str:
        return f"{self.document_id}#{self.index} (p.{self.page_start})"
