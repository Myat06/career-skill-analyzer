"""PDF text extraction with page tracking, shared by the SKKNI and curriculum
parsers. fitz (pymupdf) does fast sequential full-text extraction with a
page-offset map for citations; pdfplumber is used separately, page-by-page,
wherever a parser needs real table extraction (SKKNI's ELEMEN KOMPETENSI /
KRITERIA UNJUK KERJA table, the curriculum book's per-semester course tables).
"""

from dataclasses import dataclass
from pathlib import Path

import fitz  # pymupdf
import pdfplumber


@dataclass
class PageText:
    page_number: int  # 1-indexed
    text: str


@dataclass
class ExtractedPdf:
    path: Path
    pages: list[PageText]

    @property
    def full_text(self) -> str:
        return "\n".join(p.text for p in self.pages)

    def page_for_offset(self, offset: int) -> int:
        """Given a character offset into full_text (pages joined with '\\n'),
        return the 1-indexed page number it falls on."""
        cursor = 0
        for page in self.pages:
            page_len = len(page.text) + 1  # +1 for the joining '\n'
            if offset < cursor + page_len:
                return page.page_number
            cursor += page_len
        return self.pages[-1].page_number if self.pages else 1


def extract_text(path: Path) -> ExtractedPdf:
    pages: list[PageText] = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc):
            pages.append(PageText(page_number=i + 1, text=page.get_text()))
    return ExtractedPdf(path=path, pages=pages)


def open_plumber(path: Path) -> pdfplumber.PDF:
    """Caller is responsible for closing (use as a context manager)."""
    return pdfplumber.open(path)
