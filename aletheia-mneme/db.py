"""Database pool management — shared dependency for all routers."""

import asyncpg
import structlog

log = structlog.get_logger()

pool: asyncpg.Pool | None = None


async def _init_connection(conn):
    """Register pgvector type codec on each new connection."""
    from pgvector.asyncpg import register_vector
    await register_vector(conn)


async def init_pool(dsn: str):
    global pool
    pool = await asyncpg.create_pool(
        dsn, min_size=2, max_size=10,
        init=_init_connection
    )
    log.info("database_pool_initialized")


async def close_pool():
    global pool
    if pool:
        await pool.close()
        pool = None
        log.info("database_pool_closed")


async def get_db():
    async with pool.acquire() as conn:
        yield conn


async def health_check() -> bool:
    """Verify database connectivity."""
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception:
        return False
