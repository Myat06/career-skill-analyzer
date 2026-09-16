from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session


async def init_models() -> None:
    import app.models  # noqa: F401 -- registers all tables on Base.metadata before create_all

    async with engine.begin() as conn:
        # Idempotent -- safe to run on every startup. Needed before create_all
        # since SkkniChunk/CurriculumChunk's `embedding` columns are pgvector's
        # `vector` type.
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
