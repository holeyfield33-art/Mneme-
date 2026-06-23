import secrets
import structlog
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
import auth, mailer as em
from db import get_db

log = structlog.get_logger()
router = APIRouter()

@router.post("/signup")
async def signup(request: Request, db=Depends(get_db)):
    body = await request.json()
    user_email = body.get("email", "")
    if not user_email or "@" not in user_email:
        raise HTTPException(400, "Valid email required")

    namespace_id = "ns_" + secrets.token_urlsafe(16)
    await db.execute(
        "INSERT INTO namespaces (id, email, tier) VALUES ($1,$2,'premium')",
        namespace_id, user_email
    )
    raw_key, hashed = auth.generate_api_key("premium")
    prefix = raw_key[:9]
    await db.execute(
        "INSERT INTO api_keys (namespace_id, key_hash, key_prefix) VALUES ($1,$2,$3)",
        namespace_id, hashed, prefix
    )

    em.send_api_key(user_email, raw_key)
    log.info("namespace_created", namespace_id=namespace_id)
    return JSONResponse({"api_key": raw_key, "namespace_id": namespace_id})
