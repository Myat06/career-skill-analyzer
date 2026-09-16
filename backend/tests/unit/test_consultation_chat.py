import pytest

import app.scoring.consultation_chat as consultation_chat
from app.scoring.consultation_chat import (
    EMPTY_PROFILE_NOTICE,
    ROADMAP_LINKS,
    ChatServiceUnavailable,
    build_context,
    run_consultation_chat,
)


def _empty_context() -> str:
    return build_context(
        skill_gap=None,
        resume_score=None,
        activities=[],
        remaining_courses=[],
    )


def test_build_context_includes_roadmap_reference_links():
    context = _empty_context()
    for title, url in ROADMAP_LINKS.items():
        assert title in context
        assert url in context


def test_roadmap_links_are_all_real_roadmap_sh_urls():
    # Guards against a typo'd/hallucinated slug creeping back in -- every
    # entry must point at roadmap.sh, nothing else.
    for url in ROADMAP_LINKS.values():
        assert url.startswith("https://roadmap.sh/")


def test_empty_context_states_nothing_is_computed_yet():
    context = _empty_context()
    assert "No skill-gap analysis run yet" in context
    assert "No resume uploaded yet" in context
    assert "No activities logged yet" in context


def test_stale_skill_gap_carries_a_do_not_present_as_current_note():
    context = build_context(
        skill_gap={
            "job_role": {"role_title": "Backend Developer"},
            "match_percentage": 55.0,
            "matched_units": [],
            "partial_units": [],
            "missing_units": [],
            "recommended_courses": [],
            "stale": True,
        },
        resume_score=None,
        activities=[],
        remaining_courses=[],
    )
    assert "STALE" in context
    assert "do not present these numbers as the student's current standing" in context


def test_fresh_skill_gap_has_no_stale_note():
    context = build_context(
        skill_gap={
            "job_role": {"role_title": "Backend Developer"},
            "match_percentage": 55.0,
            "matched_units": [],
            "partial_units": [],
            "missing_units": [],
            "recommended_courses": [],
            "stale": False,
        },
        resume_score=None,
        activities=[],
        remaining_courses=[],
    )
    assert "STALE" not in context


def test_name_mismatch_note_triggers_priority_instruction():
    context = build_context(
        skill_gap=None,
        resume_score={
            "overall_score": 45.0,
            "keyword_alignment_score": 30.0,
            "rubric_categories": [],
            "scored_for_current_role": True,
            "note": "The name on this document ('MYAT MIN THU') doesn't match your registered name ('Ahmad Fauzan') -- double check this is your own resume.",
        },
        activities=[],
        remaining_courses=[],
    )
    assert "PRIORITY" in context
    assert "state this plainly as the very first thing in your answer" in context


def test_other_scoring_caveats_do_not_trigger_priority_instruction():
    context = build_context(
        skill_gap=None,
        resume_score={
            "overall_score": 45.0,
            "keyword_alignment_score": 30.0,
            "rubric_categories": [],
            "scored_for_current_role": True,
            "note": "No job target supplied -- keyword alignment score skipped.",
        },
        activities=[],
        remaining_courses=[],
    )
    assert "PRIORITY" not in context


def test_resume_present_tells_model_not_to_ask_for_one():
    context = build_context(
        skill_gap=None,
        resume_score={
            "overall_score": 80.0,
            "keyword_alignment_score": 50.0,
            "rubric_categories": [],
            "scored_for_current_role": True,
            "note": None,
        },
        activities=[],
        remaining_courses=[],
    )
    assert "A resume IS on file. Do NOT ask the student to upload one" in context


def test_remaining_courses_truncated_with_overflow_note():
    courses = [
        {"semester": i, "course_code": f"C{i:03d}", "course_name": f"Course {i}", "credits": 3, "concentration_track": None}
        for i in range(1, 20)
    ]
    context = build_context( skill_gap=None, resume_score=None, activities=[], remaining_courses=courses
    )
    assert "19 total" in context
    assert "…and 4 more further out" in context
    # Course codes are intentionally omitted from the prompt context -- see the
    # note in build_context() -- so only course names should appear.
    assert "Semester 1: Course 1 (3 cr)" in context
    assert "Semester 15: Course 15 (3 cr)" in context
    assert "Course 16" not in context
    assert "C001" not in context


def test_activities_list_shows_only_the_most_recent_eight():
    activities = [{"type": "project", "title": f"Activity {i}", "description": "desc"} for i in range(10)]
    context = build_context( skill_gap=None, resume_score=None, activities=activities, remaining_courses=[]
    )
    assert "10 logged activities" in context
    assert "Activity 9" in context
    assert "Activity 1" not in context  # only the last 8 (indices 2-9) are listed
    assert "Activity 0" not in context


@pytest.mark.asyncio
async def test_run_consultation_chat_happy_path(monkeypatch):
    seen_messages = None

    async def fake_chat(messages):
        nonlocal seen_messages
        seen_messages = messages
        return "Here's your answer."

    monkeypatch.setattr(consultation_chat, "chat", fake_chat)

    reply, status = await run_consultation_chat(
        [{"role": "user", "content": "How am I doing?"}],
        skill_gap=None,
        resume_score=None,
        activities=[],
        remaining_courses=[],
    )

    assert reply == "Here's your answer."
    assert status == "ok"
    assert seen_messages[0]["role"] == "system"
    assert seen_messages[-1] == {"role": "user", "content": "How am I doing?"}


@pytest.mark.asyncio
async def test_run_consultation_chat_degrades_gracefully_when_unavailable(monkeypatch):
    async def fake_chat(messages):
        raise ChatServiceUnavailable("down")

    monkeypatch.setattr(consultation_chat, "chat", fake_chat)

    reply, status = await run_consultation_chat(
        [{"role": "user", "content": "How am I doing?"}],
        skill_gap=None,
        resume_score=None,
        activities=[],
        remaining_courses=[],
    )

    assert status == "unavailable"
    assert "trouble reaching" in reply


@pytest.mark.asyncio
async def test_empty_profile_notice_included_only_when_no_resume_and_no_activities(monkeypatch):
    seen = {}

    async def fake_chat(messages):
        seen["system_content"] = messages[0]["content"]
        return "ok"

    monkeypatch.setattr(consultation_chat, "chat", fake_chat)

    await run_consultation_chat(
        [{"role": "user", "content": "hi"}],
        skill_gap=None,
        resume_score=None,
        activities=[],
        remaining_courses=[],
    )
    assert EMPTY_PROFILE_NOTICE.strip() in seen["system_content"]

    await run_consultation_chat(
        [{"role": "user", "content": "hi"}],
        skill_gap=None,
        resume_score=None,
        activities=[{"type": "project", "title": "X", "description": "Y"}],
        remaining_courses=[],
    )
    assert EMPTY_PROFILE_NOTICE.strip() not in seen["system_content"]
