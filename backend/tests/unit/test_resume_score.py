import asyncio

from app.scoring.resume_score import (
    compute_keyword_alignment_score,
    score_resume,
    _names_plausibly_match,
    _parse_rubric_categories,
)
import app.scoring.resume_score as resume_score


def test_keyword_alignment_perfect_match():
    assert compute_keyword_alignment_score([1.0, 0.0], [1.0, 0.0]) == 100.0


def test_keyword_alignment_orthogonal():
    assert compute_keyword_alignment_score([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_parse_rubric_categories_keeps_valid_entry_with_verbatim_quote():
    resume_text = "Led a team of five engineers to ship the feature on time."
    raw = [
        {
            "key": "work_experience",
            "score": 85,
            "feedback": "Strong action verb usage.",
            "quote": "Led a team of five engineers",
        }
    ]
    result = _parse_rubric_categories(raw, resume_text)
    assert len(result) == 1
    assert result[0]["key"] == "work_experience"
    assert result[0]["label"] == "Work/Internship Experience"
    assert result[0]["score"] == 85.0
    assert result[0]["quote"] == "Led a team of five engineers"


def test_parse_rubric_categories_nulls_fabricated_quote_but_keeps_score():
    resume_text = "Led a team of five engineers to ship the feature on time."
    raw = [
        {
            "key": "work_experience",
            "score": 60,
            "feedback": "Vague achievements.",
            "quote": "This quote does not appear anywhere",
        }
    ]
    result = _parse_rubric_categories(raw, resume_text)
    assert len(result) == 1
    assert result[0]["score"] == 60.0
    assert result[0]["quote"] is None


def test_parse_rubric_categories_drops_non_numeric_score():
    resume_text = "Some resume text."
    raw = [{"key": "education", "score": "high", "feedback": "n/a", "quote": ""}]
    assert _parse_rubric_categories(raw, resume_text) == []


def test_parse_rubric_categories_ignores_unrecognized_key():
    resume_text = "Some resume text."
    raw = [{"key": "not_a_real_category", "score": 50, "feedback": "n/a", "quote": ""}]
    assert _parse_rubric_categories(raw, resume_text) == []


def test_parse_rubric_categories_tolerates_malformed_model_output():
    resume_text = "Some resume text."
    raw = [
        {"key": "education", "score": 70, "feedback": "Fine.", "quote": ""},  # valid
        "not even a dict",
        {"key": "education"},  # missing score/feedback
        None,
    ]
    result = _parse_rubric_categories(raw, resume_text)
    assert len(result) == 1
    assert result[0]["key"] == "education"


def test_parse_rubric_categories_non_list_input_returns_empty():
    assert _parse_rubric_categories("not a list", "some text") == []
    assert _parse_rubric_categories(None, "some text") == []


def test_parse_rubric_categories_clamps_out_of_range_score():
    resume_text = "Some resume text."
    raw = [{"key": "personal_summary", "score": 150, "feedback": "Great.", "quote": ""}]
    result = _parse_rubric_categories(raw, resume_text)
    assert result[0]["score"] == 100.0


def test_names_plausibly_match_on_shared_token():
    assert _names_plausibly_match("Ahmad Fauzan", "Fauzan, Ahmad")
    assert _names_plausibly_match("Ahmad Fauzan", "Ahmad F.")


def test_names_plausibly_match_rejects_disjoint_names():
    assert not _names_plausibly_match("Ahmad Fauzan", "Budi Santoso")


def _run_score_resume(monkeypatch, *, is_resume, detected_name, student_full_name=None):
    async def fake_compute_rubric_score(resume_text):
        return [{"key": "education", "label": "Education", "score": 80.0, "feedback": "ok", "quote": None}], is_resume, detected_name

    monkeypatch.setattr(resume_score, "compute_rubric_score", fake_compute_rubric_score)
    return asyncio.run(score_resume("a" * 300, student_full_name=student_full_name))


def test_score_resume_warns_when_document_is_not_a_resume(monkeypatch):
    result = _run_score_resume(monkeypatch, is_resume=False, detected_name="")
    assert "doesn't look like a resume" in result["note"]


def test_score_resume_warns_on_name_mismatch(monkeypatch):
    result = _run_score_resume(monkeypatch, is_resume=True, detected_name="Budi Santoso", student_full_name="Ahmad Fauzan")
    assert "doesn't match your registered name" in result["note"]


def test_score_resume_no_warning_when_names_match(monkeypatch):
    # The fake only returns 1 of 7 categories, so a "Provisional" note is still
    # expected here (a separate, pre-existing guard) -- what must be absent is
    # any identity-mismatch text.
    result = _run_score_resume(monkeypatch, is_resume=True, detected_name="Ahmad Fauzan", student_full_name="Ahmad Fauzan")
    assert "doesn't match your registered name" not in (result["note"] or "")


def test_score_resume_no_warning_when_name_undetected(monkeypatch):
    # No name found on the document isn't evidence of a mismatch -- don't warn on it.
    result = _run_score_resume(monkeypatch, is_resume=True, detected_name="", student_full_name="Ahmad Fauzan")
    assert "doesn't match your registered name" not in (result["note"] or "")
