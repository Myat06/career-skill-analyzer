"""Combines semantic + lexical search via RRF, then applies named ranking
adjustments -- the same three-stage pipeline as knowledge-base's
retrieval.py + ranking.py, generalized over a pgvector-backed collection
(app/vectorstore.py) instead of a single Postgres table.

NOT CURRENTLY CALLED -- deliberately, not by oversight. Both live query paths
(app/scoring/gap_engine.py: resolve_job_target, _recommend_courses_for_unit)
call semantic_search directly, because today's corpus is ~254 chunks from two
curated PDFs, where the lexical leg adds little. This is kept for the planned
PUIS integration: once the corpus grows into a large heterogeneous set, BM25
starts to matter, since exact SKKNI unit codes ("K.62AIN00.011.2") and course
codes ("FAC101") are precisely what pure vector search handles worst. Please
don't delete it as dead code.

BEFORE WIRING IT IN, close this gap: lexical.py caches its BM25 index in
process and exposes invalidate_cache() to rebuild it after an ingestion run --
but nothing calls that function anywhere. Wired in as-is, any ingestion during
a running process would leave lexical search serving a stale index against
chunk IDs that may no longer exist. app/ingestion/index_pipeline.py is where
the call belongs.
"""

from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.lexical import lexical_search
from app.retrieval.ranking import AdjustedItem, apply_policy_adjustments
from app.retrieval.semantic import semantic_search


async def hybrid_search(
    collection,
    query: str,
    where: dict | None = None,
    required_unit_codes: set[str] | None = None,
    superseded_unit_codes: set[str] | None = None,
) -> list[AdjustedItem]:
    semantic_ranked, semantic_meta = await semantic_search(collection, query, where=where)
    lexical_ranked, lexical_meta = await lexical_search(collection, query, where=where)

    fused = reciprocal_rank_fusion(semantic_ranked, lexical_ranked)
    metadata_by_id = {**lexical_meta, **semantic_meta}
    return apply_policy_adjustments(fused, metadata_by_id, required_unit_codes, superseded_unit_codes)
