import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.database import Base

ACTIVITY_TYPES = ("project", "certification", "internship", "organization", "competition", "volunteer")
ENROLLMENT_STATUSES = ("completed", "in_progress", "failed")
RESUME_SOURCES = ("uploaded", "auto_generated")
JOB_ROLE_SOURCES = ("skkni_derived", "custom")
NARRATIVE_STATUSES = ("ok", "unavailable", "degraded")


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Student(Base):
    __tablename__ = "students"

    id: Mapped[uuid.UUID] = _uuid_pk()
    student_no: Mapped[str] = mapped_column(String, unique=True)
    full_name: Mapped[str] = mapped_column(String)
    program: Mapped[str] = mapped_column(String, default="Information Systems")
    cohort_year: Mapped[int] = mapped_column(Integer)
    email: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Course(Base):
    """course_code is a synthetic key (`IS-S{semester}-{seq}`), not from the source PDF --
    the curriculum book identifies courses by name only, not by code. See
    app/ingestion/curriculum_parser.py.
    """

    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = _uuid_pk()
    course_code: Mapped[str] = mapped_column(String, unique=True)
    course_name: Mapped[str] = mapped_column(String)
    credits: Mapped[int] = mapped_column(Integer)
    semester: Mapped[int] = mapped_column(Integer)
    concentration_track: Mapped[str | None] = mapped_column(String, nullable=True)
    course_type: Mapped[str] = mapped_column(String)
    learning_outcomes: Mapped[dict] = mapped_column(JSONB, default=dict)
    curriculum_chunk_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (CheckConstraint(f"status IN {ENROLLMENT_STATUSES}", name="ck_enrollment_status"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id"))
    course_code: Mapped[str] = mapped_column(ForeignKey("courses.course_code"))
    grade: Mapped[str | None] = mapped_column(String, nullable=True)
    grade_point: Mapped[float | None] = mapped_column(Float, nullable=True)
    semester_taken: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (CheckConstraint(f"type IN {ACTIVITY_TYPES}", name="ck_activity_type"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id"))
    type: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    issuer: Mapped[str | None] = mapped_column(String, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    skills_tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    evidence_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JobRole(Base):
    __tablename__ = "job_roles"
    __table_args__ = (CheckConstraint(f"source IN {JOB_ROLE_SOURCES}", name="ck_job_role_source"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    role_title: Mapped[str] = mapped_column(String)
    role_slug: Mapped[str] = mapped_column(String, unique=True)
    source: Mapped[str] = mapped_column(String)
    sector: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_unit_codes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    is_curated: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Resume(Base):
    __tablename__ = "resumes"
    __table_args__ = (CheckConstraint(f"source IN {RESUME_SOURCES}", name="ck_resume_source"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id"))
    source: Mapped[str] = mapped_column(String)
    original_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String, nullable=True)
    extracted_text: Mapped[str] = mapped_column(Text)
    file_checksum: Mapped[str | None] = mapped_column(String, nullable=True)
    parsed_sections: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResumeScore(Base):
    __tablename__ = "resume_scores"

    id: Mapped[uuid.UUID] = _uuid_pk()
    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resumes.id"))
    job_role_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job_roles.id"), nullable=True)
    rubric_categories: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    keyword_alignment_score: Mapped[float] = mapped_column(Float)
    overall_score: Mapped[float] = mapped_column(Float)
    suggestions: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SkillGapAnalysis(Base):
    __tablename__ = "skill_gap_analyses"
    __table_args__ = (CheckConstraint(f"narrative_status IN {NARRATIVE_STATUSES}", name="ck_narrative_status"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id"))
    job_role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_roles.id"))
    match_percentage: Mapped[float] = mapped_column(Float)
    matched_units: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    partial_units: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    missing_units: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    recommended_courses: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    narrative: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    narrative_status: Mapped[str] = mapped_column(String, default="ok")
    resume_score_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resume_scores.id"), nullable=True)
    embedding_model_version: Mapped[str] = mapped_column(String)
    ranking_config_version: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatSession(Base):
    """One saved consultation chat thread. Whole-array JSONB rather than a
    message-per-row table -- the frontend already owns two full arrays it
    round-trips verbatim: `display_messages` (everything shown in the UI,
    including system notes/role-briefings that never reach the LLM) and
    `chat_history` (just the user/assistant turns replayed into
    POST /consult). `job_role_id` is the target role active when this
    session was last saved, so reopening it restores the right context
    instead of whatever role happens to be selected elsewhere right now.
    """

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("students.id"))
    job_role_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job_roles.id"), nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    pinned: Mapped[bool] = mapped_column(default=False)
    display_messages: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    chat_history: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class IngestionManifestEntry(Base):
    """Drives incremental resync: a chunk is only re-embedded/upserted if its checksum
    changed since the last run, and rows no longer produced by a run are deleted from
    both here and the vector chunk tables. See app/ingestion/index_pipeline.py.
    """

    __tablename__ = "ingestion_manifest"

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_file: Mapped[str] = mapped_column(String)
    chunk_id: Mapped[str] = mapped_column(String, unique=True)
    embedding_model_version: Mapped[str] = mapped_column(String)
    checksum: Mapped[str] = mapped_column(String)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SkkniChunk(Base):
    """One embedded chunk of the SKKNI competency-standard PDF -- a unit's
    description, one of its elements, or (if present) its variable_scope/
    assessment_guide section. Replaces the old `skkni_units__<model>` Chroma
    collection; see app/ingestion/index_pipeline.py for what populates this
    and app/vectorstore.py for the read-side helpers built on top of it.
    No ANN index (ivfflat/hnsw) on `embedding` -- the corpus is a few hundred
    rows total (27 units), so a sequential scan with `<=>` is effectively
    free; add one if this grows past low thousands of rows.
    """

    __tablename__ = "skkni_chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dim))

    doc_type: Mapped[str] = mapped_column(String, default="skkni")
    unit_code: Mapped[str] = mapped_column(String, index=True)
    unit_title: Mapped[str] = mapped_column(String)
    sector_code: Mapped[str] = mapped_column(String)
    source_file: Mapped[str] = mapped_column(String)
    source_page: Mapped[int] = mapped_column(Integer)
    parse_confidence: Mapped[float] = mapped_column(Float)
    section_type: Mapped[str] = mapped_column(String, index=True)
    element_number: Mapped[str | None] = mapped_column(String, nullable=True)
    element_title: Mapped[str | None] = mapped_column(String, nullable=True)
    chunk_checksum: Mapped[str] = mapped_column(String)
    embedding_model_version: Mapped[str] = mapped_column(String)
    token_count: Mapped[int] = mapped_column(Integer)


class CurriculumChunk(Base):
    """One embedded chunk of the curriculum book PDF, one per course.
    Replaces the old `curriculum_courses__<model>` Chroma collection -- see
    the SkkniChunk docstring above, same reasoning applies here.
    """

    __tablename__ = "curriculum_chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dim))

    doc_type: Mapped[str] = mapped_column(String, default="curriculum")
    course_code: Mapped[str] = mapped_column(String, index=True)
    course_name: Mapped[str] = mapped_column(String)
    semester: Mapped[int] = mapped_column(Integer)
    plo_codes: Mapped[str] = mapped_column(String)
    source_file: Mapped[str] = mapped_column(String)
    source_page: Mapped[int] = mapped_column(Integer)
    chunk_checksum: Mapped[str] = mapped_column(String)
    embedding_model_version: Mapped[str] = mapped_column(String)
    token_count: Mapped[int] = mapped_column(Integer)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_file: Mapped[str] = mapped_column(String)
    chunks_written: Mapped[int] = mapped_column(Integer, default=0)
    chunks_skipped: Mapped[int] = mapped_column(Integer, default=0)
    chunks_deleted: Mapped[int] = mapped_column(Integer, default=0)
    embedding_model_version: Mapped[str] = mapped_column(String)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, default="running")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
