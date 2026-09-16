"""Pure, unit-testable chunking functions shared by the SKKNI and curriculum
parsers. Boundaries are semantic-first (unit/element, course section) -- the
sliding window here only applies *within* a section that exceeds
CHUNK_MAX_TOKENS, which most SKKNI/curriculum sections don't (real SKKNI
element+criteria blocks run roughly 150-200 tokens).
"""

import tiktoken

CHUNK_TARGET_TOKENS = 350  # midpoint of the commonly-recommended 200-500 token range
CHUNK_MAX_TOKENS = 500  # hard cap -- a section above this is split with overlap
CHUNK_MIN_TOKENS = 80  # below this a standalone chunk is a near-empty fragment;
# merge it with a neighbor instead of indexing it alone
CHUNK_OVERLAP_RATIO = 0.15  # 15%, within the standard 10-20% range so a fact split
# across a chunk boundary stays retrievable from either side

# Approximation of the Ollama embedding model's own tokenizer -- used only for
# sizing decisions, never fed to the model itself.
_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


def split_oversized(
    text: str, max_tokens: int = CHUNK_MAX_TOKENS, overlap_ratio: float = CHUNK_OVERLAP_RATIO
) -> list[str]:
    tokens = _ENCODING.encode(text)
    if len(tokens) <= max_tokens:
        return [text] if text else []

    step = max(1, int(max_tokens * (1 - overlap_ratio)))
    pieces = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        pieces.append(_ENCODING.decode(tokens[start:end]))
        if end == len(tokens):
            break
        start += step
    return pieces


def merge_small_chunks(
    chunks: list[str], min_tokens: int = CHUNK_MIN_TOKENS, joiner: str = "\n\n"
) -> list[str]:
    """Merge any chunk below min_tokens into the chunk that follows it (or the
    preceding one, if it's last), so no near-empty fragment gets indexed alone.
    """
    if not chunks:
        return []

    merged: list[str] = []
    pending: str | None = None
    for chunk in chunks:
        combined = f"{pending}{joiner}{chunk}" if pending else chunk
        if count_tokens(combined) < min_tokens:
            pending = combined
            continue
        merged.append(combined)
        pending = None

    if pending:
        if merged:
            merged[-1] = f"{merged[-1]}{joiner}{pending}"
        else:
            merged.append(pending)
    return merged


def chunk_section(text: str) -> list[str]:
    """Chunk a single semantic section (an SKKNI element block, a course row):
    pass through untouched if it already fits CHUNK_MAX_TOKENS, otherwise apply
    the token-window sliding split.
    """
    text = text.strip()
    if not text:
        return []
    return merge_small_chunks(split_oversized(text))
