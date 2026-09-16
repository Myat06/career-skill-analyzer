import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, UploadFile
from sqlalchemy import delete as sa_delete, select, update

from app.config import UPLOADS_DIR
from app.deps import SessionDep, get_student_or_404
from app.llm.chat import ChatServiceUnavailable
from app.llm.embeddings import embed_query
from app.models import Resume, ResumeScore, SkillGapAnalysis, Student
from app.resume.image_extract import is_image_resume_filename, transcribe_resume_image
from app.resume.parser import UnsupportedResumeFormat, extract_text
from app.schemas import ResumeOut, ResumeScoreOut, ResumeSuggestion
from app.scoring.gap_engine import embed_job_target, resolve_job_target
from app.scoring.resume_score import score_resume

router = APIRouter(tags=["resumes"])


@router.post("/students/{student_id}/resume/upload", response_model=ResumeOut, status_code=201)
async def upload_resume(student_id: uuid.UUID, session: SessionDep, file: UploadFile):
    await get_student_or_404(student_id, session)
    data = await file.read()
    try:
        if is_image_resume_filename(file.filename):
            text = await transcribe_resume_image(data, file.filename)
        else:
            text = extract_text(file.filename, data)
    except UnsupportedResumeFormat as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ChatServiceUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Could not read this image right now -- the AI service is unavailable. "
            "Try again shortly, or upload a PDF/DOCX instead.",
        ) from exc

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    checksum = hashlib.sha256(data).hexdigest()
    storage_path = UPLOADS_DIR / f"{student_id}-{checksum[:12]}-{file.filename}"
    storage_path.write_bytes(data)

    resume = Resume(
        student_id=student_id,
        source="uploaded",
        original_filename=file.filename,
        storage_path=str(storage_path),
        extracted_text=text,
        file_checksum=checksum,
        parsed_sections={},
    )
    session.add(resume)
    await session.commit()
    await session.refresh(resume)
    return resume


@router.get("/students/{student_id}/resume/latest", response_model=ResumeOut)
async def get_latest_resume(student_id: uuid.UUID, session: SessionDep):
    await get_student_or_404(student_id, session)
    resume = (
        await session.execute(
            select(Resume)
            .where(Resume.student_id == student_id, Resume.source == "uploaded")
            .order_by(Resume.created_at.desc())
        )
    ).scalars().first()
    if resume is None:
        raise HTTPException(status_code=404, detail="No uploaded resume found for this student")
    return resume


@router.delete("/students/{student_id}/resume/{resume_id}", status_code=204)
async def delete_resume(student_id: uuid.UUID, resume_id: uuid.UUID, session: SessionDep):
    await get_student_or_404(student_id, session)
    resume = await session.get(Resume, resume_id)
    if resume is None or resume.student_id != student_id:
        raise HTTPException(status_code=404, detail=f"Resume {resume_id} not found for this student")

    # No cascade is configured on resume_scores.resume_id or
    # skill_gap_analyses.resume_score_id, so a plain delete would fail with a foreign
    # key violation once this resume has been scored. Detach first: null out the
    # (nullable, purely informational) link on any skill-gap analysis that cites one of
    # this resume's scores -- the analysis itself is still valid and stays -- then
    # remove the score rows before the resume row they point to.
    #
    # These are Core DELETEs followed by an explicit flush, NOT session.delete().
    # models.py declares no relationship() anywhere, and SQLAlchemy's unit of work
    # derives inter-mapper delete *ordering* from relationships, not from bare
    # ForeignKey columns -- so session.delete() on the scores and then the resume
    # emitted "DELETE FROM resumes" first, hit the foreign key violation, aborted the
    # transaction, and never issued the resume_scores delete at all. Deleting any
    # scored resume returned a 500. Ordering the statements explicitly here does not
    # depend on that inference.
    score_ids = (
        await session.execute(select(ResumeScore.id).where(ResumeScore.resume_id == resume_id))
    ).scalars().all()
    if score_ids:
        await session.execute(
            update(SkillGapAnalysis).where(SkillGapAnalysis.resume_score_id.in_(score_ids)).values(resume_score_id=None)
        )
        await session.execute(sa_delete(ResumeScore).where(ResumeScore.id.in_(score_ids)))
        await session.flush()

    await session.delete(resume)
    await session.commit()

    # Only after the row is really gone. Unlinking before the commit meant every
    # failed delete still destroyed the student's uploaded file while leaving the
    # row behind -- the file vanished from disk but the resume stayed in the UI.
    if resume.storage_path:
        Path(resume.storage_path).unlink(missing_ok=True)


@router.get("/resumes/{resume_id}/score", response_model=ResumeScoreOut)
async def get_resume_score(
    resume_id: uuid.UUID,
    session: SessionDep,
    job_role_id: uuid.UUID | None = Query(None),
    job_role_query: str | None = Query(None),
):
    resume = await session.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(status_code=404, detail=f"Resume {resume_id} not found")
    student = await session.get(Student, resume.student_id)

    job_role = None
    job_target_embedding = None
    if job_role_id or job_role_query:
        job_role, _, _ = await resolve_job_target(session, job_role_id=job_role_id, job_role_query=job_role_query)
        if job_role is not None:
            await session.commit()
            job_target_embedding = await embed_job_target(job_role)

    resume_embedding = await embed_query(resume.extracted_text) if resume.extracted_text else None
    result = await score_resume(
        resume.extracted_text,
        resume_embedding,
        job_target_embedding,
        student_full_name=student.full_name if student else None,
    )

    score = ResumeScore(
        resume_id=resume.id,
        job_role_id=job_role.id if job_role else None,
        rubric_categories=result["rubric_categories"],
        keyword_alignment_score=result["keyword_alignment_score"],
        overall_score=result["overall_score"],
        suggestions=result["suggestions"],
        note=result["note"],
    )
    session.add(score)
    await session.commit()

    return ResumeScoreOut(
        resume_id=resume.id,
        job_role_id=job_role.id if job_role else None,
        rubric_categories=result["rubric_categories"],
        keyword_alignment_score=result["keyword_alignment_score"],
        overall_score=result["overall_score"],
        suggestions=[ResumeSuggestion(**s) for s in result["suggestions"]],
        note=result["note"],
    )
