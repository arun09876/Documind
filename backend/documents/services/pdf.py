"""PDF text extraction, one string per page (page numbers matter for citations)."""
from __future__ import annotations

import io
import re

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class PdfError(ValueError):
    """The file is not a usable PDF. The message is safe to show to the user."""


_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_SPACES = re.compile(r"[ \t ]+")
_MANY_NEWLINES = re.compile(r"\n{3,}")


def clean_page_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HYPHEN_BREAK.sub(r"\1\2", text)  # "exam-\nple" -> "example"
    text = _SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _MANY_NEWLINES.sub("\n\n", text).strip()


_PAGE_NUMBER = re.compile(r"^(page\s*)?\d+(\s*(of|/)\s*\d+)?$", re.IGNORECASE)
_DIGITS = re.compile(r"\d+")
_PAGE_WORD = re.compile(r"\bpage\b", re.IGNORECASE)


def _line_key(line: str) -> str:
    """Comparison key for header/footer detection. Digits are ignored only in
    page-number lines ("Handbook · Page 3"), so "Section 1"/"Section 2" stay distinct."""
    line = line.strip().lower()
    return _DIGITS.sub("#", line) if _PAGE_WORD.search(line) else line


def strip_running_lines(pages: list[str]) -> list[str]:
    """Remove running headers/footers and bare page numbers.

    A line counts as "running" if it's among the first or last two lines of a
    page and appears on at least half of the pages (page numbers ignored).
    These lines would otherwise pollute every chunk and skew retrieval.
    """
    if len(pages) < 2:
        return pages
    edge_counts: dict[str, int] = {}
    for page in pages:
        lines = [ln for ln in page.split("\n") if ln.strip()]
        for line in {*lines[:2], *lines[-2:]}:
            key = _line_key(line)
            edge_counts[key] = edge_counts.get(key, 0) + 1
    running = {k for k, n in edge_counts.items() if n >= max(2, len(pages) / 2)}

    cleaned = []
    for page in pages:
        lines = page.split("\n")
        kept = [
            ln for i, ln in enumerate(lines)
            if not (
                (i < 3 or i >= len(lines) - 3)
                and (_line_key(ln) in running or _PAGE_NUMBER.match(ln.strip()))
            )
        ]
        cleaned.append("\n".join(kept).strip())
    return cleaned


def extract_pages(data: bytes, max_pages: int) -> tuple[list[str], dict]:
    """Return (page_texts, metadata). page_texts[0] is page 1."""
    if not data.startswith(b"%PDF"):
        raise PdfError("That file isn't a PDF.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001 - pypdf raises several types here
                raise PdfError("This PDF is password-protected.") from exc
        count = len(reader.pages)
    except PdfReadError as exc:
        raise PdfError("This PDF appears to be damaged and couldn't be read.") from exc

    if count == 0:
        raise PdfError("This PDF has no pages.")
    if count > max_pages:
        raise PdfError(f"This PDF has {count} pages; the limit is {max_pages}.")

    pages = []
    for page in reader.pages:
        try:
            pages.append(clean_page_text(page.extract_text() or ""))
        except Exception:  # noqa: BLE001 - a single broken page shouldn't fail the whole document
            pages.append("")

    pages = strip_running_lines(pages)
    if sum(len(p) for p in pages) < 20:
        raise PdfError("No selectable text found. This looks like a scanned PDF, and OCR isn't supported yet.")

    meta = reader.metadata or {}
    return pages, {"title": (meta.get("/Title") or "").strip() if hasattr(meta, "get") else "", "page_count": count}
