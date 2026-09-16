"""Idempotent seed loader for data/seed/*.yaml. Students/enrollments/
activities are hand-authored fixture data (mock, not from a real SIS); job
roles are curated from data/seed/job_role_definitions.yaml and validated
against the SKKNI unit codes actually present in Postgres at seed time -- an
unknown code in the YAML fails loudly rather than producing a job role with
a silently-broken requirement.
"""

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import SEED_DATA_DIR
from app.models import Activity, Enrollment, JobRole, Student
from app.scoring.gap_engine import slugify
from app.vectorstore import skkni_collection


def _load_yaml(filename: str) -> list[dict]:
    path = SEED_DATA_DIR / filename
    with open(path) as f:
        return yaml.safe_load(f) or []


async def _known_unit_codes() -> set[str]:
    data = await skkni_collection().get(where={"section_type": "description"}, include=["metadatas"])
    return {m["unit_code"] for m in data["metadatas"]}


async def seed_students(session: AsyncSession) -> int:
    existing = {s.student_no for s in (await session.execute(select(Student))).scalars().all()}
    created = 0
    for row in _load_yaml("students.yaml"):
        if row["student_no"] in existing:
            continue
        session.add(Student(**row))
        created += 1
    return created


async def seed_enrollments(session: AsyncSession) -> int:
    students = {s.student_no: s.id for s in (await session.execute(select(Student))).scalars().all()}
    existing = {
        (e.student_id, e.course_code, e.semester_taken)
        for e in (await session.execute(select(Enrollment))).scalars().all()
    }
    created = 0
    for row in _load_yaml("enrollments.yaml"):
        student_id = students.get(row["student_no"])
        if student_id is None:
            continue
        key = (student_id, row["course_code"], row["semester_taken"])
        if key in existing:
            continue
        session.add(
            Enrollment(
                student_id=student_id,
                course_code=row["course_code"],
                grade=row.get("grade"),
                grade_point=row.get("grade_point"),
                semester_taken=row["semester_taken"],
                status=row["status"],
            )
        )
        created += 1
    return created


async def seed_activities(session: AsyncSession) -> int:
    students = {s.student_no: s.id for s in (await session.execute(select(Student))).scalars().all()}
    existing = {(a.student_id, a.title) for a in (await session.execute(select(Activity))).scalars().all()}
    created = 0
    for row in _load_yaml("activities.yaml"):
        row = dict(row)
        student_id = students.get(row.pop("student_no"))
        if student_id is None:
            continue
        if (student_id, row["title"]) in existing:
            continue
        session.add(Activity(student_id=student_id, **row))
        created += 1
    return created


async def seed_job_roles(session: AsyncSession) -> int:
    known_codes = await _known_unit_codes()
    existing = {j.role_slug for j in (await session.execute(select(JobRole))).scalars().all()}
    created = 0
    for row in _load_yaml("job_role_definitions.yaml"):
        slug = slugify(row["role_title"])
        if slug in existing:
            continue
        unknown = set(row["required_unit_codes"]) - known_codes
        if unknown:
            raise ValueError(
                f"job_role_definitions.yaml: role '{row['role_title']}' references unknown SKKNI unit "
                f"code(s) {sorted(unknown)} -- run SKKNI ingestion before seeding job roles."
            )
        session.add(
            JobRole(
                role_title=row["role_title"],
                role_slug=slug,
                source="skkni_derived",
                sector=row.get("sector"),
                description=row.get("description"),
                required_unit_codes=row["required_unit_codes"],
                is_curated=True,
            )
        )
        created += 1
    return created


async def run_seed(session: AsyncSession) -> dict[str, int]:
    counts = {
        "students": await seed_students(session),
        "job_roles": await seed_job_roles(session),
    }
    await session.flush()  # students must exist before enrollments/activities reference them
    counts["enrollments"] = await seed_enrollments(session)
    counts["activities"] = await seed_activities(session)
    await session.commit()
    return counts
