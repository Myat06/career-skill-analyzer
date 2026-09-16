"""Generates the four advisory sections of the consultation report (executive
summary, career roadmap, recommended direction, coach message) that the app's
existing scoring modules don't produce -- everything else in the report is
deterministic (academic summary, resume rubric, skill gap) or reuses
narrative.py's citation-checked strengths/weaknesses.

This is free-form advisory synthesis, not fact-by-fact claims, so it doesn't
carry narrative.py's per-claim [S1] citation-and-repair machinery -- but it
keeps the same grounding discipline (never invent a course/unit code that
isn't in the evidence given) and the same never-hard-fail contract: a chat
failure or unparseable response yields None, and the report renders without
these sections rather than failing outright.
"""

from app.llm.chat import ChatServiceUnavailable, chat, extract_json_object

ROADMAP_TIMEFRAMES = ["Immediate / 2 Weeks", "1 Month", "3 Months", "6 Months", "12 Months"]

CONSULTATION_RULES = f"""\
You are an AI career-readiness consultant writing an advisory report for a student, in \
the style of a university career center consultation. Using only the evidence given, \
always write in English:
- Never invent a course name, SKKNI unit code, or score that is not present in the \
evidence below.
- Refer to a competency unit by its English title only, and a course by its name only -- \
never state or print a raw SKKNI unit code (e.g. K.62AIN00.025.2) or a course code, even \
if either appears in the evidence below (course codes are omitted for now: the current \
curriculum data is test fixture data, not the real catalog).
- Write a 2-4 sentence "executive_summary" assessing overall readiness for the target role.
- Write a "career_roadmap": one entry per timeframe, in this exact order and using these \
exact timeframe labels: {ROADMAP_TIMEFRAMES}. Each entry's "actions" is 1-3 concrete, \
concise action items for that timeframe, grounded in the gaps and recommended courses \
given.
- Write a 1-2 sentence "recommended_direction" naming realistic role(s)/pathways that fit \
the evidence.
- Write a 2-3 sentence "coach_message": encouraging, second-person, referencing at least \
one concrete strength and one concrete next step from the evidence.
Respond ONLY with JSON: {{"executive_summary": "...", "career_roadmap": \
[{{"timeframe": "...", "actions": "..."}}], "recommended_direction": "...", "coach_message": "..."}}"""


def _coerce_text(raw) -> str:
    return raw.strip() if isinstance(raw, str) else ""


def _coerce_actions(raw) -> str:
    """The prompt asks for "1-3 concrete, concise action items", which invites a
    JSON list every bit as naturally as a sentence -- but a list used to fail
    the isinstance(actions, str) check and be dropped, and if the model
    answered that way for all five timeframes the entire roadmap came back
    empty and the report printed "AI roadmap generation unavailable" over a
    response that was actually fine. Coerce the value, not just validate its
    type -- the same lesson as _coerce_citations in scoring/narrative.py.

    Only strings are accepted as content, in both the scalar and the list case:
    unlike a citation ID, where "1" legitimately means "S1", a bare number is
    never a real action item, and coercing one would put "42." in a student's
    roadmap rather than dropping a junk entry.
    """
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, (list, tuple)):
        parts = [i.strip() for i in raw if isinstance(i, str) and i.strip()]
        # Normalize each item to a sentence so joined fragments still read
        # correctly in the report's single "actions" table cell.
        return " ".join(p if p.endswith((".", "!", "?")) else f"{p}." for p in parts)
    return ""


def _parse_roadmap(raw: list) -> list[dict]:
    """Tolerant parsing, same discipline as resume_score._parse_rubric_categories:
    never raise on a schema deviation the model doesn't reliably obey.
    """
    entries = []
    for i, item in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(item, dict):
            continue
        actions = _coerce_actions(item.get("actions"))
        if not actions:
            continue
        # The prompt pins the timeframe labels and their order, so a missing or
        # malformed label can be recovered from position rather than costing an
        # otherwise-usable entry.
        timeframe = _coerce_text(item.get("timeframe"))
        if not timeframe:
            timeframe = ROADMAP_TIMEFRAMES[i] if i < len(ROADMAP_TIMEFRAMES) else ""
        if timeframe:
            entries.append({"timeframe": timeframe, "actions": actions})
    return entries


async def generate_consultation_narrative(evidence_text: str) -> dict | None:
    messages = [
        {"role": "system", "content": CONSULTATION_RULES},
        {"role": "user", "content": f"Evidence:\n{evidence_text}"},
    ]

    # One bounded retry when the response isn't parseable JSON at all. This is
    # not narrative.py's citation-repair pass (that checks claims against
    # evidence, which this free-form advisory section has no equivalent of) --
    # it only covers the local model occasionally emitting prose around, or a
    # truncated tail on, an otherwise fine answer. Without it a single
    # malformed response cost the report four whole sections.
    parsed = None
    for attempt in range(2):
        attempt_messages = messages if attempt == 0 else messages + [
            {"role": "user", "content": "That response was not valid JSON. Reply with the JSON object only, no other text."}
        ]
        try:
            raw = await chat(attempt_messages)
        except ChatServiceUnavailable:
            return None
        parsed = extract_json_object(raw)
        if parsed is not None:
            break
    if parsed is None:
        return None

    result = {
        "executive_summary": _coerce_text(parsed.get("executive_summary")),
        "career_roadmap": _parse_roadmap(parsed.get("career_roadmap", [])),
        "recommended_direction": _coerce_text(parsed.get("recommended_direction")),
        "coach_message": _coerce_text(parsed.get("coach_message")),
    }
    # Salvage whatever parsed instead of discarding all four sections together:
    # a missing executive_summary used to return None, throwing away a
    # perfectly good career roadmap, coach message and recommended direction
    # with it -- which is precisely how the report ended up printing
    # "AI roadmap generation unavailable" for a usable roadmap. Only a
    # response with nothing usable in it at all counts as a failure.
    return result if any(result.values()) else None
