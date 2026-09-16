from app.ingestion.chunking import (
    CHUNK_MAX_TOKENS,
    CHUNK_MIN_TOKENS,
    chunk_section,
    count_tokens,
    merge_small_chunks,
    split_oversized,
)


def test_chunk_section_passes_through_small_text():
    text = "This is a short SKKNI element description."
    result = chunk_section(text)
    assert result == [text]


def test_chunk_section_empty_returns_no_chunks():
    assert chunk_section("") == []
    assert chunk_section("   \n  ") == []


def test_split_oversized_respects_max_tokens():
    text = "word " * 2000  # far larger than CHUNK_MAX_TOKENS
    pieces = split_oversized(text)
    assert len(pieces) > 1
    for piece in pieces:
        assert count_tokens(piece) <= CHUNK_MAX_TOKENS


def test_split_oversized_produces_overlap():
    text = " ".join(f"word{i}" for i in range(2000))
    pieces = split_oversized(text)
    # consecutive pieces should share some trailing/leading words (overlap)
    first_tail = pieces[0].split()[-10:]
    second_head = pieces[1].split()[:50]
    assert any(word in second_head for word in first_tail)


def test_split_oversized_under_cap_returns_single_piece():
    text = "short text well under the token cap"
    assert split_oversized(text) == [text]


def test_merge_small_chunks_merges_fragment_forward():
    chunks = ["tiny", "a longer chunk of text that clears the minimum token threshold on its own"]
    merged = merge_small_chunks(chunks, min_tokens=5)
    assert len(merged) == 1
    assert "tiny" in merged[0]


def test_merge_small_chunks_merges_trailing_fragment_backward():
    chunks = ["a longer chunk of text that clears the minimum token threshold on its own", "tiny"]
    merged = merge_small_chunks(chunks, min_tokens=5)
    assert len(merged) == 1
    assert merged[0].endswith("tiny")


def test_merge_small_chunks_leaves_adequate_chunks_alone():
    big = "word " * 200
    chunks = [big, big]
    merged = merge_small_chunks(chunks, min_tokens=CHUNK_MIN_TOKENS)
    assert len(merged) == 2


def test_merge_small_chunks_empty_input():
    assert merge_small_chunks([]) == []
