"""
SQLAlchemy ORM models for Aletheia Mneme.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class Agent(Base):
    """Registered agent that can store and query memories."""

    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    api_key_hash = Column(String(64), nullable=False, unique=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    memories = relationship("Memory", back_populates="agent", cascade="all, delete-orphan")
    subscription = relationship("Subscription", back_populates="agent", uselist=False)

    def __repr__(self) -> str:
        return f"<Agent id={self.id} name={self.name!r}>"


class Memory(Base):
    """A single persistent memory entry."""

    __tablename__ = "memories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)  # SHA-256 hex digest
    signature = Column(String(128), nullable=True)     # HMAC-SHA256 hex digest
    tags = Column(Text, nullable=True)                 # comma-separated tag list
    qdrant_id = Column(String(36), nullable=True)      # vector DB point ID
    is_deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    agent = relationship("Agent", back_populates="memories")

    def __repr__(self) -> str:
        return f"<Memory id={self.id} agent_id={self.agent_id}>"


class RelayMessage(Base):
    """Message queued in the multi-agent relay."""

    __tablename__ = "relay_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sender_agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    recipient_agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    payload = Column(Text, nullable=False)
    is_delivered = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    sender = relationship("Agent", foreign_keys=[sender_agent_id])
    recipient = relationship("Agent", foreign_keys=[recipient_agent_id])

    def __repr__(self) -> str:
        return f"<RelayMessage id={self.id}>"


class Subscription(Base):
    """Stripe subscription linked to an agent."""

    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, unique=True)
    stripe_customer_id = Column(String(255), nullable=False)
    stripe_subscription_id = Column(String(255), nullable=True)
    plan = Column(
        Enum("free", "pro", name="subscription_plan"),
        nullable=False,
        default="free",
    )
    status = Column(String(50), nullable=False, default="active")
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    agent = relationship("Agent", back_populates="subscription")

    def __repr__(self) -> str:
        return f"<Subscription id={self.id} plan={self.plan} status={self.status}>"
