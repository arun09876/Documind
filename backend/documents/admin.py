from django.contrib import admin

from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "user", "status", "page_count", "chunk_count", "embedding_model", "created_at"]
    list_filter = ["status", "embedding_model"]
    search_fields = ["title", "filename"]
