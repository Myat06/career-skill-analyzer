"""Regression check for the matching engine's two evidence sources: a
completed course mapped in the curated SKKNI-to-curriculum mapping
(data/seed/skkni_curriculum_mapping.csv, via skkni_mapping.py) should give a
real, deterministic score without any AI-specific coursework being required
for every role, and a student with genuinely no coursework or activity
evidence for a role's units should score clearly lower than one who has
relevant activity evidence. This is a small, real offline eval, not a unit
test -- it requires the real seeded fixture students/job roles and a
reachable Ollama instance (run seed_data + have Ollama serving qwen3.5 first).

Role choice matters here: "AI Business & Solution Planner"'s units (business/
technical objective-setting, architecture, project planning) are, per the
curated mapping's own human-reviewed rows, legitimately covered by generic
core IS courses every student takes (ISC101, ISC201, ...) -- so a student
with zero AI-specific coursework can legitimately score high against it, and
that's the curated mapping working as intended, not a calibration failure.
"AI Data Engineer" (data labeling/analysis/filtering/reconstruction) maps
almost entirely to Data Science for Business Analytics track courses a
core-only IS student won't have taken, making it the better "should stay low
without relevant evidence" fixture role.

The LLM-judged text-evidence side (text_evidence.py) is not perfectly
deterministic run to run (temperature/sampling), so thresholds here carry
real margin rather than pinning an exact observed percentage -- see the
gap between the actual measured values (~12.5% / ~70-73%) and the bounds
below.
"""

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.models import JobRole, Student
from app.scoring.gap_engine import analyze_skill_gap

pytestmark = pytest.mark.asyncio(loop_scope="session")

UNRELATED_CASE_MAX_MATCH = 35.0  # Dewi (core IS courses only, no Data Science track) vs AI Data Engineer stays clearly below this
RELATED_CASE_MIN_MATCH = 55.0  # Ahmad (Information System Assurance & Security + a fairness/explainability chatbot project) vs Responsible AI Specialist clears this


async def _match_percentage(student_no: str, role_title: str) -> float:
    async with SessionLocal() as session:
        student = (await session.execute(select(Student).where(Student.student_no == student_no))).scalar_one()
        job_role = (await session.execute(select(JobRole).where(JobRole.role_title == role_title))).scalar_one()
        result = await analyze_skill_gap(session, student.id, job_role)
        return result["match_percentage"]


async def test_student_without_relevant_coursework_or_activities_scores_low():
    match = await _match_percentage("S2023045", "AI Data Engineer")  # Dewi: core IS courses only, no Data Science track
    assert match < UNRELATED_CASE_MAX_MATCH


async def test_related_student_scores_meaningfully_higher_than_unrelated():
    ahmad_match = await _match_percentage("S2022007", "Responsible AI Specialist")
    dewi_match = await _match_percentage("S2023045", "AI Data Engineer")
    assert ahmad_match >= RELATED_CASE_MIN_MATCH
    assert ahmad_match > dewi_match


async def test_curated_course_mapping_alone_can_score_a_role_highly():
    # AI Business & Solution Planner's units map to generic core IS courses
    # (ISC101, ISC201, ...) per the curated mapping's own reviewed rows -- a
    # student needs no AI-specific coursework or activity evidence to score
    # well against it, which is the curated mapping working as intended, not
    # a false positive.
    match = await _match_percentage("S2023045", "AI Business & Solution Planner")
    assert match >= RELATED_CASE_MIN_MATCH
