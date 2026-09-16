from app.scoring.skkni_mapping import mapped_courses_for_unit


def test_known_unit_resolves_primary_before_supporting():
    result = mapped_courses_for_unit("K.62AIN00.001.2")
    assert [c.course_code for c in result] == ["ISC101", "FAC201"]
    assert result[0].match_strength == "Primary"
    assert result[1].match_strength == "Supporting"


def test_gap_rows_never_produce_a_course():
    # K.62AIN00.006.2 has one Supporting course (ISC401) and one curated GAP
    # row (no course covers the rest) -- the GAP row must never surface as a
    # recommendation.
    result = mapped_courses_for_unit("K.62AIN00.006.2")
    assert [c.course_code for c in result] == ["ISC401"]


def test_unknown_unit_code_returns_empty():
    assert mapped_courses_for_unit("NOT-A-REAL-UNIT") == []


def test_not_mapped_trailer_rows_are_not_attached_to_any_unit():
    # The CSV's trailing rows (FAC101, UNV301, ...) have an empty
    # skkni_unit_code and match_strength "NOT_MAPPED" -- they describe
    # courses outside the 27 AI-specific units and must not leak into any
    # unit's course list.
    for unit_code in ("K.62AIN00.001.2", "K.62AIN00.011.2", "K.62AIN00.024.2"):
        for course in mapped_courses_for_unit(unit_code):
            assert course.match_strength in ("Primary", "Supporting")


def test_match_rationale_is_populated():
    result = mapped_courses_for_unit("K.62AIN00.001.2")
    assert all(c.match_rationale for c in result)
