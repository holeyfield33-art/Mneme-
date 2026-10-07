"""Privacy and integrity regressions for the explicit local profile."""
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

import embeddings
import env
import storage
from helios.hasher import content_hash
from helios.objects import MemoryObject


@pytest.mark.asyncio
async def test_offline_embeddings_never_create_provider_or_download_model(monkeypatch):
    monkeypatch.setenv("MNEME_OFFLINE", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    env._reset_cache()
    try:
        with patch.object(embeddings, "AsyncOpenAI") as remote, patch.object(embeddings, "get_local_model") as local:
            assert await embeddings.get_embedding("private user prompt") == (None, "none")
            remote.assert_not_called()
            local.assert_not_called()
    finally:
        env._reset_cache()


@pytest.mark.asyncio
async def test_offline_cloud_sync_fails_before_network_or_context(monkeypatch):
    import tools
    monkeypatch.setenv("MNEME_OFFLINE", "true")
    env._reset_cache()
    try:
        with pytest.raises(ValueError, match="disabled"):
            await tools.cloud_sync("https://example.org")
    finally:
        env._reset_cache()


@pytest.mark.asyncio
async def test_hash_reuses_exact_persisted_timestamp_and_source():
    timestamp = datetime(2026, 9, 9, 12, 34, 56, 789000)
    expected = content_hash(MemoryObject(
        category="handoff", created_at="2026-09-09T12:34:56.000Z",
        key="agent/task", relationships=[], source="relay", value="persisted fact",
    ))
    assert await storage._compute_helios_hash("agent/task", "persisted fact", "handoff", timestamp, "relay") == expected


@pytest.mark.asyncio
async def test_store_hash_uses_timestamp_written_to_database():
    captured = {}

    async def fetchrow(query, *args):
        if "INSERT INTO memories" not in query:
            return None
        captured["args"] = args
        return {"id": "regression"}

    db = AsyncMock()
    db.fetchrow.side_effect = fetchrow
    with patch.object(embeddings, "get_embedding", return_value=(None, "none")):
        await storage.store_memory("personal", "agent/task", "persisted fact", "handoff", "relay", db)
    args = captured["args"]
    assert args[5] == await storage._compute_helios_hash(args[1], args[2], args[3], args[9], args[4])
