"""Standalone resume quality scoring: keyword alignment (embedding similarity
against the job target) is deterministic; the 7-category rubric score is the
only LLM-graded part, via chat.py, and requires the model to justify each
category with a verbatim quoted substring checked against the resume text --
the same cite-then-validate discipline as knowledge-base's answer citations.
The rubric and the reference "good resume" example are both short, complete,
always-fully-relevant documents, so they're inlined as prompt constants here
rather than run through the chunking/retrieval pipeline in app/ingestion/,
which exists for large multi-document semantic search (SKKNI units,
curriculum courses) -- chunking a single one-page rubric would be pure
overhead for zero retrieval benefit.
The resume-score endpoint must never hard-fail: with no job target or an
unreachable chat model, the missing sub-scores are simply omitted and noted.
"""

from app.llm.chat import ChatServiceUnavailable, chat, extract_json_object
from app.llm.embeddings import cosine_similarity
from app.scoring.scoring_utils import weighted_average

RUBRIC_WEIGHT = 0.7
KEYWORD_WEIGHT = 0.3
SUGGESTION_SCORE_THRESHOLD = 70
MIN_MEANINGFUL_RESUME_CHARS = 200
# A real one-page resume runs well over a thousand characters. Anything under
# this almost certainly means extraction failed rather than that the student
# wrote a three-line resume -- the exact failure that made a table-based .docx
# (see app/resume/parser.py) score near zero with no explanation. Scoring it
# silently is what turned an extraction bug into "the AI thinks my resume is
# bad", so say so instead.

RUBRIC_CATEGORIES = [
    {
        "key": "contact_information",
        "label": "Contact Information",
        "criteria": "Complete contact details: name, phone number, email, LinkedIn. No spelling errors.",
    },
    {
        "key": "education",
        "label": "Education",
        "criteria": "Most recent educational background (institution name, study program, year). "
        "Academic achievements if any (GPA, scholarships, etc.).",
    },
    {
        "key": "work_experience",
        "label": "Work/Internship Experience",
        "criteria": "Relevant work/internship experience. Clear job descriptions (tasks, achievements). "
        "Uses action verbs (e.g., designed, managed, etc.).",
    },
    {
        "key": "projects",
        "label": "Projects",
        "criteria": "Presents a portfolio of up-to-date work, clearly detailing responsibilities and project impact.",
    },
    {
        "key": "skills_certifications",
        "label": "Skills and Certifications",
        "criteria": "Lists relevant technical and soft skills. Skills aligned with educational background.",
    },
    {
        "key": "language_proficiency",
        "label": "Language Proficiency",
        "criteria": "Lists current language abilities. Resume is written in professional, clear language, "
        "free of grammatical or spelling errors. Avoids wordiness.",
    },
    {
        "key": "personal_summary",
        "label": "Personal Summary",
        "criteria": "Personal summary reflects identity, skills, and career goals effectively.",
    },
]
_RUBRIC_LABELS = {c["key"]: c["label"] for c in RUBRIC_CATEGORIES}

# Transcribed from Sample of Good Resume (1).pdf -- used only as an in-prompt
# calibration anchor for the LLM, never scored or exposed to the user itself.
# Contact details are placeholders; only the structure/content shape is real.
SAMPLE_RESUME_TEXT = """\
JANE STUDENT
Cikarang, Bekasi | +62812XXXXXXX | jane.student@example.com | linkedin.com/in/janestudent

EDUCATION
PRESIDENT UNIVERSITY, Candidate for Sarjana Komputer (S.Kom.), GPA 4.00/4.00, Sep 2022 - Sep 2025
Honors: 100% Fully-Funded Scholarship Awardee; 2nd Rank Scholarship CHEC; IISMA 2024 Awardee to Boston University, U.S.A.
Awards: 2nd Winner National-Level Mandarin Speech Competition; 1st Runner-Up International Social Business Model
Canvas Competition; 2nd Winner National Huawei ICT Competition 2023 Indonesia - Cloud Track
Activities: PUSC (President University Student Council)
SMA MONDIAL BATAM, High School Diploma, Jul 2019 - Jul 2022 -- National & International Honors 2019-2022

WORK EXPERIENCE
IISMA Mentor, International Office, President University (Jun 2024 - Present)
Handled a short semester class of 28 students for IISMA preparation. Delivered 6 meetings of extensive materials,
equivalent to 5 hours of course content. Guided students on best practices to excel in IISMA applications.
Web Developer, Marketing Bureau, President University (Jan 2024 - Present)
Developed the university's new main website using WordPress and Elementor with a team. Designed digital banners
using Figma and Adobe Illustrator. Communicated with stakeholders to gather requirements and feedback.
AI Prompt Engineer, Academic Bureau, President University (Jun 2023 - Present)
Refined prompts for a GPT-based chatbot, driving informed decision-making and cost optimization. Collaborated with
a team to ensure seamless functionality of a user-centric, efficient GPT-powered conversational experience.

PROJECTS
Community Service, Supervisor (Jun 2023 - Jul 2023) -- Supervised distribution of food packages to individuals in
need, monitored resource allocation, and collaborated with local partners to amplify outreach and impact.
Economic Survival, Team Leader (Sep 2022 - May 2023) -- Orchestrated business ideation, pitch deck creation, and
execution with a team of 8 members, fostering collaboration and proactive problem solving.
Innoverse, Project Manager (Feb 2023 - May 2023) -- Supervised 32 committees through event preparation and
execution, played a pivotal role in decision-making and risk management, and enhanced visibility via media outreach.

SKILLS & CERTIFICATES
Skills: Debate Technique, Graphic Design and Multimedia (Video and Photo Editing), Public Speaking, Research,
Software Development.
Certificates: Data Visualization, Machine Learning, AWS Cloud Practitioner, DevOps (all Dicoding Indonesia).

LANGUAGE PROFICIENCIES
English (Fluent) / DET (Score: 150/160)

PERSONAL
Enthusiastic individual with experience in Machine Learning and SaaS development, as well as pitching ideas."""

RUBRIC_RULES = f"""\
You are grading a resume against President University's Resume Evaluation Rubric. Score each of the following 7 \
categories independently on a 0-100 scale, using only the criteria given for that category:

{chr(10).join(f'- {c["key"]}: {c["label"]} -- {c["criteria"]}' for c in RUBRIC_CATEGORIES)}

For calibration, here is an example of a strong resume that would score highly across these categories:

{SAMPLE_RESUME_TEXT}

Also determine:
- "is_resume": true if the document being graded is recognizably a resume/CV (even a weak or incomplete one), \
false if it is clearly a different kind of document entirely (e.g. an essay, a course syllabus, an ID card, an \
invoice, unrelated text).
- "detected_name": the candidate's own name as it appears in the document (best guess), or an empty string if no \
personal name is identifiable.

Respond ONLY with JSON: {{"is_resume": true, "detected_name": "...", "categories": [{{"key": "...", \
"score": <0-100 integer>, "feedback": "...", "quote": "verbatim substring from the resume being graded, or empty \
string if not applicable"}}]}}
Include exactly one entry per category key listed above. Every non-empty "quote" must be an exact substring of \
the resume text provided -- never paraphrase or invent one."""

def compute_keyword_alignment_score(resume_embedding: list[float], job_target_embedding: list[float]) -> float:
    similarity = cosine_similarity(resume_embedding, job_target_embedding)
    return round(max(0.0, min(1.0, similarity)) * 100, 1)


def _parse_rubric_categories(raw: list, resume_text: str) -> list[dict]:
    """Keeps one entry per recognized category key with a numeric score and
    non-empty feedback. A quote that isn't a verbatim substring of the resume
    text is dropped (nulled), but the category's score/feedback are kept --
    those are the primary output, the quote is supporting evidence. Also
    guards against schema deviations the model doesn't reliably obey: a
    non-list `raw`, non-dict entries, or unrecognized keys must never raise.
    """
    valid: list[dict] = []
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        if key not in _RUBRIC_LABELS:
            continue
        score, feedback, quote = entry.get("score"), entry.get("feedback"), entry.get("quote")
        if not isinstance(score, (int, float)) or not isinstance(feedback, str) or not feedback:
            continue
        valid.append(
            {
                "key": key,
                "label": _RUBRIC_LABELS[key],
                "score": round(max(0.0, min(100.0, float(score))), 1),
                "feedback": feedback,
                "quote": quote if isinstance(quote, str) and quote and quote in resume_text else None,
            }
        )
    return valid


def _names_plausibly_match(registered_name: str, detected_name: str) -> bool:
    """Deliberately loose: token overlap, not exact/fuzzy string match, so a
    middle name, a nickname, or word order difference doesn't false-positive
    as a mismatch. Only meant to catch the case where a completely different
    person's name shows up on the document."""
    registered_tokens = set(registered_name.lower().split())
    detected_tokens = set(detected_name.lower().split())
    return bool(registered_tokens & detected_tokens)


async def compute_rubric_score(resume_text: str) -> tuple[list[dict] | None, bool | None, str]:
    """Returns (categories_or_None, is_resume, detected_name). is_resume is None
    (not False) when the model didn't answer or the call failed -- distinct from
    an actual "this is not a resume" verdict, so callers don't warn on a chat
    outage as if it were a document-authenticity finding."""
    messages = [
        {"role": "system", "content": RUBRIC_RULES},
        {"role": "user", "content": f"Resume to grade:\n{resume_text}"},
    ]
    try:
        raw = await chat(messages)
    except ChatServiceUnavailable:
        return None, None, ""

    parsed = extract_json_object(raw)
    if parsed is None:
        return None, None, ""

    categories = _parse_rubric_categories(parsed.get("categories", []), resume_text)
    is_resume = parsed.get("is_resume")
    detected_name = parsed.get("detected_name")
    return (
        categories or None,
        is_resume if isinstance(is_resume, bool) else None,
        detected_name.strip() if isinstance(detected_name, str) else "",
    )


async def score_resume(
    resume_text: str,
    resume_embedding: list[float] | None = None,
    job_target_embedding: list[float] | None = None,
    student_full_name: str | None = None,
) -> dict:
    keyword_score = None
    if resume_embedding is not None and job_target_embedding is not None:
        keyword_score = compute_keyword_alignment_score(resume_embedding, job_target_embedding)

    rubric_categories, is_resume, detected_name = await compute_rubric_score(resume_text)
    # _parse_rubric_categories drops entries the model returned malformed, so a
    # partial response silently became a full-looking score: 3 of 7 categories
    # graded, averaged over 3, and presented to the student as their resume
    # score with no indication anything was missing. Track the shortfall so it
    # can be disclosed instead of hidden.
    missing_categories = sorted(_RUBRIC_LABELS.keys() - {c["key"] for c in rubric_categories or []})
    rubric_average = (
        round(sum(c["score"] for c in rubric_categories) / len(rubric_categories), 1) if rubric_categories else None
    )

    components = []
    if rubric_average is not None:
        components.append((rubric_average, RUBRIC_WEIGHT))
    if keyword_score is not None:
        components.append((keyword_score, KEYWORD_WEIGHT))
    overall = weighted_average(components)

    suggestions = [
        {"text": c["feedback"], "origin": "ai-suggested"}
        for c in (rubric_categories or [])
        if c["score"] < SUGGESTION_SCORE_THRESHOLD
    ]

    notes = []
    # "Warn, don't block" -- names legitimately vary (nicknames, maiden names,
    # partial names on a resume), and a document type judged only by a 0-100
    # rubric would silently misreport a wrong-file upload as "a bad resume"
    # rather than telling the student they may have uploaded the wrong file.
    if is_resume is False:
        notes.append(
            "This file doesn't look like a resume/CV -- if you uploaded the wrong file, "
            "remove it and upload the right one."
        )
    elif student_full_name and detected_name and not _names_plausibly_match(student_full_name, detected_name):
        notes.append(
            f"The name on this document ('{detected_name}') doesn't match your registered name "
            f"('{student_full_name}') -- double check this is your own resume."
        )

    extracted_chars = len(resume_text.strip())
    if extracted_chars < MIN_MEANINGFUL_RESUME_CHARS:
        notes.append(
            f"Only {extracted_chars} characters of text could be read from this file, which is far "
            "short of a normal resume -- the scores below reflect what could be extracted, not "
            "necessarily the resume itself. If the file is image-based or an unusual layout, "
            "re-saving it as a text-based PDF and re-uploading will give a fairer result."
        )
    if keyword_score is None:
        notes.append("No job target supplied -- keyword alignment score skipped.")
    if not rubric_categories:
        # Empty and None both mean "nothing was graded" -- that has its own note
        # and must not also be described as a partial "0 of 7" rubric.
        notes.append("AI rubric grading unavailable -- scored on keyword alignment only.")
    elif missing_categories:
        graded = len(_RUBRIC_LABELS) - len(missing_categories)
        notes.append(
            f"Provisional: the AI grader returned only {graded} of {len(_RUBRIC_LABELS)} rubric categories "
            f"({', '.join(_RUBRIC_LABELS[k] for k in missing_categories)} missing), so this score averages "
            "the categories that were graded, not the full rubric. Re-run for a complete score."
        )

    return {
        "rubric_categories": rubric_categories or [],
        "keyword_alignment_score": keyword_score if keyword_score is not None else 0.0,
        "overall_score": overall,
        "suggestions": suggestions,
        "note": " ".join(notes) or None,
        "rubric_complete": bool(rubric_categories) and not missing_categories,
        "is_resume": is_resume,
        "detected_name": detected_name,
    }
