"""End-to-end smoke test over the full real stack (Postgres + pgvector +
Ollama), covering the golden path the README's Prerequisites/Backend
section assumes has already run: ingest -> seed -> analyze -> upload resume
-> score. Complements the narrower per-endpoint contract tests in
tests/integration/test_api_skill_gap.py.
"""

import io

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.asyncio(loop_scope="session")

_FAKE_DOCX_TEXT = (
    "Dewi Anggraini\nEducation: Information Systems, President University.\n"
    "Skills: business process analysis, teamwork.\n"
)


def _fake_docx_bytes() -> bytes:
    from docx import Document

    doc = Document()
    for line in _FAKE_DOCX_TEXT.splitlines():
        doc.add_paragraph(line)
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


async def test_full_golden_path():
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            health = (await client.get("/api/health")).json()
            assert health["status"] == "ok"

            students = (await client.get("/api/students")).json()
            assert len(students) > 0
            student = next(s for s in students if s["student_no"] == "S2023045")

            roles = (await client.get("/api/job-roles")).json()
            assert len(roles) == 6
            job_role = roles[0]

            gap_response = await client.post(
                f"/api/analyzer/skill-gap?student_id={student['id']}",
                json={"job_role_id": job_role["id"]},
            )
            assert gap_response.status_code == 200
            gap_body = gap_response.json()
            assert 0.0 <= gap_body["match_percentage"] <= 100.0
            for course in gap_body["recommended_courses"]:
                assert course["course_code"]  # every recommendation references a real, non-empty course code

            history = (await client.get(f"/api/students/{student['id']}/skill-gap/history")).json()
            assert any(h["id"] == gap_body["analysis_id"] for h in history)

            upload_response = await client.post(
                f"/api/students/{student['id']}/resume/upload",
                files={"file": ("resume.docx", _fake_docx_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )
            assert upload_response.status_code == 201
            resume = upload_response.json()
            assert "Dewi Anggraini" in resume["extracted_text"]

            score_response = await client.get(f"/api/resumes/{resume['id']}/score")
            assert score_response.status_code == 200
            score_body = score_response.json()
            assert 0.0 <= score_body["overall_score"] <= 100.0
            assert score_body["note"] is not None  # no job target supplied -- keyword alignment noted as skipped
