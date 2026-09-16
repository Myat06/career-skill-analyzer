"""Orchestrates PDF -> parse -> chunk -> diff-against-manifest -> embed ->
upsert into Postgres (`skkni_chunks`/`curriculum_chunks`, pgvector). Also
upserts the Postgres `courses` table directly from parsed curriculum data --
the curriculum book's per-course detail cards are the single source of
truth for course records, so there is no separate seed file for courses
(see app/ingestion/curriculum_parser.py).

Incremental resync: each chunk's content checksum is compared against
IngestionManifestEntry rows for the same source file; only new/changed
chunks are (re-)embedded and upserted, and manifest rows no longer produced
by a run are deleted from both the chunk table and the manifest. This is
the fix for knowledge-base's full delete-and-reinsert pattern that
rag-pipeline-review.pdf flagged.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.llm.embeddings import embed_texts
from app.ingestion.checksums import content_checksum
from app.ingestion.chunking import chunk_section, count_tokens
from app.ingestion.curriculum_parser import CurriculumCourse, parse_curriculum_courses
from app.ingestion.pdf_extract import extract_text
from app.ingestion.skkni_parser import SkkniUnit, parse_skkni_units
from app.models import Course, IngestionManifestEntry, IngestionRun
from app.vectorstore import (
    CURRICULUM_COLLECTION_BASE,
    SKKNI_COLLECTION_BASE,
    collection_name,
    curriculum_collection,
    skkni_collection,
)


@dataclass
class ChunkDoc:
    chunk_id: str
    text: str
    metadata: dict


def _skkni_chunks(units: list[SkkniUnit]) -> list[ChunkDoc]:
    docs: list[ChunkDoc] = []
    for unit in units:
        base_meta = {
            "doc_type": "skkni",
            "unit_code": unit.unit_code,
            "unit_title": unit.unit_title,
            "sector_code": unit.unit_code.split(".")[1] if "." in unit.unit_code else "",
            "source_file": settings.skkni_pdf_filename,
            "source_page": unit.source_page,
            "parse_confidence": unit.parse_confidence,
        }

        desc_text = f"{unit.unit_title}\n\n{unit.description}"
        for idx, piece in enumerate(chunk_section(desc_text)):
            docs.append(
                ChunkDoc(
                    chunk_id=f"skkni:{unit.unit_code}:description:{idx}",
                    text=piece,
                    metadata={**base_meta, "section_type": "description", "element_number": None},
                )
            )

        for element in unit.elements:
            criteria_text = "\n".join(f"{c.number} {c.text}" for c in element.criteria)
            element_text = f"Element {element.number}: {element.title}\n{criteria_text}"
            for idx, piece in enumerate(chunk_section(element_text)):
                docs.append(
                    ChunkDoc(
                        chunk_id=f"skkni:{unit.unit_code}:element:{element.number}:{idx}",
                        text=piece,
                        metadata={
                            **base_meta,
                            "section_type": "element",
                            "element_number": element.number,
                            "element_title": element.title,
                        },
                    )
                )

        for section_type, text in (("variable_scope", unit.variable_scope), ("assessment_guide", unit.assessment_guide)):
            if not text:
                continue
            for idx, piece in enumerate(chunk_section(text)):
                docs.append(
                    ChunkDoc(
                        chunk_id=f"skkni:{unit.unit_code}:{section_type}:{idx}",
                        text=piece,
                        metadata={**base_meta, "section_type": section_type, "element_number": None},
                    )
                )
    return docs


def _curriculum_chunks(courses: list[CurriculumCourse]) -> list[ChunkDoc]:
    docs: list[ChunkDoc] = []
    for course in courses:
        base_meta = {
            "doc_type": "curriculum",
            "course_code": course.course_code,
            "course_name": course.course_name,
            "semester": course.semester,
            "plo_codes": ",".join(course.related_plo),
            "source_file": settings.curriculum_pdf_filename,
            "source_page": course.source_page,
        }
        text = (
            f"{course.course_name} ({course.course_code})\n\n"
            f"Description: {course.description}\n\n"
            f"Learning objective: {course.cpmk}"
        )
        for idx, piece in enumerate(chunk_section(text)):
            docs.append(ChunkDoc(chunk_id=f"curriculum:{course.course_code}:{idx}", text=piece, metadata=base_meta))
    return docs


async def _sync_chunks(
    session: AsyncSession, source_file: str, collection, docs: list[ChunkDoc]
) -> tuple[int, int, int]:
    """Returns (chunks_written, chunks_skipped_unchanged, chunks_deleted)."""
    coll_name = collection.name
    checksums = {d.chunk_id: content_checksum(d.text) for d in docs}
    docs_by_id = {d.chunk_id: d for d in docs}

    existing_rows = (
        await session.execute(
            select(IngestionManifestEntry).where(
                IngestionManifestEntry.source_file == source_file,
                IngestionManifestEntry.embedding_model_version == coll_name,
            )
        )
    ).scalars().all()
    existing = {row.chunk_id: row.checksum for row in existing_rows}

    changed_ids = [cid for cid, cs in checksums.items() if existing.get(cid) != cs]
    removed_ids = [cid for cid in existing if cid not in checksums]

    if changed_ids:
        changed_docs = [docs_by_id[cid] for cid in changed_ids]
        embeddings = await embed_texts([d.text for d in changed_docs])
        metadatas = [
            {
                **d.metadata,
                "chunk_checksum": checksums[d.chunk_id],
                "embedding_model_version": coll_name,
                "token_count": count_tokens(d.text),
            }
            for d in changed_docs
        ]
        await collection.upsert(
            ids=[d.chunk_id for d in changed_docs],
            documents=[d.text for d in changed_docs],
            embeddings=embeddings,
            metadatas=metadatas,
        )
    if removed_ids:
        await collection.delete(ids=removed_ids)

    await session.execute(
        delete(IngestionManifestEntry).where(
            IngestionManifestEntry.source_file == source_file,
            IngestionManifestEntry.embedding_model_version == coll_name,
        )
    )
    session.add_all(
        IngestionManifestEntry(
            source_file=source_file, chunk_id=cid, embedding_model_version=coll_name, checksum=checksums[cid]
        )
        for cid in checksums
    )
    return len(changed_ids), len(checksums) - len(changed_ids), len(removed_ids)


async def _upsert_courses(session: AsyncSession, courses: list[CurriculumCourse]) -> None:
    existing = {c.course_code: c for c in (await session.execute(select(Course))).scalars().all()}
    for course in courses:
        learning_outcomes = {
            "description": course.description,
            "cpmk": course.cpmk,
            "related_plo": course.related_plo,
        }
        row = existing.get(course.course_code)
        if row is None:
            session.add(
                Course(
                    course_code=course.course_code,
                    course_name=course.course_name,
                    credits=course.credits,
                    semester=course.semester,
                    concentration_track=course.concentration_track,
                    course_type=course.course_type,
                    learning_outcomes=learning_outcomes,
                    curriculum_chunk_ref=f"curriculum:{course.course_code}:0",
                )
            )
        else:
            row.course_name = course.course_name
            row.credits = course.credits
            row.semester = course.semester
            row.concentration_track = course.concentration_track
            row.course_type = course.course_type
            row.learning_outcomes = learning_outcomes
            row.curriculum_chunk_ref = f"curriculum:{course.course_code}:0"


async def run_skkni_ingestion(session: AsyncSession) -> IngestionRun:
    run = IngestionRun(
        source_file=settings.skkni_pdf_filename,
        embedding_model_version=collection_name(SKKNI_COLLECTION_BASE),
        status="running",
    )
    session.add(run)
    await session.flush()

    extracted = extract_text(settings.skkni_pdf_path)
    units, blocks_skipped = parse_skkni_units(extracted)
    docs = _skkni_chunks(units)
    written, skipped, deleted = await _sync_chunks(session, settings.skkni_pdf_filename, skkni_collection(), docs)

    run.chunks_written = written
    run.chunks_skipped = skipped
    run.chunks_deleted = deleted
    run.completed_at = datetime.now(timezone.utc)
    run.status = "completed"
    run.notes = f"{len(units)} SKKNI units parsed ({len(docs)} chunks); {blocks_skipped} non-unit blocks skipped"
    await session.commit()
    return run


async def run_curriculum_ingestion(session: AsyncSession) -> IngestionRun:
    run = IngestionRun(
        source_file=settings.curriculum_pdf_filename,
        embedding_model_version=collection_name(CURRICULUM_COLLECTION_BASE),
        status="running",
    )
    session.add(run)
    await session.flush()

    extracted = extract_text(settings.curriculum_pdf_path)
    courses, cards_skipped = parse_curriculum_courses(extracted)
    docs = _curriculum_chunks(courses)
    written, skipped, deleted = await _sync_chunks(
        session, settings.curriculum_pdf_filename, curriculum_collection(), docs
    )
    await _upsert_courses(session, courses)

    run.chunks_written = written
    run.chunks_skipped = skipped
    run.chunks_deleted = deleted
    run.completed_at = datetime.now(timezone.utc)
    run.status = "completed"
    run.notes = f"{len(courses)} courses parsed ({len(docs)} chunks); {cards_skipped} non-course cards skipped"
    await session.commit()
    return run


async def run_full_ingestion(session: AsyncSession) -> list[IngestionRun]:
    return [await run_skkni_ingestion(session), await run_curriculum_ingestion(session)]
