from app.scoring.gap_engine import (
    SUPPORTING_COURSE_COVERAGE_FLOOR,
    UnitElement,
    compute_unit_coverage,
    course_unit_status,
)

# --- course_unit_status: deterministic lookup against the curated mapping ---
# (real CSV, no monkeypatching -- see data/seed/skkni_curriculum_mapping.csv)


def test_completed_primary_course_is_matched():
    assert course_unit_status("K.62AIN00.001.2", {"ISC101"}) == "matched"


def test_completed_supporting_only_course_is_partial():
    # K.62AIN00.001.2's Primary course is ISC101; FAC201 is only Supporting.
    assert course_unit_status("K.62AIN00.001.2", {"FAC201"}) == "partial"


def test_no_completed_mapped_course_is_missing():
    assert course_unit_status("K.62AIN00.001.2", {"UNRELATED101"}) == "missing"


def test_primary_outranks_supporting_when_both_completed():
    assert course_unit_status("K.62AIN00.001.2", {"ISC101", "FAC201"}) == "matched"


# --- compute_unit_coverage: combines course_status with verified text labels.
# verified_text_labels maps (unit_code, element_number) -> a human-readable
# description of the evidence that verified it (see gap_engine.py's
# _gather_text_evidence and text_evidence.py's match_text_evidence).


def _elements(*pairs: tuple[str, str]) -> list[UnitElement]:
    return [UnitElement(number, title) for number, title in pairs]


def test_matched_course_covers_every_element_with_no_text_evidence_needed():
    elements = _elements(("1", "Element one"), ("2", "Element two"))
    result = compute_unit_coverage("U1", "Unit One", elements, "matched", {})
    assert result.status == "matched"
    assert result.coverage_fraction == 1.0
    assert result.matched_elements == ["Element one", "Element two"]
    assert result.unmatched_elements == []
    assert result.matched_element_sources == {}


def test_missing_course_status_falls_through_to_text_evidence():
    elements = _elements(("1", "Element one"), ("2", "Element two"))
    verified = {("U1", "1"): "your resume"}
    result = compute_unit_coverage("U1", "Unit One", elements, "missing", verified)
    assert result.status == "partial"
    assert result.coverage_fraction == 0.5
    assert result.matched_elements == ["Element one"]
    assert result.unmatched_elements == ["Element two"]
    assert result.matched_element_sources == {"Element one": "your resume"}


def test_full_text_coverage_is_matched_even_without_a_course():
    elements = _elements(("1", "Element one"), ("2", "Element two"))
    verified = {("U1", "1"): "your resume", ("U1", "2"): 'your "RPA Hackathon" activity'}
    result = compute_unit_coverage("U1", "Unit One", elements, "missing", verified)
    assert result.status == "matched"
    assert result.coverage_fraction == 1.0
    assert result.matched_element_sources == {
        "Element one": "your resume",
        "Element two": 'your "RPA Hackathon" activity',
    }


def test_no_text_evidence_and_no_course_is_missing():
    elements = _elements(("1", "Element one"))
    result = compute_unit_coverage("U1", "Unit One", elements, "missing", {})
    assert result.status == "missing"
    assert result.coverage_fraction == 0.0
    assert result.matched_elements == []
    assert result.matched_element_sources == {}


def test_no_elements_at_all_is_missing_regardless_of_course_status():
    # course_status can never be "matched" with zero elements in practice (a
    # unit with no elements can't be in the curated mapping either), but the
    # guard against dividing by zero must still hold.
    result = compute_unit_coverage("U1", "Unit One", [], "partial", {})
    assert result.status == "missing"
    assert result.coverage_fraction == 0.0


def test_supporting_course_guarantees_a_coverage_floor_with_no_text_evidence():
    elements = _elements(("1", "Element one"), ("2", "Element two"))
    result = compute_unit_coverage("U1", "Unit One", elements, "partial", {})
    assert result.status == "partial"
    assert result.coverage_fraction == SUPPORTING_COURSE_COVERAGE_FLOOR
    assert result.matched_elements == []
    assert result.unmatched_elements == ["Element one", "Element two"]
    assert result.matched_element_sources == {}


def test_supporting_course_floor_never_lowers_stronger_text_coverage():
    elements = _elements(("1", "Element one"), ("2", "Element two"))
    verified = {("U1", "1"): "your resume", ("U1", "2"): "your resume"}  # 100% from text alone
    result = compute_unit_coverage("U1", "Unit One", elements, "partial", verified)
    assert result.status == "matched"
    assert result.coverage_fraction == 1.0


def test_matched_element_sources_only_lists_verified_elements_not_unmatched_ones():
    elements = _elements(("1", "Element one"), ("2", "Element two"), ("3", "Element three"))
    verified = {("U1", "2"): "your resume"}
    result = compute_unit_coverage("U1", "Unit One", elements, "missing", verified)
    assert set(result.matched_element_sources.keys()) == {"Element two"}
    assert "Element one" not in result.matched_element_sources
    assert "Element three" not in result.matched_element_sources
