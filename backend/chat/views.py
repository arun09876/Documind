"""Conversations API. /ask streams the answer as Server-Sent Events:

  event: sources  {"sources": [...numbered passages...]}
  event: delta    {"text": "..."}                       (many)
  event: done     {"message_id": 7, "cited": [1, 3], "mode": "claude-opus-5"}
  event: error    {"error": "..."}
"""
import json
import logging
import re

from django.conf import settings
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from documents.models import Document
from documents.services import retrieval

from .models import Conversation, Message
from .services import answer as answering
from .services.grounding import cited_sources, retrieval_query, source_payload, strip_invalid_citations

log = logging.getLogger(__name__)
HISTORY_TURNS = 6
MAX_QUESTION_CHARS = 2000


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ["id", "role", "content", "sources", "cited", "mode", "created_at"]


class ConversationSerializer(serializers.ModelSerializer):
    document_ids = serializers.PrimaryKeyRelatedField(source="documents", many=True, queryset=Document.objects.none(), required=False)
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = ["id", "title", "document_ids", "messages", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None:
            # Only the user's own documents can be put in scope.
            self.fields["document_ids"].child_relation.queryset = Document.objects.filter(user=request.user)


class ConversationListSerializer(serializers.ModelSerializer):
    document_ids = serializers.PrimaryKeyRelatedField(source="documents", many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = ["id", "title", "document_ids", "created_at", "updated_at"]


_MARKER = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")


def paired_history(previous: list[Message]) -> list[dict]:
    """Earlier complete Q&A pairs, alternating user/assistant as the API requires.

    Citation markers are removed from past answers: they refer to that turn's
    sources, not to the new ones.
    """
    history: list[dict] = []
    for question, reply in zip(previous, previous[1:]):
        if question.role == Message.Role.USER and reply.role == Message.Role.ASSISTANT:
            history.append({"role": "user", "content": question.content})
            history.append({"role": "assistant", "content": _MARKER.sub("", reply.content).strip()})
    return history


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


class ConversationViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user).prefetch_related("documents", "messages")

    def get_serializer_class(self):
        return ConversationListSerializer if self.action == "list" else ConversationSerializer

    def get_throttles(self):
        if self.action == "ask":
            self.throttle_scope = "ask"
        return super().get_throttles()

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["post"])
    def ask(self, request, pk=None):
        conversation = self.get_object()
        question = str(request.data.get("question", "")).strip()
        if not question:
            return Response({"error": "Ask a question first."}, status=status.HTTP_400_BAD_REQUEST)
        if len(question) > MAX_QUESTION_CHARS:
            return Response({"error": f"Questions can be up to {MAX_QUESTION_CHARS} characters."}, status=status.HTTP_400_BAD_REQUEST)

        previous = list(conversation.messages.order_by("-created_at", "-id")[: HISTORY_TURNS * 2])[::-1]
        previous_question = next((m.content for m in reversed(previous) if m.role == Message.Role.USER), None)
        Message.objects.create(conversation=conversation, role=Message.Role.USER, content=question)
        if conversation.title == "New chat":
            conversation.title = question[:117] + ("…" if len(question) > 117 else "")
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=["title", "updated_at"])

        scope = list(conversation.documents.values_list("id", flat=True)) or None
        hits = retrieval.search(request.user.id, retrieval_query(question, previous_question), k=settings.RETRIEVAL_TOP_K, document_ids=scope)
        sources = source_payload(hits)
        history = paired_history(previous)

        def events():
            yield sse("sources", {"sources": sources})
            parts: list[str] = []
            try:
                for delta in answering.stream_answer(question, hits, history):
                    parts.append(delta)
                    yield sse("delta", {"text": delta})
            except answering.AnswerError as exc:
                yield sse("error", {"error": str(exc)})
                return
            except Exception:  # noqa: BLE001 - never leave the client hanging mid-stream
                log.exception("Answer generation failed")
                yield sse("error", {"error": "Something went wrong while generating the answer."})
                return

            text = strip_invalid_citations("".join(parts), len(sources))
            cited = cited_sources(text, len(sources))
            msg = Message.objects.create(conversation=conversation, role=Message.Role.ASSISTANT, content=text,
                                         sources=sources, cited=cited, mode=answering.mode())
            yield sse("done", {"message_id": msg.id, "cited": cited, "mode": msg.mode, "content": text})

        response = StreamingHttpResponse(events(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"  # tell nginx not to buffer the stream
        return response

