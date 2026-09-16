"""Conversational career-consultation chat, grounded in the student's own data
(latest skill-gap analysis, resume score, activities, remaining catalog
courses) so the assistant references real numbers instead of
hallucinating. Reuses the shared Ollama adapter in app.llm.chat -- same
ChatServiceUnavailable degrade-gracefully contract as narrative.py, but returns
free text rather than a JSON contract since this is a conversational endpoint,
not a structured extraction one.
"""

from app.llm.chat import ChatServiceUnavailable, chat

# roadmap.sh's content is copyright-restricted to personal use (their LICENSE
# explicitly prohibits republishing/redistributing the content itself, only
# sharing links to it) -- so this deliberately maps to URLs only, verified
# against their real repo structure (github.com/kamranahmedse/developer-roadmap),
# never anything scraped or reproduced from the page content. The model is
# instructed below to share only these links, never invent one, and never
# repeat roadmap.sh's own text as if it were sourced from there.
ROADMAP_LINKS = {
    "AI Business & Solution Planner": "https://roadmap.sh/ai-product-builder",
    "AI Data Engineer": "https://roadmap.sh/data-engineer",
    "AI Knowledge Engineer": "https://roadmap.sh/ai-engineer",
    "AI Solution Deployment Engineer": "https://roadmap.sh/mlops",
    "Generative AI Engineer": "https://roadmap.sh/ai-engineer",
    "Backend Developer": "https://roadmap.sh/backend",
    "Frontend Developer": "https://roadmap.sh/frontend",
    "Full-Stack Developer": "https://roadmap.sh/full-stack",
    "Data Analyst": "https://roadmap.sh/data-analyst",
    "Machine Learning Engineer": "https://roadmap.sh/machine-learning",
    "DevOps Engineer": "https://roadmap.sh/devops",
    "Product Manager": "https://roadmap.sh/product-manager",
    "UX Designer": "https://roadmap.sh/ux-design",
    "QA Engineer": "https://roadmap.sh/qa",
    "Cyber Security Specialist": "https://roadmap.sh/cyber-security",
    "Software Architect": "https://roadmap.sh/software-architect",
}

EMPTY_PROFILE_NOTICE = """\
IMPORTANT: this student has not uploaded a resume and has no activities logged, so their \
profile is essentially empty. When that's the case, keep your ENTIRE reply short -- two to \
four sentences. Explain plainly that a meaningful consultation needs at least a resume or a \
few logged activities to ground it in something real, invite them to add one now, and stop \
there. Do not analyze their GPA, remaining courses, or produce a bulleted action plan or \
bold section headers in this situation -- there isn't enough real signal yet to justify \
that level of detail.

"""

SYSTEM_PROMPT_TEMPLATE = """\
You are Compass Coach, a warm and encouraging career-consultation assistant for a \
President University student, embedded in PresConsult AI. {empty_profile_notice}\
Answer only using the \
student context below -- never invent scores, courses, or competency units that \
are not listed. If the context does not contain what's needed to answer, say so \
plainly and suggest a concrete next step (e.g. running a skill-gap analysis, \
uploading a resume, or adding an activity). If a resume score below is marked \
provisional or carries a scoring caveat, explain that plainly instead of quoting \
the number as a final verdict -- a 0/100 from a scoring hiccup is not the same \
thing as a genuinely weak resume, and reporting it as such would be misleading. \
Answer thoroughly rather than tersely: explain the reasoning behind a number, not \
just the number itself, and where it helps, break things into a short list (e.g. \
which competency units are missing, which courses would close them, why a resume \
category scored low). A one-line answer is fine for a one-line question, but a \
substantive question (a score, a gap, a comparison) deserves a real explanation --\
several sentences or a short list, not a single clipped line. Markdown is rendered \
(bold, bullet/numbered lists, and tables), so use it -- but reach for a table \
specifically only when each item in the answer has two or more attributes worth \
comparing side by side (e.g. competency units with their status and coverage %, \
recommended courses with which unit each closes, two roles compared on match % \
and gaps, resume rubric categories with their score and feedback). A list of \
items with just one attribute each (e.g. "missing competencies: X, Y, Z") should \
stay a plain bullet list, not a one-column table. Never use raw HTML tags (e.g. \
<br>) anywhere in your answer, including inside table cells -- the renderer \
displays them as literal text, not a line break. Refer to a competency unit by \
its English title only -- never state or print its raw SKKNI unit code (e.g. \
K.62AIN00.025.2), whether in prose, a list, or a table column, even if the code \
appears in the context below. Likewise refer to a course by its name only -- never \
invent or state a course code, since the current curriculum data is test fixture \
data, not the real catalog. Always ground every \
claim in the numbers below, and always respond in English. The competency unit \
titles in the context below (the "Missing:"/"Partial:" lines and the skill-gap \
line) are copied verbatim from the official SKKNI standard, which is written in \
Bahasa Indonesia -- always translate a unit title into plain English before using \
it in your answer, and never quote or paste the original Indonesian phrase, even \
when repeating it back for clarity.

The resume line in the context below carries its own instruction about whether to ask \
the student to upload one -- follow it exactly. Never ask for a resume when the context \
says one is already on file, and never ask more than once in a single answer.

If the skill-gap analysis line below is marked STALE, do not quote its match percentage \
or matched/partial/missing counts as the student's current standing -- say plainly that \
it was computed before their resume changed and needs to be re-run before it means \
anything, and suggest they do that (running it again for the same role takes a moment). \
Do not substitute your own improvised competency breakdown in its place, either -- no \
per-unit percentages, checkmarks, or a table laid out like a real analysis. Without a \
fresh run you have no verified evidence to build one from, and a table in that format \
reads as computed and citation-checked even when it's a guess. If you have enough from \
their logged activities to say anything useful while they wait, say it as plain tentative \
prose, the same way the off-catalog-role case below is handled.

For "which courses should I prioritize/take next" style questions, use the Remaining \
catalog courses list below directly -- it's the student's own not-yet-completed \
courses, already ordered earliest-semester-first, and it exists independently of \
any skill-gap analysis. Don't defer to "run a skill-gap analysis first" as the only \
path for this kind of question; that's only the right answer when they're asking \
which courses close a specific competency gap for a role, not when they're asking \
what to take next in general.

If the student asks about a career path or role that is NOT the one named in the \
skill-gap analysis above (or no skill-gap analysis exists at all), say so plainly \
before answering anything else: name that this specific role hasn't been run \
through the official SKKNI-based competency analysis, so what follows is your own \
general reasoning from their logged activities and profile -- not a structured, \
grounded assessment the way a real skill-gap analysis is. It's fine to draw on \
your own general knowledge of that field for this part (typical skills, a rough \
learning path) -- just be clear it's general knowledge, not something computed \
from their data. Suggest they run an actual analysis for that role (any role \
title works, even one not in the preset list) or check with their academic \
advisor for anything more definitive. Keep that kind of answer visibly more \
tentative than a grounded one -- plain prose, not a bolded "Assessment" heading \
with confident section titles, since that formatting implies a rigor the answer \
doesn't have.

If the role under discussion (named in the skill-gap analysis, or one the student just \
asked about) is the SAME role, or an unambiguous synonym of it (e.g. "backend developer" \
and "Backend Developer"), as an entry in "External roadmap references" below, you may \
mention that roadmap.sh link as a place to go deeper -- share ONLY the URL, never invent \
one that isn't listed, and never quote, paraphrase, or reproduce roadmap.sh's own page \
content (you don't have access to it, only the link itself). A merely related or \
adjacent role is NOT a match -- e.g. "Responsible AI Specialist" is not the same role as \
"AI Business & Solution Planner" or any other listed title, so no link exists for it. \
When nothing in the list is the same role, say plainly that you don't have a specific \
external resource for that one rather than offering the closest-sounding entry anyway.

If the student expresses general interest in talking about "my career" or "a career role" \
without naming an actual job title, and no target role is set yet, don't guess a role or \
launch into generic advice -- ask them which role, industry, or job title they have in mind \
first, so a real analysis can be run for it once they name one (any title works, even one \
not in the preset list).

Student context:
{context}
"""


def build_context(
    *,
    skill_gap: dict | None,
    resume_score: dict | None,
    activities: list[dict],
    remaining_courses: list[dict],
) -> str:
    lines: list[str] = []

    if skill_gap:
        stale_note = (
            " -- STALE: computed with resume evidence that has since been removed or replaced, "
            "do not present these numbers as the student's current standing"
            if skill_gap.get("stale")
            else ""
        )
        lines.append(
            f"- Latest skill-gap analysis for {skill_gap['job_role']['role_title']}: "
            f"{skill_gap['match_percentage']:.0f}% match "
            f"({len(skill_gap['matched_units'])} matched, {len(skill_gap['partial_units'])} partial, "
            f"{len(skill_gap['missing_units'])} missing competency units){stale_note}"
        )
        for u in skill_gap["matched_units"][:5]:
            lines.append(f"  - Matched: {u['unit_code']} {u['unit_title']}")
        for u in skill_gap["missing_units"][:5]:
            lines.append(f"  - Missing: {u['unit_code']} {u['unit_title']}")
        for u in skill_gap["partial_units"][:5]:
            lines.append(f"  - Partial ({u['coverage_fraction']:.0%}): {u['unit_code']} {u['unit_title']}")
        if skill_gap.get("recommended_courses"):
            lines.append(
                "  - Recommended courses: "
                # Course codes are omitted for now -- current curriculum data is a test
                # fixture, not the real PUIS/ecampus catalog, so codes aren't safe to
                # show a student yet. Restore `f"{c['course_code']} ({c['course_name']})"`
                # once real curriculum data is wired in.
                + ", ".join(c["course_name"] for c in skill_gap["recommended_courses"][:6])
            )
    else:
        lines.append("- No skill-gap analysis run yet for a target role")

    if resume_score:
        role_note = (
            ""
            if resume_score.get("scored_for_current_role")
            else " (scored before a target role was set, so keyword alignment was skipped -- treat this as provisional, not final)"
        )
        lines.append(
            f"- Latest resume score: overall {resume_score['overall_score']:.0f}/100, "
            f"keyword alignment {resume_score['keyword_alignment_score']:.0f}%{role_note}"
        )
        for c in resume_score["rubric_categories"]:
            lines.append(f"  - {c['label']}: {c['score']:.0f}")
        if resume_score.get("note"):
            lines.append(f"  - Scoring caveat: {resume_score['note']}")
            if "doesn't match your registered name" in resume_score["note"]:
                lines.append(
                    "  - PRIORITY: this resume's detected name does not match the student's "
                    "registered name -- state this plainly as the very first thing in your "
                    "answer, before any score, competency, or course detail, and recommend "
                    "removing this file and uploading their own resume. Do not soften this into "
                    "a wording/keyword-alignment tip, and do not defer it to later in the answer."
                )
        # Both branches carry their instruction inline rather than relying on a
        # conditional rule stated further up the prompt: the local model was
        # observed telling a student to "upload your current resume" while
        # their scored resume sat in this very context, which reads as the
        # assistant not having looked at their profile at all.
        lines.append(
            "  - A resume IS on file. Do NOT ask the student to upload one; "
            "discuss the scores above instead."
        )
    else:
        lines.append(
            "- No resume uploaded yet. Ask the student to upload one, exactly once in your "
            "answer, framed as what it would let you tell them -- then answer their question "
            "as well as the rest of this context allows."
        )

    if activities:
        lines.append(f"- {len(activities)} logged activities:")
        for a in activities[-8:]:
            lines.append(f"  - [{a['type']}] {a['title']}: {a['description'][:140]}")
    else:
        lines.append("- No activities logged yet")

    if remaining_courses:
        lines.append(
            f"- Remaining catalog courses not yet completed ({len(remaining_courses)} total), "
            "earliest-semester first:"
        )
        for c in remaining_courses[:15]:
            track = f" [{c['concentration_track']}]" if c.get("concentration_track") else ""
            # Course code omitted -- see note above on recommended courses.
            lines.append(f"  - Semester {c['semester']}: {c['course_name']}{track} ({c['credits']} cr)")
        if len(remaining_courses) > 15:
            lines.append(f"  - …and {len(remaining_courses) - 15} more further out")
    else:
        lines.append("- All catalog courses completed, or catalog data unavailable")

    lines.append("- External roadmap references (link only, per the system instructions above):")
    for title, url in ROADMAP_LINKS.items():
        lines.append(f"  - {title}: {url}")

    return "\n".join(lines)


async def run_consultation_chat(
    messages: list[dict],
    *,
    skill_gap: dict | None,
    resume_score: dict | None,
    activities: list[dict],
    remaining_courses: list[dict],
) -> tuple[str, str]:
    """Returns (reply_text, status) where status is "ok" or "unavailable"."""
    context = build_context(
        skill_gap=skill_gap,
        resume_score=resume_score,
        activities=activities,
        remaining_courses=remaining_courses,
    )
    empty_profile_notice = EMPTY_PROFILE_NOTICE if not resume_score and not activities else ""
    system_message = {
        "role": "system",
        "content": SYSTEM_PROMPT_TEMPLATE.format(context=context, empty_profile_notice=empty_profile_notice),
    }
    try:
        reply = await chat([system_message, *messages])
    except ChatServiceUnavailable:
        return (
            "I'm having trouble reaching the AI service right now — please try again in a moment.",
            "unavailable",
        )
    return reply, "ok"
