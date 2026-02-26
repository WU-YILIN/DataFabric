from src.domain.search.engine import reciprocal_rank_fusion

def test_rrf_basic():
    list1 = [{"id": "A"}, {"id": "B"}, {"id": "C"}]
    list2 = [{"id": "B"}, {"id": "A"}, {"id": "D"}]
    
    # B is 2nd in list1 (rank 1) and 1st in list2 (rank 0)
    # A is 1st in list1 (rank 0) and 2nd in list2 (rank 1)
    
    results = reciprocal_rank_fusion([list1, list2], k=60)
    
    # B and A should be top (they have same total reciprocal rank score here)
    top_ids = [item["id"] for item in results[:2]]
    assert "A" in top_ids
    assert "B" in top_ids
    assert results[0]["id"] in ["A", "B"]
