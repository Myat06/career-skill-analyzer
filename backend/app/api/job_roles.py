from fastapi import APIRouter, Query
from sqlalchemy import select

from app.deps import SessionDep
from app.models import JobRole
from app.schemas import JobRoleOut, JobRoleResolveOut
from app.scoring.gap_engine import resolve_job_target

router = APIRouter(tags=["job-roles"])


@router.get("/job-roles", response_model=list[JobRoleOut])
async def list_job_roles(session: SessionDep):
    roles = (
        await session.execute(select(JobRole).where(JobRole.is_curated).order_by(JobRole.role_title))
    ).scalars().all()
    return roles


@router.get("/job-roles/resolve", response_model=JobRoleResolveOut)
async def resolve_job_role(session: SessionDep, query: str = Query(..., min_length=2)):
    job_role, confidence, low_confidence = await resolve_job_target(session, job_role_query=query)
    if job_role is not None:
        await session.commit()
    return JobRoleResolveOut(
        matched_job_role=JobRoleOut.model_validate(job_role) if job_role else None,
        confidence=round(confidence, 4),
        low_confidence=low_confidence,
        candidate_unit_codes=job_role.required_unit_codes if job_role else [],
    )
