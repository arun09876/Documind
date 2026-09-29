"""Create the demo account with two sample PDFs: `python manage.py seed_demo`.

The PDFs are generated from core/demo_content.py and ingested synchronously,
so the demo is searchable as soon as the command finishes.
"""
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from fpdf import FPDF

from core.demo_content import GUIDE, GUIDE_TITLE, HANDBOOK, HANDBOOK_TITLE
from documents.models import Document
from documents.services import ingest

DEMO_USERNAME = "demo"
DEMO_EMAIL = "demo@documind.dev"
DEMO_PASSWORD = "demo12345"


def build_pdf(title: str, pages: list[list[tuple[str, str]]]) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_title(title)
    pdf.set_author("DocuMind demo")
    pdf.set_auto_page_break(auto=False)
    pdf.set_margins(22, 22, 22)
    for number, sections in enumerate(pages, start=1):
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(150, 120, 100)
        pdf.cell(0, 6, title.upper(), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(6)
        for heading, paragraph in sections:
            pdf.set_font("Helvetica", "B", 14)
            pdf.set_text_color(30, 25, 20)
            pdf.multi_cell(0, 7, heading, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
            pdf.set_font("Helvetica", "", 10.5)
            pdf.set_text_color(60, 55, 50)
            pdf.multi_cell(0, 5.6, paragraph, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(5)
        pdf.set_y(-18)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(150, 145, 140)
        pdf.cell(0, 6, f"Page {number} of {len(pages)}", align="C")
    return bytes(pdf.output())


class Command(BaseCommand):
    help = "Create (or reset) the demo account and its sample documents."

    def handle(self, *args, **options):
        User = get_user_model()
        user, _ = User.objects.get_or_create(username=DEMO_USERNAME, defaults={"email": DEMO_EMAIL})
        user.email = DEMO_EMAIL
        user.set_password(DEMO_PASSWORD)
        user.save()
        for doc in user.documents.all():
            doc.file.delete(save=False)
        user.documents.all().delete()
        user.conversations.all().delete()

        for title, pages, filename in [
            (HANDBOOK_TITLE, HANDBOOK, "northwind-employee-handbook-2026.pdf"),
            (GUIDE_TITLE, GUIDE, "vector-search-field-guide.pdf"),
        ]:
            data = build_pdf(title, pages)
            doc = Document(user=user, title=title, filename=filename, size_bytes=len(data))
            doc.file.save(filename, ContentFile(data), save=True)
            ingest.process(doc.id)
            doc.refresh_from_db()
            self.stdout.write(f"  {doc.title}: {doc.status}, {doc.page_count} pages, {doc.chunk_count} chunks ({doc.embedding_model})")

        self.stdout.write(self.style.SUCCESS(f"Demo ready. Log in as {DEMO_USERNAME} / {DEMO_PASSWORD}"))
