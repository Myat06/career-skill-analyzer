"""Parses SKKNI unit-competency blocks out of the extracted PDF text.

Real structure (verified against SKKNI_2026-103.pdf): each unit starts with a
`KODE UNIT : K.62AIN00.NNN.V` / `JUDUL UNIT :` / `DESKRIPSI UNIT :` header,
followed by a real bordered two-column table (`ELEMEN KOMPETENSI` |
`KRITERIA UNJUK KERJA`, one row per element, each cell holding one or more
numbered criteria), then `BATASAN VARIABEL` and `PANDUAN PENILAIAN` sections
running to the next `KODE UNIT`.

Primary extraction of the element/criteria table uses pdfplumber (reliable
for a real bordered table); if no matching table is found on the unit's
pages, a regex line-based fallback runs against the flattened fitz text --
noted with a lower `parse_confidence` rather than silently dropping the unit,
since column-flattened text can interleave unpredictably.
"""

import re
from dataclasses import dataclass, field

from app.ingestion.pdf_extract import ExtractedPdf, open_plumber

UNIT_CODE_RE = re.compile(r"[A-Z]\.\d{2}[A-Z]{3}\d{2}\.\d{3}\.\d")
ELEMENT_LINE_RE = re.compile(r"^(\d+)\.\s+(.+)$")
CRITERION_LINE_RE = re.compile(r"^(\d+\.\d+)\s+(.+)$")

SECTION_MARKERS = ("BATASAN VARIABEL", "PANDUAN PENILAIAN")


@dataclass
class SkkniCriterion:
    number: str
    text: str


@dataclass
class SkkniElement:
    number: str
    title: str
    criteria: list[SkkniCriterion] = field(default_factory=list)


@dataclass
class SkkniUnit:
    unit_code: str
    unit_title: str
    description: str
    elements: list[SkkniElement]
    variable_scope: str
    assessment_guide: str
    source_page: int
    parse_confidence: float  # 1.0 = table-extracted elements, 0.5 = regex fallback, 0.0 = none found


def _extract_between(text: str, start_marker: str, end_markers: tuple[str, ...]) -> str:
    start = text.find(start_marker)
    if start == -1:
        return ""
    start += len(start_marker)
    end = len(text)
    for marker in end_markers:
        idx = text.find(marker, start)
        if idx != -1:
            end = min(end, idx)
    return text[start:end].strip(" :\n")


def parse_unit_header(block: str) -> tuple[str, str, str] | None:
    code_match = UNIT_CODE_RE.search(block)
    if not code_match:
        return None
    unit_code = code_match.group(0)
    unit_title = _extract_between(block, "JUDUL UNIT", ("DESKRIPSI UNIT",)).replace("\n", " ").strip(" :")
    description = _extract_between(block, "DESKRIPSI UNIT", ("ELEMEN KOMPETENSI",)).replace("\n", " ").strip(" :")
    return unit_code, " ".join(unit_title.split()), " ".join(description.split())


def parse_element_criteria_table(rows: list[list[str | None]]) -> list[SkkniElement]:
    """Pure function over already-extracted pdfplumber table rows (each row:
    [elemen_cell, kriteria_cell]), excluding the header row. Testable with
    synthetic fixtures, no PDF access needed.
    """
    elements: list[SkkniElement] = []
    for row in rows:
        if len(row) < 2 or not row[0] or not row[1]:
            continue
        elem_cell = " ".join((row[0] or "").split())
        crit_cell = row[1] or ""

        elem_match = re.match(r"^(\d+)\.\s*(.+)$", elem_cell, re.DOTALL)
        number = elem_match.group(1) if elem_match else str(len(elements) + 1)
        title = elem_match.group(2) if elem_match else elem_cell

        criteria: list[SkkniCriterion] = []
        crit_lines = [l.strip() for l in crit_cell.splitlines() if l.strip()]
        current: SkkniCriterion | None = None
        for line in crit_lines:
            match = CRITERION_LINE_RE.match(line)
            if match:
                current = SkkniCriterion(number=match.group(1), text=match.group(2))
                criteria.append(current)
            elif current is not None:
                current.text += " " + line
        if not criteria and crit_cell.strip():
            criteria.append(SkkniCriterion(number=f"{number}.1", text=" ".join(crit_cell.split())))

        elements.append(SkkniElement(number=number, title=" ".join(title.split()), criteria=criteria))
    return elements


def parse_element_criteria_fallback(text: str) -> list[SkkniElement]:
    """Regex line-based fallback for when no bordered table is found on the
    unit's pages -- lower-confidence, since fitz's flattened text for a
    genuinely two-column table can interleave rows unpredictably.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    elements: list[SkkniElement] = []
    current_element: SkkniElement | None = None
    for line in lines:
        crit_match = CRITERION_LINE_RE.match(line)
        elem_match = None if crit_match else ELEMENT_LINE_RE.match(line)
        if crit_match and current_element is not None:
            current_element.criteria.append(SkkniCriterion(number=crit_match.group(1), text=crit_match.group(2)))
        elif elem_match:
            current_element = SkkniElement(number=elem_match.group(1), title=elem_match.group(2))
            elements.append(current_element)
        elif current_element is not None:
            if current_element.criteria:
                current_element.criteria[-1].text += " " + line
            else:
                current_element.title += " " + line
    return elements


def _find_element_table(pdf, page_numbers: list[int]) -> list[list[str | None]] | None:
    for page_no in page_numbers:
        if page_no < 1 or page_no > len(pdf.pages):
            continue
        page = pdf.pages[page_no - 1]
        for table in page.extract_tables():
            if not table:
                continue
            header = [(cell or "").upper() for cell in table[0]]
            if any("ELEMEN KOMPETENSI" in h for h in header):
                return table[1:]
    return None


def parse_skkni_units(extracted: ExtractedPdf) -> tuple[list[SkkniUnit], int]:
    """Returns (units, blocks_skipped). blocks_skipped is front-matter/back-matter
    content that didn't contain a valid unit code -- logged by the caller into
    IngestionRun.notes rather than silently discarded.
    """
    full_text = extracted.full_text
    raw_blocks = full_text.split("KODE UNIT")
    blocks_skipped = 0
    units: list[SkkniUnit] = []

    with open_plumber(extracted.path) as pdf:
        cursor = len(raw_blocks[0]) if raw_blocks else 0  # front matter before the first real unit
        for i, raw in enumerate(raw_blocks):
            if i == 0:
                continue  # front matter (e.g. the "Daftar Unit Kompetensi" listing) -- never a unit itself
            block = "KODE UNIT" + raw
            block_start = cursor
            cursor += len(block)

            header = parse_unit_header(block)
            if header is None:
                blocks_skipped += 1
                continue
            unit_code, unit_title, description = header

            start_page = extracted.page_for_offset(block_start)
            end_page = extracted.page_for_offset(max(block_start, cursor - 1))
            page_range = list(range(start_page, min(end_page, len(pdf.pages)) + 1))

            table_rows = _find_element_table(pdf, page_range)
            if table_rows is not None:
                elements = parse_element_criteria_table(table_rows)
                confidence = 1.0
            else:
                fallback_text = _extract_between(block, "ELEMEN KOMPETENSI", SECTION_MARKERS)
                elements = parse_element_criteria_fallback(fallback_text)
                confidence = 0.5 if elements else 0.0

            variable_scope = _extract_between(block, "BATASAN VARIABEL", ("PANDUAN PENILAIAN",))
            assessment_guide = _extract_between(block, "PANDUAN PENILAIAN", ("KODE UNIT",))

            units.append(
                SkkniUnit(
                    unit_code=unit_code,
                    unit_title=unit_title,
                    description=description,
                    elements=elements,
                    variable_scope=variable_scope,
                    assessment_guide=assessment_guide,
                    source_page=start_page,
                    parse_confidence=confidence,
                )
            )

    return units, blocks_skipped
