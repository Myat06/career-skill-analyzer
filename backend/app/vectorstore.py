"""Postgres+pgvector-backed replacement for the ChromaDB collections this
project used to keep in a separate `chroma_data/` persistence directory.
`skkni_collection()`/`curriculum_collection()` return a `PgVectorCollection`
wrapper matching Chroma's own collection interface closely enough
(`.name`, `.get(where=, include=)`, `.query(query_embeddings=, n_results=,
where=)`, `.upsert(...)`, `.delete(ids=)`, `.count()`, including its
Chroma-shaped `{"ids": [...], "documents": [...], "metadatas": [...]}` /
nested-list `.query()` return shapes) that every caller written against the
old Chroma client keeps working with only an `await` added, rather than
rewriting six call sites' worth of query logic. `_apply_where()` supports
only the two filter shapes this codebase actually uses (a flat equality
dict, and `{"$and": [...]}` combining equality/`{"$in": [...]}` clauses) --
not a general Chroma-query-language interpreter.

Collection names stay versioned by embedding model (`{base}__{model}`, e.g.
`skkni_units__embeddinggemma`) purely as a logical tag stored per-chunk and
in the ingestion manifest -- unlike Chroma, the underlying Postgres tables
are fixed (`skkni_chunks`/`curriculum_chunks`), so a model swap doesn't
create a new table, but the tag is still what lets a future ingestion run
detect "this chunk was embedded under a different model" if that matters
later.
"""

from typing import Any

from sqlalchemy import delete, func, select

from app.config import settings
from app.database import SessionLocal
from app.models import CurriculumChunk, SkkniChunk

SKKNI_COLLECTION_BASE = "skkni_units"
CURRICULUM_COLLECTION_BASE = "curriculum_courses"

# Columns every chunk model carries besides its primary key/embedded text --
# what Chroma called "metadata". Reconstructed generically from each model's
# own columns rather than hardcoded per collection, since the two models'
# column sets already differ.
_NON_METADATA_COLUMNS = {"id", "content", "embedding"}


def collection_name(base: str) -> str:
    return f"{base}__{settings.embedding_model.replace(':', '-')}"


def _metadata_columns(model) -> list[str]:
    return [c.name for c in model.__table__.columns if c.name not in _NON_METADATA_COLUMNS]


def _row_to_metadata(model, row) -> dict[str, Any]:
    return {col: getattr(row, col) for col in _metadata_columns(model)}


def _apply_where(stmt, model, where: dict | None):
    """Translates the two Chroma `where` shapes actually used in this
    codebase into SQLAlchemy conditions: a flat equality dict
    (`{"field": value}`), and `{"$and": [...]}` combining equality clauses
    with `{"field": {"$in": [...]}}` clauses."""
    if not where:
        return stmt

    conditions = []

    def handle(clause: dict) -> None:
        for key, value in clause.items():
            if key == "$and":
                for sub in value:
                    handle(sub)
            elif isinstance(value, dict) and "$in" in value:
                conditions.append(getattr(model, key).in_(value["$in"]))
            else:
                conditions.append(getattr(model, key) == value)

    handle(where)
    return stmt.where(*conditions)


class PgVectorCollection:
    def __init__(self, base: str, model):
        self.name = collection_name(base)
        self._model = model

    async def get(self, where: dict | None = None, include: list[str] | None = None) -> dict:
        include = include or []
        async with SessionLocal() as session:
            stmt = _apply_where(select(self._model), self._model, where)
            rows = (await session.execute(stmt)).scalars().all()
        result: dict[str, Any] = {"ids": [r.id for r in rows]}
        if "documents" in include:
            result["documents"] = [r.content for r in rows]
        if "metadatas" in include:
            result["metadatas"] = [_row_to_metadata(self._model, r) for r in rows]
        return result

    async def query(
        self, query_embeddings: list[list[float]], n_results: int = 10, where: dict | None = None
    ) -> dict:
        embedding = query_embeddings[0]
        distance = self._model.embedding.cosine_distance(embedding).label("distance")
        async with SessionLocal() as session:
            stmt = _apply_where(select(self._model, distance), self._model, where)
            stmt = stmt.order_by("distance").limit(n_results)
            rows = (await session.execute(stmt)).all()
        return {
            "ids": [[row[0].id for row in rows]],
            "distances": [[row.distance for row in rows]],
            "metadatas": [[_row_to_metadata(self._model, row[0]) for row in rows]],
        }

    async def upsert(
        self, ids: list[str], documents: list[str], embeddings: list[list[float]], metadatas: list[dict]
    ) -> None:
        async with SessionLocal() as session:
            for chunk_id, text, embedding, metadata in zip(ids, documents, embeddings, metadatas):
                await session.merge(self._model(id=chunk_id, content=text, embedding=embedding, **metadata))
            await session.commit()

    async def delete(self, ids: list[str]) -> None:
        if not ids:
            return
        async with SessionLocal() as session:
            await session.execute(delete(self._model).where(self._model.id.in_(ids)))
            await session.commit()

    async def count(self) -> int:
        async with SessionLocal() as session:
            return (await session.execute(select(func.count()).select_from(self._model))).scalar_one()


def skkni_collection() -> PgVectorCollection:
    return PgVectorCollection(SKKNI_COLLECTION_BASE, SkkniChunk)


def curriculum_collection() -> PgVectorCollection:
    return PgVectorCollection(CURRICULUM_COLLECTION_BASE, CurriculumChunk)
