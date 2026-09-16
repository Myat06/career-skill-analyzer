"""Semantic search over a pgvector-backed collection (app/vectorstore.py).
Metadata filtering happens inside the `query()` call itself via `where`,
never post-filtered in Python.
"""

from app.llm.embeddings import embed_query
from app.retrieval.fusion import RankedItem

CANDIDATE_LIMIT = 10  # matches knowledge-base's own default; corpus is small, no tuning need yet


async def search_by_embedding(
    collection, query_embedding: list[float], where: dict | None = None, top_k: int = CANDIDATE_LIMIT
) -> tuple[list[RankedItem], dict[str, dict]]:
    """Query with an embedding that has already been computed.

    Split out from semantic_search so a caller issuing several related queries
    can embed them all in one batched embed_texts() call and then run the
    (local, cheap) vector lookups, instead of paying one sequential HTTP
    round-trip to Ollama per query. Collections use cosine distance, so
    distance is 1 - cosine_similarity and `score` below is the cosine
    similarity itself -- which is what JOB_MATCH_CONFIDENCE_THRESHOLD in
    gap_engine.py is calibrated against.
    """
    result = await collection.query(query_embeddings=[query_embedding], n_results=top_k, where=where)

    ids = result["ids"][0] if result.get("ids") else []
    distances = result["distances"][0] if result.get("distances") else []
    metadatas = result["metadatas"][0] if result.get("metadatas") else []

    ranked = [
        RankedItem(item_id=item_id, rank=i + 1, score=1.0 - distance, match_reason="semantic vector similarity")
        for i, (item_id, distance) in enumerate(zip(ids, distances))
    ]
    metadata_by_id = dict(zip(ids, metadatas))
    return ranked, metadata_by_id


async def semantic_search(
    collection, query: str, where: dict | None = None, top_k: int = CANDIDATE_LIMIT
) -> tuple[list[RankedItem], dict[str, dict]]:
    return await search_by_embedding(collection, await embed_query(query), where=where, top_k=top_k)
