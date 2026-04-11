import asyncpg
import structlog
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import env
import db as database
from billing import router as billing_router
from relay import router as relay_router
from sync import router as sync_router
from auth import get_namespace_from_key
from tools import mcp, current_namespace, current_db

log = structlog.get_logger()
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if env.PERSONAL_MODE and not env.PERSONAL_API_KEY:
        raise RuntimeError("PERSONAL_API_KEY required when PERSONAL_MODE=true")
    await database.init_pool(env.DATABASE_URL)
    log.info("app_started", product="Aletheia Mneme", version="1.0.0")
    yield
    await database.close_pool()
    log.info("app_stopped")


app = FastAPI(
    title="Aletheia Mneme",
    description="True memory for AI agents.",
    version="1.0.0",
    lifespan=lifespan
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": "Rate limit exceeded", "detail": str(exc.detail)}
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error("unhandled_exception",
              path=request.url.path,
              method=request.method,
              error=str(exc),
              error_type=type(exc).__name__)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


app.include_router(billing_router)
app.include_router(relay_router)
app.include_router(sync_router)


# ── MCP Auth Middleware ──────────────────────────────────────
# Wraps the MCP ASGI app to extract API key from Authorization header,
# resolve namespace, acquire a DB connection, and set contextvars
# so that all MCP tool functions can access them.

_mcp_app = mcp.streamable_http_app()


class MCPAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode()

            if auth_header.startswith("Bearer "):
                api_key = auth_header[7:]
                async with database.pool.acquire() as conn:
                    ns = await get_namespace_from_key(api_key, conn)
                    if ns:
                        ns_dict = dict(ns) if not isinstance(ns, dict) else ns
                        current_namespace.set(ns_dict)
                        current_db.set(conn)
                        try:
                            await conn.execute(
                                "UPDATE namespaces SET request_count_current_month = "
                                "request_count_current_month + 1 WHERE id = $1",
                                ns_dict["id"]
                            )
                        except Exception:
                            pass  # Don't block on counter failures
                        await self.app(scope, receive, send)
                        return

            # Return 401 for unauthenticated HTTP MCP requests
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({
                "type": "http.response.body",
                "body": b'{"error":"Authentication required. Provide Bearer token."}',
            })
        else:
            # Allow websocket/lifespan through
            await self.app(scope, receive, send)


app.mount("/mcp", MCPAuthMiddleware(_mcp_app))


@app.get("/health")
async def health():
    db_ok = await database.health_check() if database.pool else False
    return {
        "status": "ok" if db_ok else "degraded",
        "product": "Aletheia Mneme",
        "version": "1.0.0",
        "database": "connected" if db_ok else "disconnected",
    }


@app.get("/billing/success")
async def billing_success():
    return {"message": "Payment received. Check your email for your premium API key."}
