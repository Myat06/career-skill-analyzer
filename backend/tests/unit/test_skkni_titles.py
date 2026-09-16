from app.scoring.skkni_titles import ELEMENT_TITLES_EN, UNIT_TITLES_EN, english_element_title, english_unit_title


def test_known_unit_code_returns_the_translation():
    assert english_unit_title("K.62AIN00.001.2", "fallback text") == (
        "Determining Business Objectives for Artificial Intelligence Solutions"
    )


def test_unknown_unit_code_falls_back_to_the_parsed_text():
    assert english_unit_title("K.NOT.A.REAL.UNIT", "teks bahasa indonesia") == "teks bahasa indonesia"


def test_known_element_returns_the_translation():
    assert english_element_title("K.62AIN00.001.2", "1", "fallback text") == (
        "Identifying the business problems and objectives of the AI project"
    )


def test_unknown_element_falls_back_to_the_parsed_text():
    assert english_element_title("K.62AIN00.001.2", "99", "teks asli") == "teks asli"
    assert english_element_title("K.NOT.A.REAL.UNIT", "1", "teks asli") == "teks asli"


def test_all_27_units_have_a_translation():
    assert len(UNIT_TITLES_EN) == 27


def test_no_translation_is_blank():
    assert all(title.strip() for title in UNIT_TITLES_EN.values())
    assert all(title.strip() for title in ELEMENT_TITLES_EN.values())


def test_every_element_key_belongs_to_a_known_unit():
    # Catches a typo'd unit_code in ELEMENT_TITLES_EN that would silently
    # never match anything real (english_element_title would just always
    # fall back for that unit, same as an unknown unit entirely).
    unknown_units = sorted({unit_code for unit_code, _ in ELEMENT_TITLES_EN if unit_code not in UNIT_TITLES_EN})
    assert not unknown_units
