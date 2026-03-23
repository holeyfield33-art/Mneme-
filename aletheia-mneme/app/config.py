"""
Configuration management for Aletheia Mneme.
All settings are loaded from environment variables.
"""
import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    app_name: str = "Aletheia Mneme"
    app_version: str = "0.1.0"
    debug: bool = False
    secret_key: str = "change-me-in-production"

    # Database (PostgreSQL)
    database_url: str = "postgresql://mneme:mneme@localhost:5432/mneme"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Qdrant (vector / semantic search)
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "mneme_memories"

    # OpenAI (embedding model)
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536

    # Stripe (billing)
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id_pro: str = ""

    # Multi-agent relay
    relay_token_expiry_seconds: int = 3600
    max_memories_per_agent: int = 10000

    model_config = {"env_file": ".env", "case_sensitive": False}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
