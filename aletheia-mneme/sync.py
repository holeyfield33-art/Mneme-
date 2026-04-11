import ipaddress
import httpx
import structlog
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Request
import storage
from auth import get_namespace_from_key
from db import get_db

log = structlog.get_logger()
router = APIRouter()

VALID_CONFLICT_STRATEGIES = frozenset({"highest_version_wins", "source_wins", "target_wins"})

def _validate_sync_url(url: str):
    """Validate target URL to prevent SSRF attacks."""
    parsed = urlparse(url)
    if parsed.scheme not in ("https",):
        raise HTTPException(400, "Only HTTPS URLs are allowed for sync")
    if not parsed.hostname:
        raise HTTPException(400, "Invalid sync URL")
    blocked = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "metadata.google.internal"}
    if parsed.hostname.lower() in blocked:
        raise HTTPException(400, "Internal URLs are not allowed for sync")
    try:
        ip = ipaddress.ip_address(parsed.hostname)
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
            raise HTTPException(400, "Private/internal IPs are not allowed for sync")
    except ValueError:
        pass


async def _get_sync_namespace(request: Request, db):
    """Extract and verify API key for sync endpoints."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")
    ns = await get_namespace_from_key(auth_header[7:], db)
    if not ns:
        raise HTTPException(401, "Invalid API key")
    return ns


@router.post("/sync/push")
async def push(request: Request, db=Depends(get_db)):
    ns = await _get_sync_namespace(request, db)
    request_body = await request.json()
    target_url = request_body.get("target_url", "")
    if not target_url:
        raise HTTPException(400, "target_url is required")
    _validate_sync_url(target_url)
    namespace_id = request_body.get("namespace_id", "")
    if not namespace_id:
        raise HTTPException(400, "namespace_id is required")
    if namespace_id != ns["id"]:
        raise HTTPException(403, "namespace_id does not match authenticated namespace")
    memories = await storage.export_memories(namespace_id, db)

    packet = {
        "source_memories": [{"key": m["key"], "value": m["value"],
                              "category": m["category"], "version": m["version"]}
                             for m in memories],
        "conflict_strategy": request_body.get("conflict_strategy", "highest_version_wins"),
        "namespace_id": namespace_id,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{target_url}/sync/receive", json=packet, timeout=30)
        resp.raise_for_status()

    await db.execute("""
        INSERT INTO sync_log (namespace_id, direction, memory_count, target_url, status)
        VALUES ($1, 'push', $2, $3, 'success')
    """, namespace_id, len(memories), target_url)
    return {"pushed": len(memories)}

@router.post("/sync/receive")
async def receive(request: Request, db=Depends(get_db)):
    ns = await _get_sync_namespace(request, db)
    request_body = await request.json()
    memories = request_body.get("source_memories", [])
    namespace_id = request_body.get("namespace_id", "")
    if namespace_id != ns["id"]:
        raise HTTPException(403, "namespace_id does not match authenticated namespace")
    strategy = request_body.get("conflict_strategy", "highest_version_wins")
    if strategy not in VALID_CONFLICT_STRATEGIES:
        raise HTTPException(400, f"Invalid conflict_strategy. Must be one of: {', '.join(sorted(VALID_CONFLICT_STRATEGIES))}")
    written = 0

    for m in memories:
        existing = await storage.get_memory(namespace_id, m["key"], db)
        if existing:
            if strategy == "source_wins":
                await storage.update_memory(namespace_id, m["key"], m["value"], db)
                written += 1
            elif strategy == "highest_version_wins":
                if m["version"] > existing["version"]:
                    await storage.update_memory(namespace_id, m["key"], m["value"], db)
                    written += 1
        else:
            await storage.store_memory(namespace_id, m["key"], m["value"],
                                       m.get("category", "general"), "sync", db)
            written += 1

    return {"received": len(memories), "written": written}
