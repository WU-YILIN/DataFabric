from typing import Any, Dict, List
from src.utils.logger import get_logger

logger = get_logger(__name__)

def reciprocal_rank_fusion(
    search_results_list: List[List[Dict[str, Any]]], 
    k: int = 60
) -> List[Dict[str, Any]]:
    """
    RRF algorithm to merge multiple ranked lists.
    Each item in search_results_list must be a list of dicts with an 'id' key.
    """
    fused_scores = {}
    
    for results in search_results_list:
        for rank, item in enumerate(results):
            item_id = item["id"]
            score = 1.0 / (k + rank + 1)
            if item_id not in fused_scores:
                fused_scores[item_id] = {"score": 0.0, "item": item}
            fused_scores[item_id]["score"] += score
            
    # Sort by score descending
    sorted_results = sorted(
        fused_scores.values(), 
        key=lambda x: x["score"], 
        reverse=True
    )
    
    return [res["item"] for res in sorted_results]


class SearchEngine:
    def __init__(self, vector_store):
        self.vector_store = vector_store

    async def hybrid_search(self, query_text: str, query_vector: List[float], limit: int = 10):
        # 1. Get Vector Results
        vector_list = []
        if query_vector:
            vector_results = await self.vector_store.search_similar(query_vector, limit=limit * 5)
            vector_list = [
                {"id": r.id, "score": r.score, "payload": r.payload, "source": "vector"}
                for r in vector_results
            ]
        
        # 2. Get Keyword Results
        keyword_results = await self.vector_store.keyword_search(query_text, limit=limit * 5)
        keyword_list = [
            {"id": r.id, "score": 0.0, "payload": r.payload, "source": "keyword"} 
            for r in keyword_results
        ]
        
        # 3. Fuse
        fused_results = reciprocal_rank_fusion([vector_list, keyword_list])
        
        return fused_results[:limit]
