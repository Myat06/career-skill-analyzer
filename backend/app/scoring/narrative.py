"""Grounded strengths/weaknesses narrative generation, modeled directly on
knowledge-base's answers.py: the model receives only a bounded evidence set
and citation rules; citation existence is checked deterministically, with
one bounded repair call allowed on failure -- no retry loop. Deterministic
skill-gap fields never depend on this: the caller always has
match_percentage/unit lists/recommended_courses even if the narrative comes
back unavailable or degraded.
"""

import re

from app.llm.chat import ChatServiceUnavailable, chat, extract_json_object
from app.scoring.gap_engine import RecommendedCourse, UnitCoverageResult, format_recommended_courses_block

EVIDENCE_LIMIT = 8
_SECTION_KEYS = ("strengths", "weaknesses", "improvement_suggestions")
CITATION_RE = re.compile(r"\[S(\d+)\]")
# "S1" is what the prompt asks for, but local models return "1", "s1", "[S1]"
# or " S1 " interchangeably -- the same value-level (not just type-level)
# deviation _coerce_citations() already handles for the container type.
_CITATION_ID_RE = re.compile(r"^\[?\s*s?(\d+)\s*\]?$", re.IGNORECASE)

NARRATIVE_RULES = """\
You are a career-readiness advisor. Using only the evidence below:
- Always write in English, even though the evidence (SKKNI unit titles/elements) is in \
Bahasa Indonesia -- translate any Indonesian terms you reference rather than quoting them as-is.
- Cite every claim with [S1], [S2], etc., using only the evidence IDs supplied.
- A matched element followed by "(via your resume)" or "(via your \"...\" activity)" tells you \
specifically what evidenced it -- prefer naming that source in a strength's text (e.g. "your \
\"RPA Hackathon\" activity demonstrates...") over a generic "the student demonstrates..." when \
that detail is available, since it's more concrete and lets the student see exactly what's \
carrying the claim.
- Do not claim more competency than the evidence supports.
- Never invent a course name or SKKNI unit code that is not in the evidence below.
- Refer to a competency unit by its English title only -- never state or print its raw SKKNI \
unit code (e.g. K.62AIN00.025.2) in your text, even though the code appears in the evidence below.
- Refer to a course by its name only -- never state or invent a course code, since the current \
curriculum data is test fixture data, not the real catalog.
- Distinguish strengths (matched competencies) from weaknesses (missing/partial competencies).
- Respond ONLY as JSON: {"strengths": [{"text": "...", "citations": ["S1"]}], "weaknesses": [...], "improvement_suggestions": [...]}"""


def _build_evidence(
    matched: list[UnitCoverageResult], gaps: list[UnitCoverageResult], recommended_courses: list[RecommendedCourse]
) -> tuple[str, set[str]]:
    half = EVIDENCE_LIMIT // 2
    matched_items = matched[:half]
    items = matched_items + gaps[: EVIDENCE_LIMIT - len(matched_items)]

    blocks = []
    ids: set[str] = set()
    for i, coverage in enumerate(items, start=1):
        sid = f"S{i}"
        ids.add(sid)
        # Elements matched via a completed course (see gap_engine.py's
        # compute_unit_coverage) carry no source label -- there's only one
        # kind of course evidence, already implied by status=matched. An
        # element matched via resume/activity text does carry one, so the
        # model can say *which* activity backs a strength instead of just
        # that something does.
        matched_with_sources = [
            f"{label} (via {coverage.matched_element_sources[label]})"
            if label in coverage.matched_element_sources
            else label
            for label in coverage.matched_elements
        ]
        blocks.append(
            f"[{sid}] Unit {coverage.unit_code} - {coverage.unit_title}: status={coverage.status}, "
            f"coverage={coverage.coverage_fraction:.0%}, "
            f"matched elements: {', '.join(matched_with_sources) or 'none'}, "
            f"unmatched elements: {', '.join(coverage.unmatched_elements) or 'none'}"
        )

    blocks.append(format_recommended_courses_block(recommended_courses))
    return "\n".join(blocks), ids


def _normalize_citation(raw: str) -> str | None:
    match = _CITATION_ID_RE.match(raw)
    return f"S{match.group(1)}" if match else None


def cited_ids(point: dict) -> set[str]:
    """Every evidence ID a single claim references. Reads BOTH the structured
    `citations` array (what the JSON schema actually asks for) and any inline
    [S1] markers in the prose -- an earlier version scanned only the prose,
    so whenever the model correctly put its citations in the array instead of
    the sentence, the check saw zero citations and passed trivially.
    """
    ids = {n for raw in point.get("citations", []) if (n := _normalize_citation(raw))}
    ids |= {f"S{m}" for m in CITATION_RE.findall(point.get("text", ""))}
    return ids


def partition_by_support(points: list[dict], valid_ids: set[str]) -> tuple[list[dict], list[dict]]:
    """Splits claims into (supported, unsupported). A claim is supported only
    if it cites at least one evidence ID AND every ID it cites is real --
    an uncited claim about a student's competency is exactly as ungrounded as
    one citing an invented [S99], so neither may be shown as analysis.
    """
    supported: list[dict] = []
    unsupported: list[dict] = []
    for point in points:
        ids = cited_ids(point)
        (supported if ids and ids <= valid_ids else unsupported).append(point)
    return supported, unsupported


def _coerce_citations(raw) -> list[str]:
    """The model is instructed to return citations as a list of strings like
    "S1", but sometimes returns a bare string, a list of ints, or omits the
    field -- coerce to list[str] so the Pydantic response model never 500s
    on a schema deviation. A malformed citation that doesn't match a real
    evidence ID still fails validate_citations() downstream and triggers the
    existing repair pass, which is the correct place to reject it, not here.
    """
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [str(c) for c in raw if isinstance(c, (str, int, float))]


def _extract_points(parsed: dict, key: str) -> list[dict]:
    """The model is instructed to return {"text": ..., "citations": [...]}
    objects but sometimes returns plain strings instead -- tolerate both
    rather than crash on a schema deviation the model doesn't reliably obey.
    """
    points = []
    for p in parsed.get(key, []):
        if isinstance(p, dict):
            text = p.get("text", "")
            points.append({"text": text if isinstance(text, str) else str(text), "citations": _coerce_citations(p.get("citations"))})
        elif isinstance(p, str):
            points.append({"text": p, "citations": []})
    return points


async def generate_narrative(
    matched: list[UnitCoverageResult],
    partial: list[UnitCoverageResult],
    missing: list[UnitCoverageResult],
    recommended_courses: list[RecommendedCourse],
) -> tuple[dict | None, str]:
    """Returns (narrative_dict_or_none, narrative_status)."""
    gaps = partial + missing
    if not matched and not gaps:
        return None, "unavailable"

    evidence_text, valid_ids = _build_evidence(matched, gaps, recommended_courses)
    messages = [
        {"role": "system", "content": NARRATIVE_RULES},
        {"role": "user", "content": f"Evidence:\n{evidence_text}"},
    ]

    try:
        raw = await chat(messages)
    except ChatServiceUnavailable:
        return None, "unavailable"

    parsed = extract_json_object(raw)
    if parsed is None:
        return None, "degraded"

    def _sections(parsed: dict) -> dict[str, list[dict]]:
        return {key: _extract_points(parsed, key) for key in _SECTION_KEYS}

    def _unsupported_count(sections: dict[str, list[dict]]) -> int:
        return sum(len(partition_by_support(points, valid_ids)[1]) for points in sections.values())

    sections = _sections(parsed)
    citations_valid = _unsupported_count(sections) == 0
    repair_attempted = False

    if not citations_valid:
        repair_attempted = True
        repair_messages = messages + [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": (
                    f"Some claims are unsupported. Every claim must carry at least one citation, "
                    f"and you may only cite these IDs: {sorted(valid_ids)}. Revise your JSON response."
                ),
            },
        ]
        try:
            raw = await chat(repair_messages)
            parsed = extract_json_object(raw)
            if parsed is not None:
                sections = _sections(parsed)
                citations_valid = _unsupported_count(sections) == 0
        except ChatServiceUnavailable:
            pass

    # Whatever is still unsupported after the one repair attempt is dropped
    # rather than rendered: the PDF/poster/frontend present these bullets as
    # evidence-backed findings about a real student, so an uncited or
    # invented-citation claim must not reach them. Deterministic fields
    # (match %, unit lists, recommended courses) are unaffected -- the caller
    # always has those even when every claim here is discarded.
    dropped = 0
    kept: dict[str, list[dict]] = {}
    for key, points in sections.items():
        supported, unsupported = partition_by_support(points, valid_ids)
        kept[key] = supported
        dropped += len(unsupported)

    narrative = {
        **kept,
        "citations_valid": citations_valid,
        "repair_attempted": repair_attempted,
        "unsupported_claims_dropped": dropped,
    }
    return narrative, ("ok" if citations_valid else "degraded")
