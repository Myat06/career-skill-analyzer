import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.deps import SessionDep, get_student_or_404
from app.models import Activity, Course, Enrollment, Student
from app.schemas import ActivityIn, ActivityOut, EnrollmentOut, StudentOut, StudentProfileOut
from app.scoring.scoring_utils import compute_gpa

router = APIRouter(tags=["students"])


@router.get("/students", response_model=list[StudentOut])
async def list_students(session: SessionDep):
    students = (await session.execute(select(Student).order_by(Student.full_name))).scalars().all()
    return students


@router.get("/students/{student_id}/profile", response_model=StudentProfileOut)
async def get_student_profile(student_id: uuid.UUID, session: SessionDep):
    student = await get_student_or_404(student_id, session)

    enrollments = (
        await session.execute(
            select(Enrollment)
            .join(Course, Enrollment.course_code == Course.course_code)
            .where(Enrollment.student_id == student_id)
            .order_by(Enrollment.semester_taken)
        )
    ).scalars().all()
    activities = (
        await session.execute(
            select(Activity).where(Activity.student_id == student_id).order_by(Activity.start_date)
        )
    ).scalars().all()

    completed = [e for e in enrollments if e.status == "completed"]
    in_progress = [e for e in enrollments if e.status == "in_progress"]

    course_credits = {
        c.course_code: c.credits
        for c in (await session.execute(select(Course))).scalars().all()
    }
    graded = [e for e in completed if e.grade_point is not None]
    gpa = compute_gpa(graded, course_credits)

    return StudentProfileOut(
        student=StudentOut.model_validate(student),
        completed_courses=[EnrollmentOut.model_validate(e) for e in completed],
        in_progress_courses=[EnrollmentOut.model_validate(e) for e in in_progress],
        activities=[ActivityOut.model_validate(a) for a in activities],
        gpa=gpa,
    )


@router.post("/students/{student_id}/projects", response_model=ActivityOut, status_code=201)
async def add_student_activity(student_id: uuid.UUID, payload: ActivityIn, session: SessionDep):
    await get_student_or_404(student_id, session)
    activity = Activity(student_id=student_id, **payload.model_dump())
    session.add(activity)
    await session.commit()
    await session.refresh(activity)
    return activity


@router.delete("/students/{student_id}/projects/{activity_id}", status_code=204)
async def delete_student_activity(student_id: uuid.UUID, activity_id: uuid.UUID, session: SessionDep):
    await get_student_or_404(student_id, session)
    activity = await session.get(Activity, activity_id)
    if activity is None or activity.student_id != student_id:
        raise HTTPException(status_code=404, detail=f"Activity {activity_id} not found for this student")
    await session.delete(activity)
    await session.commit()
