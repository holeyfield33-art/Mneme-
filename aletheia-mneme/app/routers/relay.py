"""
FastAPI router: multi-agent relay.
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_agent
from app.models import Agent, RelayMessage
from app.schemas import RelayMessageCreate, RelayMessageOut

router = APIRouter(prefix="/relay", tags=["relay"])


@router.post("/", response_model=RelayMessageOut, status_code=status.HTTP_201_CREATED)
def send_message(
    body: RelayMessageCreate,
    db: Session = Depends(get_db),
    agent: Agent = Depends(get_current_agent),
):
    """Send a message to another agent."""
    recipient = db.query(Agent).filter(
        Agent.id == body.recipient_agent_id,
        Agent.is_active.is_(True),
    ).first()
    if recipient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipient agent not found",
        )
    msg = RelayMessage(
        sender_agent_id=agent.id,
        recipient_agent_id=body.recipient_agent_id,
        payload=body.payload,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


@router.get("/inbox", response_model=List[RelayMessageOut])
def get_inbox(
    db: Session = Depends(get_db),
    agent: Agent = Depends(get_current_agent),
):
    """Return undelivered messages addressed to the current agent."""
    messages = (
        db.query(RelayMessage)
        .filter(
            RelayMessage.recipient_agent_id == agent.id,
            RelayMessage.is_delivered.is_(False),
        )
        .order_by(RelayMessage.created_at.asc())
        .all()
    )
    # Mark as delivered
    for msg in messages:
        msg.is_delivered = True
    db.commit()
    return messages
