"""Bounded, named, inspectable adjustments applied after rank fusion -- same
shape as knowledge-base's ranking.py: normalize the fused score to [0, 1]
relative to the top candidate (so a fixed-magnitude policy bump can't
dominate relevance), then add capped deltas, each carrying a human-readable
reason (the "reason ledger").
"""

from dataclasses import dataclass

from app.retrieval.fusion import FusedItem

UNIT_RELEVANCE_BONUS = 0.1  # a chunk whose unit_code is required by the target job role
ELEMENT_SPECIFICITY_BONUS = 0.05  # element-type chunks are the most specific match granularity
VERSION_FRESHNESS_PENALTY = 0.1  # an SKKNI unit version superseded by a newer one in the same collection


@dataclass
class PolicyAdjustment:
    kind: str
    adjustment: float
    reason: str


@dataclass
class AdjustedItem:
    fused: FusedItem
    adjusted_score: float
    adjustments: list[PolicyAdjustment]
    metadata: dict


def _unit_relevance_adjustment(metadata: dict, required_unit_codes: set[str]) -> PolicyAdjustment | None:
    unit_code = metadata.get("unit_code")
    if unit_code and unit_code in required_unit_codes:
        return PolicyAdjustment(
            "unit_relevance", UNIT_RELEVANCE_BONUS, "unit is part of the target job role's required competencies"
        )
    return None


def _element_specificity_adjustment(metadata: dict) -> PolicyAdjustment | None:
    if metadata.get("section_type") == "element":
        return PolicyAdjustment(
            "element_specificity",
            ELEMENT_SPECIFICITY_BONUS,
            "competency element is the most specific chunk type for skill matching",
        )
    return None


def _version_freshness_adjustment(metadata: dict, superseded_unit_codes: set[str]) -> PolicyAdjustment | None:
    unit_code = metadata.get("unit_code")
    if unit_code and unit_code in superseded_unit_codes:
        return PolicyAdjustment(
            "version_freshness",
            -VERSION_FRESHNESS_PENALTY,
            "a newer revision of this SKKNI unit exists in the index",
        )
    return None


def apply_policy_adjustments(
    fused: list[FusedItem],
    metadata_by_id: dict[str, dict],
    required_unit_codes: set[str] | None = None,
    superseded_unit_codes: set[str] | None = None,
) -> list[AdjustedItem]:
    required_unit_codes = required_unit_codes or set()
    superseded_unit_codes = superseded_unit_codes or set()
    top_score = fused[0].score if fused else 1.0

    results: list[AdjustedItem] = []
    for item in fused:
        metadata = metadata_by_id.get(item.item_id, {})
        adjustments = [
            a
            for a in (
                _unit_relevance_adjustment(metadata, required_unit_codes),
                _element_specificity_adjustment(metadata),
                _version_freshness_adjustment(metadata, superseded_unit_codes),
            )
            if a is not None
        ]
        normalized_score = item.score / top_score if top_score else 0.0
        adjusted_score = normalized_score + sum(a.adjustment for a in adjustments)
        results.append(
            AdjustedItem(fused=item, adjusted_score=adjusted_score, adjustments=adjustments, metadata=metadata)
        )

    results.sort(key=lambda r: r.adjusted_score, reverse=True)
    return results
