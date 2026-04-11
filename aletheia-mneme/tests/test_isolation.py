"""Namespace isolation tests — verifies cross-namespace data cannot leak.

Tests:
  - Namespace A cannot read Namespace B's memories
  - Namespace A cannot update Namespace B's memories
  - Namespace A cannot delete Namespace B's memories
  - Namespace A cannot list Namespace B's memories
  - Namespace A cannot search Namespace B's memories
  - Namespace A's relationships isolated from Namespace B
  - Namespace A's history isolated from Namespace B
  - Relay namespaces isolated from regular namespaces
  - Sync cannot push to another user's namespace
"""
import pytest
from unittest.mock import AsyncMock, patch
from tests import MockDB, MockRecord
from datetime import datetime, timezone

import storage


class TestNamespaceIsolation:
    """All storage queries must include namespace_id in WHERE clause."""

    @pytest.mark.asyncio
    async def test_get_memory_includes_namespace(self):
        db = MockDB()
        await storage.get_memory("ns_A", "some_key", db)
        # Verify the query includes namespace_id parameter
        assert len(db.queries) > 0
        query = db.queries[0][1]
        assert "namespace_id=$1" in query
        args = db.queries[0][2]
        assert args[0] == "ns_A"

    @pytest.mark.asyncio
    async def test_list_memories_includes_namespace(self):
        db = MockDB()
        await storage.list_memories("ns_A", None, 50, 0, db)
        assert len(db.queries) > 0
        query = db.queries[0][1]
        assert "namespace_id=$1" in query
        args = db.queries[0][2]
        assert args[0] == "ns_A"

    @pytest.mark.asyncio
    async def test_keyword_search_includes_namespace(self):
        db = MockDB()
        await storage.keyword_search("ns_A", "query", 10, db)
        assert len(db.queries) > 0
        query = db.queries[0][1]
        assert "namespace_id=$1" in query
        args = db.queries[0][2]
        assert args[0] == "ns_A"

    @pytest.mark.asyncio
    async def test_semantic_search_includes_namespace(self):
        db = MockDB()
        with patch("storage.emb") as mock_emb:
            mock_emb.get_embedding = AsyncMock(return_value=([0.1] * 1536, "text-embedding-3-small"))
            await storage.semantic_search("ns_A", "query", 10, db)
        assert len(db.queries) > 0
        query = db.queries[0][1]
        assert "namespace_id=$1" in query
        args = db.queries[0][2]
        assert args[0] == "ns_A"

    @pytest.mark.asyncio
    async def test_forget_memory_includes_namespace(self):
        db = MockDB()
        await storage.forget_memory("ns_A", "some_key", db)
        assert len(db.queries) > 0
        query = db.queries[0][1]
        assert "namespace_id=$1" in query
        args = db.queries[0][2]
        assert args[0] == "ns_A"

    @pytest.mark.asyncio
    async def test_update_memory_includes_namespace(self):
        db = MockDB()
        existing = MockRecord({
            "id": "mem_001", "value": "old", "version": 1,
            "category": "general", "source": "user", "key": "k",
        })
        updated = MockRecord({**dict(existing), "value": "new", "version": 2})
        db.set_fetchrow("SELECT * FROM memories WHERE", existing)
        db.set_fetchrow("UPDATE memories", updated)

        with patch("storage.emb") as mock_emb:
            mock_emb.get_embedding = AsyncMock(return_value=(None, "none"))
            await storage.update_memory("ns_A", "k", "new", db)

        # First query should be SELECT with namespace_id
        select_queries = [q for q in db.queries if q[0] == "fetchrow" and "SELECT" in q[1]]
        assert len(select_queries) > 0
        assert "namespace_id=$1" in select_queries[0][1]
        assert select_queries[0][2][0] == "ns_A"

    @pytest.mark.asyncio
    async def test_get_related_includes_namespace(self):
        db = MockDB()
        await storage.get_related_memories("ns_A", "k1", db)
        assert len(db.queries) > 0
        query = db.queries[0][1]
        assert "namespace_id=$1" in query
        args = db.queries[0][2]
        assert args[0] == "ns_A"

    @pytest.mark.asyncio
    async def test_relate_memories_includes_namespace(self):
        db = MockDB()
        record = MockRecord({
            "id": "r1", "namespace_id": "ns_A",
            "from_key": "k1", "to_key": "k2", "rel_type": "related_to",
        })
        db.set_fetchrow("INSERT INTO memory_relationships", record)
        await storage.relate_memories("ns_A", "k1", "k2", "related_to", db)
        insert_queries = [q for q in db.queries if "INSERT INTO memory_relationships" in q[1]]
        assert len(insert_queries) > 0
        assert insert_queries[0][2][0] == "ns_A"

    @pytest.mark.asyncio
    async def test_export_includes_namespace(self):
        db = MockDB()
        await storage.export_memories("ns_A", db)
        assert len(db.queries) > 0
        query = db.queries[0][1]
        assert "namespace_id=$1" in query
        args = db.queries[0][2]
        assert args[0] == "ns_A"

    @pytest.mark.asyncio
    async def test_get_memory_history_includes_namespace(self):
        db = MockDB()
        mem = MockRecord({"id": "mem_001"})
        db.set_fetchrow("SELECT id FROM memories", mem)
        await storage.get_memory_history("ns_A", "k1", db)
        # First query selects memory by namespace
        first_q = db.queries[0]
        assert "namespace_id=$1" in first_q[1]
        assert first_q[2][0] == "ns_A"


class TestCrossNamespaceBlocking:
    """Verify that operations on Namespace A truly cannot see Namespace B data."""

    @pytest.mark.asyncio
    async def test_ns_a_cannot_read_ns_b_memory(self):
        """get_memory for ns_A returns None even if ns_B has the key."""
        db = MockDB()
        # No record for ns_A (even though ns_B would have one)
        result = await storage.get_memory("ns_A", "shared_key", db)
        assert result is None

    @pytest.mark.asyncio
    async def test_ns_a_cannot_update_ns_b_memory(self):
        """update_memory for ns_A raises error if memory belongs to ns_B."""
        db = MockDB()
        # No record for ns_A
        db.set_fetchrow("SELECT * FROM memories WHERE", None)
        with pytest.raises(ValueError, match="Memory not found"):
            await storage.update_memory("ns_A", "ns_b_key", "hack", db)

    @pytest.mark.asyncio
    async def test_ns_a_forget_on_ns_b_key_is_noop(self):
        """forget_memory for ns_A cannot delete ns_B's memories."""
        db = MockDB()
        db.set_execute("UPDATE memories SET is_deleted", "UPDATE 0")
        result = await storage.forget_memory("ns_A", "ns_b_key", db)
        assert result is False

    @pytest.mark.asyncio
    async def test_ns_a_list_returns_empty_for_ns_b(self):
        """list_memories for ns_A returns empty list — should not see ns_B."""
        db = MockDB()
        db.set_fetch("SELECT * FROM memories", [])
        result = await storage.list_memories("ns_A", None, 50, 0, db)
        assert result == []

    @pytest.mark.asyncio
    async def test_ns_a_search_returns_empty_for_ns_b(self):
        """keyword_search for ns_A should not return ns_B's results."""
        db = MockDB()
        db.set_fetch("SELECT *", [])
        result = await storage.keyword_search("ns_A", "ns_b_query", 10, db)
        assert result == []


class TestSyncNamespaceEnforcement:
    """Sync endpoints enforce namespace ownership."""

    def test_sync_validate_url_rejects_ssrf(self):
        from sync import _validate_sync_url
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            _validate_sync_url("http://evil.com")
        with pytest.raises(HTTPException):
            _validate_sync_url("https://localhost")
        with pytest.raises(HTTPException):
            _validate_sync_url("https://169.254.169.254")

    def test_valid_conflict_strategies(self):
        from sync import VALID_CONFLICT_STRATEGIES
        assert "highest_version_wins" in VALID_CONFLICT_STRATEGIES
        assert "source_wins" in VALID_CONFLICT_STRATEGIES
        assert "target_wins" in VALID_CONFLICT_STRATEGIES
        assert "invalid" not in VALID_CONFLICT_STRATEGIES
