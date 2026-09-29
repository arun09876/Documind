"""Split page texts into overlapping chunks that remember which pages they came from.

Chunks never cross a page break (so a citation names one exact page) and are
built from whole sentences (never cutting one in half unless it's
longer than the maximum), so each chunk reads naturally and a citation points
at a coherent passage. Consecutive chunks share ~overlap characters of
sentences, so an answer that spans a chunk boundary is still retrievable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])")
_PARAGRAPH = re.compile(r"\n\s*\n")


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    page_start: int
    page_end: int


@dataclass(frozen=True)
class _Unit:
    text: str
    page: int


_TERMINAL = ".!?:;,"
# A line ending in one of these is a sentence wrapped mid-way, not a heading.
_CONTINUATION = frozenset("a an and as at by for from in into of on or the to with".split())


def _join_lines(paragraph: str) -> str:
    """Join a paragraph's lines, turning heading lines into "Heading: text".

    PDF extraction gives headings as short lines without punctuation; left as-is
    they run into the next sentence ("Parental leave Primary caregivers ...").
    """
    lines = [ln.strip() for ln in paragraph.split("\n") if ln.strip()]
    out = []
    for i, line in enumerate(lines):
        words = line.split()
        is_heading = (
            len(line) <= 60 and len(words) <= 8 and line[-1] not in _TERMINAL
            and ":" not in line  # "Version Control: Git, GitHub" is a label/value line, not a heading
            and words[-1].lower() not in _CONTINUATION
            and i + 1 < len(lines) and lines[i + 1][:1].isupper()
        )
        # Only a heading if the previous line ended a sentence (not a wrapped line).
        if is_heading and (i == 0 or lines[i - 1][-1] in ".!?:"):
            out.append(line + ":")
        else:
            out.append(line)
    return " ".join(out)


def _units(pages: list[str], max_chars: int) -> list[_Unit]:
    units: list[_Unit] = []
    for page_no, page in enumerate(pages, start=1):
        for paragraph in _PARAGRAPH.split(page):
            paragraph = " ".join(_join_lines(paragraph).split())
            if not paragraph:
                continue
            for sentence in _SENTENCE_END.split(paragraph):
                sentence = sentence.strip()
                while len(sentence) > max_chars:  # pathological: no sentence breaks at all
                    cut = sentence.rfind(" ", 0, max_chars)
                    cut = cut if cut > max_chars // 2 else max_chars
                    units.append(_Unit(sentence[:cut].strip(), page_no))
                    sentence = sentence[cut:].strip()
                if sentence:
                    units.append(_Unit(sentence, page_no))
    return units


def chunk_pages(pages: list[str], target_chars: int = 900, overlap_chars: int = 180) -> list[Chunk]:
    max_chars = int(target_chars * 1.4)
    units = _units(pages, max_chars)
    chunks: list[Chunk] = []
    current: list[_Unit] = []
    size = 0
    fresh = 0  # sentences in `current` that no emitted chunk contains yet

    def emit() -> None:
        text = " ".join(u.text for u in current)
        chunks.append(Chunk(len(chunks), text, current[0].page, current[-1].page))

    for unit in units:
        new_page = bool(current) and unit.page != current[-1].page
        if new_page and fresh:
            # Chunks never cross a page break, so every citation points at one exact page.
            emit()
            current, size, fresh = [], 0, 0
        elif new_page:
            current, size = [], 0  # only overlap from the previous page is pending: drop it
        elif current and fresh and size + len(unit.text) + 1 > target_chars:
            emit()
            # Carry trailing sentences forward as overlap (within the same page).
            carried: list[_Unit] = []
            carried_size = 0
            for prev in reversed(current):
                if carried_size + len(prev.text) > overlap_chars:
                    break
                carried.insert(0, prev)
                carried_size += len(prev.text) + 1
            current, size, fresh = carried, carried_size, 0
        current.append(unit)
        size += len(unit.text) + 1
        fresh += 1

    if fresh:
        emit()
    return chunks
