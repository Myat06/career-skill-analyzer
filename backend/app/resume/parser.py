"""Parses an uploaded resume file (PDF or DOCX) into plain text plus a light
section breakdown, used both for standalone resume scoring
(app/scoring/resume_score.py) and as lower-weight supplementary evidence in
the skill-gap engine (app/scoring/gap_engine.py).
"""

import io
from typing import Iterator

import pdfplumber
from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph


class UnsupportedResumeFormat(ValueError):
    pass


def extract_text_from_pdf(data: bytes) -> str:
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _iter_block_text(element, document) -> Iterator[str]:
    """Yields paragraph and table text in document order, recursing into table
    cells (which may themselves hold paragraphs and nested tables).

    Reading `document.paragraphs` alone -- as this module previously did --
    silently skips every table in the file. That is not an edge case for
    resumes: table-based layouts are one of the most common resume template
    styles, and a resume laid out that way extracted to nothing but the name.
    Everything downstream then degraded quietly rather than erroring: the
    rubric grader had no text to grade (so it returned no categories, and the
    report printed "no improvements suggested"), keyword alignment compared
    against an almost-empty document, and the skill-gap engine got an empty
    evidence item. A near-empty extraction is indistinguishable from a weak
    resume unless the text is actually captured.
    """
    for child in element.iterchildren():
        if child.tag == qn("w:p"):
            text = Paragraph(child, document).text.strip()
            if text:
                yield text
        elif child.tag == qn("w:tbl"):
            for row in Table(child, document).rows:
                cells = [" ".join(_iter_block_text(cell._element, document)).strip() for cell in row.cells]
                # Merged cells repeat in python-docx's row.cells, so drop
                # consecutive duplicates rather than emitting the same text twice.
                deduped = [c for i, c in enumerate(cells) if c and (i == 0 or c != cells[i - 1])]
                if deduped:
                    yield " ".join(deduped)


def extract_text_from_docx(data: bytes) -> str:
    document = Document(io.BytesIO(data))
    parts = list(_iter_block_text(document.element.body, document))

    # Contact details in particular are routinely placed in the header, and the
    # rubric's very first category grades exactly those -- so a resume could be
    # marked down for "missing" a phone number that was in the file all along.
    for section in document.sections:
        for container in (section.header, section.footer):
            if container is not None:
                parts.extend(_iter_block_text(container._element, document))

    return "\n".join(parts)


def extract_text(filename: str, data: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return extract_text_from_pdf(data)
    if lower.endswith(".docx"):
        return extract_text_from_docx(data)
    raise UnsupportedResumeFormat(f"Unsupported resume file type: {filename}")
