import uuid

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.deps import SessionDep, get_student_or_404
from app.models import Activity, Course, Enrollment, JobRole, Resume, ResumeScore, SkillGapAnalysis
from app.scoring.consultation_chat import run_consultation_chat

router = APIRouter(tags=["consultation"])


class ChatMessageIn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ConsultationChatRequest(BaseModel):
    messages: list[ChatMessageIn]
    job_role_id: uuid.UUID | None = None


class ConsultationChatResponse(BaseModel):
    reply: str
    status: str


@router.post("/students/{student_id}/consult", response_model=ConsultationChatResponse)
async def consult(student_id: uuid.UUID, payload: ConsultationChatRequest, session: SessionDep):
    await get_student_or_404(student_id, session)

    gap_query = select(SkillGapAnalysis).where(SkillGapAnalysis.student_id == student_id)
    if payload.job_role_id:
        gap_query = gap_query.where(SkillGapAnalysis.job_role_id == payload.job_role_id)
    analysis = (
        await session.execute(gap_query.order_by(SkillGapAnalysis.created_at.desc()).limit(1))
    ).scalar_one_or_none()

    # Scope to the student's most recent resume upload (re-uploads happen, e.g. while
    # testing, and an older resume's score shouldn't outrank the current one), then
    # within that resume prefer a score run against the CURRENT target role -- a resume
    # can carry several ResumeScore rows (one per job_role_id it was scored against,
    # plus a role-less one from the moment it was first uploaded), and the most recent
    # by time is not necessarily the most relevant one to quote back to the student.
    latest_resume = (
        await session.execute(
            select(Resume).where(Resume.student_id == student_id).order_by(Resume.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()

    skill_gap = None
    if analysis is not None:
        job_role = await session.get(JobRole, analysis.job_role_id)
        # The resume is scored as evidence when this analysis runs (see gap_engine.py's
        # "uploaded_resume" weight) -- if it's since been removed, or replaced by a
        # resume uploaded after this analysis ran, the match/matched/partial/missing
        # numbers below no longer reflect the student's actual current evidence.
        stale = latest_resume is None or latest_resume.created_at > analysis.created_at
        skill_gap = {
            "job_role": {"role_title": job_role.role_title if job_role else "your target role"},
            "match_percentage": analysis.match_percentage,
            "matched_units": analysis.matched_units,
            "partial_units": analysis.partial_units,
            "missing_units": analysis.missing_units,
            "recommended_courses": analysis.recommended_courses,
            "stale": stale,
        }

    resume_score_row = None
    scored_for_current_role = False
    if latest_resume is not None:
        resume_query = select(ResumeScore).where(ResumeScore.resume_id == latest_resume.id)
        if payload.job_role_id:
            resume_score_row = (
                await session.execute(
                    resume_query.where(ResumeScore.job_role_id == payload.job_role_id)
                    .order_by(ResumeScore.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        scored_for_current_role = resume_score_row is not None
        if resume_score_row is None:
            resume_score_row = (
                await session.execute(resume_query.order_by(ResumeScore.created_at.desc()).limit(1))
            ).scalar_one_or_none()

    resume_score = (
        {
            "overall_score": resume_score_row.overall_score,
            "keyword_alignment_score": resume_score_row.keyword_alignment_score,
            "rubric_categories": resume_score_row.rubric_categories,
            "note": resume_score_row.note,
            "scored_for_current_role": scored_for_current_role,
        }
        if resume_score_row is not None
        else None
    )

    activities = (
        await session.execute(
            select(Activity).where(Activity.student_id == student_id).order_by(Activity.created_at)
        )
    ).scalars().all()
    activities_payload = [{"type": a.type, "title": a.title, "description": a.description} for a in activities]

    # "Which courses should I take next?" is a question the chat could only answer
    # before via a skill-gap analysis's recommended_courses -- which only exist for
    # units that are actually missing/partial, so a 100%-match analysis (or no
    # analysis at all) left the assistant with no course data whatsoever, honest but
    # useless ("I don't have your curriculum"). Give it the student's own remaining
    # catalog courses directly so it can answer that question regardless of whether a
    # skill-gap analysis happens to exist for whatever role is currently in view.
    completed_codes = set(
        (
            await session.execute(
                select(Enrollment.course_code).where(
                    Enrollment.student_id == student_id, Enrollment.status == "completed"
                )
            )
        )
        .scalars()
        .all()
    )
    all_courses = (await session.execute(select(Course).order_by(Course.semester, Course.course_code))).scalars().all()
    remaining_courses_payload = [
        {
            "course_code": c.course_code,
            "course_name": c.course_name,
            "semester": c.semester,
            "credits": c.credits,
            "concentration_track": c.concentration_track,
        }
        for c in all_courses
        if c.course_code not in completed_codes
    ]

    reply, status = await run_consultation_chat(
        [m.model_dump() for m in payload.messages],
        skill_gap=skill_gap,
        resume_score=resume_score,
        activities=activities_payload,
        remaining_courses=remaining_courses_payload,
    )
    return ConsultationChatResponse(reply=reply, status=status)
