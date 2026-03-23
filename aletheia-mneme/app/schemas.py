"""
Pydantic schemas used in request / response bodies.
"""
from typing import List, Optional
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., description="Contact e-mail for billing")


class AgentOut(BaseModel):
    id: UUID
    name: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentWithKey(AgentOut):
    api_key: str = Field(..., description="Plain-text API key — store securely, shown once")


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class MemoryCreate(BaseModel):
    content: str = Field(..., min_length=1)
    tags: Optional[List[str]] = None


class MemoryOut(BaseModel):
    id: UUID
    content: str
    content_hash: str
    tags: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class SearchQuery(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(10, ge=1, le=100)


class SearchResult(BaseModel):
    id: str
    score: float
    payload: dict


# ---------------------------------------------------------------------------
# Relay
# ---------------------------------------------------------------------------

class RelayMessageCreate(BaseModel):
    recipient_agent_id: UUID
    payload: str = Field(..., min_length=1)


class RelayMessageOut(BaseModel):
    id: UUID
    sender_agent_id: UUID
    recipient_agent_id: UUID
    payload: str
    is_delivered: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Billing
# ---------------------------------------------------------------------------

class CheckoutRequest(BaseModel):
    success_url: str
    cancel_url: str


class CheckoutResponse(BaseModel):
    checkout_url: str


class SubscriptionOut(BaseModel):
    plan: str
    status: str
    stripe_subscription_id: Optional[str]
    current_period_end: Optional[datetime]

    model_config = {"from_attributes": True}
