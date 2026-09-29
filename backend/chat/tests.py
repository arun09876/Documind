import json
import shutil
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from chat.models import Message
from chat.services.grounding import cited_sources, retrieval_query, strip_invalid_citations
from chat.views import paired_history
from documents.models import Document
from documents.tests import make_pdf

User = get_user_model()


def parse_sse(response) -> list[tuple[str, dict]]:
    body = b"".join(response.streaming_content).decode()
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


class GroundingTests(TestCase):
    def test_cited_sources_handles_lists_and_ignores_invalid(self):
        self.assertEqual(cited_sources("A [2]. B [1, 3]. C [2][9].", 3), [2, 1, 3])

    def test_invalid_markers_are_removed(self):
        self.assertEqual(strip_invalid_citations("Fact [1][7]. Other [2, 8].", 2), "Fact [1]. Other [2].")

    def test_short_follow_ups_borrow_the_previous_question(self):
        self.assertIn("parental leave", retrieval_query("and sick leave?", "How much parental leave?"))
        long_q = "What is the policy on working from another country for a month?"
        self.assertEqual(retrieval_query(long_q, "anything"), long_q)

    def test_extractive_mode_admits_weak_matches_and_splits_bullets(self):
        from chat.services.answer import _stream_extractive
        from documents.services.retrieval import Hit

        resume = Hit(1, 1, "resume.pdf", "Priya Sharma: Software Engineer. PROJECTS • Student Management System built with Django. "
                     "• Built secure workflows for student records.", 1, 1, 1.0, 1, 1)
        with patch("chat.services.answer.time.sleep"):
            weak = "".join(_stream_extractive("What is the name of the student?", [resume]))
            strong = "".join(_stream_extractive("Which framework built the student management system?", [resume]))
        self.assertIn("couldn't find a sentence that directly answers", weak)
        self.assertNotIn("couldn't find", strong)
        self.assertIn("- Student Management System built with Django. [1]", strong)  # one bullet, not a run-on

    def test_ollama_stream_is_parsed_and_errors_are_friendly(self):
        from chat.services import answer
        from documents.services.retrieval import Hit

        hit = Hit(1, 1, "doc.pdf", "Core hours are 11:00 to 16:00.", 1, 1, 1.0, 1, 1)
        lines = [json.dumps({"message": {"content": "Core hours "}, "done": False}),
                 json.dumps({"message": {"content": "are 11-16 [1]."}, "done": False}), json.dumps({"done": True})]

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def iter_lines(self):
                return iter(lines)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch("chat.services.answer.httpx.stream", return_value=FakeResponse()) as stream:
            self.assertEqual("".join(answer._stream_ollama("When?", [hit], [])), "Core hours are 11-16 [1].")
        payload = stream.call_args.kwargs["json"]
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertGreaterEqual(payload["options"]["num_ctx"], 8192)  # never Ollama's small default

        FakeResponse.status_code = 404
        with patch("chat.services.answer.httpx.stream", return_value=FakeResponse()):
            with self.assertRaisesMessage(answer.AnswerError, "ollama pull"):
                list(answer._stream_ollama("When?", [hit], []))

    def test_gemini_stream_is_parsed_and_errors_are_friendly(self):
        from chat.services import answer
        from documents.services.retrieval import Hit

        hit = Hit(1, 1, "doc.pdf", "Core hours are 11:00 to 16:00.", 1, 1, 1.0, 1, 1)
        chunk = lambda text, **extra: "data: " + json.dumps(  # noqa: E731
            {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, **extra}]})

        class FakeResponse:
            status_code = 200
            lines = [chunk("Core hours "), "", chunk("are 11-16 [1].", finishReason="STOP")]
            body = b""

            def iter_lines(self):
                return iter(self.lines)

            def read(self):
                return self.body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        history = [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"}]
        with override_settings(GEMINI_API_KEY="key", GEMINI_MODEL="gemini-test"), \
                patch("chat.services.answer.httpx.stream", return_value=FakeResponse()) as stream:
            self.assertEqual("".join(answer._stream_gemini("When?", [hit], history)), "Core hours are 11-16 [1].")
        self.assertIn("models/gemini-test:streamGenerateContent", stream.call_args.args[1])
        self.assertEqual(stream.call_args.kwargs["headers"]["x-goog-api-key"], "key")  # key in a header, not the URL
        payload = stream.call_args.kwargs["json"]
        self.assertEqual([c["role"] for c in payload["contents"]], ["user", "model", "user"])
        self.assertIn("parts", payload["systemInstruction"])

        FakeResponse.status_code = 400
        FakeResponse.body = json.dumps({"error": {"code": 400, "message": "API key not valid.", "status": "INVALID_ARGUMENT",
                                                  "details": [{"reason": "API_KEY_INVALID"}]}}).encode()
        with patch("chat.services.answer.httpx.stream", return_value=FakeResponse()):
            with self.assertRaisesMessage(answer.AnswerError, "GEMINI_API_KEY"):
                list(answer._stream_gemini("When?", [hit], []))
        FakeResponse.status_code = 429
        FakeResponse.body = b'{"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}}'
        with patch("chat.services.answer.httpx.stream", return_value=FakeResponse()):
            with self.assertRaisesMessage(answer.AnswerError, "rate limit"):
                list(answer._stream_gemini("When?", [hit], []))

    def test_provider_auto_prefers_claude_then_gemini_then_ollama_then_extractive(self):
        from chat.services import answer

        with override_settings(LLM_PROVIDER="auto", ANTHROPIC_API_KEY="k", GEMINI_API_KEY="g"):
            self.assertEqual(answer.provider(), "anthropic")
        with override_settings(LLM_PROVIDER="auto", ANTHROPIC_API_KEY="", GEMINI_API_KEY="g"):
            self.assertEqual(answer.provider(), "gemini")
        with override_settings(LLM_PROVIDER="auto", ANTHROPIC_API_KEY="", GEMINI_API_KEY=""):
            with patch("chat.services.answer.ollama_status", return_value="ready"):
                self.assertEqual(answer.provider(), "ollama")
            with patch("chat.services.answer.ollama_status", return_value="offline"):
                self.assertEqual(answer.provider(), "extractive")

    def test_history_only_contains_complete_pairs(self):
        m = lambda role, text: Message(role=role, content=text)  # noqa: E731
        previous = [m("user", "q1"), m("assistant", "a1 [1]"), m("user", "q2 (failed, no answer)")]
        self.assertEqual(paired_history(previous), [{"role": "user", "content": "q1"}, {"role": "assistant", "content": "a1"}])


TEST_MEDIA = tempfile.mkdtemp(prefix="documind-test-")


@override_settings(INGEST_SYNC=True, EMBEDDING_BACKEND="hash", ANTHROPIC_API_KEY="", LLM_PROVIDER="extractive", MEDIA_ROOT=TEST_MEDIA)
class ApiTests(TestCase):
    def setUp(self):
        from documents.services import embeddings

        embeddings._build.cache_clear()
        self.user = User.objects.create_user("alice", "alice@example.com", "pw-Strong-123")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def tearDown(self):
        from documents.services import embeddings

        embeddings._build.cache_clear()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA, ignore_errors=True)

    def upload(self, pages, name="notes.pdf", client=None):
        client = client or self.client
        with self.captureOnCommitCallbacks(execute=True):
            response = client.post("/api/documents/", {"file": SimpleUploadedFile(name, make_pdf(pages), "application/pdf")})
        return response

    def test_upload_ingests_and_lists_document(self):
        r = self.upload(["The warranty lasts 36 months from purchase.", "Returns are accepted within 14 days."])
        self.assertEqual(r.status_code, 201, r.data)
        doc = Document.objects.get(pk=r.data["id"])
        self.assertEqual(doc.status, Document.Status.READY)
        self.assertEqual(doc.page_count, 2)
        chunks = self.client.get(f"/api/documents/{doc.id}/chunks/").json()
        self.assertEqual({c["page_start"] for c in chunks}, {1, 2})

    def test_rejects_non_pdf(self):
        r = self.client.post("/api/documents/", {"file": SimpleUploadedFile("x.pdf", b"not a pdf", "application/pdf")})
        self.assertEqual(r.status_code, 400)

    def test_ask_streams_sources_answer_and_citations(self):
        self.upload(["The warranty lasts 36 months from purchase. It covers manufacturing defects.",
                     "Returns are accepted within 14 days if the product is unused."])
        conv = self.client.post("/api/conversations/", {}, format="json").json()
        response = self.client.post(f"/api/conversations/{conv['id']}/ask/", {"question": "How long is the warranty?"}, format="json")
        self.assertEqual(response["Content-Type"], "text/event-stream")
        events = parse_sse(response)
        kinds = [e for e, _ in events]
        self.assertEqual(kinds[0], "sources")
        self.assertIn("delta", kinds)
        self.assertEqual(kinds[-1], "done")

        sources = events[0][1]["sources"]
        self.assertEqual(sources[0]["page_start"], 1)  # the warranty page ranks first
        done = events[-1][1]
        self.assertEqual(done["mode"], "extractive")
        self.assertIn(1, done["cited"])
        self.assertIn("36 months", done["content"])

        detail = self.client.get(f"/api/conversations/{conv['id']}/").json()
        self.assertEqual([m["role"] for m in detail["messages"]], ["user", "assistant"])
        self.assertEqual(detail["title"], "How long is the warranty?")

    def test_llm_answer_is_streamed_and_invalid_citations_removed(self):
        self.upload(["Office hours are 11:00 to 16:00 on weekdays."])
        conv = self.client.post("/api/conversations/", {}, format="json").json()
        with override_settings(ANTHROPIC_API_KEY="test", LLM_PROVIDER="anthropic"), \
                patch("chat.services.answer._stream_claude", return_value=iter(["Core hours are ", "11:00-16:00 [1][4]."])):
            events = parse_sse(self.client.post(f"/api/conversations/{conv['id']}/ask/", {"question": "When are core hours?"}, format="json"))
        done = events[-1][1]
        self.assertEqual(done["content"], "Core hours are 11:00-16:00 [1].")
        self.assertEqual(done["cited"], [1])
        self.assertEqual(done["mode"], "claude-opus-5")

    def test_scope_limits_search_to_selected_documents(self):
        a = self.upload(["Apples are red and crunchy."], name="apples.pdf").data["id"]
        self.upload(["Bananas are yellow and sweet."], name="bananas.pdf")
        conv = self.client.post("/api/conversations/", {"document_ids": [a]}, format="json").json()
        events = parse_sse(self.client.post(f"/api/conversations/{conv['id']}/ask/", {"question": "What colour are bananas?"}, format="json"))
        self.assertTrue(all(s["document_id"] == a for s in events[0][1]["sources"]))

    def test_users_cannot_see_or_search_each_others_documents(self):
        doc_id = self.upload(["Secret launch date is March 3."]).data["id"]
        bob = APIClient()
        bob.force_authenticate(User.objects.create_user("bob", "bob@example.com", "pw-Strong-123"))
        self.assertEqual(bob.get(f"/api/documents/{doc_id}/file/").status_code, 404)
        self.assertEqual(bob.get("/api/documents/").json(), [])
        r = bob.post("/api/conversations/", {"document_ids": [doc_id]}, format="json")
        self.assertEqual(r.status_code, 400)  # can't scope a chat to someone else's document
        conv = bob.post("/api/conversations/", {}, format="json").json()
        events = parse_sse(bob.post(f"/api/conversations/{conv['id']}/ask/", {"question": "launch date"}, format="json"))
        self.assertEqual(events[0][1]["sources"], [])

    def test_auth_flow(self):
        anon = APIClient()
        self.assertEqual(anon.get("/api/documents/").status_code, 401)
        r = anon.post("/api/auth/register/", {"username": "carol", "email": "carol@example.com", "password": "Sup3r-secret!"}, format="json")
        self.assertEqual(r.status_code, 201)
        login = anon.post("/api/auth/login/", {"username": "carol@example.com", "password": "Sup3r-secret!"}, format="json")
        self.assertIn("access", login.json())
