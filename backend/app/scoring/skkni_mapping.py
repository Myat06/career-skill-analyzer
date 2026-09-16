"""Loads the curated SKKNI-unit -> curriculum-course mapping used to
recommend courses for a gap unit.

Course recommendations used to come from a live semantic search over ingested
course descriptions (cosine similarity between a unit's title/unmatched
elements and course text) -- see the git history of gap_engine.py's
_fuse_recommendations. That approach was inherently noisy: matching a short
unit title against paragraph-length course text compresses similarity scores
into a narrow band (see the old COURSE_MATCH_MIN_SIMILARITY calibration
comment), so a floor was needed just to keep it from confidently
recommending unrelated courses.

A hand-authored, row-by-row-reviewed mapping already existed for exactly this
purpose at data/seed/skkni_curriculum_mapping.csv -- every one of the 27
SKKNI units, each course mapped to it graded Primary/Supporting with a written
rationale, and explicit GAP rows where no course in the catalog actually
covers a unit -- but nothing in the running app ever read it. This loads that
CSV directly instead, so course recommendations are the reviewed ground truth
rather than a re-derived, uncalibrated approximation of it.
"""

import csv
from dataclasses import dataclass
from functools import lru_cache

from app.config import SEED_DATA_DIR

MAPPING_CSV_FILENAME = "skkni_curriculum_mapping.csv"

_STRENGTH_ORDER = {"Primary": 0, "Supporting": 1}


@dataclass
class MappedCourse:
    course_code: str
    course_name: str
    match_strength: str
    match_score: int
    match_rationale: str


@lru_cache(maxsize=1)
def _load_mapping() -> dict[str, list[MappedCourse]]:
    path = SEED_DATA_DIR / MAPPING_CSV_FILENAME
    with path.open(newline="", encoding="utf-8") as f:
        lines = f.readlines()

    # First line is an Excel `sep=,` hint, not part of the CSV header/body.
    reader = csv.DictReader(lines[1:])
    mapping: dict[str, list[MappedCourse]] = {}
    for row in reader:
        unit_code = (row.get("skkni_unit_code") or "").strip()
        course_code = (row.get("course_code") or "").strip()
        # Skips GAP rows (curated as "no course covers this unit") and the
        # trailing NOT_MAPPED rows (courses unrelated to any of the 27 units)
        # -- both have no course_code to recommend, or an empty unit_code.
        if not unit_code or not course_code:
            continue
        mapping.setdefault(unit_code, []).append(
            MappedCourse(
                course_code=course_code,
                course_name=(row.get("course_name") or "").strip(),
                match_strength=(row.get("match_strength") or "").strip(),
                match_score=int(row["match_score"]),
                match_rationale=(row.get("match_rationale") or "").strip(),
            )
        )

    for rows in mapping.values():
        rows.sort(key=lambda r: (_STRENGTH_ORDER.get(r.match_strength, 2), -r.match_score))
    return mapping


def mapped_courses_for_unit(unit_code: str) -> list[MappedCourse]:
    """Curated course matches for one SKKNI unit, Primary before Supporting,
    highest match_score first within each. Empty if the unit isn't in the
    mapping or every mapped row for it is a curated GAP (no course covers it)."""
    return _load_mapping().get(unit_code, [])
