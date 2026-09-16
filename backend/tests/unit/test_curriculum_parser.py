from app.ingestion.curriculum_parser import _extract_fields_from_block, parse_curriculum_courses
from app.ingestion.pdf_extract import ExtractedPdf, PageText

SIMPLE_CARD = """FAC103 - Programming Concept
Component Description
Course Code
FAC103
Course Name
Programming Concept
Semester
1
Credits
3
Course Type
Faculty Compulsory
Concentration
All
Course Description
This course introduces algorithmic thinking, basic programming constructs.
Related PLO
PLO-1, PLO-2, PLO-3
Course Objective / CPMK
Students are able to analyze simple problems and implement programs.
"""

# Regression fixture: a concentration-track card whose "Course Type" value
# ("Concentration Bootcamp") textually collides with the *label* "Concentration"
# that immediately follows it -- this once caused the real "Concentration"
# label to be matched inside the Course Type value instead of on its own line.
COLLISION_CARD = """DSB501 - Fundamental of Data Science for Business Analytics
Component
Description
Course Code
DSB501
Course Name
Fundamental of Data Science for Business Analytics
Semester
5
Credits
3
Course Type
Concentration Bootcamp
Concentration
Data Science for Business Analytics
Course Description
This course introduces data science concepts and workflows.
Related PLO
PLO-1, PLO-3, PLO-4
Course Objective / CPMK
Students are able to apply data science techniques to business problems.
"""


def test_extract_fields_from_block_basic():
    fields = _extract_fields_from_block(SIMPLE_CARD)
    assert fields["Course Code"] == "FAC103"
    assert fields["Course Name"] == "Programming Concept"
    assert fields["Semester"] == "1"
    assert fields["Credits"] == "3"
    assert fields["Course Type"] == "Faculty Compulsory"
    assert fields["Concentration"] == "All"
    assert "algorithmic thinking" in fields["Course Description"]
    assert fields["Related PLO"] == "PLO-1, PLO-2, PLO-3"


def test_extract_fields_from_block_does_not_confuse_value_with_label():
    fields = _extract_fields_from_block(COLLISION_CARD)
    assert fields["Course Type"] == "Concentration Bootcamp"
    assert fields["Concentration"] == "Data Science for Business Analytics"
    assert "9" not in fields["Concentration"]  # no stray page-footer digits


def test_extract_fields_from_block_missing_label_is_empty_not_crash():
    card_without_credits = SIMPLE_CARD.replace("Credits\n3\n", "")
    fields = _extract_fields_from_block(card_without_credits)
    assert fields["Credits"] == ""
    assert fields["Course Code"] == "FAC103"  # other fields still resolve


def _extracted_pdf(text: str, page_number: int = 1) -> ExtractedPdf:
    return ExtractedPdf(path=None, pages=[PageText(page_number=page_number, text=text)])


def test_parse_curriculum_courses_end_to_end():
    extracted = _extracted_pdf(SIMPLE_CARD + COLLISION_CARD)
    courses, skipped = parse_curriculum_courses(extracted)
    assert skipped == 0
    assert {c.course_code for c in courses} == {"FAC103", "DSB501"}
    dsb = next(c for c in courses if c.course_code == "DSB501")
    assert dsb.concentration_track == "Data Science for Business Analytics"
    assert dsb.course_type == "Concentration Bootcamp"
    assert dsb.semester == 5
    assert dsb.credits == 3


def test_parse_curriculum_courses_skips_non_course_header_matches():
    noise = "AB1234 - Not actually a course, just a header-shaped line with no fields.\n"
    extracted = _extracted_pdf(noise + SIMPLE_CARD)
    courses, skipped = parse_curriculum_courses(extracted)
    assert skipped == 1
    assert len(courses) == 1
