from app.retrieval.fusion import RRF_K, RankedItem, reciprocal_rank_fusion


def test_fusion_boosts_items_appearing_in_both_lists():
    semantic = [RankedItem("a", 1, 0.9, "semantic"), RankedItem("b", 2, 0.8, "semantic")]
    lexical = [RankedItem("b", 1, 5.0, "lexical"), RankedItem("c", 2, 3.0, "lexical")]

    fused = reciprocal_rank_fusion(semantic, lexical)
    fused_by_id = {f.item_id: f for f in fused}

    assert fused[0].item_id == "b"  # appears in both lists -> highest fused score
    assert fused_by_id["b"].score == 1 / (RRF_K + 2) + 1 / (RRF_K + 1)
    assert "semantic" in fused_by_id["b"].match_reason
    assert "lexical" in fused_by_id["b"].match_reason


def test_fusion_assigns_sequential_ranks():
    semantic = [RankedItem("a", 1, 0.9, "semantic")]
    lexical = [RankedItem("b", 1, 5.0, "lexical")]
    fused = reciprocal_rank_fusion(semantic, lexical)
    assert [f.rank for f in fused] == [1, 2]


def test_fusion_empty_lists():
    assert reciprocal_rank_fusion([], []) == []


def test_fusion_single_list_preserves_order():
    ranked = [RankedItem("a", 1, 0.9, "semantic"), RankedItem("b", 2, 0.5, "semantic")]
    fused = reciprocal_rank_fusion(ranked)
    assert [f.item_id for f in fused] == ["a", "b"]
