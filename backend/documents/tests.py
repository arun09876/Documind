import io
import shutil
import tempfile

import numpy as np
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from fpdf import FPDF

from documents.services.chunking import chunk_pages
from documents.services.embeddings import HashingEmbedder
from documents.services.pdf import PdfError, clean_page_text, extract_pages
from documents.services.retrieval import BM25, tokenize

User = get_user_model()


def make_pdf(pages: list[str]) -> bytes:
    pdf = FPDF()
    for text in pages:
        pdf.add_page()
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(0, 6, text)
    return bytes(pdf.output())


class PdfTests(TestCase):
    def test_extracts_text_per_page(self):
        pages, meta = extract_pages(make_pdf(["First page about apples.", "Second page about pears."]), max_pages=10)
        self.assertEqual(meta["page_count"], 2)
        self.assertIn("apples", pages[0])
        self.assertIn("pears", pages[1])

    def test_rejects_non_pdf_and_too_many_pages(self):
        with self.assertRaisesMessage(PdfError, "isn't a PDF"):
            extract_pages(b"hello", max_pages=10)
        with self.assertRaisesMessage(PdfError, "the limit is 1"):
            extract_pages(make_pdf(["a" * 50, "b" * 50]), max_pages=1)

    def test_rejects_pdf_without_text(self):
        pdf = FPDF()
        pdf.add_page()
        with self.assertRaisesMessage(PdfError, "scanned PDF"):
            extract_pages(bytes(pdf.output()), max_pages=10)

    def test_cleaning_joins_hyphenated_words(self):
        self.assertEqual(clean_page_text("infor-\nmation   retrieval"), "information retrieval")

    def test_running_headers_and_page_numbers_are_removed(self):
        from documents.services.pdf import strip_running_lines

        pages = [f"ACME HANDBOOK\nSection {i} body text that differs.\nPage {i} of 3" for i in range(1, 4)]
        cleaned = strip_running_lines(pages)
        self.assertTrue(all("ACME HANDBOOK" not in p and "Page" not in p for p in cleaned))
        self.assertIn("Section 2 body text", cleaned[1])


class ChunkingTests(TestCase):
    def test_chunks_never_cross_pages_and_keep_page_numbers(self):
        pages = [" ".join(f"Page one sentence {i} is here." for i in range(40)), "Short second page. It has two sentences."]
        chunks = chunk_pages(pages, target_chars=300, overlap_chars=60)
        self.assertTrue(all(c.page_start == c.page_end for c in chunks))
        self.assertEqual(chunks[-1].page_start, 2)
        self.assertEqual([c.index for c in chunks], list(range(len(chunks))))

    def test_overlap_repeats_trailing_sentences(self):
        text = " ".join(f"Sentence number {i} ends here." for i in range(30))
        a, b = chunk_pages([text], target_chars=250, overlap_chars=80)[:2]
        last_sentence_of_a = a.text.rsplit(". ", 1)[-1]
        self.assertIn(last_sentence_of_a.rstrip("."), b.text)

    def test_every_sentence_is_kept(self):
        sentences = [f"Fact {i} is important." for i in range(50)]
        chunks = chunk_pages([" ".join(sentences)], target_chars=200, overlap_chars=40)
        joined = " ".join(c.text for c in chunks)
        self.assertTrue(all(s in joined for s in sentences))

    def test_heading_lines_are_joined_with_a_colon(self):
        chunks = chunk_pages(["Intro sentence ends here.\nSick leave\nYou are entitled to 12 days of paid sick leave."])
        self.assertIn("Sick leave: You are entitled", chunks[0].text)

    def test_label_value_lines_are_not_headings(self):
        chunks = chunk_pages(["Languages: Python, Java\nVersion Control: Git, GitHub\nWeb: HTML, CSS"])
        self.assertIn("Git, GitHub Web: HTML", chunks[0].text)
        self.assertNotIn("GitHub:", chunks[0].text)

    def test_wrapped_lines_are_not_mistaken_for_headings(self):
        chunks = chunk_pages(["The policy applies to\nAll staff in every office."])
        self.assertIn("applies to All staff", chunks[0].text)

    def test_very_long_sentence_is_split(self):
        chunks = chunk_pages(["word " * 1000], target_chars=300, overlap_chars=0)
        self.assertTrue(all(len(c.text) <= 300 * 1.4 + 1 for c in chunks))


class RetrievalUnitTests(TestCase):
    def test_bm25_prefers_rare_matching_terms(self):
        docs = [tokenize("the parental leave policy"), tokenize("the meal allowance policy"), tokenize("laptop refresh")]
        scores = BM25(docs).scores(tokenize("parental leave"))
        self.assertEqual(int(np.argmax(scores)), 0)
        self.assertEqual(scores[2], 0)

    def test_hashing_embedder_is_normalized_and_deterministic(self):
        e = HashingEmbedder()
        v1, v2 = e.embed_query("vector search"), e.embed_query("vector search")
        self.assertAlmostEqual(float(np.linalg.norm(v1)), 1.0, places=5)
        np.testing.assert_array_equal(v1, v2)
        passages = e.embed_passages(["vector search engines", "banana bread recipe"])
        self.assertGreater(float(passages[0] @ v1), float(passages[1] @ v1))


EVAL_MEDIA = tempfile.mkdtemp(prefix="documind-eval-")


@override_settings(INGEST_SYNC=True, MEDIA_ROOT=EVAL_MEDIA)
class RetrievalEvalTests(TestCase):
    """Retrieval quality on the demo documents, with the real local embedding model.

    Guards against regressions when chunking, embeddings or fusion change.
    Skipped if the BGE model isn't available (e.g. no network on first run).
    """

    CASES = [
        ("How many weeks of parental leave do primary caregivers get?", "Handbook", 3),
        ("What's the daily meal allowance when travelling?", "Handbook", 4),
        ("How does HNSW compare to IVF?", "Vector", 2),
        ("Why combine BM25 with vector search?", "Vector", 4),
        ("time off when I have a baby", "Handbook", 3),  # paraphrase: semantic match
        ("how long to report a lost laptop", "Handbook", 5),
        ("what is nprobe", "Vector", 2),  # rare exact term: keyword match
        ("can I work from Spain for two months", "Handbook", 2),
    ]

    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        from documents.services.embeddings import get_embedder

        if get_embedder().name.startswith("hashing"):
            cls.skip = True
            return
        cls.skip = False
        call_command("seed_demo", stdout=io.StringIO())

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(EVAL_MEDIA, ignore_errors=True)

    def test_recall_and_top1(self):
        if self.skip:
            self.skipTest("Local embedding model unavailable")
        from documents.services.retrieval import search

        user = User.objects.get(username="demo")
        top1 = recall6 = 0
        for question, doc, page in self.CASES:
            hits = search(user.id, question, k=6)
            ranks = [i for i, h in enumerate(hits) if doc in h.document_title and h.page_start == page]
            top1 += bool(ranks and ranks[0] == 0)
            recall6 += bool(ranks)
        self.assertEqual(recall6, len(self.CASES), "every answer page must reach the model's context")
        self.assertGreaterEqual(top1, 6)
