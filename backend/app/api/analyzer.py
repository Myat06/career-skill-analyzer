import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.deps import SessionDep, get_student_or_404
from app.models import JobRole, SkillGapAnalysis
from app.schemas import (
    JobRoleOut,
    Narrative,
    RecommendedCourse as RecommendedCourseSchema,
    SkillGapRequest,
    SkillGapResponse,
    SkillGapSummary,
    UnitCoverage,
)
from app.scoring.gap_engine import (
    analyze_skill_gap,
    resolve_job_target,
    JOB_MATCH_CONFIDENCE_THRESHOLD,
    MATCHING_ENGINE_VERSION,
    UNIT_MATCH_ELEMENT_RATIO,
)
from app.scoring.narrative import generate_narrative
from app.vectorstore import SKKNI_COLLECTION_BASE, collection_name

router = APIRouter(tags=["analyzer"])

RANKING_CONFIG_VERSION = (
    f"engine={MATCHING_ENGINE_VERSION}|ratio={UNIT_MATCH_ELEMENT_RATIO}|job={JOB_MATCH_CONFIDENCE_THRESHOLD}"
)


def _coverage_out(c) -> UnitCoverage:
    return UnitCoverage(
        unit_code=c.unit_code,
        unit_title=c.unit_title,
        coverage_fraction=round(c.coverage_fraction, 4),
        matched_elements=c.matched_elements,
        unmatched_elements=c.unmatched_elements,
    )


@router.post("/analyzer/skill-gap", response_model=SkillGapResponse)
async def run_skill_gap_analysis(student_id: uuid.UUID, payload: SkillGapRequest, session: SessionDep):
    await get_student_or_404(student_id, session)

    job_role, _, low_confidence = await resolve_job_target(
        session, job_role_id=payload.job_role_id, job_role_query=payload.job_role_query
    )
    if job_role is None:
        raise HTTPException(
            status_code=422,
            detail="Could not resolve a job target. Provide job_role_id from GET /job-roles, "
            "or a more specific job_role_query." + (" (low confidence match)" if low_confidence else ""),
        )

    result = await analyze_skill_gap(session, student_id, job_role, payload.include_uploaded_resume)
    narrative, narrative_status = await generate_narrative(
        result["matched_units"], result["partial_units"], result["missing_units"], result["recommended_courses"]
    )

    embedding_model_version = collection_name(SKKNI_COLLECTION_BASE)
    analysis = SkillGapAnalysis(
        student_id=student_id,
        job_role_id=job_role.id,
        match_percentage=result["match_percentage"],
        matched_units=[_coverage_out(c).model_dump() for c in result["matched_units"]],
        partial_units=[_coverage_out(c).model_dump() for c in result["partial_units"]],
        missing_units=[_coverage_out(c).model_dump() for c in result["missing_units"]],
        recommended_courses=[
            {
                "course_code": c.course_code,
                "course_name": c.course_name,
                "for_unit_code": c.for_unit_code,
                "match_reason": c.match_reason,
            }
            for c in result["recommended_courses"]
        ],
        narrative=narrative,
        narrative_status=narrative_status,
        embedding_model_version=embedding_model_version,
        ranking_config_version=RANKING_CONFIG_VERSION,
    )
    session.add(analysis)
    await session.commit()
    await session.refresh(analysis)

    return SkillGapResponse(
        analysis_id=analysis.id,
        job_role=JobRoleOut.model_validate(job_role),
        match_percentage=result["match_percentage"],
        matched_units=[_coverage_out(c) for c in result["matched_units"]],
        partial_units=[_coverage_out(c) for c in result["partial_units"]],
        missing_units=[_coverage_out(c) for c in result["missing_units"]],
        recommended_courses=[
            RecommendedCourseSchema(
                course_code=c.course_code, course_name=c.course_name, for_unit_code=c.for_unit_code, match_reason=c.match_reason
            )
            for c in result["recommended_courses"]
        ],
        narrative=Narrative.model_validate(narrative) if narrative else None,
        narrative_status=narrative_status,
        embedding_model_version=embedding_model_version,
    )


@router.get("/analyzer/skill-gap/{analysis_id}", response_model=SkillGapResponse)
async def get_skill_gap_analysis(analysis_id: uuid.UUID, session: SessionDep):
    analysis = await session.get(SkillGapAnalysis, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")
    job_role = await session.get(JobRole, analysis.job_role_id)
    return SkillGapResponse(
        analysis_id=analysis.id,
        job_role=JobRoleOut.model_validate(job_role),
        match_percentage=analysis.match_percentage,
        matched_units=[UnitCoverage(**u) for u in analysis.matched_units],
        partial_units=[UnitCoverage(**u) for u in analysis.partial_units],
        missing_units=[UnitCoverage(**u) for u in analysis.missing_units],
        recommended_courses=[RecommendedCourseSchema(**c) for c in analysis.recommended_courses],
        narrative=Narrative.model_validate(analysis.narrative) if analysis.narrative else None,
        narrative_status=analysis.narrative_status,
        embedding_model_version=analysis.embedding_model_version,
    )


@router.get("/students/{student_id}/skill-gap/history", response_model=list[SkillGapSummary])
async def get_skill_gap_history(student_id: uuid.UUID, session: SessionDep):
    await get_student_or_404(student_id, session)
    analyses = (
        await session.execute(
            select(SkillGapAnalysis)
            .where(SkillGapAnalysis.student_id == student_id)
            .order_by(SkillGapAnalysis.created_at.desc())
        )
    ).scalars().all()
    return analyses
