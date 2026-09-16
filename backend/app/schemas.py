import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Students / courses / activities -------------------------------------------------


class CourseOut(ORMModel):
    id: uuid.UUID
    course_code: str
    course_name: str
    credits: int
    semester: int
    concentration_track: str | None
    course_type: str
    learning_outcomes: dict


class EnrollmentOut(ORMModel):
    id: uuid.UUID
    course_code: str
    grade: str | None
    grade_point: float | None
    semester_taken: int
    status: str


class ActivityIn(BaseModel):
    type: str
    title: str
    description: str
    issuer: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    skills_tags: list[str] = []
    evidence_url: str | None = None


class ActivityOut(ORMModel):
    id: uuid.UUID
    type: str
    title: str
    description: str
    issuer: str | None
    start_date: date | None
    end_date: date | None
    skills_tags: list[str]
    evidence_url: str | None
    created_at: datetime


class StudentOut(ORMModel):
    id: uuid.UUID
    student_no: str
    full_name: str
    program: str
    cohort_year: int
    email: str


class StudentProfileOut(BaseModel):
    student: StudentOut
    completed_courses: list[EnrollmentOut]
    in_progress_courses: list[EnrollmentOut]
    activities: list[ActivityOut]
    gpa: float | None


# --- Resumes ---------------------------------------------------------------------------


class ResumeOut(ORMModel):
    id: uuid.UUID
    student_id: uuid.UUID
    source: str
    original_filename: str | None
    extracted_text: str
    parsed_sections: dict
    created_at: datetime


class ResumeSuggestion(BaseModel):
    text: str
    origin: str  # "rule-based" | "ai-suggested"


class RubricCategoryScore(BaseModel):
    key: str
    label: str
    score: float
    feedback: str
    quote: str | None


class ResumeScoreOut(BaseModel):
    resume_id: uuid.UUID
    job_role_id: uuid.UUID | None
    rubric_categories: list[RubricCategoryScore]
    keyword_alignment_score: float
    overall_score: float
    suggestions: list[ResumeSuggestion]
    note: str | None


# --- Job roles ---------------------------------------------------------------------------


class JobRoleOut(ORMModel):
    id: uuid.UUID
    role_title: str
    role_slug: str
    source: str
    sector: str | None
    description: str | None
    required_unit_codes: list[str]
    is_curated: bool


class JobRoleResolveOut(BaseModel):
    matched_job_role: JobRoleOut | None
    confidence: float
    low_confidence: bool
    candidate_unit_codes: list[str]


# --- Skill-gap analysis ------------------------------------------------------------------


class SkillGapRequest(BaseModel):
    job_role_id: uuid.UUID | None = None
    job_role_query: str | None = None
    include_uploaded_resume: bool = True


class UnitCoverage(BaseModel):
    unit_code: str
    unit_title: str
    coverage_fraction: float
    matched_elements: list[str]
    unmatched_elements: list[str]


class RecommendedCourse(BaseModel):
    course_code: str
    course_name: str
    for_unit_code: str
    match_reason: str


class NarrativePoint(BaseModel):
    text: str
    citations: list[str]


class Narrative(BaseModel):
    strengths: list[NarrativePoint]
    weaknesses: list[NarrativePoint]
    improvement_suggestions: list[NarrativePoint]
    citations_valid: bool
    repair_attempted: bool
    # How many claims the model produced that cited nothing, or cited an
    # evidence ID that doesn't exist, and were therefore dropped before
    # rendering (app/scoring/narrative.py). Exposed rather than hidden so the
    # hallucination rate is measurable from stored analyses instead of
    # invisible. Defaulted for analyses persisted before this field existed.
    unsupported_claims_dropped: int = 0


class SkillGapResponse(BaseModel):
    analysis_id: uuid.UUID
    job_role: JobRoleOut
    match_percentage: float
    matched_units: list[UnitCoverage]
    partial_units: list[UnitCoverage]
    missing_units: list[UnitCoverage]
    recommended_courses: list[RecommendedCourse]
    narrative: Narrative | None
    narrative_status: str
    embedding_model_version: str


class SkillGapSummary(ORMModel):
    id: uuid.UUID
    job_role_id: uuid.UUID
    match_percentage: float
    created_at: datetime


# --- Ingestion --------------------------------------------------------------------------


class IngestionRunOut(ORMModel):
    id: uuid.UUID
    source_file: str
    chunks_written: int
    chunks_skipped: int
    chunks_deleted: int
    embedding_model_version: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    notes: str | None


class IngestionStatusOut(BaseModel):
    collection_counts: dict[str, int]
    last_run_at: datetime | None


class HealthOut(BaseModel):
    status: str
    postgres: bool
    vector_store: bool
    ollama: bool


# --- Chat sessions -----------------------------------------------------------------------


class ChatSessionSummaryOut(ORMModel):
    id: uuid.UUID
    title: str | None
    job_role_id: uuid.UUID | None
    pinned: bool
    updated_at: datetime


class ChatSessionOut(ChatSessionSummaryOut):
    display_messages: list[dict]
    chat_history: list[dict]
    job_role: JobRoleOut | None


class ChatSessionSaveIn(BaseModel):
    display_messages: list[dict]
    chat_history: list[dict]
    job_role_id: uuid.UUID | None = None


class ChatSessionPinIn(BaseModel):
    pinned: bool
