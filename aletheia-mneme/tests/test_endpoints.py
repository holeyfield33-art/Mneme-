"""Endpoint E2E tests — signup, relay, sync, and health.

Tests:
  - GET /health
  - POST /signup (valid + invalid email)
  - POST /relay (store, fetch, search, capacity limit, auth rejection)
  - POST /sync/push (SSRF validation, missing fields)
  - POST /sync/receive (conflict strategies)
  - MCP auth middleware (401 for unauthenticated)
"""
import pytest
import json
import time
from unittest.mock import AsyncMock, patch, MagicMock, PropertyMock
from datetime import datetime, timezone
from tests import MockDB, MockRecord

from fastapi.testclient import TestClient


# ── App Fixture ──────────────────────────────────────────────

@pytest.fixture
def app_client():
    """Create a FastAPI TestClient with mocked database."""
    # Must import after env vars are set (done in tests/__init__.py)
    import db as database
    from main import app
    from db import get_db

    mock_db = MockDB()

    async def mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = mock_get_db

    # Mock the database pool for health check and MCP
    with patch.object(database, "pool", None):
        with patch.object(database, "health_check", AsyncMock(return_value=False)):
            client = TestClient(app, raise_server_exceptions=False)
            yield client, mock_db

    app.dependency_overrides.clear()


# ── Health Endpoint ──────────────────────────────────────────

class TestHealthEndpoint:
    def test_health_returns_product(self, app_client):
        client, _ = app_client
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["product"] == "Aletheia Mneme"
        assert data["version"] == "1.0.0"

    def test_health_shows_degraded_without_db(self, app_client):
        client, _ = app_client
        resp = client.get("/health")
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["database"] == "disconnected"


# ── Signup ───────────────────────────────────────────────────

class TestSignup:
    @patch("signup.em.send_api_key")
    def test_signup_valid_email(self, mock_email, app_client):
        client, mock_db = app_client

        resp = client.post("/signup", json={"email": "user@example.com"})
        assert resp.status_code == 200
        data = resp.json()
        assert "api_key" in data
        assert "namespace_id" in data
        assert data["api_key"].startswith("mneme_p_")
        mock_email.assert_called_once()

    def test_signup_invalid_email(self, app_client):
        client, _ = app_client
        resp = client.post("/signup", json={"email": "not-an-email"})
        assert resp.status_code == 400

    def test_signup_missing_email(self, app_client):
        client, _ = app_client
        resp = client.post("/signup", json={})
        assert resp.status_code == 400


# ── Relay Endpoint ───────────────────────────────────────────

class TestRelayEndpoint:
    def _relay_headers(self):
        return {"Authorization": "Bearer test_relay_secret_token_for_testing"}

    @patch("relay.storage.store_memory", new_callable=AsyncMock)
    def test_relay_store(self, mock_store, app_client):
        client, mock_db = app_client
        mock_store.return_value = {"key": "test", "value": "data"}

        resp = client.post("/relay", json={
            "session_id": "sess_001",
            "agent_id": "agent_001",
            "operation": "store",
            "payload": {"key": "test", "value": "data"},
        }, headers=self._relay_headers())
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @patch("relay.storage.get_memory", new_callable=AsyncMock)
    def test_relay_fetch(self, mock_get, app_client):
        client, mock_db = app_client
        mock_get.return_value = {"key": "test", "value": "data"}

        resp = client.post("/relay", json={
            "session_id": "sess_001",
            "agent_id": "agent_001",
            "operation": "fetch",
            "payload": {"key": "test"},
        }, headers=self._relay_headers())
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @patch("relay.storage.keyword_search", new_callable=AsyncMock)
    def test_relay_search(self, mock_search, app_client):
        client, mock_db = app_client
        mock_search.return_value = [{"key": "test", "value": "data"}]

        resp = client.post("/relay", json={
            "session_id": "sess_001",
            "agent_id": "agent_001",
            "operation": "search",
            "payload": {"query": "test query"},
        }, headers=self._relay_headers())
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_relay_store_missing_payload_key(self, app_client):
        client, mock_db = app_client
        resp = client.post("/relay", json={
            "session_id": "sess_001",
            "agent_id": "agent_001",
            "operation": "store",
            "payload": {"value": "data"},  # missing 'key'
        }, headers=self._relay_headers())
        assert resp.status_code == 400

    def test_relay_fetch_missing_key(self, app_client):
        client, mock_db = app_client
        resp = client.post("/relay", json={
            "session_id": "sess_001",
            "agent_id": "agent_001",
            "operation": "fetch",
            "payload": {},  # missing 'key'
        }, headers=self._relay_headers())
        assert resp.status_code == 400

    def test_relay_search_missing_query(self, app_client):
        client, mock_db = app_client
        resp = client.post("/relay", json={
            "session_id": "sess_001",
            "agent_id": "agent_001",
            "operation": "search",
            "payload": {},  # missing 'query'
        }, headers=self._relay_headers())
        assert resp.status_code == 400

    def test_relay_unknown_operation(self, app_client):
        client, mock_db = app_client
        resp = client.post("/relay", json={
            "session_id": "sess_001",
            "agent_id": "agent_001",
            "operation": "unknown_op",
            "payload": {},
        }, headers=self._relay_headers())
        assert resp.status_code == 400

    def test_relay_unauthorized(self, app_client):
        client, _ = app_client
        resp = client.post("/relay", json={
            "session_id": "sess_001",
            "operation": "store",
            "payload": {"key": "t", "value": "v"},
        }, headers={"Authorization": "Bearer wrong_token"})
        assert resp.status_code == 401

    def test_relay_no_auth_header(self, app_client):
        client, _ = app_client
        resp = client.post("/relay", json={
            "session_id": "sess_001",
            "operation": "store",
            "payload": {"key": "t", "value": "v"},
        })
        assert resp.status_code == 401

    @patch("relay.storage.store_memory", new_callable=AsyncMock)
    def test_relay_capacity_limit(self, mock_store, app_client):
        client, mock_db = app_client
        mock_db.set_fetchrow("SELECT id FROM namespaces", MockRecord({"id": "relay_ns"}))
        mock_db.set_fetchval("SELECT COUNT(*)", 300)

        resp = client.post("/relay", json={
            "session_id": "sess_001",
            "agent_id": "agent_001",
            "operation": "store",
            "payload": {"key": "k", "value": "v"},
        }, headers=self._relay_headers())
        assert resp.status_code == 429


# ── Sync SSRF Prevention ────────────────────────────────────

class TestSyncSSRF:
    """Sync endpoints now require auth. Mock auth to test SSRF validation."""

    @patch("sync.get_namespace_from_key", new_callable=AsyncMock,
           return_value={"id": "ns_1", "tier": "premium", "is_active": True})
    def test_sync_push_rejects_http(self, mock_auth, app_client):
        client, _ = app_client
        resp = client.post("/sync/push", json={
            "target_url": "http://evil.com",
            "namespace_id": "ns_1",
        }, headers={"Authorization": "Bearer valid_key"})
        assert resp.status_code == 400
        assert "HTTPS" in resp.json()["detail"]

    @patch("sync.get_namespace_from_key", new_callable=AsyncMock,
           return_value={"id": "ns_1", "tier": "premium", "is_active": True})
    def test_sync_push_rejects_localhost(self, mock_auth, app_client):
        client, _ = app_client
        resp = client.post("/sync/push", json={
            "target_url": "https://localhost",
            "namespace_id": "ns_1",
        }, headers={"Authorization": "Bearer valid_key"})
        assert resp.status_code == 400

    @patch("sync.get_namespace_from_key", new_callable=AsyncMock,
           return_value={"id": "ns_1", "tier": "premium", "is_active": True})
    def test_sync_push_rejects_private_ip(self, mock_auth, app_client):
        client, _ = app_client
        resp = client.post("/sync/push", json={
            "target_url": "https://192.168.1.1",
            "namespace_id": "ns_1",
        }, headers={"Authorization": "Bearer valid_key"})
        assert resp.status_code == 400

    @patch("sync.get_namespace_from_key", new_callable=AsyncMock,
           return_value={"id": "ns_1", "tier": "premium", "is_active": True})
    def test_sync_push_rejects_loopback(self, mock_auth, app_client):
        client, _ = app_client
        resp = client.post("/sync/push", json={
            "target_url": "https://127.0.0.1",
            "namespace_id": "ns_1",
        }, headers={"Authorization": "Bearer valid_key"})
        assert resp.status_code == 400

    @patch("sync.get_namespace_from_key", new_callable=AsyncMock,
           return_value={"id": "ns_1", "tier": "premium", "is_active": True})
    def test_sync_push_rejects_metadata(self, mock_auth, app_client):
        client, _ = app_client
        resp = client.post("/sync/push", json={
            "target_url": "https://metadata.google.internal",
            "namespace_id": "ns_1",
        }, headers={"Authorization": "Bearer valid_key"})
        assert resp.status_code == 400

    @patch("sync.get_namespace_from_key", new_callable=AsyncMock,
           return_value={"id": "ns_1", "tier": "premium", "is_active": True})
    def test_sync_push_missing_target_url(self, mock_auth, app_client):
        client, _ = app_client
        resp = client.post("/sync/push", json={"namespace_id": "ns_1"},
                           headers={"Authorization": "Bearer valid_key"})
        assert resp.status_code == 400

    @patch("sync.get_namespace_from_key", new_callable=AsyncMock,
           return_value={"id": "ns_1", "tier": "premium", "is_active": True})
    def test_sync_push_missing_namespace(self, mock_auth, app_client):
        client, _ = app_client
        resp = client.post("/sync/push", json={
            "target_url": "https://remote.example.com",
        }, headers={"Authorization": "Bearer valid_key"})
        assert resp.status_code == 400

    def test_sync_push_no_auth_returns_401(self, app_client):
        client, _ = app_client
        resp = client.post("/sync/push", json={
            "target_url": "https://example.com",
            "namespace_id": "ns_1",
        })
        assert resp.status_code == 401

    def test_sync_receive_no_auth_returns_401(self, app_client):
        client, _ = app_client
        resp = client.post("/sync/receive", json={
            "source_memories": [],
            "namespace_id": "ns_1",
        })
        assert resp.status_code == 401

    @patch("sync.get_namespace_from_key", new_callable=AsyncMock,
           return_value={"id": "ns_1", "tier": "premium", "is_active": True})
    def test_sync_push_namespace_mismatch_returns_403(self, mock_auth, app_client):
        client, _ = app_client
        resp = client.post("/sync/push", json={
            "target_url": "https://remote.example.com",
            "namespace_id": "ns_OTHER",
        }, headers={"Authorization": "Bearer valid_key"})
        assert resp.status_code == 403


# ── Sync Receive ─────────────────────────────────────────────

class TestSyncReceive:
    @patch("sync.get_namespace_from_key", new_callable=AsyncMock,
           return_value={"id": "ns_1", "tier": "premium", "is_active": True})
    @patch("sync.storage.get_memory", new_callable=AsyncMock)
    @patch("sync.storage.store_memory", new_callable=AsyncMock)
    def test_receive_new_memories(self, mock_store, mock_get, mock_auth, app_client):
        client, _ = app_client
        mock_get.return_value = None  # No existing
        mock_store.return_value = {"key": "k1", "value": "v1"}

        resp = client.post("/sync/receive", json={
            "source_memories": [
                {"key": "k1", "value": "v1", "category": "general", "version": 1},
            ],
            "namespace_id": "ns_1",
            "conflict_strategy": "highest_version_wins",
        }, headers={"Authorization": "Bearer valid_key"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["received"] == 1
        assert data["written"] == 1

    @patch("sync.get_namespace_from_key", new_callable=AsyncMock,
           return_value={"id": "ns_1", "tier": "premium", "is_active": True})
    @patch("sync.storage.get_memory", new_callable=AsyncMock)
    @patch("sync.storage.update_memory", new_callable=AsyncMock)
    def test_receive_source_wins_strategy(self, mock_update, mock_get, mock_auth, app_client):
        client, _ = app_client
        mock_get.return_value = {"key": "k1", "value": "old", "version": 5}
        mock_update.return_value = {"key": "k1", "value": "new"}

        resp = client.post("/sync/receive", json={
            "source_memories": [
                {"key": "k1", "value": "new", "category": "general", "version": 1},
            ],
            "namespace_id": "ns_1",
            "conflict_strategy": "source_wins",
        }, headers={"Authorization": "Bearer valid_key"})
        assert resp.status_code == 200
        assert resp.json()["written"] == 1

    @patch("sync.get_namespace_from_key", new_callable=AsyncMock,
           return_value={"id": "ns_1", "tier": "premium", "is_active": True})
    @patch("sync.storage.get_memory", new_callable=AsyncMock)
    def test_receive_highest_version_skips_older(self, mock_get, mock_auth, app_client):
        client, _ = app_client
        mock_get.return_value = {"key": "k1", "value": "newer", "version": 5}

        resp = client.post("/sync/receive", json={
            "source_memories": [
                {"key": "k1", "value": "older", "category": "general", "version": 2},
            ],
            "namespace_id": "ns_1",
            "conflict_strategy": "highest_version_wins",
        }, headers={"Authorization": "Bearer valid_key"})
        assert resp.status_code == 200
        assert resp.json()["written"] == 0

    @patch("sync.get_namespace_from_key", new_callable=AsyncMock,
           return_value={"id": "ns_1", "tier": "premium", "is_active": True})
    def test_receive_invalid_conflict_strategy(self, mock_auth, app_client):
        client, _ = app_client
        resp = client.post("/sync/receive", json={
            "source_memories": [],
            "namespace_id": "ns_1",
            "conflict_strategy": "invalid_strategy",
        }, headers={"Authorization": "Bearer valid_key"})
        assert resp.status_code == 400

    @patch("sync.get_namespace_from_key", new_callable=AsyncMock,
           return_value={"id": "ns_1", "tier": "premium", "is_active": True})
    def test_receive_namespace_mismatch_returns_403(self, mock_auth, app_client):
        client, _ = app_client
        resp = client.post("/sync/receive", json={
            "source_memories": [],
            "namespace_id": "ns_OTHER",
            "conflict_strategy": "highest_version_wins",
        }, headers={"Authorization": "Bearer valid_key"})
        assert resp.status_code == 403
