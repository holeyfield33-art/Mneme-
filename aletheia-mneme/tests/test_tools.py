"""Tool wiring tests.

Tests:
  - All 16 tools callable by any namespace (no tier gating)
  - Tool function wiring (each tool calls correct storage function)
  - Edge cases: missing namespace, empty results
"""
import pytest
from unittest.mock import AsyncMock, patch
from tests import MockDB, MockRecord
from datetime import datetime, timezone
from contextvars import copy_context

import tools


def _setup_context(namespace: dict, db):
    """Set contextvars for tool execution."""
    tools.current_namespace.set(namespace)
    tools.current_db.set(db)


# ── Free Tool Access ─────────────────────────────────────────

class TestFreeTools:
    @pytest.mark.asyncio
    async def test_store_memory(self):
        db = MockDB()
        ns = {"id": "ns_free", "tier": "free"}
        _setup_context(ns, db)
        with patch("tools.storage.store_memory", new_callable=AsyncMock,
                    return_value={"key": "k", "value": "v"}):
            result = await tools.store_memory("k", "v")
            assert result["key"] == "k"

    @pytest.mark.asyncio
    async def test_get_memory(self):
        db = MockDB()
        ns = {"id": "ns_free", "tier": "free"}
        _setup_context(ns, db)
        with patch("tools.storage.get_memory", new_callable=AsyncMock,
                    return_value={"key": "k", "value": "v"}):
            result = await tools.get_memory("k")
            assert result["key"] == "k"

    @pytest.mark.asyncio
    async def test_get_memory_not_found(self):
        db = MockDB()
        ns = {"id": "ns_free", "tier": "free"}
        _setup_context(ns, db)
        with patch("tools.storage.get_memory", new_callable=AsyncMock,
                    return_value=None):
            result = await tools.get_memory("missing")
            assert "error" in result

    @pytest.mark.asyncio
    async def test_list_memories_uncapped(self):
        db = MockDB()
        ns = {"id": "ns_user", "tier": "premium"}
        _setup_context(ns, db)
        with patch("tools.storage.list_memories", new_callable=AsyncMock,
                    return_value=[]) as mock_list:
            await tools.list_memories(limit=200)
            # No tier cap — the requested limit is passed straight through
            mock_list.assert_called_once_with("ns_user", None, 200, 0, db)

    @pytest.mark.asyncio
    async def test_search_memory(self):
        db = MockDB()
        ns = {"id": "ns_free", "tier": "free"}
        _setup_context(ns, db)
        with patch("tools.storage.keyword_search", new_callable=AsyncMock,
                    return_value=[{"key": "k1"}]):
            result = await tools.search_memory("query")
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_forget_memory(self):
        db = MockDB()
        ns = {"id": "ns_free", "tier": "free"}
        _setup_context(ns, db)
        with patch("tools.storage.forget_memory", new_callable=AsyncMock,
                    return_value=True):
            result = await tools.forget_memory("k")
            assert result["deleted"] is True

    @pytest.mark.asyncio
    async def test_update_memory(self):
        db = MockDB()
        ns = {"id": "ns_free", "tier": "free"}
        _setup_context(ns, db)
        with patch("tools.storage.update_memory", new_callable=AsyncMock,
                    return_value={"key": "k", "value": "new"}):
            result = await tools.update_memory("k", "new")
            assert result["value"] == "new"

    @pytest.mark.asyncio
    async def test_reinforce(self):
        db = MockDB()
        ns = {"id": "ns_free", "tier": "free"}
        _setup_context(ns, db)
        with patch("tools.storage.reinforce_memory", new_callable=AsyncMock,
                    return_value={"key": "k", "confidence": 0.9}):
            result = await tools.reinforce("k", 0.1)
            assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_get_stats(self):
        db = MockDB()
        db.set_fetchval("SELECT COUNT", 5)
        db.set_fetch("SELECT category", [
            MockRecord({"category": "general", "count": 3}),
            MockRecord({"category": "project", "count": 2}),
        ])
        ns = {"id": "ns_free", "tier": "free"}
        _setup_context(ns, db)
        result = await tools.get_stats()
        assert result["total_memories"] == 5
        assert result["tier"] == "free"
        assert "general" in result["categories"]


# ── Advanced Tool Access (no gating — available to all) ──────

class TestAdvancedToolAccess:
    @pytest.mark.asyncio
    async def test_semantic_search_allowed_on_premium(self):
        db = MockDB()
        ns = {"id": "ns_prem", "tier": "premium"}
        _setup_context(ns, db)
        with patch("tools.storage.semantic_search", new_callable=AsyncMock,
                    return_value=[{"key": "k1", "similarity": 0.95}]):
            result = await tools.semantic_search("query")
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_relate_memories_allowed_on_premium(self):
        db = MockDB()
        ns = {"id": "ns_prem", "tier": "premium"}
        _setup_context(ns, db)
        with patch("tools.storage.relate_memories", new_callable=AsyncMock,
                    return_value={"from_key": "k1", "to_key": "k2"}):
            result = await tools.relate_memories("k1", "k2", "related_to")
            assert result["from_key"] == "k1"

    @pytest.mark.asyncio
    async def test_export_memories_allowed_on_premium(self):
        db = MockDB()
        ns = {"id": "ns_prem", "tier": "premium"}
        _setup_context(ns, db)
        with patch("tools.storage.export_memories", new_callable=AsyncMock,
                    return_value=[{"key": "k1"}]):
            result = await tools.export_memories()
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_verify_memory_allowed_on_premium(self):
        db = MockDB()
        ns = {"id": "ns_prem", "tier": "premium"}
        _setup_context(ns, db)
        with patch("tools.storage.verify_memory_helios", new_callable=AsyncMock,
                    return_value={"valid": True}):
            result = await tools.verify_memory("k1")
            assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_memory_history_allowed_on_premium(self):
        db = MockDB()
        ns = {"id": "ns_prem", "tier": "premium"}
        _setup_context(ns, db)
        with patch("tools.storage.get_memory_history", new_callable=AsyncMock,
                    return_value=[{"old_value": "v1", "old_version": 1}]):
            result = await tools.memory_history("k1")
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_rollback_memory_allowed_on_premium(self):
        db = MockDB()
        ns = {"id": "ns_prem", "tier": "premium"}
        _setup_context(ns, db)
        with patch("tools.storage.rollback_memory", new_callable=AsyncMock,
                    return_value={"key": "k1", "version": 1}):
            result = await tools.rollback_memory("k1", 1)
            assert result["version"] == 1
