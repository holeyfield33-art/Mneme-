"""Auth module — API key generation, hashing, and lookup tests.

Tests:
  - Key generation format (mneme_f_ / mneme_p_ prefix)
  - Argon2id hash verification
  - Key prefix extraction
  - Personal mode authentication
  - Namespace lookup with mock DB
  - Invalid key rejection
"""
import pytest
import secrets
from unittest.mock import AsyncMock, patch, MagicMock
from tests import MockDB, MockRecord

import auth


class TestKeyGeneration:
    def test_free_key_prefix(self):
        raw, hashed = auth.generate_api_key("free")
        assert raw.startswith("mneme_f_")

    def test_premium_key_prefix(self):
        raw, hashed = auth.generate_api_key("premium")
        assert raw.startswith("mneme_p_")

    def test_key_length_reasonable(self):
        raw, _ = auth.generate_api_key("free")
        assert len(raw) > 40  # prefix + 40 bytes base64

    def test_hash_is_argon2(self):
        _, hashed = auth.generate_api_key("free")
        assert hashed.startswith("$argon2")

    def test_hash_verifies_against_raw(self):
        raw, hashed = auth.generate_api_key("free")
        assert auth.ph.verify(hashed, raw) is True

    def test_different_keys_each_time(self):
        raw1, _ = auth.generate_api_key("free")
        raw2, _ = auth.generate_api_key("free")
        assert raw1 != raw2

    def test_hash_differs_even_for_same_tier(self):
        _, h1 = auth.generate_api_key("free")
        _, h2 = auth.generate_api_key("free")
        assert h1 != h2

    def test_prefix_extraction_9_chars(self):
        raw, _ = auth.generate_api_key("free")
        prefix = raw[:9]
        assert len(prefix) == 9
        assert prefix.startswith("mneme_f_")


class TestPersonalMode:
    @pytest.mark.asyncio
    async def test_personal_mode_returns_premium(self):
        db = MockDB()
        with patch.object(auth, "env") as mock_env:
            mock_env.PERSONAL_MODE = True
            mock_env.PERSONAL_API_KEY = "my_personal_key"
            result = await auth.get_namespace_from_key("my_personal_key", db)
            assert result is not None
            assert result["tier"] == "premium"
            assert result["id"] == "personal"

    @pytest.mark.asyncio
    async def test_personal_mode_rejects_wrong_key(self):
        db = MockDB()
        with patch.object(auth, "env") as mock_env:
            mock_env.PERSONAL_MODE = True
            mock_env.PERSONAL_API_KEY = "correct_key"
            result = await auth.get_namespace_from_key("wrong_key", db)
            # Falls through to DB lookup, returns None from empty mock
            assert result is None


class TestNamespaceLookup:
    @pytest.mark.asyncio
    async def test_valid_key_returns_namespace(self):
        raw, hashed = auth.generate_api_key("free")
        prefix = raw[:9]
        namespace = MockRecord({
            "id": "ns_test", "tier": "free", "is_active": True, "email": "t@t.com"
        })
        key_row = MockRecord({
            "id": "key_001", "key_hash": hashed, "key_prefix": prefix,
            "namespace_id": "ns_test", "revoked_at": None
        })

        db = MockDB()
        db.set_fetch("api_keys", [key_row])
        db.set_fetchrow("namespaces", namespace)

        with patch.object(auth, "env") as mock_env:
            mock_env.PERSONAL_MODE = False
            result = await auth.get_namespace_from_key(raw, db)
            assert result is not None
            assert result["id"] == "ns_test"

    @pytest.mark.asyncio
    async def test_invalid_key_returns_none(self):
        db = MockDB()
        db.set_fetch("api_keys", [])

        with patch.object(auth, "env") as mock_env:
            mock_env.PERSONAL_MODE = False
            result = await auth.get_namespace_from_key("mneme_f_invalid_key_here", db)
            assert result is None

    @pytest.mark.asyncio
    async def test_revoked_key_not_returned(self):
        """Keys with revoked_at set should not be in query results (filtered by SQL)."""
        db = MockDB()
        db.set_fetch("api_keys", [])  # No non-revoked keys

        with patch.object(auth, "env") as mock_env:
            mock_env.PERSONAL_MODE = False
            result = await auth.get_namespace_from_key("mneme_f_some_key", db)
            assert result is None

    @pytest.mark.asyncio
    async def test_short_key_handled(self):
        db = MockDB()
        db.set_fetch("api_keys", [])

        with patch.object(auth, "env") as mock_env:
            mock_env.PERSONAL_MODE = False
            result = await auth.get_namespace_from_key("short", db)
            assert result is None
