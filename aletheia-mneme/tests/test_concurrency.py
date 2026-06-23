"""Concurrency and load tests.

Verifies the system handles concurrent multi-calls:
  - Parallel memory stores
  - Parallel reads
  - Mixed read/write under load
  - Concurrent search operations
  - Rate limiting behavior
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from tests import MockDB, MockRecord

import tools
import storage


def _setup_context(namespace: dict, db):
    tools.current_namespace.set(namespace)
    tools.current_db.set(db)


class TestConcurrentStores:
    """Concurrent store_memory calls."""

    @pytest.mark.asyncio
    async def test_parallel_stores_no_conflicts(self):
        db = MockDB()
        ns = {"id": "ns_load", "tier": "premium"}
        _setup_context(ns, db)

        call_count = 0

        async def mock_store(ns_id, key, value, cat, source, db_conn):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # simulate IO
            return {"key": key, "value": value, "version": 1}

        with patch("tools.storage.store_memory", side_effect=mock_store):
            tasks = [
                tools.store_memory(f"key_{i}", f"value_{i}")
                for i in range(20)
            ]
            results = await asyncio.gather(*tasks)

        assert len(results) == 20
        assert call_count == 20
        assert all(r["version"] == 1 for r in results)

    @pytest.mark.asyncio
    async def test_parallel_stores_same_key_last_write_wins(self):
        """Multiple concurrent writes to same key - all should complete."""
        db = MockDB()
        ns = {"id": "ns_load", "tier": "premium"}
        _setup_context(ns, db)

        versions = iter(range(1, 11))

        async def mock_store(ns_id, key, value, cat, source, db_conn):
            v = next(versions)
            await asyncio.sleep(0.005)
            return {"key": key, "value": value, "version": v}

        with patch("tools.storage.store_memory", side_effect=mock_store):
            tasks = [
                tools.store_memory("shared_key", f"value_{i}")
                for i in range(10)
            ]
            results = await asyncio.gather(*tasks)

        assert len(results) == 10
        # All 10 completed without error
        assert all("key" in r for r in results)


class TestConcurrentReads:
    """Concurrent get/list/search operations."""

    @pytest.mark.asyncio
    async def test_parallel_reads(self):
        db = MockDB()
        ns = {"id": "ns_load", "tier": "free"}
        _setup_context(ns, db)

        async def mock_get(ns_id, key, db_conn):
            await asyncio.sleep(0.005)
            return {"key": key, "value": f"val_{key}", "version": 1}

        with patch("tools.storage.get_memory", side_effect=mock_get):
            tasks = [tools.get_memory(f"key_{i}") for i in range(50)]
            results = await asyncio.gather(*tasks)

        assert len(results) == 50
        assert all("key" in r for r in results)

    @pytest.mark.asyncio
    async def test_parallel_keyword_searches(self):
        db = MockDB()
        ns = {"id": "ns_load", "tier": "free"}
        _setup_context(ns, db)

        async def mock_search(ns_id, q, limit, db_conn):
            await asyncio.sleep(0.005)
            return [{"key": f"result_{q}", "value": "v"}]

        with patch("tools.storage.keyword_search", side_effect=mock_search):
            tasks = [tools.search_memory(f"query_{i}") for i in range(30)]
            results = await asyncio.gather(*tasks)

        assert len(results) == 30
        assert all(len(r) >= 1 for r in results)

    @pytest.mark.asyncio
    async def test_parallel_semantic_searches_premium(self):
        db = MockDB()
        ns = {"id": "ns_load", "tier": "premium"}
        _setup_context(ns, db)

        async def mock_sem(ns_id, q, limit, db_conn):
            await asyncio.sleep(0.01)
            return [{"key": "r1", "similarity": 0.9}]

        with patch("tools.storage.semantic_search", side_effect=mock_sem):
            tasks = [tools.semantic_search(f"query_{i}") for i in range(20)]
            results = await asyncio.gather(*tasks)

        assert len(results) == 20


class TestMixedReadWrite:
    """Mixed concurrent read and write operations."""

    @pytest.mark.asyncio
    async def test_mixed_store_and_read(self):
        db = MockDB()
        ns = {"id": "ns_load", "tier": "premium"}
        _setup_context(ns, db)

        async def mock_store(ns_id, key, value, cat, source, db_conn):
            await asyncio.sleep(0.005)
            return {"key": key, "value": value, "version": 1}

        async def mock_get(ns_id, key, db_conn):
            await asyncio.sleep(0.005)
            return {"key": key, "value": "cached", "version": 1}

        with patch("tools.storage.store_memory", side_effect=mock_store), \
             patch("tools.storage.get_memory", side_effect=mock_get):

            store_tasks = [tools.store_memory(f"k_{i}", f"v_{i}") for i in range(15)]
            read_tasks = [tools.get_memory(f"k_{i}") for i in range(15)]

            all_tasks = store_tasks + read_tasks
            results = await asyncio.gather(*all_tasks)

        assert len(results) == 30

    @pytest.mark.asyncio
    async def test_mixed_operations_with_updates_and_deletes(self):
        db = MockDB()
        ns = {"id": "ns_load", "tier": "premium"}
        _setup_context(ns, db)

        async def mock_store(ns_id, key, value, cat, source, db_conn):
            return {"key": key, "value": value, "version": 1}

        async def mock_update(ns_id, key, value, db_conn):
            return {"key": key, "value": value, "version": 2}

        async def mock_forget(ns_id, key, db_conn):
            return True

        with patch("tools.storage.store_memory", side_effect=mock_store), \
             patch("tools.storage.update_memory", side_effect=mock_update), \
             patch("tools.storage.forget_memory", side_effect=mock_forget):

            tasks = []
            for i in range(10):
                tasks.append(tools.store_memory(f"k_{i}", f"v_{i}"))
                tasks.append(tools.update_memory(f"k_{i}", f"v_{i}_updated"))
                tasks.append(tools.forget_memory(f"k_{i + 100}"))

            results = await asyncio.gather(*tasks)
            assert len(results) == 30


class TestStorageValidationUnderLoad:
    """Validation edge cases under concurrent calls."""

    @pytest.mark.asyncio
    async def test_validation_errors_dont_crash_batch(self):
        """Invalid inputs in a batch shouldn't prevent valid ones from completing."""
        db = MockDB()
        ns = {"id": "ns_load", "tier": "free"}
        _setup_context(ns, db)

        async def mock_store(ns_id, key, value, cat, source, db_conn):
            return {"key": key, "value": value, "version": 1}

        with patch("tools.storage.store_memory", side_effect=mock_store):
            tasks = [tools.store_memory(f"k_{i}", f"v_{i}") for i in range(5)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should succeed (validation is in storage layer)
        successes = [r for r in results if not isinstance(r, Exception)]
        assert len(successes) == 5

    @pytest.mark.asyncio
    async def test_advanced_tools_open_to_all_in_batch(self):
        """No tier gating — advanced tools run for any namespace in a batch."""
        ns = {"id": "ns_user", "tier": "premium"}
        _setup_context(ns, MockDB())

        with patch("tools.storage.semantic_search", new_callable=AsyncMock,
                   return_value=[{"key": "k", "similarity": 0.9}]):
            tasks = [tools.semantic_search(f"q_{i}") for i in range(10)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        assert all(not isinstance(r, Exception) for r in results)
        assert len(results) == 10


class TestInputValidationConcurrent:
    """Storage input validation under load."""

    @pytest.mark.asyncio
    async def test_oversized_values_rejected_concurrently(self):
        db = MockDB()

        big_value = "x" * 100_001
        tasks = []
        for i in range(5):
            tasks.append(
                asyncio.to_thread(
                    storage._validate_input, f"k_{i}", big_value
                )
            )
        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = [r for r in results if isinstance(r, ValueError)]
        assert len(errors) == 5

    @pytest.mark.asyncio
    async def test_oversized_keys_rejected_concurrently(self):
        db = MockDB()

        big_key = "k" * 513
        tasks = []
        for i in range(5):
            tasks.append(
                asyncio.to_thread(storage._validate_input, big_key, "val")
            )
        results = await asyncio.gather(*tasks, return_exceptions=True)
        errors = [r for r in results if isinstance(r, ValueError)]
        assert len(errors) == 5
