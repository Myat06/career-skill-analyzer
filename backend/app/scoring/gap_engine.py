"""Skill-gap scoring: resolves a job target to required SKKNI units, then
computes per-unit coverage from two independent, non-embedding evidence
sources:

- Completed courses, checked deterministically against the curated
  SKKNI-to-curriculum mapping (data/seed/skkni_curriculum_mapping.csv, via
  skkni_mapping.py) -- a course code either is or isn't mapped to a unit at
  Primary/Supporting strength, reviewed by a human, no approximation needed.
- Resume text and logged activities, which have no fixed mapping (free text),
  judged by the chat model against each unit's real elements and verified
  quote-by-quote (see text_evidence.py) -- the one place in this pipeline a
  model's judgment, not curated data, decides an outcome.

This replaces an earlier embedding-cosine-similarity approach for both
sources (see git history / ELEMENT_MATCH_THRESHOLD in old revisions): course
evidence had a real ground truth available and didn't need approximating,
and unstructured text evidence is more reliably judged by asking the model
directly and verifying its citation than by an uncalibrated similarity floor.
Free-text job-role resolution (resolve_job_target, for a role that isn't one
of the curated presets) is unaffected -- there is no curated unit list for an
arbitrary user-typed role, so it still resolves via semantic search.

analyze_skill_gap() is fingerprint-cached (see _matching_fingerprint below),
the same in-process, staleness-structurally-impossible pattern reporting/
consultation.py already uses for its own, larger cache. This wasn't optional
polish: the old embedding-only version had no LLM call at all and was
effectively instant, so nothing needed caching; this version adds one real
Ollama call (match_text_evidence) that measured ~16s alone, on top of the
generate_narrative call api/analyzer.py already makes right after it -- ~40s
total per analysis, every time a student sets or re-sets a target role in the
consultation chat, without this cache.
"""

import re
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.fingerprint_cache import FingerprintCache
from app.ingestion.checksums import content_checksum
from app.llm.embeddings import embed_query
from app.models import Activity, Enrollment, JobRole, Resume
from app.retrieval.semantic import semantic_search
from app.scoring.skkni_mapping import mapped_courses_for_unit
from app.scoring.skkni_titles import english_element_title, english_unit_title
from app.scoring.text_evidence import EvidenceItem, RequiredElement, match_text_evidence
from app.vectorstore import skkni_collection

UNIT_MATCH_ELEMENT_RATIO = 0.6
# Carried over from the old embedding-based engine, where it was swept
# against continuous cosine-similarity scores (see git history) -- that
# specific calibration doesn't transfer, since this fraction is now computed
# over binary verified-quote outcomes (and the forced 1.0/floor values from
# course evidence), a different kind of number entirely. 0.6 stays as a
# method-agnostic policy call ("more than half, leaning toward two-thirds, of
# a unit's elements must be evidenced to call it done") rather than a
# recalibrated one -- not re-validated against real outcomes under this
# engine yet, the same first-pass-constant caveat the now-removed Career
# Readiness feature's blended weights used to carry.
#
# Checked live, though, that this choice is low-stakes: sweeping 0.5/0.6/0.7
# against three real fixture (student, role) pairs left match_percentage
# completely unchanged in every case -- it's an average of coverage_fraction,
# which this ratio never touches -- and only relabeled a unit between
# "matched" and "partial" when its coverage_fraction sat exactly at
# SUPPORTING_COURSE_COVERAGE_FLOOR (0.5). So the headline percentage a
# student sees can't silently swing on this value; only which bucket a
# Supporting-course-only unit is filed under can.
SUPPORTING_COURSE_COVERAGE_FLOOR = 0.5
# Not an independent guess: the curated mapping CSV already scores a
# Supporting-strength match as 50 out of a possible 100 (Primary), i.e. half
# credit, in its own match_score column (see match_score in
# skkni_curriculum_mapping.csv / SCORE_BY_STRENGTH in
# test_skkni_curriculum_mapping.py) -- this floor just carries that same
# human-authored 50% weighting through to unit coverage, rather than
# inventing a separate number for the same judgment. A completed
# Supporting-strength course is real, curated partial credit -- not a claim
# of full coverage, but also not nothing. There's no element-level breakdown
# for course evidence (the CSV maps at the unit level), so this is a fixed
# floor rather than a computed fraction; it only ever raises
# coverage_fraction, never lowers what text evidence already found.
JOB_MATCH_CONFIDENCE_THRESHOLD = 0.45
# Calibrated for the (paragraph-length) unit *description* chunks used in
# free-text job-role resolution: a precise real query ("Generative AI
# Engineer specializing in prompt engineering") scored 0.527 against its
# correct unit and 0.35-0.39 against unrelated ones -- 0.45 sits between
# those two bands. This threshold is specific to role resolution (matching a
# typed job title to a cluster of SKKNI units) and is unrelated to student
# competency matching above.
RECOMMENDED_COURSES_PER_UNIT = 3
MATCHING_ENGINE_VERSION = "curated-course-mapping+llm-text-v1"
# Bumped whenever the matching method itself changes (not just a threshold
# tweak) -- stored on SkillGapAnalysis.ranking_config_version (api/analyzer.py)
# so past analyses in the DB stay distinguishable from ones computed under a
# different engine.


@dataclass
class UnitElement:
    element_number: str
    element_title: str


@dataclass
class UnitCoverageResult:
    unit_code: str
    unit_title: str
    matched_elements: list[str] = field(default_factory=list)
    unmatched_elements: list[str] = field(default_factory=list)
    coverage_fraction: float = 0.0
    status: str = "missing"  # matched | partial | missing
    matched_element_sources: dict[str, str] = field(default_factory=dict)
    # Maps a matched_elements label to a human-readable description of the
    # text evidence that verified it (e.g. "your resume" or "your \"RPA
    # Hackathon\" activity") -- see _gather_text_evidence's source_labels.
    # Empty for a unit matched via a completed course (no text evidence was
    # needed) and for any element that didn't get a verified text match.


@dataclass
class RecommendedCourse:
    course_code: str
    course_name: str
    for_unit_code: str
    match_reason: str


def format_recommended_courses_block(courses: list[RecommendedCourse]) -> str:
    """Turns a role's recommended-courses list into a single prompt-ready
    line, stating "NONE" explicitly when empty -- an absent section reads to
    the model as "unspecified" and invites a plausible-sounding invented
    course code, whereas a stated "none" is a fact it can report. Shared by
    narrative.py and reporting/consultation.py's evidence-builders, which
    each carried an identical copy of this instruction text before being
    consolidated here."""
    if courses:
        # Course codes are omitted -- current curriculum data is a test fixture, not
        # the real catalog, so codes aren't safe to show a student yet. Restore
        # `f"{c.course_code} ({c.course_name})"` once real curriculum data lands.
        return "Available course recommendations (only reference these by name, never invent others): " + ", ".join(
            c.course_name for c in courses
        )
    return (
        "Available course recommendations: NONE. No course in the university catalog "
        "covers these gaps closely enough to recommend. Say so plainly; do not name any course."
    )


def course_unit_status(unit_code: str, completed_course_codes: set[str]) -> str:
    """'matched' if a completed course maps Primary to this unit in the
    curated mapping, 'partial' if only a Supporting-strength course does,
    else 'missing' (no completed course is mapped to this unit at all)."""
    completed = [m for m in mapped_courses_for_unit(unit_code) if m.course_code in completed_course_codes]
    if any(m.match_strength == "Primary" for m in completed):
        return "matched"
    if completed:
        return "partial"
    return "missing"


def compute_unit_coverage(
    unit_code: str,
    unit_title: str,
    elements: list[UnitElement],
    course_status: str,
    verified_text_labels: dict[tuple[str, str], str],
) -> UnitCoverageResult:
    """Combines the course-based and text-based evidence signals for one unit.

    A Primary-matched course is trusted to cover the unit outright (every
    element counted matched) with no text evidence needed -- the curated
    mapping's own rationale already asserts that course teaches this exact
    competency, which is a stronger claim than an LLM's best guess against
    free text. Otherwise, status follows element-level coverage from
    verified text evidence, with a Supporting-matched course guaranteeing a
    coverage floor (see SUPPORTING_COURSE_COVERAGE_FLOOR) even when no
    element individually has a verified quote.

    verified_text_labels maps (unit_code, element_number) -> a human-readable
    description of whichever evidence item verified it (see
    _gather_text_evidence's source_labels) -- carried into
    matched_element_sources so a caller (narrative.py, the consultation
    chat) can say *which* activity or the resume backs a specific matched
    element, not just that something did.
    """
    total = len(elements)

    if course_status == "matched":
        labels = [e.element_title or f"Element {e.element_number}" for e in elements]
        return UnitCoverageResult(
            unit_code=unit_code,
            unit_title=unit_title,
            matched_elements=labels,
            unmatched_elements=[],
            coverage_fraction=1.0,
            status="matched",
        )

    matched: list[str] = []
    unmatched: list[str] = []
    matched_sources: dict[str, str] = {}
    for e in elements:
        label = e.element_title or f"Element {e.element_number}"
        source_label = verified_text_labels.get((unit_code, e.element_number))
        if source_label is not None:
            matched.append(label)
            matched_sources[label] = source_label
        else:
            unmatched.append(label)

    coverage_fraction = (len(matched) / total) if total else 0.0
    if course_status == "partial" and total > 0:
        coverage_fraction = max(coverage_fraction, SUPPORTING_COURSE_COVERAGE_FLOOR)

    if total == 0:
        status = "missing"
    elif coverage_fraction >= UNIT_MATCH_ELEMENT_RATIO:
        status = "matched"
    elif coverage_fraction > 0:
        status = "partial"
    else:
        status = "missing"

    return UnitCoverageResult(
        unit_code=unit_code,
        unit_title=unit_title,
        matched_elements=matched,
        unmatched_elements=unmatched,
        coverage_fraction=coverage_fraction,
        status=status,
        matched_element_sources=matched_sources,
    )


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


async def resolve_job_target(
    session: AsyncSession, job_role_id: str | None = None, job_role_query: str | None = None
) -> tuple[JobRole | None, float, bool]:
    """Returns (job_role, confidence, low_confidence). A curated job_role_id
    is trusted outright; a free-text query is resolved by semantic search
    against SKKNI unit descriptions and cached as a new custom JobRole."""
    if job_role_id:
        job_role = await session.get(JobRole, job_role_id)
        return job_role, 1.0, job_role is None

    if not job_role_query:
        return None, 0.0, True

    ranked, metadata_by_id = await semantic_search(
        skkni_collection(), job_role_query, where={"section_type": "description"}, top_k=10
    )
    if not ranked:
        return None, 0.0, True

    top_score = ranked[0].score
    candidate_codes = [metadata_by_id[r.item_id]["unit_code"] for r in ranked if r.score >= JOB_MATCH_CONFIDENCE_THRESHOLD]
    if not candidate_codes:
        return None, top_score, True

    slug = slugify(job_role_query)
    existing = (await session.execute(select(JobRole).where(JobRole.role_slug == slug))).scalar_one_or_none()
    if existing:
        return existing, top_score, False

    job_role = JobRole(
        role_title=job_role_query,
        role_slug=slug,
        source="custom",
        required_unit_codes=candidate_codes,
        is_curated=False,
    )
    session.add(job_role)
    await session.flush()
    return job_role, top_score, False


async def embed_job_target(job_role: JobRole) -> list[float]:
    """Embeds the concatenated SKKNI unit descriptions for a job role's required units
    (falling back to the role title if none match) -- shared by the resume keyword-
    alignment score (api/resumes.py) and the consultation report builder
    (app/reporting/consultation.py), so both compare a resume against the identical
    job-target representation.
    """
    matching_docs: list[str] = []
    if job_role.required_unit_codes:
        unit_data = await skkni_collection().get(
            where={"$and": [{"section_type": "description"}, {"unit_code": {"$in": job_role.required_unit_codes}}]},
            include=["documents"],
        )
        matching_docs = unit_data.get("documents", [])
    combined_text = " ".join(matching_docs) or job_role.role_title
    return await embed_query(combined_text)


async def _gather_text_evidence(
    session: AsyncSession, student_id, include_uploaded_resume: bool = True
) -> tuple[list[EvidenceItem], dict[str, str]]:
    """Resume + activity text only -- completed courses are matched
    deterministically against the curated mapping (course_unit_status) and
    never need to go through the chat model.

    Returns (items, source_labels): source_labels maps each EvidenceItem's
    source_id to a human-readable description of it (e.g. "your resume", or
    the activity's own title) -- gathered here since only this function has
    the activity/resume rows in hand; match_text_evidence itself only ever
    sees opaque per-call "E1"/"E2" ids, never these real identifiers.
    """
    items: list[EvidenceItem] = []
    source_labels: dict[str, str] = {}

    activities = (await session.execute(select(Activity).where(Activity.student_id == student_id))).scalars().all()
    for activity in activities:
        text = f"{activity.title}: {activity.description} Skills: {', '.join(activity.skills_tags or [])}"
        source_id = f"activity:{activity.id}"
        items.append(EvidenceItem(source_id=source_id, text=text))
        source_labels[source_id] = f'your "{activity.title}" activity'

    if include_uploaded_resume:
        uploaded = (
            await session.execute(
                select(Resume)
                .where(Resume.student_id == student_id, Resume.source == "uploaded")
                .order_by(Resume.created_at.desc())
            )
        ).scalars().first()
        if uploaded:
            items.append(EvidenceItem(source_id="resume", text=uploaded.extracted_text))
            source_labels["resume"] = "your resume"

    return items, source_labels


async def _get_units_elements(unit_codes: list[str]) -> dict[str, tuple[str, list[UnitElement]]]:
    """Batched lookup for every one of a role's required units in one call
    (grouped by unit_code afterward), replacing what used to be a separate
    .get() per unit -- a role has 4-5 required units, so that was 4-5
    sequential round trips where one, filtered with unit_code $in [...],
    does the same job."""
    if not unit_codes:
        return {}
    data = await skkni_collection().get(
        where={"$and": [{"unit_code": {"$in": unit_codes}}, {"section_type": "element"}]},
        include=["metadatas"],
    )
    titles: dict[str, str] = {}
    elements_by_unit: dict[str, list[UnitElement]] = {code: [] for code in unit_codes}
    for meta in data["metadatas"]:
        unit_code = meta.get("unit_code", "")
        titles[unit_code] = meta.get("unit_title", titles.get(unit_code, ""))
        element_number = str(meta.get("element_number", ""))
        # Same single-point-of-translation reasoning as english_unit_title()
        # above: element_title is Bahasa Indonesia as parsed from the PDF,
        # translated here once so every downstream consumer -- the LLM
        # text-evidence prompt (text_evidence.py) as well as every display
        # surface -- sees English without needing its own translation step.
        elements_by_unit.setdefault(unit_code, []).append(
            UnitElement(
                element_number=element_number,
                element_title=english_element_title(unit_code, element_number, meta.get("element_title", "")),
            )
        )
    return {code: (titles.get(code, ""), elements_by_unit.get(code, [])) for code in unit_codes}


def _recommend_courses_for_unit(
    unit_code: str, completed_course_codes: set[str]
) -> list[RecommendedCourse]:
    """Recommends courses for one gap unit from the curated SKKNI-to-curriculum
    mapping (data/seed/skkni_curriculum_mapping.csv via skkni_mapping.py),
    Primary matches before Supporting. A unit with no mapped courses, or where
    every mapped row is a curated GAP (no course covers it), returns [].
    """
    recommendations: list[RecommendedCourse] = []
    seen_course_codes: set[str] = set()
    for mapped in mapped_courses_for_unit(unit_code):
        if mapped.course_code in completed_course_codes or mapped.course_code in seen_course_codes:
            continue
        seen_course_codes.add(mapped.course_code)
        recommendations.append(
            RecommendedCourse(
                course_code=mapped.course_code,
                course_name=mapped.course_name,
                for_unit_code=unit_code,
                match_reason=f"{mapped.match_strength} match: {mapped.match_rationale}",
            )
        )
        if len(recommendations) >= RECOMMENDED_COURSES_PER_UNIT:
            break
    return recommendations


async def recommend_courses(
    coverages: list[UnitCoverageResult], completed_course_codes: set[str]
) -> list[RecommendedCourse]:
    """Recommends courses for every gap unit, from the curated mapping file.

    Synchronous under the hood (a cached CSV lookup, no embedding/retrieval
    call) but kept async since every caller already awaits it as part of the
    analyze_skill_gap pipeline.
    """
    recommendations: list[RecommendedCourse] = []
    for coverage in coverages:
        recommendations.extend(_recommend_courses_for_unit(coverage.unit_code, completed_course_codes))
    return recommendations


MATCH_CACHE_SIZE = 128
_match_cache: FingerprintCache[dict] = FingerprintCache(MATCH_CACHE_SIZE)


async def _matching_fingerprint(
    session: AsyncSession, student_id, job_role: JobRole, include_uploaded_resume: bool
) -> str:
    """Hashes every input that can change analyze_skill_gap's own output:
    completed courses (course-based status), logged activities and the
    uploaded resume (text-evidence status), and the role's required units.
    Aggregate max(created_at)+count per table -- the same cheap trick
    reporting/consultation.py's _input_fingerprint already uses -- so this
    changes whenever the underlying rows change, without reading their full
    content. Deliberately narrower than that fingerprint: it excludes
    SkillGapAnalysis/ResumeScore rows, which are downstream of this
    computation, not inputs to it.
    """
    latest_enrollment_at, enrollment_count = (
        await session.execute(
            select(func.max(Enrollment.created_at), func.count(Enrollment.id)).where(
                Enrollment.student_id == student_id, Enrollment.status == "completed"
            )
        )
    ).one()
    latest_activity_at, activity_count = (
        await session.execute(
            select(func.max(Activity.created_at), func.count(Activity.id)).where(Activity.student_id == student_id)
        )
    ).one()
    latest_resume_at = None
    if include_uploaded_resume:
        latest_resume_at = (
            await session.execute(
                select(func.max(Resume.created_at)).where(
                    Resume.student_id == student_id, Resume.source == "uploaded"
                )
            )
        ).scalar_one()

    parts = [
        str(student_id),
        str(job_role.id),
        str(tuple(job_role.required_unit_codes)),
        str(latest_enrollment_at),
        str(enrollment_count),
        str(latest_activity_at),
        str(activity_count),
        str(latest_resume_at),
    ]
    return content_checksum("|".join(parts))


async def analyze_skill_gap(
    session: AsyncSession, student_id, job_role: JobRole, include_uploaded_resume: bool = True
) -> dict:
    """Cached on a fingerprint of its inputs (see _matching_fingerprint) --
    the LLM-judged text-evidence step (text_evidence.py) is real latency
    (~16s measured), unlike the deterministic course-matching half, so a
    student re-picking the same role without changing their profile must not
    pay for it again. The cache lives in-process, same trade-off as
    reporting/consultation.py's: a restart just costs one recompute.
    """
    fingerprint = await _matching_fingerprint(session, student_id, job_role, include_uploaded_resume)
    cached = _match_cache.get(fingerprint)
    if cached is not None:
        return cached

    result = await _analyze_skill_gap_uncached(session, student_id, job_role, include_uploaded_resume)
    _match_cache.set(fingerprint, result)
    return result


async def _analyze_skill_gap_uncached(
    session: AsyncSession, student_id, job_role: JobRole, include_uploaded_resume: bool = True
) -> dict:
    completed_course_codes = {
        row.course_code
        for row in (
            await session.execute(
                select(Enrollment.course_code).where(
                    Enrollment.student_id == student_id, Enrollment.status == "completed"
                )
            )
        ).all()
    }

    unit_elements: dict[str, tuple[str, list[UnitElement]]] = {}
    all_elements: list[RequiredElement] = []
    units_data = await _get_units_elements(job_role.required_unit_codes)
    for unit_code in job_role.required_unit_codes:
        unit_title, elements = units_data[unit_code]
        # SKKNI_2026-103.pdf (and therefore this unit_title) is in Bahasa
        # Indonesia -- translate here, once, at the single point every
        # downstream consumer (frontend, chat, poster, PDF) reads unit_title
        # from, rather than leaving each display surface to cope with Bahasa
        # on its own.
        unit_title = english_unit_title(unit_code, unit_title)
        unit_elements[unit_code] = (unit_title, elements)
        all_elements.extend(RequiredElement(unit_code, e.element_number, e.element_title) for e in elements)

    evidence_items, source_labels = await _gather_text_evidence(session, student_id, include_uploaded_resume)
    verified_text_sources, _text_evidence_status = await match_text_evidence(all_elements, evidence_items)
    verified_text_labels = {pair: source_labels.get(source_id, source_id) for pair, source_id in verified_text_sources.items()}

    coverages: list[UnitCoverageResult] = []
    for unit_code, (unit_title, elements) in unit_elements.items():
        course_status = course_unit_status(unit_code, completed_course_codes)
        coverages.append(compute_unit_coverage(unit_code, unit_title, elements, course_status, verified_text_labels))

    match_percentage = round(sum(c.coverage_fraction for c in coverages) / len(coverages) * 100, 1) if coverages else 0.0

    matched = [c for c in coverages if c.status == "matched"]
    partial = [c for c in coverages if c.status == "partial"]
    missing = [c for c in coverages if c.status == "missing"]

    recommended_courses = await recommend_courses(partial + missing, completed_course_codes)

    return {
        "match_percentage": match_percentage,
        "matched_units": matched,
        "partial_units": partial,
        "missing_units": missing,
        "recommended_courses": recommended_courses,
    }
