from contextvars import ContextVar
from mcp.server.fastmcp import FastMCP
import storage

mcp = FastMCP("Aletheia Mneme")

# Set by auth middleware in main.py before each tool invocation
current_namespace: ContextVar[dict] = ContextVar("current_namespace")
current_db: ContextVar = ContextVar("current_db")


def _ns() -> dict:
    return current_namespace.get()


def _db():
    return current_db.get()


def _require_premium():
    ns = _ns()
    if ns["tier"] != "premium":
        raise ValueError("Premium subscription required for this tool")


# ── FREE TOOLS (8) ──────────────────────────────────────────

@mcp.tool()
async def store_memory(key: str, value: str, category: str = "general") -> dict:
    """Store a memory. Available on free and premium tiers."""
    ns = _ns()
    return await storage.store_memory(ns["id"], key, value, category, "user", _db())


@mcp.tool()
async def get_memory(key: str) -> dict:
    """Retrieve a memory by key."""
    ns = _ns()
    result = await storage.get_memory(ns["id"], key, _db())
    return result or {"error": "Memory not found"}


@mcp.tool()
async def list_memories(category: str = None, limit: int = 50) -> list:
    """List memories. Free tier limited to 50."""
    ns = _ns()
    max_limit = 50 if ns["tier"] == "free" else limit
    return await storage.list_memories(ns["id"], category, max_limit, 0, _db())


@mcp.tool()
async def search_memory(query: str, limit: int = 10) -> list:
    """Keyword search. Free tier only."""
    ns = _ns()
    return await storage.keyword_search(ns["id"], query, limit, _db())


@mcp.tool()
async def forget_memory(key: str) -> dict:
    """Soft delete a memory."""
    ns = _ns()
    deleted = await storage.forget_memory(ns["id"], key, _db())
    return {"deleted": deleted, "key": key}


@mcp.tool()
async def update_memory(key: str, value: str) -> dict:
    """Update a memory value."""
    ns = _ns()
    return await storage.update_memory(ns["id"], key, value, _db())


@mcp.tool()
async def reinforce(key: str, amount: float = 0.1) -> dict:
    """Increase confidence score for a memory."""
    ns = _ns()
    return await storage.reinforce_memory(ns["id"], key, amount, _db())


@mcp.tool()
async def get_stats() -> dict:
    """Return usage stats and tier info."""
    ns = _ns()
    db = _db()
    total = await db.fetchval(
        "SELECT COUNT(*) FROM memories WHERE namespace_id=$1 AND is_deleted=FALSE", ns["id"]
    )
    categories = await db.fetch(
        "SELECT category, COUNT(*) as count FROM memories "
        "WHERE namespace_id=$1 AND is_deleted=FALSE GROUP BY category",
        ns["id"]
    )
    return {
        "namespace_id": ns["id"],
        "tier": ns["tier"],
        "total_memories": total,
        "categories": {r["category"]: r["count"] for r in categories},
    }


# ── PREMIUM TOOLS (8) ────────────────────────────────────────

@mcp.tool()
async def semantic_search(query: str, limit: int = 10) -> list:
    """Vector cosine similarity search. Premium only."""
    _require_premium()
    ns = _ns()
    return await storage.semantic_search(ns["id"], query, limit, _db())


@mcp.tool()
async def relate_memories(from_key: str, to_key: str, rel_type: str) -> dict:
    """Create a relationship between two memories. Premium only."""
    _require_premium()
    ns = _ns()
    return await storage.relate_memories(ns["id"], from_key, to_key, rel_type, _db())


@mcp.tool()
async def get_related(key: str) -> list:
    """Get memories related to a key. Premium only."""
    _require_premium()
    ns = _ns()
    return await storage.get_related_memories(ns["id"], key, _db())


@mcp.tool()
async def memory_history(key: str) -> list:
    """Get full edit history for a memory. Premium only."""
    _require_premium()
    ns = _ns()
    return await storage.get_memory_history(ns["id"], key, _db())


@mcp.tool()
async def rollback_memory(key: str, version: int) -> dict:
    """Restore a previous version. Premium only."""
    _require_premium()
    ns = _ns()
    return await storage.rollback_memory(ns["id"], key, version, _db())


@mcp.tool()
async def export_memories() -> list:
    """Export all memories as JSON. Premium only."""
    _require_premium()
    ns = _ns()
    return await storage.export_memories(ns["id"], _db())


@mcp.tool()
async def verify_memory(key: str) -> dict:
    """Verify Helios cryptographic integrity. Premium only."""
    _require_premium()
    ns = _ns()
    return await storage.verify_memory_helios(ns["id"], key, _db())


@mcp.tool()
async def cloud_sync(target_url: str, direction: str = "push",
                     conflict_strategy: str = "highest_version_wins") -> dict:
    """Push or pull memories to another Mneme instance. Premium only."""
    _require_premium()
    from sync import _validate_sync_url, VALID_CONFLICT_STRATEGIES
    _validate_sync_url(target_url)
    if conflict_strategy not in VALID_CONFLICT_STRATEGIES:
        raise ValueError(f"Invalid conflict_strategy. Must be one of: {', '.join(sorted(VALID_CONFLICT_STRATEGIES))}")
    if direction not in ("push", "pull"):
        raise ValueError(f"Unknown direction: {direction}")
    ns = _ns()
    db = _db()
    if direction == "push":
        memories = await storage.export_memories(ns["id"], db)
        import httpx
        packet = {
            "source_memories": [{"key": m["key"], "value": m["value"],
                                  "category": m["category"], "version": m["version"]}
                                 for m in memories],
            "conflict_strategy": conflict_strategy,
            "namespace_id": ns["id"],
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{target_url}/sync/receive", json=packet, timeout=30)
            resp.raise_for_status()
        return {"direction": "push", "count": len(memories)}
    elif direction == "pull":
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{target_url}/sync/push", json={
                "namespace_id": ns["id"], "target_url": "",
                "conflict_strategy": conflict_strategy
            }, timeout=30)
            resp.raise_for_status()
        return {"direction": "pull", "status": "requested"}
    else:
        raise ValueError(f"Unknown direction: {direction}")
