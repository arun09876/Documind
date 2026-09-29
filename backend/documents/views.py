from django.conf import settings
from django.http import FileResponse
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from .models import Chunk, Document
from .services import ingest, retrieval


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["id", "title", "filename", "size_bytes", "page_count", "chunk_count", "status", "error",
                  "embedding_model", "created_at", "processed_at"]


class ChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chunk
        fields = ["id", "index", "text", "page_start", "page_end"]


class DocumentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    serializer_class = DocumentSerializer
    parser_classes = [MultiPartParser]

    def get_queryset(self):
        return Document.objects.filter(user=self.request.user)

    def get_throttles(self):
        if self.action == "create":
            self.throttle_scope = "upload"
        return super().get_throttles()

    def create(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"error": "Attach a PDF in the `file` field."}, status=status.HTTP_400_BAD_REQUEST)
        if upload.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            return Response({"error": f"PDFs can be up to {settings.MAX_UPLOAD_MB} MB."}, status=status.HTTP_400_BAD_REQUEST)
        head = upload.read(5)
        upload.seek(0)
        if not upload.name.lower().endswith(".pdf") or head != b"%PDF-":
            return Response({"error": "Only PDF files are supported."}, status=status.HTTP_400_BAD_REQUEST)

        name = upload.name[:255]
        doc = Document.objects.create(user=request.user, title=name.rsplit(".", 1)[0][:255], filename=name,
                                      file=upload, size_bytes=upload.size)
        ingest.schedule(doc.id)
        return Response(DocumentSerializer(doc).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        instance.file.delete(save=False)
        instance.delete()
        retrieval.invalidate(self.request.user.id)

    @action(detail=True, methods=["get"])
    def file(self, request, pk=None):
        """The original PDF, for the in-app viewer. Owner only (via get_queryset)."""
        doc = self.get_object()
        response = FileResponse(doc.file.open("rb"), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{doc.filename}"'
        response["Cache-Control"] = "private, max-age=3600"
        return response

    @action(detail=True, methods=["get"])
    def chunks(self, request, pk=None):
        """How the document was split: useful for understanding (and debugging) retrieval."""
        doc = self.get_object()
        return Response(ChunkSerializer(doc.chunks.all(), many=True).data)
