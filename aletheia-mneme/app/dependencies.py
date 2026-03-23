"""
FastAPI dependency: resolve the current agent from the X-API-Key header.
"""
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.crypto import hash_api_key
from app.database import get_db
from app.models import Agent

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


def get_current_agent(
    api_key: str = Security(api_key_header),
    db: Session = Depends(get_db),
) -> Agent:
    """Return the active Agent matching *api_key*, or raise 401."""
    hashed = hash_api_key(api_key)
    agent = (
        db.query(Agent)
        .filter(Agent.api_key_hash == hashed, Agent.is_active.is_(True))
        .first()
    )
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
        )
    return agent
