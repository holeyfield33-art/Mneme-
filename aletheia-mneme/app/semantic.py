"""
Semantic search via Qdrant + OpenAI embeddings.
"""
from typing import List, Optional
from uuid import UUID

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from app.config import get_settings

settings = get_settings()

_qdrant: Optional[QdrantClient] = None
_openai: Optional[OpenAI] = None


def get_qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    return _qdrant


def get_openai() -> OpenAI:
    global _openai
    if _openai is None:
        _openai = OpenAI(api_key=settings.openai_api_key)
    return _openai


def ensure_collection() -> None:
    """Create the Qdrant collection if it does not already exist."""
    client = get_qdrant()
    existing = {c.name for c in client.get_collections().collections}
    if settings.qdrant_collection not in existing:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=settings.embedding_dimension,
                distance=Distance.COSINE,
            ),
        )


def embed(text: str) -> List[float]:
    """Return the embedding vector for *text*."""
    response = get_openai().embeddings.create(
        input=text,
        model=settings.embedding_model,
    )
    return response.data[0].embedding


def upsert_memory(memory_id: UUID, content: str, payload: dict) -> None:
    """Store or update a memory vector in Qdrant."""
    ensure_collection()
    vector = embed(content)
    get_qdrant().upsert(
        collection_name=settings.qdrant_collection,
        points=[
            PointStruct(
                id=str(memory_id),
                vector=vector,
                payload=payload,
            )
        ],
    )


def search_memories(query: str, agent_id: UUID, limit: int = 10) -> List[dict]:
    """
    Semantic search for memories belonging to *agent_id*.

    Returns a list of dicts with keys: ``id``, ``score``, ``payload``.
    """
    ensure_collection()
    vector = embed(query)
    results = get_qdrant().search(
        collection_name=settings.qdrant_collection,
        query_vector=vector,
        limit=limit,
        query_filter={
            "must": [{"key": "agent_id", "match": {"value": str(agent_id)}}]
        },
    )
    return [
        {"id": hit.id, "score": hit.score, "payload": hit.payload}
        for hit in results
    ]


def delete_memory_vector(memory_id: UUID) -> None:
    """Remove a memory vector from Qdrant."""
    get_qdrant().delete(
        collection_name=settings.qdrant_collection,
        points_selector=[str(memory_id)],
    )
