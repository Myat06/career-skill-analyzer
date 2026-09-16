"""Data-quality checks for the hand-curated data/seed/skkni_curriculum_mapping.csv
(job_role values mirror data/seed/job_role_definitions.yaml; unit titles mirror
app/scoring/skkni_titles.py). app/scoring/skkni_mapping.py now reads this file
at runtime (course recommendations, and course-based competency matching in
gap_engine.py both go through it) -- so a stale course code, a drifted course
name, or a silent gap in unit coverage would no longer just be an eyeballing
problem, it would be a live scoring bug. These tests check it against the real
source PDFs instead of fixtures, so any drift between the mapping and the
actual SKKNI/curriculum content fails loudly here.

Needs the real PDFs at data/raw/ (like test_ingestion_pipeline.py) but not
Postgres or Ollama -- parsing is pure local PDF extraction.
"""

from collections import Counter, defaultdict

import pytest

from app.config import SEED_DATA_DIR, settings
from app.ingestion.curriculum_parser import parse_curriculum_courses
from app.ingestion.pdf_extract import extract_text
from app.ingestion.skkni_parser import parse_skkni_units
from app.scoring.skkni_titles import UNIT_TITLES_EN

MAPPING_CSV_PATH = SEED_DATA_DIR / "skkni_curriculum_mapping.csv"
VALID_STRENGTHS = {"Primary", "Supporting", "GAP", "NOT_MAPPED"}
SCORE_BY_STRENGTH = {"Primary": "100", "Supporting": "50", "GAP": "0", "NOT_MAPPED": ""}
EXPECTED_HEADER = {
    "skkni_unit_code", "skkni_unit_title_en", "job_role",
    "course_code", "course_name", "concentration_track", "semester",
    "match_strength", "match_score", "match_rationale",
}


def _load_rows() -> list[dict]:
    import csv

    with open(MAPPING_CSV_PATH, newline="", encoding="utf-8") as f:
        first_line = f.readline()
        if not first_line.startswith("sep="):
            f.seek(0)  # not every future edit is guaranteed to keep the sentinel
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def rows():
    return _load_rows()


@pytest.fixture(scope="module")
def skkni_units():
    extracted = extract_text(settings.skkni_pdf_path)
    units, _ = parse_skkni_units(extracted)
    return {u.unit_code: u for u in units}


@pytest.fixture(scope="module")
def curriculum_courses():
    extracted = extract_text(settings.curriculum_pdf_path)
    courses, _ = parse_curriculum_courses(extracted)
    return {c.course_code: c for c in courses}


def test_sep_sentinel_present():
    """Forces Excel to use ',' as the field delimiter regardless of the machine's
    regional settings -- without it, a comma-decimal locale (e.g. Indonesian
    Excel) treats the whole row as one cell when the file is opened directly."""
    with open(MAPPING_CSV_PATH, encoding="utf-8") as f:
        first_line = f.readline().strip()
    assert first_line == "sep=,"


def test_header_columns(rows):
    assert rows
    assert set(rows[0].keys()) == EXPECTED_HEADER


def test_every_unit_code_is_real(rows, skkni_units):
    bad = sorted({r["skkni_unit_code"] for r in rows if r["skkni_unit_code"] and r["skkni_unit_code"] not in skkni_units})
    assert not bad, f"unit codes not found in the real SKKNI PDF: {bad}"


def test_every_course_code_is_real(rows, curriculum_courses):
    bad = sorted({r["course_code"] for r in rows if r["course_code"] and r["course_code"] not in curriculum_courses})
    assert not bad, f"course codes not found in the real curriculum PDF: {bad}"


def test_all_units_covered(rows, skkni_units):
    covered = {r["skkni_unit_code"] for r in rows if r["skkni_unit_code"]}
    assert covered == set(skkni_units), f"missing units: {sorted(set(skkni_units) - covered)}"


def test_all_courses_covered(rows, curriculum_courses):
    covered = {r["course_code"] for r in rows if r["course_code"]}
    assert covered == set(curriculum_courses), f"missing courses: {sorted(set(curriculum_courses) - covered)}"


def test_course_name_matches_source(rows, curriculum_courses):
    mismatches = [
        (r["course_code"], r["course_name"], curriculum_courses[r["course_code"]].course_name)
        for r in rows
        if r["course_code"] and r["course_name"] != curriculum_courses[r["course_code"]].course_name
    ]
    assert not mismatches, f"course_name drifted from the parsed PDF: {mismatches}"


def test_unit_title_matches_translation_table(rows):
    mismatches = [
        (r["skkni_unit_code"], r["skkni_unit_title_en"], UNIT_TITLES_EN.get(r["skkni_unit_code"]))
        for r in rows
        if r["skkni_unit_code"] and r["skkni_unit_title_en"] != UNIT_TITLES_EN.get(r["skkni_unit_code"])
    ]
    assert not mismatches, f"unit title drifted from app/scoring/skkni_titles.py: {mismatches}"


def test_no_duplicate_unit_course_pairs(rows):
    pairs = Counter((r["skkni_unit_code"], r["course_code"]) for r in rows if r["skkni_unit_code"] and r["course_code"])
    dupes = [p for p, n in pairs.items() if n > 1]
    assert not dupes, f"duplicate (unit, course) rows: {dupes}"


def test_no_course_both_mapped_and_not_mapped(rows):
    mapped = {r["course_code"] for r in rows if r["course_code"] and r["match_strength"] in ("Primary", "Supporting")}
    not_mapped = {r["course_code"] for r in rows if r["match_strength"] == "NOT_MAPPED"}
    contradiction = mapped & not_mapped
    assert not contradiction, f"course marked both mapped and NOT_MAPPED: {contradiction}"


def test_match_strength_values_are_known(rows):
    bad = sorted({r["match_strength"] for r in rows} - VALID_STRENGTHS)
    assert not bad


def test_match_score_matches_strength(rows):
    mismatches = [
        (r["skkni_unit_code"] or "(unmapped)", r["course_code"], r["match_strength"], r["match_score"])
        for r in rows
        if r["match_score"] != SCORE_BY_STRENGTH[r["match_strength"]]
    ]
    assert not mismatches, f"match_score inconsistent with match_strength: {mismatches}"


def test_gap_rows_have_no_course(rows):
    bad = [r["skkni_unit_code"] for r in rows if r["match_strength"] == "GAP" and r["course_code"]]
    assert not bad, "a GAP row should not name a course"


def test_not_mapped_rows_have_no_unit(rows):
    bad = [r["course_code"] for r in rows if r["match_strength"] == "NOT_MAPPED" and r["skkni_unit_code"]]
    assert not bad, "a NOT_MAPPED row should not name a unit"


def test_mapped_rows_have_both_unit_and_course(rows):
    bad = [
        (r["skkni_unit_code"], r["course_code"])
        for r in rows
        if r["match_strength"] in ("Primary", "Supporting") and not (r["skkni_unit_code"] and r["course_code"])
    ]
    assert not bad


def test_every_row_has_a_rationale(rows):
    bad = [(r["skkni_unit_code"], r["course_code"]) for r in rows if not r["match_rationale"].strip()]
    assert not bad


def test_semester_matches_source(rows, curriculum_courses):
    mismatches = [
        (r["course_code"], r["semester"], curriculum_courses[r["course_code"]].semester)
        for r in rows
        if r["course_code"] and r["semester"] and int(r["semester"]) != curriculum_courses[r["course_code"]].semester
    ]
    assert not mismatches


def test_concentration_track_matches_source(rows, curriculum_courses):
    mismatches = [
        (r["course_code"], r["concentration_track"], curriculum_courses[r["course_code"]].concentration_track)
        for r in rows
        if r["course_code"] and (r["concentration_track"] or None) != curriculum_courses[r["course_code"]].concentration_track
    ]
    assert not mismatches


def test_every_unit_has_coverage_or_an_explicit_gap_row(rows, skkni_units):
    """A unit with zero mapped courses and no GAP row would be a silent
    omission -- every unit must either earn score from a mapped course or be
    explicitly flagged as a curriculum gap."""
    scores = defaultdict(int)
    gap_units = set()
    for r in rows:
        if not r["skkni_unit_code"]:
            continue
        if r["match_strength"] in ("Primary", "Supporting"):
            scores[r["skkni_unit_code"]] += int(r["match_score"])
        elif r["match_strength"] == "GAP":
            gap_units.add(r["skkni_unit_code"])

    silent_omissions = [
        unit_code for unit_code in skkni_units if scores.get(unit_code, 0) == 0 and unit_code not in gap_units
    ]
    assert not silent_omissions, f"units with no mapped course and no GAP row: {silent_omissions}"
