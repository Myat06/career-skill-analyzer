from types import SimpleNamespace

from app.reporting.consultation import _band
from app.reporting.narrative_prompts import _parse_roadmap
from app.reporting.pdf_report import render_consultation_pdf
from app.reporting.poster import render_consultation_poster
from app.scoring.gap_engine import RecommendedCourse, UnitCoverageResult


def test_band_thresholds():
    assert _band(90) == "High"
    assert _band(75) == "High"
    assert _band(60) == "Moderate"
    assert _band(50) == "Moderate"
    assert _band(20) == "Limited evidence"


def test_parse_roadmap_keeps_well_formed_entries():
    raw = [
        {"timeframe": "1 Month", "actions": "Interview 10 customers."},
        {"timeframe": "3 Months", "actions": 42},  # non-string actions
        "not even a dict",
        {"timeframe": "6 Months"},  # missing actions
    ]
    result = _parse_roadmap(raw)
    assert result == [{"timeframe": "1 Month", "actions": "Interview 10 customers."}]


def test_parse_roadmap_non_list_input_returns_empty():
    assert _parse_roadmap("not a list") == []
    assert _parse_roadmap(None) == []


def _synthetic_data(*, with_resume: bool = True, with_narrative: bool = True, with_consultation_narrative: bool = True) -> dict:
    student = SimpleNamespace(
        full_name="Test Student",
        student_no="S9999999",
        program="Information Systems",
        cohort_year=2023,
        email="test.student@example.com",
    )
    job_role = SimpleNamespace(role_title="AI Business & Solution Planner")
    academic = {
        "gpa": 3.78,
        "completed_courses": 30,
        "total_catalog_courses": 48,
        "activity_count": 3,
    }
    resume_result = (
        {
            "overall_score": 74.0,
            "keyword_alignment_score": 60.0,
            "rubric_categories": [
                {"key": "contact_information", "label": "Contact Information", "score": 40.0, "feedback": "Add a LinkedIn URL."},
                {"key": "education", "label": "Education", "score": 90.0, "feedback": "Strong."},
            ],
            "suggestions": [{"text": "Add a LinkedIn URL.", "origin": "ai-suggested"}],
        }
        if with_resume
        else None
    )
    gap_result = {
        "match_percentage": 62.5,
        "matched_units": [UnitCoverageResult(unit_code="U1", unit_title="Unit One", coverage_fraction=0.8, status="matched")],
        "partial_units": [],
        "missing_units": [UnitCoverageResult(unit_code="U2", unit_title="Unit Two", coverage_fraction=0.1, status="missing")],
        "recommended_courses": [RecommendedCourse(course_code="C1", course_name="Course One", for_unit_code="U2", match_reason="semantic match")],
    }
    narrative = (
        {
            "strengths": [{"text": "Strong in Unit One.", "citations": ["S1"]}],
            "weaknesses": [{"text": "Gap in Unit Two.", "citations": ["S2"]}],
            "improvement_suggestions": [],
            "citations_valid": True,
            "repair_attempted": False,
        }
        if with_narrative
        else None
    )
    consultation_narrative = (
        {
            "executive_summary": "Test Student shows moderate readiness for the target role.",
            "career_roadmap": [{"timeframe": "Immediate / 2 Weeks", "actions": "Revise resume."}],
            "recommended_direction": "Business analyst pathway.",
            "coach_message": "You're building strong momentum -- keep documenting your project impact.",
        }
        if with_consultation_narrative
        else None
    )
    confidence = {"Skill Match": "Moderate"}
    if resume_result:
        confidence["Resume Quality"] = "Moderate"

    return {
        "student": student,
        "job_role": job_role,
        "academic": academic,
        "resume_result": resume_result,
        "gap_result": gap_result,
        "narrative": narrative,
        "narrative_status": "ok",
        "consultation_narrative": consultation_narrative,
        "confidence": confidence,
    }


def test_render_consultation_pdf_produces_valid_pdf_bytes():
    pdf_bytes = render_consultation_pdf(_synthetic_data())
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 500


def test_render_consultation_pdf_handles_no_resume_and_no_narrative():
    pdf_bytes = render_consultation_pdf(_synthetic_data(with_resume=False, with_narrative=False))
    assert pdf_bytes.startswith(b"%PDF")


def test_render_consultation_pdf_handles_no_consultation_narrative():
    """Covers the degraded-AI path -- executive summary/roadmap/direction/coach
    message sections must fall back to placeholder text rather than crash when
    the chat model was unreachable (consultation_narrative is None)."""
    pdf_bytes = render_consultation_pdf(_synthetic_data(with_consultation_narrative=False))
    assert pdf_bytes.startswith(b"%PDF")


def test_render_consultation_poster_handles_no_consultation_narrative():
    png_bytes = render_consultation_poster(_synthetic_data(with_consultation_narrative=False, with_narrative=False))
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_render_consultation_poster_produces_valid_png_bytes():
    png_bytes = render_consultation_poster(_synthetic_data())
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png_bytes) > 500


def test_render_consultation_poster_handles_no_resume_and_no_narrative():
    png_bytes = render_consultation_poster(_synthetic_data(with_resume=False, with_narrative=False))
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_consultation_data_is_cached_across_renderers(monkeypatch):
    """The PDF and poster endpoints each call build_consultation_data for the
    same consultation, seconds apart -- previously paying twice for the same
    three 60-90s LLM calls."""
    import asyncio

    import app.reporting.consultation as consultation

    builds = {"n": 0}

    async def fake_uncached(session, student, job_role):
        builds["n"] += 1
        return {"built": builds["n"]}

    async def fake_fingerprint(session, student, job_role):
        return "stable-fingerprint"

    monkeypatch.setattr(consultation, "_build_consultation_data_uncached", fake_uncached)
    monkeypatch.setattr(consultation, "_input_fingerprint", fake_fingerprint)
    consultation._consultation_cache.clear()

    first = asyncio.run(consultation.build_consultation_data(None, None, None))
    second = asyncio.run(consultation.build_consultation_data(None, None, None))

    assert builds["n"] == 1  # the poster reused the PDF's build
    assert first is second


def test_changed_inputs_bypass_the_consultation_cache(monkeypatch):
    """Fingerprint-keyed, not time-keyed: logging an activity or uploading a
    resume must be reflected in the very next download."""
    import asyncio

    import app.reporting.consultation as consultation

    builds = {"n": 0}
    fingerprints = iter(["before-change", "before-change", "after-change", "after-change"])

    async def fake_uncached(session, student, job_role):
        builds["n"] += 1
        return {"built": builds["n"]}

    async def fake_fingerprint(session, student, job_role):
        return next(fingerprints)

    monkeypatch.setattr(consultation, "_build_consultation_data_uncached", fake_uncached)
    monkeypatch.setattr(consultation, "_input_fingerprint", fake_fingerprint)
    consultation._consultation_cache.clear()

    asyncio.run(consultation.build_consultation_data(None, None, None))
    asyncio.run(consultation.build_consultation_data(None, None, None))

    assert builds["n"] == 2


def test_consultation_cache_is_bounded(monkeypatch):
    import asyncio

    import app.reporting.consultation as consultation

    counter = {"n": 0}

    async def fake_uncached(session, student, job_role):
        return {"x": 1}

    async def fake_fingerprint(session, student, job_role):
        counter["n"] += 1
        return f"fp-{counter['n'] // 2}"  # same key pre/post build

    monkeypatch.setattr(consultation, "_build_consultation_data_uncached", fake_uncached)
    monkeypatch.setattr(consultation, "_input_fingerprint", fake_fingerprint)
    consultation._consultation_cache.clear()

    for _ in range(consultation.CONSULTATION_CACHE_SIZE + 10):
        asyncio.run(consultation.build_consultation_data(None, None, None))

    assert len(consultation._consultation_cache) <= consultation.CONSULTATION_CACHE_SIZE


# --- roadmap / advisory-section resilience -------------------------------------
# Regression tests for the report printing "AI roadmap generation unavailable"
# over model responses that were actually usable.

def test_parse_roadmap_accepts_a_list_of_action_items():
    # The prompt asks for "1-3 concrete action items", which invites a list --
    # previously dropped outright, emptying the whole roadmap.
    from app.reporting.narrative_prompts import _parse_roadmap

    raw = [{"timeframe": "1 Month", "actions": ["Interview 10 customers", "Ship a prototype."]}]
    result = _parse_roadmap(raw)
    assert result == [{"timeframe": "1 Month", "actions": "Interview 10 customers. Ship a prototype."}]


def test_parse_roadmap_recovers_a_missing_timeframe_from_position():
    from app.reporting.narrative_prompts import ROADMAP_TIMEFRAMES, _parse_roadmap

    raw = [{"actions": "Do the first thing."}, {"actions": "Do the second thing."}]
    result = _parse_roadmap(raw)
    assert [r["timeframe"] for r in result] == ROADMAP_TIMEFRAMES[:2]


def test_parse_roadmap_drops_junk_scalar_actions():
    from app.reporting.narrative_prompts import _parse_roadmap

    # A bare number is never a real action item -- unlike a citation ID, it
    # must be dropped rather than coerced into "42." in a student's roadmap.
    assert _parse_roadmap([{"timeframe": "1 Month", "actions": 42}]) == []


def test_parse_roadmap_ignores_junk_inside_an_action_list():
    from app.reporting.narrative_prompts import _parse_roadmap

    result = _parse_roadmap([{"timeframe": "1 Month", "actions": ["Real action.", 42, None]}])
    assert result == [{"timeframe": "1 Month", "actions": "Real action."}]


def _run_consultation_narrative(monkeypatch, responses):
    import asyncio

    import app.reporting.narrative_prompts as np

    queue = list(responses)

    async def fake_chat(messages):
        return queue.pop(0)

    monkeypatch.setattr(np, "chat", fake_chat)
    return asyncio.run(np.generate_consultation_narrative("evidence")), queue


def test_missing_executive_summary_no_longer_discards_the_roadmap(monkeypatch):
    # The original failure: one malformed field returned None for the whole
    # response, so a perfectly good roadmap/coach message was thrown away and
    # the report printed "AI roadmap generation unavailable".
    import json

    body = json.dumps(
        {
            "career_roadmap": [{"timeframe": "1 Month", "actions": "Do the thing."}],
            "coach_message": "You are doing well.",
            "recommended_direction": "Data engineering.",
        }
    )
    result, _ = _run_consultation_narrative(monkeypatch, [body])
    assert result is not None
    assert len(result["career_roadmap"]) == 1
    assert result["coach_message"] == "You are doing well."
    assert result["executive_summary"] == ""


def test_unparseable_json_is_retried_once(monkeypatch):
    import json

    good = json.dumps({"executive_summary": "Solid progress.", "career_roadmap": []})
    result, remaining = _run_consultation_narrative(monkeypatch, ["not json at all", good])
    assert result is not None
    assert result["executive_summary"] == "Solid progress."
    assert remaining == []  # both responses consumed: the retry happened


def test_two_unparseable_responses_give_up(monkeypatch):
    result, _ = _run_consultation_narrative(monkeypatch, ["nope", "still nope"])
    assert result is None


def test_response_with_nothing_usable_is_treated_as_failure(monkeypatch):
    import json

    result, _ = _run_consultation_narrative(monkeypatch, [json.dumps({"unrelated_key": "x"})])
    assert result is None
