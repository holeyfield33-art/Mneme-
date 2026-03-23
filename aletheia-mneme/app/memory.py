"""
Memory CRUD operations (PostgreSQL + Qdrant).
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app import semantic
from app.config import get_settings
from app.crypto import hash_content, sign_content
from app.models import Memory

settings = get_settings()


def create_memory(
    db: Session,
    agent_id: UUID,
    content: str,
    tags: Optional[List[str]] = None,
) -> Memory:
    """Persist a new memory and index it for semantic search."""
    content_hash = hash_content(content)
    signature = sign_content(content, settings.secret_key)
    tags_str = ",".join(tags) if tags else None

    memory = Memory(
        agent_id=agent_id,
        content=content,
        content_hash=content_hash,
        signature=signature,
        tags=tags_str,
    )
    db.add(memory)
    db.flush()  # populate memory.id before upsert

    semantic.upsert_memory(
        memory_id=memory.id,
        content=content,
        payload={
            "agent_id": str(agent_id),
            "content_hash": content_hash,
            "tags": tags_str or "",
        },
    )

    db.commit()
    db.refresh(memory)
    return memory


def get_memory(db: Session, memory_id: UUID, agent_id: UUID) -> Optional[Memory]:
    """Return a single non-deleted memory owned by *agent_id*."""
    return (
        db.query(Memory)
        .filter(
            Memory.id == memory_id,
            Memory.agent_id == agent_id,
            Memory.is_deleted.is_(False),
        )
        .first()
    )


def list_memories(
    db: Session,
    agent_id: UUID,
    skip: int = 0,
    limit: int = 50,
) -> List[Memory]:
    """Return a paginated list of non-deleted memories for *agent_id*."""
    return (
        db.query(Memory)
        .filter(Memory.agent_id == agent_id, Memory.is_deleted.is_(False))
        .order_by(Memory.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def soft_delete_memory(db: Session, memory_id: UUID, agent_id: UUID) -> bool:
    """
    Soft-delete a memory.

    Returns True when the memory was found and marked as deleted,
    False when not found.
    """
    memory = get_memory(db, memory_id, agent_id)
    if memory is None:
        return False
    memory.is_deleted = True
    db.commit()
    semantic.delete_memory_vector(memory_id)
    return True


def search_memories(
    query: str,
    agent_id: UUID,
    limit: int = 10,
) -> List[dict]:
    """Delegate semantic search to the Qdrant layer."""
    return semantic.search_memories(query=query, agent_id=agent_id, limit=limit)
