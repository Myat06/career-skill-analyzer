"""Runs data/eval/skill_gap_eval_set.yaml against the real matching engine.

This is the harness for a real accuracy measurement, not just a regression
guard (see test_gap_engine_calibration.py for that). The eval set ships with
every expected_status null (TODO) -- structural checks below (every pair
resolves to a real fixture, every unit_code actually belongs to that role)
run regardless and catch a broken file immediately; the actual agreement
check only has something to assert once a human reviewer has filled in real
labels, and is a no-op (reported, not failed) until then.

Requires the real seeded fixture students/job roles and a reachable Ollama
instance, same as test_gap_engine_calibration.py.
"""

import pytest
import yaml
from sqlalchemy import select

from app.config import EVAL_DATA_DIR
from app.database import SessionLocal
from app.models import JobRole, Student
from app.scoring.gap_engine import analyze_skill_gap

# Applied per-test rather than as a blanket pytestmark: this file mixes async
# tests (need the DB) with plain sync ones (pure file/structure checks), and
# pytest-asyncio warns if the mark lands on a non-async function.
asyncio_test = pytest.mark.asyncio(loop_scope="session")

EVAL_SET_PATH = EVAL_DATA_DIR / "skill_gap_eval_set.yaml"
VALID_STATUSES = {"matched", "partial", "missing"}

# Not a real accuracy target -- there is no labeled data yet to target
# against. This is a bare sanity floor: if agreement against real human
# labels ever falls below half, something is more likely broken than merely
# imprecise, and that's worth a loud failure rather than a quiet report.
# Revisit once a real labeled set exists and its own difficulty is known.
MINIMUM_SANE_AGREEMENT = 0.5


def _load_eval_set() -> list[dict]:
    if not EVAL_SET_PATH.exists():
        return []
    with EVAL_SET_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or []


@pytest.fixture(scope="module")
def eval_set() -> list[dict]:
    return _load_eval_set()


async def _resolve(student_no: str, role_title: str) -> tuple[Student, JobRole]:
    async with SessionLocal() as session:
        student = (await session.execute(select(Student).where(Student.student_no == student_no))).scalar_one()
        job_role = (await session.execute(select(JobRole).where(JobRole.role_title == role_title))).scalar_one()
        return student, job_role


def test_eval_set_file_is_not_empty(eval_set):
    assert eval_set, f"{EVAL_SET_PATH} is missing or empty"


@asyncio_test
async def test_every_pair_resolves_to_a_real_student_and_role(eval_set):
    bad = []
    for entry in eval_set:
        try:
            await _resolve(entry["student_no"], entry["role_title"])
        except Exception:
            bad.append((entry["student_no"], entry["role_title"]))
    assert not bad, f"eval set pairs that don't resolve to a real seeded student/role: {bad}"


@asyncio_test
async def test_every_expected_unit_actually_belongs_to_its_role(eval_set):
    """Catches a copy-paste error -- a unit_code listed under the wrong
    role's expected_units, which resolving alone wouldn't reveal."""
    mismatches = []
    for entry in eval_set:
        _, job_role = await _resolve(entry["student_no"], entry["role_title"])
        required = set(job_role.required_unit_codes)
        for unit in entry["expected_units"]:
            if unit["unit_code"] not in required:
                mismatches.append((entry["role_title"], unit["unit_code"]))
    assert not mismatches, f"expected_units entries naming a unit not required by that role: {mismatches}"


def test_every_labeled_status_is_a_real_value(eval_set):
    bad = [
        (entry["student_no"], entry["role_title"], unit["unit_code"], unit["expected_status"])
        for entry in eval_set
        for unit in entry["expected_units"]
        if unit["expected_status"] is not None and unit["expected_status"] not in VALID_STATUSES
    ]
    assert not bad, f"expected_status must be matched/partial/missing/null, found: {bad}"


@asyncio_test
async def test_agreement_against_labeled_units(eval_set):
    """The actual eval: for every unit with a real (non-null) expected_status,
    compares it to what analyze_skill_gap actually produced. Reports full
    detail either way; only fails outright below MINIMUM_SANE_AGREEMENT, and
    only once at least one unit is actually labeled -- an all-null file
    (the shipped default) has nothing to disagree with, so it passes as a
    reminder that labeling hasn't started yet, not a false "100% accurate".
    """
    comparisons: list[tuple[str, str, str, str, bool]] = []  # (student_no, role, unit_code, expected, agree)

    for entry in eval_set:
        labeled_units = [u for u in entry["expected_units"] if u["expected_status"] is not None]
        if not labeled_units:
            continue

        async with SessionLocal() as session:
            student = (await session.execute(select(Student).where(Student.student_no == entry["student_no"]))).scalar_one()
            job_role = (await session.execute(select(JobRole).where(JobRole.role_title == entry["role_title"]))).scalar_one()
            result = await analyze_skill_gap(session, student.id, job_role)

        actual_status_by_unit = {
            c.unit_code: c.status
            for c in result["matched_units"] + result["partial_units"] + result["missing_units"]
        }
        for unit in labeled_units:
            actual = actual_status_by_unit.get(unit["unit_code"])
            comparisons.append(
                (entry["student_no"], entry["role_title"], unit["unit_code"], unit["expected_status"], actual == unit["expected_status"])
            )

    if not comparisons:
        pytest.skip(
            f"No labeled units yet in {EVAL_SET_PATH.name} -- structural checks above still ran. "
            "See the file's own header for how to label an entry."
        )

    agreement_count = sum(1 for *_, agree in comparisons if agree)
    agreement_rate = agreement_count / len(comparisons)

    print(f"\nSkill-gap eval set agreement: {agreement_count}/{len(comparisons)} ({agreement_rate:.0%})")
    disagreements = [c for c in comparisons if not c[-1]]
    for student_no, role_title, unit_code, expected, _ in disagreements:
        print(f"  DISAGREE: {student_no} vs {role_title}, {unit_code}: expected {expected}")

    assert agreement_rate >= MINIMUM_SANE_AGREEMENT, (
        f"Agreement against labeled ground truth ({agreement_rate:.0%}) fell below the "
        f"sanity floor ({MINIMUM_SANE_AGREEMENT:.0%}) -- see printed disagreements above."
    )
