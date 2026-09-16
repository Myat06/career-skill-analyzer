"""Regression tests for deleting an uploaded resume.

Deleting a resume that had ever been scored returned a 500. models.py declares
no relationship() anywhere, and SQLAlchemy's unit of work derives inter-mapper
delete *ordering* from relationships rather than from bare ForeignKey columns,
so marking the ResumeScore rows and the Resume row with session.delete() and
committing emitted "DELETE FROM resumes" first -- which violated
resume_scores_resume_id_fkey, aborted the transaction, and meant the
resume_scores delete was never issued at all.

Same setup requirements as the rest of the integration suite (real
Postgres+pgvector and Ollama, ingested and seeded).
"""

import io

import pytest
from docx import Document
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models import JobRole, Resume, ResumeScore

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _docx_bytes(text: str) -> bytes:
    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


async def _upload(client: AsyncClient, student_id: str) -> str:
    response = await client.post(
        f"/api/students/{student_id}/resume/upload",
        files={
            "file": (
                "regression-test.docx",
                _docx_bytes("Regression test resume for the delete path."),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _first_student_id(client: AsyncClient) -> str:
    response = await client.get("/api/students")
    assert response.status_code == 200
    return response.json()[0]["id"]


async def test_delete_unscored_resume_succeeds():
    async with app.router.lifespan_context(app), await _client() as client:
        student_id = await _first_student_id(client)
        resume_id = await _upload(client, student_id)

        response = await client.delete(f"/api/students/{student_id}/resume/{resume_id}")
        assert response.status_code == 204, response.text

        async with SessionLocal() as session:
            assert await session.get(Resume, resume_id) is None


async def test_delete_scored_resume_succeeds_and_removes_its_scores():
    """The case that used to 500: a resume with at least one ResumeScore row."""
    async with app.router.lifespan_context(app), await _client() as client:
        student_id = await _first_student_id(client)
        resume_id = await _upload(client, student_id)

        # Attach a score row directly rather than calling the scoring endpoint,
        # which would spend a 60-90s LLM call to produce the same precondition.
        async with SessionLocal() as session:
            job_role = (await session.execute(select(JobRole).limit(1))).scalars().first()
            session.add(
                ResumeScore(
                    resume_id=resume_id,
                    job_role_id=job_role.id,
                    rubric_categories=[],
                    keyword_alignment_score=50.0,
                    overall_score=50.0,
                    suggestions=[],
                    note=None,
                )
            )
            await session.commit()

        response = await client.delete(f"/api/students/{student_id}/resume/{resume_id}")
        assert response.status_code == 204, response.text

        async with SessionLocal() as session:
            assert await session.get(Resume, resume_id) is None
            remaining = (
                await session.execute(select(ResumeScore).where(ResumeScore.resume_id == resume_id))
            ).scalars().all()
            assert remaining == []


async def test_delete_is_404_for_a_resume_belonging_to_another_student():
    async with app.router.lifespan_context(app), await _client() as client:
        students = (await client.get("/api/students")).json()
        if len(students) < 2:
            pytest.skip("needs at least two fixture students")
        owner_id, other_id = students[0]["id"], students[1]["id"]
        resume_id = await _upload(client, owner_id)
        try:
            response = await client.delete(f"/api/students/{other_id}/resume/{resume_id}")
            assert response.status_code == 404
        finally:
            await client.delete(f"/api/students/{owner_id}/resume/{resume_id}")
