from typing import Any, Dict, List, Optional
from qdrant_client import QdrantClient, AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, SearchRequest
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

class QdrantAdapter:
    def __init__(self):
        self.client = AsyncQdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            grpc_port=settings.QDRANT_GRPC_PORT,
            prefer_grpc=True
        )
        self.collection_name = "events"

    async def ensure_collection(self, vector_size: int = 1536):
        collections = await self.client.get_collections()
        exists = any(c.name == self.collection_name for c in collections.collections)
        
        if not exists:
            logger.info(f"Creating Qdrant collection: {self.collection_name}")
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    async def upsert_event(self, event_id: int, vector: List[float], payload: Dict[str, Any]):
        await self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=event_id,
                    vector=vector,
                    payload=payload
                )
            ]
        )

    async def search_similar(self, vector: List[float], limit: int = 10, threshold: float = 0.7):
        results = await self.client.search(
            collection_name=self.collection_name,
            query_vector=vector,
            limit=limit,
            score_threshold=threshold,
            with_payload=True
        )
        return results

    async def keyword_search(self, query_text: str, limit: int = 10):
        # Using Qdrant's full-text search index on a payload field 'text'
        from qdrant_client.models import Filter, FieldCondition, MatchText
        
        results = await self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="description",
                        match=MatchText(text=query_text)
                    )
                ]
            ),
            limit=limit,
            with_payload=True
        )
        return results[0]  # scroll returns (points, offset)
