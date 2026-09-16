"""LLM-judged matching between free-text student evidence (uploaded resume,
logged activities) and specific SKKNI competency-unit elements.

Completed courses are matched deterministically against the curated
SKKNI-to-curriculum mapping (see skkni_mapping.py) -- a course code either is
or isn't mapped to a unit, no judgment call needed. Resume text and logged
activities have no such fixed mapping (a student can write anything), so they
still need a judgment call about whether the text demonstrates a competency
element. Rather than approximating that with embedding cosine similarity (the
previous approach -- see git history), this asks the chat model directly and
then verifies its answer: the same cite-then-validate discipline as
narrative.py/resume_score.py. The model must produce a VERBATIM quote for
every element it claims is demonstrated; a quote that isn't an exact
substring of its claimed source text is discarded rather than trusted. This
is the one place in the matching pipeline where a model's judgment, not
curated data, decides a matched/missing outcome, so a hallucinated citation
must not silently count as evidence -- an unverifiable claim is dropped, not
kept as a weaker version of a match.

Two things were confirmed live (against the real qwen3.5 model) to matter,
not just in theory:
- Element titles must be English. Handed the raw Indonesian element_title,
  the model returned an empty match set for evidence that plainly supported
  it; handed the English translation (see skkni_titles.py), it found the
  match immediately. gap_engine.py translates element titles before they
  ever reach here, but this module's own tests exercise both cases so this
  requirement stays visible and doesn't silently regress.
- Evidence must be cited by a short opaque ID (E1, E2, ...), not by the
  source's real identifier. Asked to echo back a descriptive source_id
  (e.g. "activity:<uuid>"), the model instead echoed the entire bracketed
  "[id] text" line as the id. Short IDs are the same pattern narrative.py
  already uses for its own citations (S1, S2, ...) for exactly this reason.
- Run-to-run consistency needed temperature=0. The same student/evidence
  measured two different match_percentage results (70% vs 73.3%) across two
  otherwise-identical calls at the default temperature. Unlike the citation
  checks above, this isn't a hallucination risk to guard against after the
  fact -- it's sampling variance in *which* true elements the model notices
  on a given pass, so the fix is upstream (pin temperature=0 on this call
  specifically, not narrative.py's/resume_score.py's/consultation_chat.py's
  calls, which still want the model's normal creative range).
"""

from dataclasses import dataclass

from app.llm.chat import ChatServiceUnavailable, chat, extract_json_object

# Generous headroom for one role's required units (job_role_definitions.yaml
# roles have 4-5 units, ~3-5 elements each -- comfortably under this even
# summed with a resume + several activities, within CHAT_NUM_CTX=8192).
MAX_ELEMENTS_PER_CALL = 60

SYSTEM_PROMPT = """\
You are checking whether a student's evidence texts demonstrate specific professional \
competency elements from the official SKKNI standard. For each element listed below, decide \
whether ANY of the evidence texts demonstrates it. Only claim a match when you can quote a \
VERBATIM substring -- an exact, character-for-character copy, not a paraphrase or summary -- \
from the evidence text that supports it. If no evidence text supports an element, simply omit \
it from your answer; do not guess or force a weak match. "evidence_id" must be exactly one of \
the bracketed IDs shown before each evidence text (e.g. "E1") -- never the evidence text itself \
and never a description of it. Respond ONLY as JSON: {"matches": [{"unit_code": "...", \
"element_number": "...", "evidence_id": "E1", "quote": "..."}]}"""


@dataclass
class EvidenceItem:
    source_id: str  # "resume" or "activity:<id>" -- for the caller's own bookkeeping only, never sent to the model
    text: str


@dataclass
class RequiredElement:
    unit_code: str
    element_number: str
    element_title: str


def _build_user_prompt(elements: list[RequiredElement], evidence_texts: dict[str, str]) -> str:
    element_lines = "\n".join(
        f"- unit_code={e.unit_code} element_number={e.element_number}: {e.element_title}" for e in elements
    )
    evidence_lines = "\n".join(f"[{eid}] {text}" for eid, text in evidence_texts.items())
    return f"Competency elements to check:\n{element_lines}\n\nEvidence texts:\n{evidence_lines}"


async def match_text_evidence(
    elements: list[RequiredElement], evidence: list[EvidenceItem]
) -> tuple[dict[tuple[str, str], str], str]:
    """Returns ({(unit_code, element_number): source_id, ...} verified as
    demonstrated, status).

    source_id is the EvidenceItem's own real identifier ("resume" or
    "activity:<id>") -- callers can use this to attribute a match to a
    specific piece of evidence (e.g. "matched via your RPA hackathon
    activity") instead of just knowing an element matched *something*. If
    more than one evidence item verifiably supports the same element, the
    first one the model returned wins; which evidence gets attributed
    doesn't change whether the element counts as matched.

    status is "ok", "no_evidence" (nothing to check -- no elements or no
    evidence text at all, so the chat model was never called), "unavailable"
    (chat model unreachable), or "degraded" (reply wasn't valid JSON). A
    pair only ever lands in the returned dict carrying a quote that
    genuinely appears in its claimed evidence text -- callers don't see the
    quote itself, only which real evidence item verified it, since a
    rejected claim must not leave any trace that could be mistaken for
    evidence.
    """
    if not elements or not evidence:
        return {}, "no_evidence"

    evidence_by_id = {f"E{i}": e for i, e in enumerate(evidence, start=1)}
    evidence_texts = {eid: item.text for eid, item in evidence_by_id.items()}
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(elements[:MAX_ELEMENTS_PER_CALL], evidence_texts)},
    ]
    try:
        raw = await chat(messages, temperature=0.0)
    except ChatServiceUnavailable:
        return {}, "unavailable"

    parsed = extract_json_object(raw)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("matches"), list):
        return {}, "degraded"

    verified: dict[tuple[str, str], str] = {}
    for m in parsed["matches"]:
        if not isinstance(m, dict):
            continue
        unit_code, element_number, evidence_id, quote = (
            m.get("unit_code"),
            m.get("element_number"),
            m.get("evidence_id"),
            m.get("quote"),
        )
        if not (isinstance(unit_code, str) and isinstance(quote, str) and quote):
            continue
        if not isinstance(element_number, (str, int)):
            continue
        evidence_item = evidence_by_id.get(evidence_id) if isinstance(evidence_id, str) else None
        if evidence_item is None or quote not in evidence_item.text:
            continue  # unverifiable or hallucinated citation -- discard, don't trust
        verified.setdefault((unit_code, str(element_number)), evidence_item.source_id)
    return verified, "ok"
