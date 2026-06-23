import hashlib
import secrets
import structlog
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, HTTPException, Depends
import env, storage
from db import get_db

log = structlog.get_logger()
router = APIRouter()

def _verify_relay_auth(request: Request):
    auth_header = request.headers.get("Authorization", "")
    expected = f"Bearer {env.RELAY_SECRET}"
    if not secrets.compare_digest(auth_header, expected):
        raise HTTPException(401, "Invalid relay token")

@router.post("/relay")
async def relay_operation(request: Request, db=Depends(get_db)):
    _verify_relay_auth(request)
    body = await request.json()

    session_id = body.get("session_id", "unknown")
    agent_id = body.get("agent_id", "unknown")
    operation = body.get("operation", "store")
    payload = body.get("payload", {})

    namespace_id = f"relay_{session_id}_{int(hashlib.sha256(agent_id.encode()).hexdigest()[:12], 16) % 999999:06d}"

    existing = await db.fetchrow("SELECT id FROM namespaces WHERE id=$1", namespace_id)
    if not existing:
        await db.execute(
            "INSERT INTO namespaces (id, tier) VALUES ($1, 'premium')", namespace_id
        )

    count = await db.fetchval(
        "SELECT COUNT(*) FROM memories WHERE namespace_id=$1 AND is_deleted=FALSE", namespace_id
    )
    if count >= 300 and operation == "store":
        raise HTTPException(429, "Session namespace at capacity (300 memories)")

    if operation == "store":
        if "key" not in payload or "value" not in payload:
            raise HTTPException(400, "payload must include 'key' and 'value'")
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        result = await storage.store_memory(
            namespace_id, payload["key"], payload["value"],
            payload.get("category", "relay"), "relay", db,
            expires_at=expires_at
        )
        return {"ok": True, "entry": result}
    elif operation == "fetch":
        if "key" not in payload:
            raise HTTPException(400, "payload must include 'key'")
        result = await storage.get_memory(namespace_id, payload["key"], db)
        return {"ok": True, "entry": result}
    elif operation == "search":
        if "query" not in payload:
            raise HTTPException(400, "payload must include 'query'")
        result = await storage.keyword_search(namespace_id, payload["query"], 10, db)
        return {"ok": True, "results": result}
    else:
        raise HTTPException(400, f"Unknown operation: {operation}")
