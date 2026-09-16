from app.scoring.gap_engine import UnitCoverageResult
from app.scoring.narrative import _build_evidence, _extract_points, cited_ids, partition_by_support


def _point(text: str, citations: list[str] | None = None) -> dict:
    return {"text": text, "citations": citations or []}


def test_cited_ids_reads_the_structured_citations_array():
    # The regression this whole check exists for: the JSON schema asks the
    # model to put citations in the array, NOT inline in the prose, so a
    # prose-only scan saw zero citations and passed everything trivially.
    assert cited_ids(_point("Strong in data analysis.", ["S1", "S2"])) == {"S1", "S2"}


def test_cited_ids_reads_inline_markers_too():
    assert cited_ids(_point("Strong in [S1] and [S2].")) == {"S1", "S2"}


def test_cited_ids_normalizes_model_id_variants():
    # Local models return "1"/"s1"/"[S1]"/" S1 " interchangeably despite the
    # prompt asking for "S1" -- all mean the same evidence item.
    assert cited_ids(_point("A", ["1", "s2", "[S3]", " S4 "])) == {"S1", "S2", "S3", "S4"}


def test_cited_ids_ignores_unparseable_citations():
    assert cited_ids(_point("A", ["BOGUS", ""])) == set()


def test_partition_accepts_a_fully_supported_claim():
    supported, unsupported = partition_by_support([_point("A", ["S1"])], {"S1", "S2"})
    assert len(supported) == 1 and unsupported == []


def test_partition_rejects_an_invented_evidence_id():
    supported, unsupported = partition_by_support([_point("A", ["S99"])], {"S1"})
    assert supported == [] and len(unsupported) == 1


def test_partition_rejects_an_uncited_claim():
    # An uncited claim about a student's competency is exactly as ungrounded
    # as one citing an invented ID -- neither may be rendered as analysis.
    supported, unsupported = partition_by_support([_point("Strong in AI.")], {"S1"})
    assert supported == [] and len(unsupported) == 1


def test_partition_rejects_a_claim_mixing_real_and_invented_ids():
    supported, unsupported = partition_by_support([_point("A", ["S1", "S99"])], {"S1"})
    assert supported == [] and len(unsupported) == 1


def test_build_evidence_assigns_sequential_ids_within_limit():
    matched = [UnitCoverageResult(f"U{i}", f"Unit {i}", status="matched", coverage_fraction=1.0) for i in range(5)]
    gaps = [UnitCoverageResult(f"G{i}", f"Gap {i}", status="missing", coverage_fraction=0.0) for i in range(5)]

    evidence_text, ids = _build_evidence(matched, gaps, [])
    assert len(ids) <= 8  # EVIDENCE_LIMIT
    assert ids == {f"S{i}" for i in range(1, len(ids) + 1)}
    assert "Unit 0" in evidence_text  # matched units represented


def test_extract_points_tolerates_plain_strings_from_the_model():
    # the model is instructed to return {"text":..., "citations":[...]} but
    # sometimes returns bare strings instead -- must not crash on this.
    parsed = {"improvement_suggestions": ["Do X better [S1]", {"text": "Do Y [S2]", "citations": ["S2"]}]}
    points = _extract_points(parsed, "improvement_suggestions")
    assert points == [
        {"text": "Do X better [S1]", "citations": []},
        {"text": "Do Y [S2]", "citations": ["S2"]},
    ]


def test_extract_points_missing_key_returns_empty_list():
    assert _extract_points({}, "strengths") == []


def test_extract_points_coerces_malformed_citations():
    # the model is instructed to return citations as a list of strings but
    # sometimes returns a bare string, a list of ints, or omits the field --
    # none of these should ever raise.
    parsed = {
        "strengths": [
            {"text": "A", "citations": "S1"},
            {"text": "B", "citations": [1, 2]},
            {"text": "C", "citations": None},
            {"text": "D"},
        ]
    }
    points = _extract_points(parsed, "strengths")
    assert points[0]["citations"] == ["S1"]
    assert points[1]["citations"] == ["1", "2"]
    assert points[2]["citations"] == []
    assert points[3]["citations"] == []
    assert all(isinstance(p["text"], str) for p in points)


def test_build_evidence_includes_recommended_courses():
    from app.scoring.gap_engine import RecommendedCourse

    gaps = [UnitCoverageResult("G1", "Gap One", status="missing", coverage_fraction=0.0)]
    courses = [RecommendedCourse("FAC101", "Course One", "G1", "semantic match")]
    evidence_text, _ = _build_evidence([], gaps, courses)
    # Course codes are intentionally omitted from evidence text -- see the note in
    # format_recommended_courses_block() -- so only the course name should appear.
    assert "Course One" in evidence_text
    assert "FAC101" not in evidence_text


def test_build_evidence_annotates_a_matched_element_with_its_source():
    matched = [
        UnitCoverageResult(
            "U1",
            "Unit One",
            status="matched",
            coverage_fraction=1.0,
            matched_elements=["Element one"],
            matched_element_sources={"Element one": 'your "RPA Hackathon" activity'},
        )
    ]
    evidence_text, _ = _build_evidence(matched, [], [])
    assert 'Element one (via your "RPA Hackathon" activity)' in evidence_text


def test_build_evidence_leaves_a_course_matched_element_unannotated():
    # No source label exists for a unit matched via a completed course (see
    # gap_engine.py's compute_unit_coverage) -- must not fabricate one.
    matched = [
        UnitCoverageResult(
            "U1", "Unit One", status="matched", coverage_fraction=1.0, matched_elements=["Element one"]
        )
    ]
    evidence_text, _ = _build_evidence(matched, [], [])
    assert "matched elements: Element one," in evidence_text
    assert "(via" not in evidence_text
