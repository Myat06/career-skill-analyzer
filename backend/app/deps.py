import uuid
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Student

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_student_or_404(student_id: uuid.UUID, session: SessionDep) -> Student:
    student = await session.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail=f"Student {student_id} not found")
    return student
