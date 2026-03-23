"""
FastAPI router: memory CRUD + semantic search.
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import memory as mem_service
from app import billing as billing_service
from app.database import get_db
from app.dependencies import get_current_agent
from app.models import Agent, Subscription
from app.schemas import MemoryCreate, MemoryOut, SearchQuery, SearchResult

router = APIRouter(prefix="/memories", tags=["memories"])


def _check_memory_limit(db: Session, agent: Agent) -> None:
    """Raise 402 when the agent has reached their plan's memory limit."""
    sub: Subscription | None = agent.subscription
    plan = sub.plan if sub else "free"
    current_count = (
        db.query(mem_service.Memory)
        .filter_by(agent_id=agent.id, is_deleted=False)
        .count()
    )
    if not billing_service.is_within_limit(current_count, plan):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Memory limit reached for the '{plan}' plan. Please upgrade.",
        )


@router.post("/", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
def create_memory(
    body: MemoryCreate,
    db: Session = Depends(get_db),
    agent: Agent = Depends(get_current_agent),
):
    _check_memory_limit(db, agent)
    return mem_service.create_memory(
        db=db,
        agent_id=agent.id,
        content=body.content,
        tags=body.tags,
    )


@router.get("/", response_model=List[MemoryOut])
def list_memories(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    agent: Agent = Depends(get_current_agent),
):
    return mem_service.list_memories(db=db, agent_id=agent.id, skip=skip, limit=limit)


@router.get("/{memory_id}", response_model=MemoryOut)
def get_memory(
    memory_id: UUID,
    db: Session = Depends(get_db),
    agent: Agent = Depends(get_current_agent),
):
    memory = mem_service.get_memory(db=db, memory_id=memory_id, agent_id=agent.id)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return memory


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(
    memory_id: UUID,
    db: Session = Depends(get_db),
    agent: Agent = Depends(get_current_agent),
):
    deleted = mem_service.soft_delete_memory(db=db, memory_id=memory_id, agent_id=agent.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")


@router.post("/search", response_model=List[SearchResult])
def search_memories(
    body: SearchQuery,
    agent: Agent = Depends(get_current_agent),
):
    results = mem_service.search_memories(
        query=body.query,
        agent_id=agent.id,
        limit=body.limit,
    )
    return [SearchResult(**r) for r in results]
