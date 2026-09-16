"""FastAPI contract tests against the real app + real services (Postgres,
Ollama must be running, with ingestion + seed data already loaded --
see the README). Exercises the actual HTTP surface, not just the underlying
functions.

Uses httpx.AsyncClient over an ASGI transport (not the sync TestClient)
deliberately: TestClient runs the app in a separate thread with its own
event loop via anyio's portal, which conflicts with this app's module-level
asyncpg engine when the rest of the integration suite already owns the
pytest-asyncio session-scoped loop -- the async client shares that same
loop instead.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_health_endpoint_reports_all_services_up():
    async with app.router.lifespan_context(app), await _client() as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["postgres"] and body["vector_store"] and body["ollama"]


async def test_list_students_returns_seeded_fixtures():
    async with app.router.lifespan_context(app), await _client() as client:
        response = await client.get("/api/students")
    assert response.status_code == 200
    students = response.json()
    assert len(students) >= 4
    assert {"S2023001", "S2022014", "S2023045", "S2022007"}.issubset({s["student_no"] for s in students})


async def test_list_job_roles_returns_curated_roles():
    async with app.router.lifespan_context(app), await _client() as client:
        response = await client.get("/api/job-roles")
    assert response.status_code == 200
    roles = response.json()
    assert len(roles) == 6
    assert all(r["is_curated"] for r in roles)


async def test_skill_gap_analysis_end_to_end_contract():
    async with app.router.lifespan_context(app), await _client() as client:
        students = (await client.get("/api/students")).json()
        ahmad = next(s for s in students if s["student_no"] == "S2022007")
        roles = (await client.get("/api/job-roles")).json()
        responsible_ai = next(r for r in roles if r["role_title"] == "Responsible AI Specialist")

        response = await client.post(
            f"/api/analyzer/skill-gap?student_id={ahmad['id']}",
            json={"job_role_id": responsible_ai["id"]},
        )
    assert response.status_code == 200
    body = response.json()

    assert 0.0 <= body["match_percentage"] <= 100.0
    required = set(responsible_ai["required_unit_codes"])
    partitioned = {u["unit_code"] for group in ("matched_units", "partial_units", "missing_units") for u in body[group]}
    assert partitioned == required  # every required unit appears in exactly one bucket, no gaps/dupes
    assert body["narrative_status"] in ("ok", "unavailable", "degraded")
    assert body["embedding_model_version"]


async def test_skill_gap_analysis_rejects_unresolvable_job_target():
    async with app.router.lifespan_context(app), await _client() as client:
        students = (await client.get("/api/students")).json()
        student = students[0]
        response = await client.post(
            f"/api/analyzer/skill-gap?student_id={student['id']}",
            json={"job_role_query": "xyzzy nonsense query unrelated to anything"},
        )
    assert response.status_code == 422


async def test_get_student_profile_not_found_returns_404():
    async with app.router.lifespan_context(app), await _client() as client:
        response = await client.get("/api/students/00000000-0000-0000-0000-000000000000/profile")
    assert response.status_code == 404
