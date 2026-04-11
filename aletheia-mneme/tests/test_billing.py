"""Billing module — checkout, webhook, idempotency, and email tests.

Tests:
  - Checkout creates namespace + free key
  - Checkout validates email format
  - Checkout sends Stripe session + email
  - Webhook handles checkout.session.completed
  - Webhook handles customer.subscription.deleted
  - Webhook idempotency via processed_events
  - Webhook signature verification
  - Webhook internal error returns success (Stripe retry safety)
  - Premium key generation on upgrade
  - Downgrade revokes premium keys
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from tests import MockDB, MockRecord

import auth
import billing


class TestCheckoutFlow:
    @pytest.mark.asyncio
    @patch("billing.stripe.checkout.Session.create")
    @patch("billing.em.send_free_key")
    async def test_checkout_creates_namespace(self, mock_email, mock_stripe):
        mock_stripe.return_value = MagicMock(url="https://stripe.com/test")
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
            resp = client.post("/billing/checkout", json={"email": "user@test.com"})

        app.dependency_overrides.clear()
        assert resp.status_code == 200
        # Verify namespace was inserted
        ns_inserts = [q for q in db.queries if "INSERT INTO namespaces" in q[1]]
        assert len(ns_inserts) > 0
        # Verify api_key was inserted
        key_inserts = [q for q in db.queries if "INSERT INTO api_keys" in q[1]]
        assert len(key_inserts) > 0

    @pytest.mark.asyncio
    @patch("billing.stripe.checkout.Session.create")
    @patch("billing.em.send_free_key")
    async def test_checkout_returns_free_key(self, mock_email, mock_stripe):
        mock_stripe.return_value = MagicMock(url="https://stripe.com/test")
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
            resp = client.post("/billing/checkout", json={"email": "user@test.com"})

        app.dependency_overrides.clear()
        data = resp.json()
        assert data["api_key"].startswith("mneme_f_")
        assert "checkout_url" in data

    @pytest.mark.asyncio
    @patch("billing.stripe.checkout.Session.create")
    @patch("billing.em.send_free_key")
    async def test_checkout_sends_email(self, mock_email, mock_stripe):
        mock_stripe.return_value = MagicMock(url="https://stripe.com/test")
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
            client.post("/billing/checkout", json={"email": "user@test.com"})

        app.dependency_overrides.clear()
        mock_email.assert_called_once()
        call_args = mock_email.call_args
        assert call_args[0][0] == "user@test.com"

    def test_checkout_rejects_empty_email(self):
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
            resp = client.post("/billing/checkout", json={"email": ""})

        app.dependency_overrides.clear()
        assert resp.status_code == 400

    def test_checkout_rejects_no_at_sign(self):
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
            resp = client.post("/billing/checkout", json={"email": "no-at-sign"})

        app.dependency_overrides.clear()
        assert resp.status_code == 400


class TestWebhookProcessing:
    @patch("billing.stripe.Webhook.construct_event")
    @patch("billing.em.send_premium_upgrade")
    def test_upgrade_creates_premium_key(self, mock_email, mock_construct):
        mock_construct.return_value = {
            "id": "evt_upgrade_001",
            "type": "checkout.session.completed",
            "data": {"object": {"metadata": {"namespace_id": "ns_test"}, "customer_email": "u@t.com"}},
        }
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
            resp = client.post("/billing/webhook", content=b"payload",
                               headers={"stripe-signature": "sig"})

        app.dependency_overrides.clear()
        assert resp.status_code == 200
        # Verify namespace upgraded
        tier_updates = [q for q in db.queries if "tier='premium'" in q[1]]
        assert len(tier_updates) > 0
        # Verify premium key inserted
        key_inserts = [q for q in db.queries if "INSERT INTO api_keys" in q[1]]
        assert len(key_inserts) > 0

    @patch("billing.stripe.Webhook.construct_event")
    @patch("billing.em.send_downgrade")
    def test_downgrade_revokes_premium_keys(self, mock_email, mock_construct):
        mock_construct.return_value = {
            "id": "evt_downgrade_001",
            "type": "customer.subscription.deleted",
            "data": {"object": {"metadata": {"namespace_id": "ns_test"}}},
        }
        db = MockDB()
        db.set_fetchrow("SELECT email", MockRecord({"email": "u@t.com"}))

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
            resp = client.post("/billing/webhook", content=b"payload",
                               headers={"stripe-signature": "sig"})

        app.dependency_overrides.clear()
        assert resp.status_code == 200
        # Verify premium keys revoked
        revoke_queries = [q for q in db.queries if "revoked_at" in q[1]]
        assert len(revoke_queries) > 0
        mock_email.assert_called_once_with("u@t.com")

    @patch("billing.stripe.Webhook.construct_event")
    def test_idempotency_prevents_double_processing(self, mock_construct):
        mock_construct.return_value = {
            "id": "evt_dup",
            "type": "checkout.session.completed",
            "data": {"object": {"metadata": {"namespace_id": "ns_test"}, "customer_email": ""}},
        }
        db = MockDB()
        db.set_fetchrow("processed_events", MockRecord({"id": "evt_dup"}))

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
            resp = client.post("/billing/webhook", content=b"payload",
                               headers={"stripe-signature": "sig"})

        app.dependency_overrides.clear()
        assert resp.json()["status"] == "already_handled"
        # No namespace update should have occurred
        tier_updates = [q for q in db.queries if "tier='premium'" in q[1]]
        assert len(tier_updates) == 0

    @patch("billing.stripe.Webhook.construct_event")
    def test_webhook_processing_error_still_returns_success(self, mock_construct):
        """Internal processing error should not cause Stripe retry storms."""
        mock_construct.return_value = {
            "id": "evt_error_001",
            "type": "checkout.session.completed",
            "data": {"object": {"metadata": {"namespace_id": "ns_test"}, "customer_email": "u@t.com"}},
        }
        db = MockDB()

        # Make the namespace update fail
        original_execute = db.execute
        call_count = 0
        async def failing_execute(query, *args):
            nonlocal call_count
            call_count += 1
            if "tier='premium'" in query:
                raise RuntimeError("DB connection lost")
            return await original_execute(query, *args)

        db.execute = failing_execute

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
            resp = client.post("/billing/webhook", content=b"payload",
                               headers={"stripe-signature": "sig"})

        app.dependency_overrides.clear()
        # Should still return 200 even though processing failed
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_webhook_bad_signature_returns_400(self):
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
            resp = client.post("/billing/webhook", content=b"payload",
                               headers={"stripe-signature": "bad"})

        app.dependency_overrides.clear()
        assert resp.status_code == 400


class TestKeyGeneration:
    def test_free_key_has_f_prefix(self):
        raw, _ = auth.generate_api_key("free")
        assert raw.startswith("mneme_f_")

    def test_premium_key_has_p_prefix(self):
        raw, _ = auth.generate_api_key("premium")
        assert raw.startswith("mneme_p_")

    def test_prefix_extraction_matches(self):
        raw, _ = auth.generate_api_key("free")
        assert raw[:9] == "mneme_f_" + raw[8]

    def test_key_is_unique(self):
        keys = {auth.generate_api_key("free")[0] for _ in range(10)}
        assert len(keys) == 10
