from app.retrieval.fusion import FusedItem
from app.retrieval.ranking import (
    ELEMENT_SPECIFICITY_BONUS,
    UNIT_RELEVANCE_BONUS,
    VERSION_FRESHNESS_PENALTY,
    apply_policy_adjustments,
)


def test_unit_relevance_bonus_applied_and_reasoned():
    fused = [FusedItem("chunk1", 1, 1.0, "semantic")]
    metadata = {"chunk1": {"unit_code": "K.62AIN00.001.2", "section_type": "description"}}
    results = apply_policy_adjustments(fused, metadata, required_unit_codes={"K.62AIN00.001.2"})

    assert len(results[0].adjustments) == 1
    assert results[0].adjustments[0].kind == "unit_relevance"
    assert results[0].adjustments[0].adjustment == UNIT_RELEVANCE_BONUS
    assert "required competencies" in results[0].adjustments[0].reason


def test_element_specificity_bonus_only_for_elements():
    fused = [FusedItem("chunk1", 1, 1.0, "semantic")]
    metadata = {"chunk1": {"section_type": "element"}}
    results = apply_policy_adjustments(fused, metadata)
    assert any(a.kind == "element_specificity" for a in results[0].adjustments)
    assert results[0].adjustments[0].adjustment == ELEMENT_SPECIFICITY_BONUS


def test_version_freshness_penalty_applied():
    fused = [FusedItem("chunk1", 1, 1.0, "semantic")]
    metadata = {"chunk1": {"unit_code": "K.62AIN00.001.1"}}
    results = apply_policy_adjustments(fused, metadata, superseded_unit_codes={"K.62AIN00.001.1"})
    assert results[0].adjustments[0].kind == "version_freshness"
    assert results[0].adjustments[0].adjustment == -VERSION_FRESHNESS_PENALTY


def test_no_adjustments_when_nothing_applies():
    fused = [FusedItem("chunk1", 1, 1.0, "semantic")]
    results = apply_policy_adjustments(fused, {"chunk1": {"section_type": "description"}})
    assert results[0].adjustments == []
    assert results[0].adjusted_score == 1.0  # normalized against itself as the top score


def test_score_normalized_relative_to_top_before_adjustments():
    fused = [FusedItem("a", 1, 1.0, "semantic"), FusedItem("b", 2, 0.5, "semantic")]
    results = apply_policy_adjustments(fused, {})
    by_id = {r.fused.item_id: r for r in results}
    assert by_id["a"].adjusted_score == 1.0
    assert by_id["b"].adjusted_score == 0.5


def test_results_resorted_by_adjusted_score():
    fused = [FusedItem("a", 1, 1.0, "semantic"), FusedItem("b", 2, 0.9, "semantic")]
    metadata = {"b": {"unit_code": "X", "section_type": "element"}}
    results = apply_policy_adjustments(fused, metadata, required_unit_codes={"X"})
    # b: 0.9 + 0.1 (relevance) + 0.05 (specificity) = 1.05 > a's 1.0
    assert results[0].fused.item_id == "b"


def test_empty_fused_list():
    assert apply_policy_adjustments([], {}) == []
