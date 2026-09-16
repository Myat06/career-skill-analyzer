import httpx
from fastapi import APIRouter
from sqlalchemy import text

from app.config import settings
from app.deps import SessionDep
from app.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
async def health(session: SessionDep):
    postgres_ok = False
    try:
        await session.execute(text("SELECT 1"))
        postgres_ok = True
    except Exception:
        postgres_ok = False

    vector_store_ok = False
    try:
        result = await session.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
        vector_store_ok = result.scalar_one_or_none() is not None
    except Exception:
        vector_store_ok = False

    ollama_ok = False
    try:
        async with httpx.AsyncClient(base_url=settings.ollama_host, timeout=5) as client:
            response = await client.get("/api/tags")
            ollama_ok = response.status_code == 200
    except Exception:
        ollama_ok = False

    status = "ok" if (postgres_ok and vector_store_ok and ollama_ok) else "degraded"
    return HealthOut(status=status, postgres=postgres_ok, vector_store=vector_store_ok, ollama=ollama_ok)
