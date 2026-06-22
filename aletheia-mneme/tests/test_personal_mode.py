"""Personal mode lifespan bootstrap tests.

Tests:
  - lifespan inserts 'personal' namespace row when PERSONAL_MODE=true
  - INSERT uses ON CONFLICT DO NOTHING (idempotent — called twice safely)
  - lifespan raises when PERSONAL_MODE=true but PERSONAL_API_KEY is absent
  - lifespan skips bootstrap entirely when PERSONAL_MODE=false
  - bootstrap row has tier='premium' and is_active=TRUE
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from tests import MockDB


class TestPersonalModeBootstrap:
    @pytest.mark.asyncio
    async def test_bootstrap_executes_insert_when_personal_mode_on(self):
        """Lifespan must run the personal namespace INSERT when PERSONAL_MODE=true."""
        mock_pool = MagicMock()
        mock_conn = MockDB()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        import main
        import db as database
        import env as env_module

        with patch.object(env_module, "PERSONAL_MODE", True), \
             patch.object(env_module, "PERSONAL_API_KEY", "test_key"), \
             patch.object(env_module, "DATABASE_URL", "postgresql://x"), \
             patch("main.database.init_pool", AsyncMock()), \
             patch("main.database.close_pool", AsyncMock()), \
             patch.object(database, "pool", mock_pool):

            app_gen = main.lifespan(main.app)
            await app_gen.__aenter__()
            await app_gen.__aexit__(None, None, None)

        insert_queries = [
            q for (kind, q, _) in mock_conn.queries
            if kind == "execute" and "INSERT INTO namespaces" in q
        ]
        assert len(insert_queries) == 1
        assert "'personal'" in insert_queries[0]
        assert "ON CONFLICT" in insert_queries[0]
        assert "'premium'" in insert_queries[0]

    @pytest.mark.asyncio
    async def test_bootstrap_is_idempotent(self):
        """Calling lifespan twice must not error — ON CONFLICT DO NOTHING absorbs duplicates."""
        mock_pool = MagicMock()
        mock_conn = MockDB()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        import main
        import db as database
        import env as env_module

        with patch.object(env_module, "PERSONAL_MODE", True), \
             patch.object(env_module, "PERSONAL_API_KEY", "test_key"), \
             patch.object(env_module, "DATABASE_URL", "postgresql://x"), \
             patch("main.database.init_pool", AsyncMock()), \
             patch("main.database.close_pool", AsyncMock()), \
             patch.object(database, "pool", mock_pool):

            for _ in range(2):
                app_gen = main.lifespan(main.app)
                await app_gen.__aenter__()
                await app_gen.__aexit__(None, None, None)

        insert_queries = [
            q for (kind, q, _) in mock_conn.queries
            if kind == "execute" and "INSERT INTO namespaces" in q
        ]
        # Both lifetimes ran; each should have triggered exactly one INSERT
        assert len(insert_queries) == 2

    @pytest.mark.asyncio
    async def test_bootstrap_skipped_when_personal_mode_off(self):
        """No namespace INSERT should happen when PERSONAL_MODE=false."""
        mock_pool = MagicMock()
        mock_conn = MockDB()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        import main
        import db as database
        import env as env_module

        with patch.object(env_module, "PERSONAL_MODE", False), \
             patch.object(env_module, "DATABASE_URL", "postgresql://x"), \
             patch("main.database.init_pool", AsyncMock()), \
             patch("main.database.close_pool", AsyncMock()), \
             patch.object(database, "pool", mock_pool):

            app_gen = main.lifespan(main.app)
            await app_gen.__aenter__()
            await app_gen.__aexit__(None, None, None)

        insert_queries = [
            q for (kind, q, _) in mock_conn.queries
            if kind == "execute" and "INSERT INTO namespaces" in q
        ]
        assert insert_queries == []

    @pytest.mark.asyncio
    async def test_missing_personal_api_key_raises(self):
        """RuntimeError must be raised if PERSONAL_MODE=true but PERSONAL_API_KEY is empty."""
        import main
        import env as env_module

        with patch.object(env_module, "PERSONAL_MODE", True), \
             patch.object(env_module, "PERSONAL_API_KEY", ""), \
             patch.object(env_module, "DATABASE_URL", "postgresql://x"), \
             patch("main.database.init_pool", AsyncMock()), \
             patch("main.database.close_pool", AsyncMock()):

            with pytest.raises(RuntimeError, match="PERSONAL_API_KEY"):
                app_gen = main.lifespan(main.app)
                await app_gen.__aenter__()

    @pytest.mark.asyncio
    async def test_bootstrap_row_has_premium_tier(self):
        """The INSERT must set tier='premium' so personal namespace passes premium gating."""
        mock_pool = MagicMock()
        mock_conn = MockDB()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

        import main
        import db as database
        import env as env_module

        with patch.object(env_module, "PERSONAL_MODE", True), \
             patch.object(env_module, "PERSONAL_API_KEY", "any_key"), \
             patch.object(env_module, "DATABASE_URL", "postgresql://x"), \
             patch("main.database.init_pool", AsyncMock()), \
             patch("main.database.close_pool", AsyncMock()), \
             patch.object(database, "pool", mock_pool):

            app_gen = main.lifespan(main.app)
            await app_gen.__aenter__()
            await app_gen.__aexit__(None, None, None)

        insert_sql = next(
            q for (kind, q, _) in mock_conn.queries
            if kind == "execute" and "INSERT INTO namespaces" in q
        )
        assert "'premium'" in insert_sql
        assert "TRUE" in insert_sql
