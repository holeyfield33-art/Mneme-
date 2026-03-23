"""
FastAPI router: agent registration.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.crypto import generate_api_key, hash_api_key
from app.database import get_db
from app.models import Agent
from app.schemas import AgentCreate, AgentOut, AgentWithKey

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/register", response_model=AgentWithKey, status_code=status.HTTP_201_CREATED)
def register_agent(body: AgentCreate, db: Session = Depends(get_db)):
    """Register a new agent and return a one-time API key."""
    api_key = generate_api_key()
    agent = Agent(
        name=body.name,
        api_key_hash=hash_api_key(api_key),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return AgentWithKey(**AgentOut.model_validate(agent).model_dump(), api_key=api_key)
