from django.conf import settings
from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from chat.services.answer import llm_enabled, mode, ollama_status, provider
from documents.services.embeddings import get_embedder


@api_view(["GET"])
@permission_classes([AllowAny])
def status_view(_request):
    """What's configured, so the UI can explain answer quality honestly."""
    embedder = get_embedder()
    return Response({
        "llm": llm_enabled(),
        "provider": provider(),  # anthropic | gemini | ollama | extractive
        "model": mode() if llm_enabled() else None,
        "ollama": ollama_status(),  # ready | no-model | offline (lets the UI give setup hints)
        "ollama_model": settings.OLLAMA_MODEL,
        "embeddings": embedder.name,
        "embeddings_local_model": not embedder.name.startswith("hashing"),
        "max_upload_mb": settings.MAX_UPLOAD_MB,
    })


urlpatterns = [path("status/", status_view)]
