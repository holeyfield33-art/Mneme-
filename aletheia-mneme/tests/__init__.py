"""Shared test configuration — env vars must be set BEFORE any app imports."""
import os

# ── Set ALL required env vars for testing ──────────────────────
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test_mneme"
os.environ["OPENAI_API_KEY"] = "sk-test-00000000000000000000000000000000000000000000"
os.environ["RESEND_API_KEY"] = "re_test_00000000000000000000000000"
os.environ["EMAIL_FROM"] = "test@aletheia-test.dev"
os.environ["RELAY_SECRET"] = "test_relay_secret_token_for_testing"
os.environ["PERSONAL_MODE"] = "false"
os.environ["HELIOS_ENABLED"] = "true"

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


# ── Mock asyncpg Record ──────────────────────────────────────

class MockRecord(dict):
    """Behaves like asyncpg.Record — dict-like with index access."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


# ── Mock DB Connection ───────────────────────────────────────

class MockDB:
    """Mock asyncpg connection for testing."""

    def __init__(self):
        self.queries = []
        self._fetchrow_returns = {}
        self._fetchval_returns = {}
        self._fetch_returns = {}
        self._execute_returns = {}

    def set_fetchrow(self, query_contains: str, result):
        self._fetchrow_returns[query_contains] = result

    def set_fetchval(self, query_contains: str, result):
        self._fetchval_returns[query_contains] = result

    def set_fetch(self, query_contains: str, result):
        self._fetch_returns[query_contains] = result

    def set_execute(self, query_contains: str, result):
        self._execute_returns[query_contains] = result

    def _find_return(self, registry, query):
        for pattern, result in registry.items():
            if pattern in query:
                return result
        return None

    async def execute(self, query, *args):
        self.queries.append(("execute", query, args))
        result = self._find_return(self._execute_returns, query)
        return result if result is not None else "UPDATE 1"

    async def fetch(self, query, *args):
        self.queries.append(("fetch", query, args))
        result = self._find_return(self._fetch_returns, query)
        return result if result is not None else []

    async def fetchrow(self, query, *args):
        self.queries.append(("fetchrow", query, args))
        return self._find_return(self._fetchrow_returns, query)

    async def fetchval(self, query, *args):
        self.queries.append(("fetchval", query, args))
        result = self._find_return(self._fetchval_returns, query)
        return result if result is not None else 0


@pytest.fixture
def mock_db():
    return MockDB()


@pytest.fixture
def sample_memory_record():
    return MockRecord({
        "id": "mem_001",
        "namespace_id": "ns_test",
        "key": "test/memory",
        "value": "Test value",
        "category": "general",
        "source": "user",
        "confidence": 1.0,
        "content_hash": "abc123",
        "embedding_model": "text-embedding-3-small",
        "embedding": None,
        "version": 1,
        "last_updated": datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        "last_accessed": datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        "access_count": 0,
        "expires_at": None,
        "is_deleted": False,
    })


@pytest.fixture
def free_namespace():
    return {"id": "ns_free", "tier": "free", "is_active": True, "email": "free@test.com"}


@pytest.fixture
def premium_namespace():
    return {"id": "ns_premium", "tier": "premium", "is_active": True, "email": "premium@test.com"}
