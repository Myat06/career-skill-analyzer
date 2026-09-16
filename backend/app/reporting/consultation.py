"""Assembles all the data behind a student's consultation report/poster into
one dict, reusing the app's existing scoring modules end to end rather than
recomputing anything: resume rubric scoring (app/scoring/resume_score.py),
skill gap + grounded narrative (app/scoring/gap_engine.py,
app/scoring/narrative.py), plus a plain academic snapshot (GPA, course
completion, activity count -- no blended "Career Readiness" score; that
feature was removed as an uncalibrated, unreliable formula over fixture data).
The only new computation here is the four advisory sections from
narrative_prompts.py and the deterministic Evidence & Confidence bands.
Rendering (PDF/PNG) lives in pdf_report.py/poster.py and consumes this dict --
kept separate so both renderers share one data-gathering pass per report
request.

The skill-gap narrative is the one piece worth caching: by the time a report
or poster is requested, the frontend has almost always just run
POST /analyzer/skill-gap for this exact (student, job_role) seconds earlier
(its own ~60-90s LLM call), so recomputing it here would silently double that
wait on top of the resume-grading and advisory-narrative calls this function
also makes. Reusing the latest matching SkillGapAnalysis row's narrative
avoids that duplicate call; the fallback (no such row yet) keeps this
endpoint self-sufficient if hit directly.
"""

import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.fingerprint_cache import FingerprintCache
from app.ingestion.checksums import content_checksum
from app.llm.embeddings import embed_query
from app.models import Activity, Course, Enrollment, JobRole, Resume, ResumeScore, SkillGapAnalysis, Student
from app.reporting.narrative_prompts import generate_consultation_narrative
from app.scoring.gap_engine import analyze_skill_gap, embed_job_target, format_recommended_courses_block
from app.scoring.narrative import generate_narrative
from app.scoring.resume_score import score_resume
from app.scoring.scoring_utils import compute_gpa

CONFIDENCE_HIGH_THRESHOLD = 75
CONFIDENCE_MODERATE_THRESHOLD = 50

CONSULTATION_CACHE_SIZE = 32
_consultation_cache: FingerprintCache[dict] = FingerprintCache(CONSULTATION_CACHE_SIZE)


async def _input_fingerprint(session: AsyncSession, student: Student, job_role: JobRole) -> str:
    """Hashes every input that can change the rendered report.

    The PDF and the poster are two renderings of the *same* consultation, and
    the frontend requests them seconds apart -- but each endpoint called this
    builder independently, so a student downloading both paid twice for the
    same three 60-90s LLM calls (rubric grading, skill-gap narrative, and the
    advisory sections, which unlike the other two were never reused at all).

    Deliberately fingerprint-keyed rather than time-to-live: a student who logs
    an activity, uploads a resume, or re-runs an analysis must see that
    reflected in the very next download, which a TTL cache cannot promise.
    Any change to the inputs below produces a different key, so staleness is
    structurally impossible rather than merely unlikely.
    """
    latest_activity_at, activity_count = (
        await session.execute(
            select(func.max(Activity.created_at), func.count(Activity.id)).where(Activity.student_id == student.id)
        )
    ).one()
    latest_enrollment_at, enrollment_count = (
        await session.execute(
            select(func.max(Enrollment.created_at), func.count(Enrollment.id)).where(
                Enrollment.student_id == student.id
            )
        )
    ).one()
    latest_analysis_at = (
        await session.execute(
            select(func.max(SkillGapAnalysis.created_at)).where(
                SkillGapAnalysis.student_id == student.id, SkillGapAnalysis.job_role_id == job_role.id
            )
        )
    ).scalar_one()
    latest_resume_at = (
        await session.execute(select(func.max(Resume.created_at)).where(Resume.student_id == student.id))
    ).scalar_one()
    latest_resume_score_at = (
        await session.execute(
            select(func.max(ResumeScore.created_at))
            .join(Resume, ResumeScore.resume_id == Resume.id)
            .where(Resume.student_id == student.id)
        )
    ).scalar_one()

    parts = [
        str(student.id),
        str(job_role.id),
        str(latest_activity_at),
        str(activity_count),
        str(latest_enrollment_at),
        str(enrollment_count),
        str(latest_analysis_at),
        str(latest_resume_at),
        str(latest_resume_score_at),
    ]
    return content_checksum("|".join(parts))


def _band(score: float) -> str:
    if score >= CONFIDENCE_HIGH_THRESHOLD:
        return "High"
    if score >= CONFIDENCE_MODERATE_THRESHOLD:
        return "Moderate"
    return "Limited evidence"


async def _build_academic_summary(session: AsyncSession, student_id) -> dict:
    """Plain academic facts (GPA, course completion, activity count) for the
    report/poster profile section and the evidence text below -- no blended
    score, unlike the removed Career Readiness feature."""
    enrollments = (
        await session.execute(select(Enrollment).where(Enrollment.student_id == student_id))
    ).scalars().all()
    activity_count = (
        await session.execute(select(func.count(Activity.id)).where(Activity.student_id == student_id))
    ).scalar_one()
    course_credits = {c.course_code: c.credits for c in (await session.execute(select(Course))).scalars().all()}
    completed = [e for e in enrollments if e.status == "completed"]
    graded = [e for e in completed if e.grade_point is not None]
    return {
        "gpa": compute_gpa(graded, course_credits),
        "completed_courses": len(completed),
        "total_catalog_courses": len(course_credits),
        "activity_count": activity_count,
    }


async def _fetch_latest_resume(session: AsyncSession, student_id) -> Resume | None:
    return (
        await session.execute(
            select(Resume).where(Resume.student_id == student_id).order_by(Resume.created_at.desc())
        )
    ).scalars().first()


async def _fetch_latest_skill_gap_analysis(session: AsyncSession, student_id, job_role_id) -> SkillGapAnalysis | None:
    return (
        await session.execute(
            select(SkillGapAnalysis)
            .where(SkillGapAnalysis.student_id == student_id, SkillGapAnalysis.job_role_id == job_role_id)
            .order_by(SkillGapAnalysis.created_at.desc())
        )
    ).scalars().first()


async def _fetch_latest_resume_score(session: AsyncSession, resume_id, job_role_id) -> ResumeScore | None:
    return (
        await session.execute(
            select(ResumeScore)
            .where(ResumeScore.resume_id == resume_id, ResumeScore.job_role_id == job_role_id)
            .order_by(ResumeScore.created_at.desc())
        )
    ).scalars().first()


async def _score_resume(
    resume: Resume | None, job_role: JobRole, existing_score: ResumeScore | None, student_full_name: str
) -> dict | None:
    """No session access -- safe to run concurrently with generate_narrative() via
    asyncio.gather (a single AsyncSession isn't safe for concurrent use, so anything
    gathered here must have already finished its DB reads). existing_score is looked
    up ahead of time (same reason): the frontend's Upload Resume flow always scores a
    resume against the current target role right after upload, so by the time a
    report/poster is requested that scoring almost always already exists -- reusing it
    skips a second ~60-90s rubric-grading LLM call."""
    if resume is None or not resume.extracted_text:
        return None
    if existing_score is not None:
        return {
            "rubric_categories": existing_score.rubric_categories,
            "keyword_alignment_score": existing_score.keyword_alignment_score,
            "overall_score": existing_score.overall_score,
            "suggestions": existing_score.suggestions,
            "note": existing_score.note,
            "source": resume.source,
        }
    # Neither depends on the other's result, and neither touches the session.
    resume_embedding, job_target_embedding = await asyncio.gather(
        embed_query(resume.extracted_text), embed_job_target(job_role)
    )
    result = await score_resume(
        resume.extracted_text, resume_embedding, job_target_embedding, student_full_name=student_full_name
    )
    result["source"] = resume.source
    return result


def _build_evidence_text(job_role: JobRole, academic: dict, resume_result: dict | None, gap_result: dict) -> str:
    lines = [f"Target role: {job_role.role_title}"]

    lines.append(
        f"Academic standing: GPA {academic['gpa']}, "
        f"{academic['completed_courses']}/{academic['total_catalog_courses']} courses completed. "
        f"Logged activities: {academic['activity_count']}. "
        f"There is no overall 'career readiness' score to report -- discuss academic standing and "
        f"activities as plain facts, not a blended score or percentage."
    )

    if resume_result:
        weak = [c["label"] for c in resume_result["rubric_categories"] if c["score"] < 70]
        strong = [c["label"] for c in resume_result["rubric_categories"] if c["score"] >= 70]
        lines.append(
            f"Resume rubric: strong in {', '.join(strong) or 'none'}; weak in {', '.join(weak) or 'none'}."
        )
    else:
        lines.append("Resume: none on file.")

    lines.append(f"Skill match against target role: {gap_result['match_percentage']}%.")
    if gap_result["matched_units"]:
        lines.append("Matched competencies: " + "; ".join(u.unit_title or u.unit_code for u in gap_result["matched_units"]))
    gaps = gap_result["partial_units"] + gap_result["missing_units"]
    if gaps:
        lines.append("Competency gaps: " + "; ".join(u.unit_title or u.unit_code for u in gaps))
    lines.append(format_recommended_courses_block(gap_result["recommended_courses"]))
    return "\n".join(lines)


async def build_consultation_data(session: AsyncSession, student: Student, job_role: JobRole) -> dict:
    """Cached on a fingerprint of its inputs (see _input_fingerprint) so the PDF
    and poster renderings of one consultation share a single expensive build.
    The cache lives in-process: a restart simply costs one rebuild, and nothing
    downstream depends on it existing.
    """
    fingerprint = await _input_fingerprint(session, student, job_role)
    cached = _consultation_cache.get(fingerprint)
    if cached is not None:
        return cached

    data = await _build_consultation_data_uncached(session, student, job_role)

    # The build itself may persist a freshly-computed ResumeScore, which moves
    # the fingerprint -- so cache under the post-build key as well, or the very
    # next request (the poster following the PDF) would miss and rebuild,
    # exactly the duplicate this cache exists to remove.
    for key in {fingerprint, await _input_fingerprint(session, student, job_role)}:
        _consultation_cache.set(key, data)
    return data


async def _build_consultation_data_uncached(session: AsyncSession, student: Student, job_role: JobRole) -> dict:
    # DB reads happen sequentially on the shared session first; the two LLM calls that
    # follow (resume rubric grading, skill-gap narrative) touch no session state, so they
    # run concurrently -- each takes 60-90s alone, and they're otherwise independent.
    academic = await _build_academic_summary(session, student.id)
    resume = await _fetch_latest_resume(session, student.id)
    gap_result = await analyze_skill_gap(session, student.id, job_role)
    existing_analysis = await _fetch_latest_skill_gap_analysis(session, student.id, job_role.id)
    existing_resume_score = (
        await _fetch_latest_resume_score(session, resume.id, job_role.id) if resume is not None else None
    )

    async def _get_narrative() -> tuple[dict | None, str]:
        # Only reuse a cached narrative that actually succeeded -- reusing one
        # that previously came back "unavailable"/"degraded" would permanently
        # bake a past LLM hiccup into every future report for this (student,
        # job_role) instead of just retrying it, which defeats the point of a
        # narrative existing at all (empty strengths/gaps columns forever).
        if existing_analysis is not None and existing_analysis.narrative_status == "ok":
            return existing_analysis.narrative, existing_analysis.narrative_status
        return await generate_narrative(
            gap_result["matched_units"], gap_result["partial_units"], gap_result["missing_units"], gap_result["recommended_courses"]
        )

    resume_result, (narrative, narrative_status) = await asyncio.gather(
        _score_resume(resume, job_role, existing_resume_score, student.full_name),
        _get_narrative(),
    )

    # A freshly-computed score (existing_resume_score was None going in) never got
    # persisted anywhere -- score_resume() just returns a dict. Without saving it here,
    # this exact ~60-90s rubric-grading call would silently re-run on every future
    # report/poster request for this (resume, job_role), AND the chat endpoint would
    # never be able to see or cite this number (it only reads ResumeScore rows).
    if resume is not None and resume_result is not None and existing_resume_score is None:
        session.add(
            ResumeScore(
                resume_id=resume.id,
                job_role_id=job_role.id,
                rubric_categories=resume_result["rubric_categories"],
                keyword_alignment_score=resume_result["keyword_alignment_score"],
                overall_score=resume_result["overall_score"],
                suggestions=resume_result["suggestions"],
                note=resume_result["note"],
            )
        )
        await session.commit()

    evidence_text = _build_evidence_text(job_role, academic, resume_result, gap_result)
    consultation_narrative = await generate_consultation_narrative(evidence_text)

    confidence = {
        "Skill Match": _band(gap_result["match_percentage"]),
    }
    if resume_result:
        rubric_scores = [c["score"] for c in resume_result["rubric_categories"]]
        rubric_average = sum(rubric_scores) / len(rubric_scores) if rubric_scores else 0.0
        confidence["Resume Quality"] = _band(rubric_average)

    return {
        "student": student,
        "job_role": job_role,
        "academic": academic,
        "resume_result": resume_result,
        "gap_result": gap_result,
        "narrative": narrative,
        "narrative_status": narrative_status,
        "consultation_narrative": consultation_narrative,
        "confidence": confidence,
    }
