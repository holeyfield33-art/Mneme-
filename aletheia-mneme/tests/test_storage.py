"""Storage module — CRUD, search, versioning, validation, and Helios tests.

Tests:
  - Input validation (key length, value length, category length)
  - Store memory with Helios hash
  - Get memory with access count update
  - Update memory with version history
  - Forget (soft delete)
  - List memories with category filter
  - Keyword search
  - Semantic search fallback
  - Reinforce memory
  - Memory history
  - Rollback memory
  - Relate memories
  - Export memories
  - Verify memory Helios integrity
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from tests import MockDB, MockRecord

import storage


# ── Input Validation ─────────────────────────────────────────

class TestInputValidation:
    def test_empty_key_rejected(self):
        with pytest.raises(ValueError, match="Key must be"):
            storage._validate_input("", "value")

    def test_key_too_long_rejected(self):
        with pytest.raises(ValueError, match="Key must be"):
            storage._validate_input("x" * 513, "value")

    def test_empty_value_rejected(self):
        with pytest.raises(ValueError, match="Value must be"):
            storage._validate_input("key", "")

    def test_value_too_long_rejected(self):
        with pytest.raises(ValueError, match="Value must be"):
            storage._validate_input("key", "x" * 100_001)

    def test_category_too_long_rejected(self):
        with pytest.raises(ValueError, match="Category must be"):
            storage._validate_input("key", "value", "x" * 129)

    def test_valid_input_passes(self):
        storage._validate_input("valid/key", "valid value", "general")

    def test_max_key_length_passes(self):
        storage._validate_input("x" * 512, "value")

    def test_max_value_length_passes(self):
        storage._validate_input("key", "x" * 100_000)


# ── Store Memory ─────────────────────────────────────────────

class TestStoreMemory:
    @pytest.mark.asyncio
    async def test_store_new_memory(self):
        db = MockDB()
        db.set_fetchrow("SELECT id FROM memories", None)  # No existing
        result_record = MockRecord({
            "id": "mem_001", "namespace_id": "ns_1", "key": "test/key",
            "value": "test value", "category": "general", "source": "user",
            "content_hash": "abc123", "version": 1,
            "embedding_model": "text-embedding-3-small", "embedding": None,
            "confidence": 1.0, "last_updated": datetime.now(timezone.utc),
            "last_accessed": datetime.now(timezone.utc), "access_count": 0,
            "expires_at": None, "is_deleted": False,
        })
        db.set_fetchrow("INSERT INTO memories", result_record)

        with patch("storage.emb") as mock_emb:
            mock_emb.get_embedding = AsyncMock(return_value=(None, "none"))
            result = await storage.store_memory("ns_1", "test/key", "test value", "general", "user", db)
            assert result["key"] == "test/key"
            assert result["value"] == "test value"

    @pytest.mark.asyncio
    async def test_store_validates_input(self):
        db = MockDB()
        with pytest.raises(ValueError, match="Key must be"):
            await storage.store_memory("ns_1", "", "test value", "general", "user", db)

    @pytest.mark.asyncio
    async def test_store_existing_triggers_update(self):
        db = MockDB()
        db.set_fetchrow("SELECT id FROM memories", MockRecord({"id": "existing"}))
        existing_record = MockRecord({
            "id": "existing", "namespace_id": "ns_1", "key": "test/key",
            "value": "old value", "category": "general", "source": "user",
            "content_hash": "old_hash", "version": 1,
            "embedding_model": "text-embedding-3-small", "embedding": None,
            "confidence": 1.0, "last_updated": datetime.now(timezone.utc),
            "last_accessed": datetime.now(timezone.utc), "access_count": 0,
            "expires_at": None, "is_deleted": False,
            "helios_created_at": "2025-01-15T10:30:00.000Z",
        })
        updated_record = MockRecord({**dict(existing_record), "value": "new value", "version": 2})
        db.set_fetchrow("SELECT * FROM memories", existing_record)
        db.set_fetchrow("UPDATE memories", updated_record)

        with patch("storage.emb") as mock_emb:
            mock_emb.get_embedding = AsyncMock(return_value=(None, "none"))
            result = await storage.store_memory("ns_1", "test/key", "new value", "general", "user", db)
            assert result["version"] == 2


# ── Get Memory ───────────────────────────────────────────────

class TestGetMemory:
    @pytest.mark.asyncio
    async def test_get_existing_memory(self):
        db = MockDB()
        record = MockRecord({
            "id": "mem_001", "namespace_id": "ns_1", "key": "test/key",
            "value": "test value", "category": "general", "source": "user",
            "confidence": 1.0, "version": 1, "access_count": 0,
        })
        db.set_fetchrow("SELECT * FROM memories", record)
        result = await storage.get_memory("ns_1", "test/key", db)
        assert result is not None
        assert result["key"] == "test/key"

    @pytest.mark.asyncio
    async def test_get_nonexistent_memory(self):
        db = MockDB()
        result = await storage.get_memory("ns_1", "nonexistent", db)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_increments_access_count(self):
        db = MockDB()
        record = MockRecord({"id": "mem_001", "key": "test/key", "value": "test"})
        db.set_fetchrow("SELECT * FROM memories", record)
        await storage.get_memory("ns_1", "test/key", db)
        access_queries = [q for q in db.queries if "access_count" in q[1]]
        assert len(access_queries) > 0


# ── Forget Memory ────────────────────────────────────────────

class TestForgetMemory:
    @pytest.mark.asyncio
    async def test_forget_existing(self):
        db = MockDB()
        db.set_execute("UPDATE memories SET is_deleted", "UPDATE 1")
        result = await storage.forget_memory("ns_1", "test/key", db)
        assert result is True

    @pytest.mark.asyncio
    async def test_forget_nonexistent(self):
        db = MockDB()
        db.set_execute("UPDATE memories SET is_deleted", "UPDATE 0")
        result = await storage.forget_memory("ns_1", "missing", db)
        assert result is False


# ── List Memories ────────────────────────────────────────────

class TestListMemories:
    @pytest.mark.asyncio
    async def test_list_all(self):
        db = MockDB()
        records = [
            MockRecord({"key": "k1", "value": "v1"}),
            MockRecord({"key": "k2", "value": "v2"}),
        ]
        db.set_fetch("SELECT * FROM memories", records)
        result = await storage.list_memories("ns_1", None, 50, 0, db)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_with_category(self):
        db = MockDB()
        records = [MockRecord({"key": "k1", "value": "v1", "category": "project"})]
        db.set_fetch("SELECT * FROM memories", records)
        result = await storage.list_memories("ns_1", "project", 50, 0, db)
        assert len(result) == 1


# ── Update Memory ────────────────────────────────────────────

class TestUpdateMemory:
    @pytest.mark.asyncio
    async def test_update_validates_input(self):
        db = MockDB()
        with pytest.raises(ValueError, match="Key must be"):
            await storage.update_memory("ns_1", "", "new value", db)

    @pytest.mark.asyncio
    async def test_update_nonexistent_raises(self):
        db = MockDB()
        db.set_fetchrow("SELECT * FROM memories WHERE", None)
        with pytest.raises(ValueError, match="Memory not found"):
            await storage.update_memory("ns_1", "missing", "new value", db)

    @pytest.mark.asyncio
    async def test_update_creates_history(self):
        db = MockDB()
        existing = MockRecord({
            "id": "mem_001", "value": "old value", "version": 1,
            "category": "general", "source": "user", "key": "test/key",
            "helios_created_at": "2025-01-15T10:30:00.000Z",
        })
        updated = MockRecord({**dict(existing), "value": "new value", "version": 2})
        db.set_fetchrow("SELECT * FROM memories WHERE", existing)
        db.set_fetchrow("UPDATE memories", updated)

        with patch("storage.emb") as mock_emb:
            mock_emb.get_embedding = AsyncMock(return_value=(None, "none"))
            result = await storage.update_memory("ns_1", "test/key", "new value", db)
            history_inserts = [q for q in db.queries if "memory_history" in q[1]]
            assert len(history_inserts) > 0


# ── Reinforce Memory ────────────────────────────────────────

class TestReinforceMemory:
    @pytest.mark.asyncio
    async def test_reinforce_returns_updated(self):
        db = MockDB()
        record = MockRecord({"key": "k1", "confidence": 0.9})
        db.set_fetchrow("UPDATE memories SET confidence", record)
        result = await storage.reinforce_memory("ns_1", "k1", 0.1, db)
        assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_reinforce_nonexistent_returns_empty(self):
        db = MockDB()
        result = await storage.reinforce_memory("ns_1", "missing", 0.1, db)
        assert result == {}


# ── Semantic Search Fallback ─────────────────────────────────

class TestSemanticSearch:
    @pytest.mark.asyncio
    async def test_falls_back_to_keyword_on_embedding_failure(self):
        db = MockDB()
        with patch("storage.emb") as mock_emb:
            mock_emb.get_embedding = AsyncMock(return_value=(None, "none"))
            result = await storage.semantic_search("ns_1", "query", 10, db)
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_uses_vector_when_available(self):
        db = MockDB()
        fake_vector = [0.1] * 1536
        db.set_fetch("SELECT *", [])
        with patch("storage.emb") as mock_emb:
            mock_emb.get_embedding = AsyncMock(return_value=(fake_vector, "text-embedding-3-small"))
            result = await storage.semantic_search("ns_1", "query", 10, db)
            # Should have used the embedding query not keyword
            vector_queries = [q for q in db.queries if "embedding" in q[1]]
            assert len(vector_queries) > 0


# ── Helios Hash Computation ──────────────────────────────────

class TestHeliosHash:
    @pytest.mark.asyncio
    async def test_compute_helios_hash_returns_hex(self):
        ts = "2025-01-15T10:30:00.000Z"
        h = await storage._compute_helios_hash("test/key", "test value", "general", ts)
        assert h is not None
        assert len(h) == 64

    @pytest.mark.asyncio
    async def test_compute_helios_hash_deterministic(self):
        ts = "2025-01-15T10:30:00.000Z"
        h1 = await storage._compute_helios_hash("test/key", "test value", "general", ts)
        h2 = await storage._compute_helios_hash("test/key", "test value", "general", ts)
        # Same created_at → hashes must be identical
        assert h1 is not None and h2 is not None
        assert h1 == h2

    @pytest.mark.asyncio
    async def test_compute_helios_hash_differs_for_different_timestamps(self):
        h1 = await storage._compute_helios_hash("k", "v", "general", "2025-01-01T00:00:00.000Z")
        h2 = await storage._compute_helios_hash("k", "v", "general", "2025-06-01T00:00:00.000Z")
        assert h1 != h2


# ── Memory Relationships ─────────────────────────────────────

class TestRelationships:
    @pytest.mark.asyncio
    async def test_relate_memories(self):
        db = MockDB()
        record = MockRecord({
            "id": "rel_001", "namespace_id": "ns_1",
            "from_key": "k1", "to_key": "k2", "rel_type": "related_to",
        })
        db.set_fetchrow("INSERT INTO memory_relationships", record)
        result = await storage.relate_memories("ns_1", "k1", "k2", "related_to", db)
        assert result["from_key"] == "k1"
        assert result["to_key"] == "k2"

    @pytest.mark.asyncio
    async def test_get_related(self):
        db = MockDB()
        records = [
            MockRecord({"from_key": "k1", "to_key": "k2", "rel_type": "related_to"}),
        ]
        db.set_fetch("SELECT * FROM memory_relationships", records)
        result = await storage.get_related_memories("ns_1", "k1", db)
        assert len(result) == 1


# ── Rollback Memory ──────────────────────────────────────────

class TestRollbackMemory:
    @pytest.mark.asyncio
    async def test_rollback_nonexistent_raises(self):
        db = MockDB()
        with pytest.raises(ValueError, match="Memory not found"):
            await storage.rollback_memory("ns_1", "missing", 1, db)

    @pytest.mark.asyncio
    async def test_rollback_missing_version_raises(self):
        db = MockDB()
        mem = MockRecord({"id": "mem_001", "key": "test/key"})
        db.set_fetchrow("SELECT * FROM memories WHERE", mem)
        # No history for version
        with pytest.raises(ValueError, match="Version .* not found"):
            await storage.rollback_memory("ns_1", "test/key", 99, db)


# ── Export Memories ──────────────────────────────────────────

class TestExportMemories:
    @pytest.mark.asyncio
    async def test_export_returns_list(self):
        db = MockDB()
        records = [
            MockRecord({"key": "k1", "value": "v1"}),
            MockRecord({"key": "k2", "value": "v2"}),
        ]
        db.set_fetch("SELECT * FROM memories WHERE namespace_id", records)
        result = await storage.export_memories("ns_1", db)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_export_empty_namespace(self):
        db = MockDB()
        result = await storage.export_memories("ns_empty", db)
        assert result == []


# ── Verify Memory Helios ────────────────────────────────────

class TestVerifyMemory:
    @pytest.mark.asyncio
    async def test_verify_nonexistent_memory(self):
        db = MockDB()
        result = await storage.verify_memory_helios("ns_1", "missing", db)
        assert result["valid"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_verify_pre_migration_record_is_unverifiable(self):
        """Rows stored before migration 005 have helios_created_at=None.
        verify_memory_helios must report unverifiable rather than valid=False."""
        db = MockDB()
        record = MockRecord({
            "id": "mem_pre", "namespace_id": "ns_1", "key": "old/key",
            "value": "some value", "category": "general", "source": "user",
            "content_hash": "deadbeef", "version": 1,
            "helios_created_at": None,
        })
        db.set_fetchrow("SELECT * FROM memories", record)
        result = await storage.verify_memory_helios("ns_1", "old/key", db)
        assert result["valid"] is False
        assert result.get("unverifiable") is True
        assert "pre-migration" in result["reason"]

    @pytest.mark.asyncio
    async def test_verify_valid_memory_returns_true(self):
        """A record stored with migration 005 should verify correctly."""
        ts = "2025-01-15T10:30:00.000Z"
        # Compute the expected hash the same way store_memory does.
        expected_hash = await storage._compute_helios_hash("test/key", "test value", "general", ts)
        db = MockDB()
        record = MockRecord({
            "id": "mem_001", "namespace_id": "ns_1", "key": "test/key",
            "value": "test value", "category": "general", "source": "user",
            "content_hash": expected_hash, "version": 1,
            "helios_created_at": ts,
        })
        db.set_fetchrow("SELECT * FROM memories", record)
        result = await storage.verify_memory_helios("ns_1", "test/key", db)
        assert result["valid"] is True
        assert result["computed_hash"] == result["stored_hash"]

    @pytest.mark.asyncio
    async def test_verify_tampered_value_returns_false(self):
        """A record whose value was altered out-of-band must fail verification."""
        ts = "2025-01-15T10:30:00.000Z"
        original_hash = await storage._compute_helios_hash("test/key", "original", "general", ts)
        db = MockDB()
        record = MockRecord({
            "id": "mem_001", "namespace_id": "ns_1", "key": "test/key",
            "value": "tampered",          # value changed but hash not updated
            "category": "general", "source": "user",
            "content_hash": original_hash, "version": 1,
            "helios_created_at": ts,
        })
        db.set_fetchrow("SELECT * FROM memories", record)
        result = await storage.verify_memory_helios("ns_1", "test/key", db)
        assert result["valid"] is False
        assert result["computed_hash"] != result["stored_hash"]
