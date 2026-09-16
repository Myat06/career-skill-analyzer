"""Parses the curriculum book's per-course detail cards (section 7, "Course
Details" -- verified against IS_Curriculum_Book_2025.pdf starting page 23).

Real structure: each course is a plain-text card starting with a
`"{CODE} - {Name}"` header line (real course codes, e.g. `FAC103`, `ISC101`),
followed by a fixed, ordered sequence of labeled fields: Course Code, Course
Name, Semester, Credits, Course Type, Concentration, Course Description,
Related PLO, Course Objective / CPMK. This is more reliable to parse from
flattened text than the earlier per-semester summary tables in section 6.2
(which list courses by name only, with no codes) -- those tables are not
used by this parser.
"""

import re
from dataclasses import dataclass

from app.ingestion.pdf_extract import ExtractedPdf

COURSE_HEADER_RE = re.compile(r"^[A-Z]{2,4}\d{3,4}\s*-\s*.+$", re.MULTILINE)

FIELD_LABELS = [
    "Course Code",
    "Course Name",
    "Semester",
    "Credits",
    "Course Type",
    "Concentration",
    "Course Description",
    "Related PLO",
    "Course Objective / CPMK",
]
REQUIRED_LABELS = {"Course Code", "Course Name", "Semester", "Credits"}
NUMERIC_VALUE_LABELS = {"Semester", "Credits"}  # the only labels with a legitimately bare-numeric value
_NUMERIC_LINE_RE = re.compile(r"^\d{1,4}$")


@dataclass
class CurriculumCourse:
    course_code: str
    course_name: str
    semester: int
    credits: int
    course_type: str
    concentration_track: str | None
    description: str
    cpmk: str
    related_plo: list[str]
    source_page: int
    parse_confidence: float


def _clean(text: str) -> str:
    return " ".join(text.split())


def _extract_fields_from_block(block: str) -> dict[str, str]:
    """Line-based label scan: fitz renders each label alone on its own line,
    with the value following on subsequent line(s) until the next label
    line. This matters because a value can itself contain a label's text as
    a substring (e.g. a 'Course Type' of "Concentration Bootcamp" sitting
    right before the real 'Concentration' label) -- matching whole
    stripped lines against the label set, rather than substring search,
    avoids that collision.
    """
    label_set = set(FIELD_LABELS)
    values: dict[str, list[str]] = {label: [] for label in FIELD_LABELS}
    current_label: str | None = None

    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line in label_set:
            current_label = line
            continue
        if current_label is None:
            continue
        if current_label not in NUMERIC_VALUE_LABELS and _NUMERIC_LINE_RE.match(line):
            continue  # likely a page-footer number leaking into a free-text field
        values[current_label].append(line)

    return {label: _clean(" ".join(parts)) for label, parts in values.items()}


def _parse_int(text: str) -> int:
    match = re.search(r"\d+", text)
    return int(match.group(0)) if match else 0


def parse_curriculum_courses(extracted: ExtractedPdf) -> tuple[list[CurriculumCourse], int]:
    """Returns (courses, cards_skipped). cards_skipped counts course-header-
    shaped lines that never resolved a 'Course Code' field nearby (i.e. not
    actually a course card) -- logged by the caller into IngestionRun.notes.
    """
    text = extracted.full_text
    matches = list(COURSE_HEADER_RE.finditer(text))
    courses: list[CurriculumCourse] = []
    skipped = 0

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]

        if "Course Code" not in block[:400]:
            skipped += 1
            continue

        fields = _extract_fields_from_block(block)
        found_labels = {label for label in FIELD_LABELS if fields[label]}
        if not REQUIRED_LABELS.issubset(found_labels):
            skipped += 1
            continue

        related_plo = [tag.strip() for tag in fields["Related PLO"].split(",") if tag.strip()]
        concentration = fields["Concentration"]
        track = None if concentration.lower() in ("", "all", "-", "none") else concentration

        courses.append(
            CurriculumCourse(
                course_code=fields["Course Code"] or match.group(0).split(" - ")[0].strip(),
                course_name=fields["Course Name"],
                semester=_parse_int(fields["Semester"]),
                credits=_parse_int(fields["Credits"]),
                course_type=fields["Course Type"],
                concentration_track=track,
                description=fields["Course Description"],
                cpmk=fields["Course Objective / CPMK"],
                related_plo=related_plo,
                source_page=extracted.page_for_offset(start),
                parse_confidence=len(found_labels) / len(FIELD_LABELS),
            )
        )

    return courses, skipped
