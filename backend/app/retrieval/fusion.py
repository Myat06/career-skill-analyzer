"""Reciprocal Rank Fusion over dependency-free ranked items -- a direct
reimplementation of knowledge-base's retrieval.py::reciprocal_rank_fusion,
generalized to not require a live DB/Chroma record so it's trivially
unit-testable with synthetic lists.
"""

from dataclasses import dataclass

RRF_K = 60  # standard TREC-style constant; matches knowledge-base's own default


@dataclass
class RankedItem:
    item_id: str
    rank: int
    score: float
    match_reason: str


@dataclass
class FusedItem:
    item_id: str
    rank: int
    score: float
    match_reason: str


def reciprocal_rank_fusion(*ranked_lists: list[RankedItem]) -> list[FusedItem]:
    """score(id) = sum(1 / (k + rank_in_each_list)), summed across every list
    it appears in."""
    scores: dict[str, float] = {}
    reasons: dict[str, set[str]] = {}

    for ranked_list in ranked_lists:
        for item in ranked_list:
            scores[item.item_id] = scores.get(item.item_id, 0.0) + 1.0 / (RRF_K + item.rank)
            reasons.setdefault(item.item_id, set()).add(item.match_reason)

    fused = [
        FusedItem(item_id=item_id, rank=0, score=score, match_reason=" + ".join(sorted(reasons[item_id])))
        for item_id, score in scores.items()
    ]
    fused.sort(key=lambda f: f.score, reverse=True)
    for i, item in enumerate(fused):
        item.rank = i + 1
    return fused
