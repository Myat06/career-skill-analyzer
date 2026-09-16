import uuid

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from app.deps import SessionDep, get_student_or_404
from app.reporting.consultation import build_consultation_data
from app.reporting.pdf_report import render_consultation_pdf
from app.reporting.poster import render_consultation_poster
from app.scoring.gap_engine import resolve_job_target

router = APIRouter(tags=["reports"])


class RoadmapStep(BaseModel):
    timeframe: str
    actions: str


class ConsultationSummary(BaseModel):
    """The advisory content that goes *into* the PDF/poster, returned as JSON.

    The report endpoints return binary, so everything the model wrote for a
    consultation -- the executive summary, the coach message, the roadmap --
    reached the student only if they opened the downloaded file. This exposes
    the same content so the app can say something substantive after generating
    one, instead of "check your downloads".

    Cheap by construction: build_consultation_data is cached on a fingerprint
    of its inputs (app/reporting/consultation.py), so a call made right after
    the PDF or poster download hits that cache and costs no further LLM calls.
    """

    job_role_title: str
    match_percentage: float
    executive_summary: str
    coach_message: str
    recommended_direction: str
    next_step: RoadmapStep | None
    confidence: dict[str, str]
    resume_note: str | None


async def _resolve_report_target(student_id: uuid.UUID, session: SessionDep, job_role_id, job_role_query):
    student = await get_student_or_404(student_id, session)
    job_role, _, low_confidence = await resolve_job_target(session, job_role_id=job_role_id, job_role_query=job_role_query)
    if job_role is None:
        raise HTTPException(
            status_code=422,
            detail="Could not resolve a job target. Provide job_role_id from GET /job-roles, "
            "or a more specific job_role_query." + (" (low confidence match)" if low_confidence else ""),
        )
    await session.commit()
    return student, job_role


@router.get("/students/{student_id}/consultation-report.pdf")
async def get_consultation_report_pdf(
    student_id: uuid.UUID,
    session: SessionDep,
    job_role_id: uuid.UUID | None = Query(None),
    job_role_query: str | None = Query(None),
):
    student, job_role = await _resolve_report_target(student_id, session, job_role_id, job_role_query)
    data = await build_consultation_data(session, student, job_role)
    pdf_bytes = render_consultation_pdf(data)
    filename = f"{student.student_no}-consultation-report.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/students/{student_id}/consultation-poster.png")
async def get_consultation_poster_png(
    student_id: uuid.UUID,
    session: SessionDep,
    job_role_id: uuid.UUID | None = Query(None),
    job_role_query: str | None = Query(None),
):
    student, job_role = await _resolve_report_target(student_id, session, job_role_id, job_role_query)
    data = await build_consultation_data(session, student, job_role)
    png_bytes = render_consultation_poster(data)
    filename = f"{student.student_no}-consultation-poster.png"
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/students/{student_id}/consultation-summary", response_model=ConsultationSummary)
async def get_consultation_summary(
    student_id: uuid.UUID,
    session: SessionDep,
    job_role_id: uuid.UUID | None = Query(None),
    job_role_query: str | None = Query(None),
):
    student, job_role = await _resolve_report_target(student_id, session, job_role_id, job_role_query)
    data = await build_consultation_data(session, student, job_role)
    consult = data["consultation_narrative"] or {}
    roadmap = consult.get("career_roadmap") or []
    return ConsultationSummary(
        job_role_title=job_role.role_title,
        match_percentage=data["gap_result"]["match_percentage"],
        executive_summary=consult.get("executive_summary", ""),
        coach_message=consult.get("coach_message", ""),
        recommended_direction=consult.get("recommended_direction", ""),
        next_step=RoadmapStep(**roadmap[0]) if roadmap else None,
        confidence=data["confidence"],
        resume_note=(data["resume_result"] or {}).get("note"),
    )
