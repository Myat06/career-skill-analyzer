"""Regression tests for the three guards that were found not to guard:
course recommendations had no relevance floor (since replaced entirely by a
curated mapping file -- see the course-recommendation section below), the
resume rubric was averaged over however many categories the model happened
to return, and the narrative citation check never looked at the citations.
See the comments at each constant/function under test for the original
failure.
"""

import asyncio

import pytest

import app.scoring.gap_engine as gap_engine
from app.scoring.gap_engine import UnitCoverageResult, recommend_courses
from app.scoring.resume_score import RUBRIC_CATEGORIES, score_resume
from app.scoring.skkni_mapping import MappedCourse


def _unit(unit_code: str = "K.1") -> UnitCoverageResult:
    return UnitCoverageResult(unit_code=unit_code, unit_title="Some Competency", status="missing")


def _mapped(course_code: str, strength: str = "Primary", score: int = 100, rationale: str = "matches well") -> MappedCourse:
    return MappedCourse(
        course_code=course_code,
        course_name=f"Course {course_code}",
        match_strength=strength,
        match_score=score,
        match_rationale=rationale,
    )


# --- course recommendations -----------------------------------------------
# These used to come from a live semantic search over ingested course
# descriptions, floored at a calibrated cosine threshold so a weak match
# wasn't confidently recommended. That whole mechanism is gone: course
# recommendations now come from the hand-authored, row-reviewed mapping in
# data/seed/skkni_curriculum_mapping.csv (see app/scoring/skkni_mapping.py),
# so there is no similarity floor to guard -- a course is either in the
# curated mapping for a unit or it isn't. skkni_mapping.py's own CSV-parsing
# behaviour (GAP rows, NOT_MAPPED rows, Primary/Supporting ordering) is
# covered in test_skkni_mapping.py; these test gap_engine's lookup/filter
# logic on top of it.


def test_units_with_no_mapped_courses_get_no_recommendations(monkeypatch):
    # A curated GAP unit (or one absent from the mapping) must not fall back
    # to inventing a recommendation -- the honest answer is "no course in the
    # catalog covers this".
    monkeypatch.setattr(gap_engine, "mapped_courses_for_unit", lambda unit_code: [])
    assert asyncio.run(recommend_courses([_unit()], set())) == []


def test_mapped_courses_are_recommended_in_curated_order(monkeypatch):
    monkeypatch.setattr(
        gap_engine,
        "mapped_courses_for_unit",
        lambda unit_code: [_mapped("A", "Primary"), _mapped("B", "Supporting")],
    )
    result = asyncio.run(recommend_courses([_unit()], set()))
    assert [c.course_code for c in result] == ["A", "B"]


def test_match_reason_carries_the_curated_strength_and_rationale(monkeypatch):
    monkeypatch.setattr(
        gap_engine,
        "mapped_courses_for_unit",
        lambda unit_code: [_mapped("A", "Primary", rationale="teaches the exact skill")],
    )
    result = asyncio.run(recommend_courses([_unit()], set()))
    assert result[0].match_reason == "Primary match: teaches the exact skill"


def test_completed_courses_are_never_recommended(monkeypatch):
    monkeypatch.setattr(
        gap_engine,
        "mapped_courses_for_unit",
        lambda unit_code: [_mapped("A"), _mapped("B")],
    )
    result = asyncio.run(recommend_courses([_unit()], {"A"}))
    assert [c.course_code for c in result] == ["B"]


def test_duplicate_course_rows_for_one_unit_are_recommended_once(monkeypatch):
    monkeypatch.setattr(
        gap_engine,
        "mapped_courses_for_unit",
        lambda unit_code: [_mapped("A"), _mapped("A")],
    )
    result = asyncio.run(recommend_courses([_unit()], set()))
    assert [c.course_code for c in result] == ["A"]


def test_recommendations_capped_per_unit(monkeypatch):
    monkeypatch.setattr(
        gap_engine,
        "mapped_courses_for_unit",
        lambda unit_code: [_mapped(f"C{i}") for i in range(gap_engine.RECOMMENDED_COURSES_PER_UNIT + 2)],
    )
    result = asyncio.run(recommend_courses([_unit()], set()))
    assert len(result) == gap_engine.RECOMMENDED_COURSES_PER_UNIT


def test_no_gap_units_means_no_lookups_and_no_recommendations(monkeypatch):
    called = False

    def fake_mapped(unit_code):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(gap_engine, "mapped_courses_for_unit", fake_mapped)
    assert asyncio.run(recommend_courses([], set())) == []
    assert called is False


def test_each_unit_is_looked_up_independently(monkeypatch):
    monkeypatch.setattr(
        gap_engine, "mapped_courses_for_unit", lambda unit_code: [_mapped(f"{unit_code}-COURSE")]
    )
    result = asyncio.run(recommend_courses([_unit("K.1"), _unit("K.2")], set()))
    assert [c.course_code for c in result] == ["K.1-COURSE", "K.2-COURSE"]


def test_real_mapping_resolves_a_known_unit():
    # Integration-style check against the real seed CSV (no monkeypatching):
    # AI Business & Solution Planner's first unit is mapped Primary -> ISC101,
    # Supporting -> FAC201 in data/seed/skkni_curriculum_mapping.csv.
    result = asyncio.run(recommend_courses([_unit("K.62AIN00.001.2")], set()))
    assert [c.course_code for c in result] == ["ISC101", "FAC201"]


def _run_score_resume(categories):
    async def fake_rubric(resume_text):
        return categories, None, ""

    import app.scoring.resume_score as rs

    original = rs.compute_rubric_score
    rs.compute_rubric_score = fake_rubric
    try:
        return asyncio.run(score_resume("some resume text"))
    finally:
        rs.compute_rubric_score = original


def _category(key, score=80):
    return {"key": key, "label": key, "score": score, "feedback": "ok", "quote": None}


def test_partial_rubric_is_flagged_provisional():
    # 3 of 7 categories graded: previously averaged over 3 and presented as a
    # complete resume score with no indication anything was missing.
    partial = [_category(c["key"]) for c in RUBRIC_CATEGORIES[:3]]
    result = _run_score_resume(partial)
    assert result["rubric_complete"] is False
    assert "Provisional" in result["note"]
    assert "3 of 7" in result["note"]


def test_complete_rubric_is_not_flagged():
    full = [_category(c["key"]) for c in RUBRIC_CATEGORIES]
    result = _run_score_resume(full)
    assert result["rubric_complete"] is True
    assert result["note"] is None or "Provisional" not in result["note"]


def test_missing_category_is_named_in_the_note():
    full_but_one = [_category(c["key"]) for c in RUBRIC_CATEGORIES[:-1]]
    result = _run_score_resume(full_but_one)
    assert RUBRIC_CATEGORIES[-1]["label"] in result["note"]


@pytest.mark.parametrize("categories", [None, []])
def test_ungraded_rubric_is_not_reported_as_partial(categories):
    # A total grading failure already has its own note -- it must not also be
    # described as "0 of 7 categories returned".
    result = _run_score_resume(categories)
    assert result["rubric_complete"] is False
    assert "Provisional" not in (result["note"] or "")
