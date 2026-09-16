from app.ingestion.skkni_parser import (
    parse_element_criteria_fallback,
    parse_element_criteria_table,
    parse_unit_header,
)

SAMPLE_UNIT_BLOCK = """KODE UNIT :
K.62AIN00.001.2
JUDUL UNIT :
Menentukan Sasaran Bisnis Solusi Artificial Intelligence
DESKRIPSI UNIT :
Unit kompetensi ini berhubungan dengan pengetahuan, keterampilan, dan sikap kerja.
ELEMEN KOMPETENSI
KRITERIA UNJUK KERJA
BATASAN VARIABEL
1. Konteks variabel
   1.1 Unit ini berlaku untuk seseorang.
PANDUAN PENILAIAN
1. Konteks penilaian
   1.1 Dilakukan di tempat kerja.
"""


def test_parse_unit_header_extracts_code_title_description():
    result = parse_unit_header(SAMPLE_UNIT_BLOCK)
    assert result is not None
    code, title, description = result
    assert code == "K.62AIN00.001.2"
    assert "Sasaran Bisnis" in title
    assert "pengetahuan" in description


def test_parse_unit_header_returns_none_without_code():
    assert parse_unit_header("no unit code here at all") is None


def test_parse_element_criteria_table_basic():
    rows = [
        ["1. Mengidentifikasi permasalahan bisnis", "1.1 Latar belakang diidentifikasi.\n1.2 Sasaran bisnis dipilih."],
        ["2. Menyusun kriteria kesuksesan", "2.1 Elemen metrik dibuat.\n2.2 Kriteria dipilih."],
    ]
    elements = parse_element_criteria_table(rows)
    assert len(elements) == 2
    assert elements[0].number == "1"
    assert "Mengidentifikasi" in elements[0].title
    assert len(elements[0].criteria) == 2
    assert elements[0].criteria[0].number == "1.1"
    assert elements[0].criteria[0].text == "Latar belakang diidentifikasi."


def test_parse_element_criteria_table_skips_empty_rows():
    rows = [["", ""], ["1. Element one", "1.1 Criterion one."]]
    elements = parse_element_criteria_table(rows)
    assert len(elements) == 1


def test_parse_element_criteria_table_handles_wrapped_criterion_lines():
    rows = [["1. Element", "1.1 A criterion that wraps\nonto a second physical line."]]
    elements = parse_element_criteria_table(rows)
    assert len(elements[0].criteria) == 1
    assert "wraps onto a second physical line" in elements[0].criteria[0].text


def test_parse_element_criteria_fallback_extracts_elements_and_criteria():
    text = (
        "1. Mengidentifikasi permasalahan bisnis\n"
        "1.1 Latar belakang diidentifikasi.\n"
        "1.2 Sasaran bisnis dipilih.\n"
        "2. Menyusun kriteria kesuksesan\n"
        "2.1 Elemen metrik dibuat.\n"
    )
    elements = parse_element_criteria_fallback(text)
    assert len(elements) == 2
    assert len(elements[0].criteria) == 2
    assert len(elements[1].criteria) == 1


def test_parse_element_criteria_fallback_empty_text():
    assert parse_element_criteria_fallback("") == []
