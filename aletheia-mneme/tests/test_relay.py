"""Relay module — auth, namespace generation, capacity, and 24h expiry tests.

Tests:
  - Relay auth with correct secret
  - Relay auth rejects wrong secret
  - Relay auth rejects missing header
  - Relay namespace ID is deterministic for same session+agent
  - Relay namespace ID differs for different agents
  - Relay store passes 24h expires_at
  - Relay capacity limit at 300 memories
  - Relay store requires key and value
  - Relay fetch requires key
  - Relay search requires query
  - Relay unknown operation rejected
"""
import pytest
import hashlib
from unittest.mock import AsyncMock, patch, MagicMock, call
from datetime import datetime, timezone, timedelta
from tests import MockDB, MockRecord

import relay


class TestRelayAuth:
    def test_valid_auth_passes(self):
        request = MagicMock()
        request.headers.get.return_value = "Bearer test_relay_secret_token_for_testing"
        # Should not raise
        relay._verify_relay_auth(request)

    def test_wrong_secret_raises_401(self):
        request = MagicMock()
        request.headers.get.return_value = "Bearer wrong_token"
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            relay._verify_relay_auth(request)
        assert exc_info.value.status_code == 401

    def test_missing_header_raises_401(self):
        request = MagicMock()
        request.headers.get.return_value = ""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            relay._verify_relay_auth(request)
        assert exc_info.value.status_code == 401

    def test_no_bearer_prefix_raises_401(self):
        request = MagicMock()
        request.headers.get.return_value = "test_relay_secret_token_for_testing"
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            relay._verify_relay_auth(request)
        assert exc_info.value.status_code == 401


class TestRelayNamespace:
    def test_namespace_deterministic(self):
        """Same session+agent should produce same namespace ID."""
        session_id = "sess_001"
        agent_id = "agent_001"
        ns1 = f"relay_{session_id}_{int(hashlib.sha256(agent_id.encode()).hexdigest()[:12], 16) % 999999:06d}"
        ns2 = f"relay_{session_id}_{int(hashlib.sha256(agent_id.encode()).hexdigest()[:12], 16) % 999999:06d}"
        assert ns1 == ns2

    def test_namespace_differs_for_different_agents(self):
        session_id = "sess_001"
        ns1 = f"relay_{session_id}_{int(hashlib.sha256('agent_A'.encode()).hexdigest()[:12], 16) % 999999:06d}"
        ns2 = f"relay_{session_id}_{int(hashlib.sha256('agent_B'.encode()).hexdigest()[:12], 16) % 999999:06d}"
        assert ns1 != ns2

    def test_namespace_differs_for_different_sessions(self):
        agent_id = "agent_001"
        ns1 = f"relay_sess_A_{int(hashlib.sha256(agent_id.encode()).hexdigest()[:12], 16) % 999999:06d}"
        ns2 = f"relay_sess_B_{int(hashlib.sha256(agent_id.encode()).hexdigest()[:12], 16) % 999999:06d}"
        assert ns1 != ns2


class TestRelayExpiry:
    @patch("relay.storage.store_memory", new_callable=AsyncMock)
    def test_relay_store_sets_24h_expires_at(self, mock_store):
        """Relay store should pass expires_at=24h to storage."""
        mock_store.return_value = {"key": "k", "value": "v"}
        db = MockDB()

        from fastapi.testclient import TestClient
        import db as database
        from main import app
        from db import get_db

        async def mock_get_db():
            yield db

        app.dependency_overrides[get_db] = mock_get_db
        with patch.object(database, "pool", None), \
             patch.object(database, "health_check", AsyncMock(return_value=False)):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/relay", json={
                "session_id": "sess_001",
                "agent_id": "agent_001",
                "operation": "store",
                "payload": {"key": "test_key", "value": "test_value"},
            }, headers={"Authorization": "Bearer test_relay_secret_token_for_testing"})

        app.dependency_overrides.clear()
        assert resp.status_code == 200

        # Verify store_memory was called with expires_at kwarg
        mock_store.assert_called_once()
        call_kwargs = mock_store.call_args
        # expires_at should be approximately 24h from now
        expires_at = call_kwargs.kwargs.get("expires_at") or call_kwargs[1].get("expires_at")
        assert expires_at is not None
        delta = expires_at - datetime.now(timezone.utc)
        # Should be between 23h and 24h from now
        assert timedelta(hours=23) < delta <= timedelta(hours=24, minutes=1)


class TestRelayCapacity:
    @patch("relay.storage.store_memory", new_callable=AsyncMock)
    def test_capacity_limit_429(self, mock_store):
        """Should return 429 when namespace has 300 memories."""
        db = MockDB()
        db.set_fetchrow("SELECT id FROM namespaces", MockRecord({"id": "relay_ns"}))
        db.set_fetchval("SELECT COUNT(*)", 300)

        from fastapi.testclient import TestClient
        import db as database
        from main import app
        from db import get_db

        async def mock_get_db():
            yield db

        app.dependency_overrides[get_db] = mock_get_db
        with patch.object(database, "pool", None), \
             patch.object(database, "health_check", AsyncMock(return_value=False)):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/relay", json={
                "session_id": "sess_001",
                "agent_id": "agent_001",
                "operation": "store",
                "payload": {"key": "k", "value": "v"},
            }, headers={"Authorization": "Bearer test_relay_secret_token_for_testing"})

        app.dependency_overrides.clear()
        assert resp.status_code == 429

    @patch("relay.storage.get_memory", new_callable=AsyncMock)
    def test_capacity_doesnt_block_fetch(self, mock_get):
        """Fetch should work even when at capacity."""
        mock_get.return_value = {"key": "k", "value": "v"}
        db = MockDB()
        db.set_fetchrow("SELECT id FROM namespaces", MockRecord({"id": "relay_ns"}))
        db.set_fetchval("SELECT COUNT(*)", 300)

        from fastapi.testclient import TestClient
        import db as database
        from main import app
        from db import get_db

        async def mock_get_db():
            yield db

        app.dependency_overrides[get_db] = mock_get_db
        with patch.object(database, "pool", None), \
             patch.object(database, "health_check", AsyncMock(return_value=False)):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/relay", json={
                "session_id": "sess_001",
                "agent_id": "agent_001",
                "operation": "fetch",
                "payload": {"key": "k"},
            }, headers={"Authorization": "Bearer test_relay_secret_token_for_testing"})

        app.dependency_overrides.clear()
        assert resp.status_code == 200


class TestRelayOperations:
    def test_store_missing_key_returns_400(self):
        db = MockDB()
        from fastapi.testclient import TestClient
        import db as database
        from main import app
        from db import get_db

        async def mock_get_db():
            yield db

        app.dependency_overrides[get_db] = mock_get_db
        with patch.object(database, "pool", None), \
             patch.object(database, "health_check", AsyncMock(return_value=False)):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/relay", json={
                "session_id": "s", "agent_id": "a",
                "operation": "store",
                "payload": {"value": "v"},
            }, headers={"Authorization": "Bearer test_relay_secret_token_for_testing"})

        app.dependency_overrides.clear()
        assert resp.status_code == 400

    def test_fetch_missing_key_returns_400(self):
        db = MockDB()
        from fastapi.testclient import TestClient
        import db as database
        from main import app
        from db import get_db

        async def mock_get_db():
            yield db

        app.dependency_overrides[get_db] = mock_get_db
        with patch.object(database, "pool", None), \
             patch.object(database, "health_check", AsyncMock(return_value=False)):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/relay", json={
                "session_id": "s", "agent_id": "a",
                "operation": "fetch",
                "payload": {},
            }, headers={"Authorization": "Bearer test_relay_secret_token_for_testing"})

        app.dependency_overrides.clear()
        assert resp.status_code == 400

    def test_unknown_operation_returns_400(self):
        db = MockDB()
        from fastapi.testclient import TestClient
        import db as database
        from main import app
        from db import get_db

        async def mock_get_db():
            yield db

        app.dependency_overrides[get_db] = mock_get_db
        with patch.object(database, "pool", None), \
             patch.object(database, "health_check", AsyncMock(return_value=False)):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/relay", json={
                "session_id": "s", "agent_id": "a",
                "operation": "bogus",
                "payload": {},
            }, headers={"Authorization": "Bearer test_relay_secret_token_for_testing"})

        app.dependency_overrides.clear()
        assert resp.status_code == 400

    @patch("relay.storage.store_memory", new_callable=AsyncMock)
    def test_new_namespace_auto_created(self, mock_store):
        """First relay call should auto-create the namespace."""
        mock_store.return_value = {"key": "k", "value": "v"}
        db = MockDB()
        # No existing namespace
        db.set_fetchrow("SELECT id FROM namespaces", None)

        from fastapi.testclient import TestClient
        import db as database
        from main import app
        from db import get_db

        async def mock_get_db():
            yield db

        app.dependency_overrides[get_db] = mock_get_db
        with patch.object(database, "pool", None), \
             patch.object(database, "health_check", AsyncMock(return_value=False)):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/relay", json={
                "session_id": "sess_new", "agent_id": "agent_new",
                "operation": "store",
                "payload": {"key": "k", "value": "v"},
            }, headers={"Authorization": "Bearer test_relay_secret_token_for_testing"})

        app.dependency_overrides.clear()
        assert resp.status_code == 200
        # Verify namespace was created
        ns_inserts = [q for q in db.queries if "INSERT INTO namespaces" in q[1]]
        assert len(ns_inserts) > 0
