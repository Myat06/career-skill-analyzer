"""Integration test against the real PDFs and real Postgres+pgvector:
proves the parsers find the expected real counts, and that a second
ingestion run is a true no-op (the incremental-resync guarantee).
Requires Postgres.app and Ollama running locally.
"""

import pytest

from app.database import SessionLocal
from app.ingestion.index_pipeline import run_curriculum_ingestion, run_skkni_ingestion

pytestmark = pytest.mark.asyncio(loop_scope="session")

EXPECTED_SKKNI_UNIT_COUNT = 27
EXPECTED_CURRICULUM_COURSE_COUNT = 48


async def test_skkni_ingestion_finds_all_known_units():
    async with SessionLocal() as session:
        run = await run_skkni_ingestion(session)
    assert f"{EXPECTED_SKKNI_UNIT_COUNT} SKKNI units parsed" in run.notes
    assert "0 non-unit blocks skipped" in run.notes


async def test_curriculum_ingestion_finds_all_known_courses():
    async with SessionLocal() as session:
        run = await run_curriculum_ingestion(session)
    assert f"{EXPECTED_CURRICULUM_COURSE_COUNT} courses parsed" in run.notes
    assert "0 non-course cards skipped" in run.notes


async def test_second_ingestion_run_writes_nothing_new():
    async with SessionLocal() as session:
        skkni_run = await run_skkni_ingestion(session)
        curriculum_run = await run_curriculum_ingestion(session)

    assert skkni_run.chunks_written == 0
    assert skkni_run.chunks_deleted == 0
    assert skkni_run.chunks_skipped > 0

    assert curriculum_run.chunks_written == 0
    assert curriculum_run.chunks_deleted == 0
    assert curriculum_run.chunks_skipped > 0
