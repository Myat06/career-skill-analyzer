from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.deps import SessionDep
from app.ingestion.index_pipeline import run_curriculum_ingestion, run_skkni_ingestion
from app.models import IngestionRun
from app.schemas import IngestionRunOut, IngestionStatusOut
from app.vectorstore import curriculum_collection, skkni_collection

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


class IngestionRunRequest(BaseModel):
    sources: list[str] | None = None  # any of "skkni", "curriculum"; None runs both


@router.post("/run", response_model=list[IngestionRunOut])
async def trigger_ingestion(payload: IngestionRunRequest, session: SessionDep):
    sources = payload.sources or ["skkni", "curriculum"]
    runs = []
    if "skkni" in sources:
        runs.append(await run_skkni_ingestion(session))
    if "curriculum" in sources:
        runs.append(await run_curriculum_ingestion(session))
    return runs


@router.get("/runs", response_model=list[IngestionRunOut])
async def list_ingestion_runs(session: SessionDep):
    runs = (await session.execute(select(IngestionRun).order_by(IngestionRun.started_at.desc()))).scalars().all()
    return runs


@router.get("/status", response_model=IngestionStatusOut)
async def ingestion_status(session: SessionDep):
    last_run = (
        await session.execute(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(1))
    ).scalar_one_or_none()
    return IngestionStatusOut(
        collection_counts={
            "skkni_units": await skkni_collection().count(),
            "curriculum_courses": await curriculum_collection().count(),
        },
        last_run_at=last_run.started_at if last_run else None,
    )
