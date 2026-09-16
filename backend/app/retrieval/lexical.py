"""Lexical search. The pgvector-backed collections (app/vectorstore.py) have
no full-text index (unlike knowledge-base's Postgres ts_rank leg), so this
fetches a collection's full document/metadata set once via `get()`, builds
an in-process BM25 index, and caches it -- rebuilt lazily (see
invalidate_cache) after an ingestion run. The corpus here is a few hundred
chunks total, so keeping the whole set in memory is cheap; the metadata
`where` filter is applied against the cached set rather than re-querying per
call, which is a deliberate exception to "filter inside the query call" --
BM25 needs the candidate text in memory regardless, and unlike knowledge-base
these filters are relevance filters (doc_type/unit_code/course_code), not
access-control boundaries, so nothing security-relevant depends on where the
filter is applied. semantic.py's query-side `where` is the one that matters
for that concern.
"""

from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from app.retrieval.fusion import RankedItem

CANDIDATE_LIMIT = 10


@dataclass
class _Bm25Cache:
    ids: list[str]
    metadatas: list[dict]
    bm25: BM25Okapi | None


_cache: dict[str, _Bm25Cache] = {}


def invalidate_cache(collection_name: str) -> None:
    _cache.pop(collection_name, None)


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


async def _get_or_build_cache(collection) -> _Bm25Cache:
    name = collection.name
    cached = _cache.get(name)
    if cached is not None:
        return cached

    data = await collection.get(include=["documents", "metadatas"])
    ids = data["ids"]
    documents = data["documents"]
    metadatas = data["metadatas"]
    bm25 = BM25Okapi([_tokenize(doc) for doc in documents]) if documents else None
    cache = _Bm25Cache(ids=ids, metadatas=metadatas, bm25=bm25)
    _cache[name] = cache
    return cache


async def lexical_search(
    collection, query: str, where: dict | None = None, top_k: int = CANDIDATE_LIMIT
) -> tuple[list[RankedItem], dict[str, dict]]:
    cache = await _get_or_build_cache(collection)
    if cache.bm25 is None:
        return [], {}

    if where:
        eligible = [i for i, meta in enumerate(cache.metadatas) if all(meta.get(k) == v for k, v in where.items())]
    else:
        eligible = list(range(len(cache.ids)))
    if not eligible:
        return [], {}

    scores = cache.bm25.get_scores(_tokenize(query))
    ranked_indices = sorted(eligible, key=lambda i: scores[i], reverse=True)[:top_k]

    ranked = [
        RankedItem(item_id=cache.ids[i], rank=rank + 1, score=float(scores[i]), match_reason="lexical keyword match")
        for rank, i in enumerate(ranked_indices)
        if scores[i] > 0
    ]
    metadata_by_id = {cache.ids[i]: cache.metadatas[i] for i in eligible}
    return ranked, metadata_by_id
