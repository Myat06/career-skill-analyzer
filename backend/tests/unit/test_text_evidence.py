import asyncio
import json

import app.scoring.text_evidence as text_evidence
from app.llm.chat import ChatServiceUnavailable
from app.scoring.text_evidence import MAX_ELEMENTS_PER_CALL, EvidenceItem, RequiredElement, match_text_evidence

# Evidence is cited back by the chat model as a short opaque ID ("E1", "E2",
# ...) assigned in list order -- the first EvidenceItem passed to
# match_text_evidence is always "E1", the second "E2", etc. See
# text_evidence.py's module docstring for why (a live check found the model
# echoing back the entire "[id] text" evidence line when asked for a
# descriptive source_id instead of a short opaque one).
#
# Every fake_chat below accepts a `temperature` kwarg even when it ignores
# the value, because match_text_evidence always calls chat(messages,
# temperature=0.0) -- see test_matching_call_pins_temperature_to_zero for the
# test that actually checks that value.


def _element(unit_code="U1", number="1", title="Element one") -> RequiredElement:
    return RequiredElement(unit_code=unit_code, element_number=number, element_title=title)


def _run(elements, evidence):
    return asyncio.run(match_text_evidence(elements, evidence))


def test_no_elements_or_no_evidence_skips_the_chat_call(monkeypatch):
    called = False

    async def fake_chat(messages, temperature=None):
        nonlocal called
        called = True
        return "{}"

    monkeypatch.setattr(text_evidence, "chat", fake_chat)
    assert _run([], [EvidenceItem("resume", "some text")]) == ({}, "no_evidence")
    assert _run([_element()], []) == ({}, "no_evidence")
    assert called is False


def test_matching_call_pins_temperature_to_zero(monkeypatch):
    # This is the fix for a live-observed problem, not a style preference:
    # the same student/evidence measured two different match_percentage
    # results (70% vs 73.3%) across two otherwise-identical calls at the
    # model's default temperature. Pinning temperature=0 removes that
    # sampling variance for this factual yes/no matching task.
    seen_temperature = "not passed"

    async def fake_chat(messages, temperature=None):
        nonlocal seen_temperature
        seen_temperature = temperature
        return "{}"

    monkeypatch.setattr(text_evidence, "chat", fake_chat)
    _run([_element()], [EvidenceItem("resume", "some text")])
    assert seen_temperature == 0.0


def test_verbatim_quote_is_accepted(monkeypatch):
    reply = json.dumps(
        {"matches": [{"unit_code": "U1", "element_number": "1", "evidence_id": "E1", "quote": "led a team of 5"}]}
    )
    monkeypatch.setattr(text_evidence, "chat", lambda messages, temperature=None: _async_return(reply))

    verified, status = _run([_element()], [EvidenceItem("resume", "In 2024 I led a team of 5 engineers.")])
    assert verified == {("U1", "1"): "resume"}
    assert status == "ok"


def test_non_verbatim_quote_is_rejected(monkeypatch):
    # The model paraphrased instead of quoting -- not an exact substring of the
    # source text, so it must not count as evidence.
    reply = json.dumps(
        {"matches": [{"unit_code": "U1", "element_number": "1", "evidence_id": "E1", "quote": "managed a team"}]}
    )
    monkeypatch.setattr(text_evidence, "chat", lambda messages, temperature=None: _async_return(reply))

    verified, status = _run([_element()], [EvidenceItem("resume", "In 2024 I led a team of 5 engineers.")])
    assert verified == {}
    assert status == "ok"


def test_quote_attributed_to_an_evidence_id_that_does_not_contain_it_is_rejected(monkeypatch):
    # Quote is verbatim in the resume (E1), but claimed against a different
    # evidence item (E2, an activity) that doesn't contain it -- must not count.
    reply = json.dumps(
        {"matches": [{"unit_code": "U1", "element_number": "1", "evidence_id": "E2", "quote": "led a team of 5"}]}
    )
    monkeypatch.setattr(text_evidence, "chat", lambda messages, temperature=None: _async_return(reply))

    verified, status = _run(
        [_element()],
        [EvidenceItem("resume", "I led a team of 5 engineers."), EvidenceItem("activity:1", "Volunteered at a shelter.")],
    )
    assert verified == {}
    assert status == "ok"


def test_unknown_evidence_id_is_rejected(monkeypatch):
    reply = json.dumps(
        {"matches": [{"unit_code": "U1", "element_number": "1", "evidence_id": "E99", "quote": "led a team"}]}
    )
    monkeypatch.setattr(text_evidence, "chat", lambda messages, temperature=None: _async_return(reply))

    verified, status = _run([_element()], [EvidenceItem("resume", "I led a team.")])
    assert verified == {}


def test_evidence_id_that_is_the_full_bracketed_line_is_rejected(monkeypatch):
    # The exact failure mode observed live: the model echoes back the whole
    # "[id] text" line instead of the bare id -- must not resolve to anything.
    reply = json.dumps(
        {
            "matches": [
                {
                    "unit_code": "U1",
                    "element_number": "1",
                    "evidence_id": "[E1] I led a team of 5 engineers.",
                    "quote": "led a team of 5",
                }
            ]
        }
    )
    monkeypatch.setattr(text_evidence, "chat", lambda messages, temperature=None: _async_return(reply))

    verified, status = _run([_element()], [EvidenceItem("resume", "I led a team of 5 engineers.")])
    assert verified == {}
    assert status == "ok"


def test_chat_service_unavailable_degrades_gracefully(monkeypatch):
    async def fake_chat(messages, temperature=None):
        raise ChatServiceUnavailable("down")

    monkeypatch.setattr(text_evidence, "chat", fake_chat)
    verified, status = _run([_element()], [EvidenceItem("resume", "some text")])
    assert verified == {}
    assert status == "unavailable"


def test_malformed_json_reply_is_degraded(monkeypatch):
    monkeypatch.setattr(text_evidence, "chat", lambda messages, temperature=None: _async_return("not json at all"))
    verified, status = _run([_element()], [EvidenceItem("resume", "some text")])
    assert verified == {}
    assert status == "degraded"


def test_reply_missing_matches_key_is_degraded(monkeypatch):
    monkeypatch.setattr(
        text_evidence, "chat", lambda messages, temperature=None: _async_return(json.dumps({"other": []}))
    )
    verified, status = _run([_element()], [EvidenceItem("resume", "some text")])
    assert verified == {}
    assert status == "degraded"


def test_multiple_elements_and_evidence_items_all_verified(monkeypatch):
    reply = json.dumps(
        {
            "matches": [
                {"unit_code": "U1", "element_number": "1", "evidence_id": "E1", "quote": "built a REST API"},
                {"unit_code": "U1", "element_number": "2", "evidence_id": "E2", "quote": "ran a workshop"},
            ]
        }
    )
    monkeypatch.setattr(text_evidence, "chat", lambda messages, temperature=None: _async_return(reply))

    verified, status = _run(
        [_element(number="1"), _element(number="2", title="Element two")],
        [EvidenceItem("resume", "I built a REST API for the team."), EvidenceItem("activity:9", "I ran a workshop on Git.")],
    )
    assert verified == {("U1", "1"): "resume", ("U1", "2"): "activity:9"}
    assert status == "ok"


def test_first_verified_evidence_item_wins_when_two_both_support_one_element(monkeypatch):
    # Both E1 and E2 verifiably support the same element -- attribution
    # doesn't change whether it counts as matched, only which source it's
    # credited to, and that's the first one the model returned.
    reply = json.dumps(
        {
            "matches": [
                {"unit_code": "U1", "element_number": "1", "evidence_id": "E1", "quote": "built a REST API"},
                {"unit_code": "U1", "element_number": "1", "evidence_id": "E2", "quote": "built a REST API"},
            ]
        }
    )
    monkeypatch.setattr(text_evidence, "chat", lambda messages, temperature=None: _async_return(reply))

    verified, status = _run(
        [_element()],
        [
            EvidenceItem("resume", "I built a REST API for the team."),
            EvidenceItem("activity:9", "Also: built a REST API for a class project."),
        ],
    )
    assert verified == {("U1", "1"): "resume"}
    assert status == "ok"


def test_elements_beyond_the_per_call_cap_are_not_sent_to_the_model(monkeypatch):
    sent_prompt = None

    async def fake_chat(messages, temperature=None):
        nonlocal sent_prompt
        sent_prompt = messages[1]["content"]
        return "{}"

    monkeypatch.setattr(text_evidence, "chat", fake_chat)

    elements = [_element(number=str(i), title=f"Element {i}") for i in range(MAX_ELEMENTS_PER_CALL + 5)]
    _run(elements, [EvidenceItem("resume", "some text")])

    assert f"Element {MAX_ELEMENTS_PER_CALL - 1}" in sent_prompt
    assert f"Element {MAX_ELEMENTS_PER_CALL}" not in sent_prompt


async def _async_return(value):
    return value
