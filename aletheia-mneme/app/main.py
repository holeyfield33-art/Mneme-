"""
Aletheia Mneme — FastAPI application entry point.
"""
from fastapi import FastAPI

from app.config import get_settings
from app.models import Base
from app.database import engine
from app.routers import agents, billing, memories, relay

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Persistent AI memory with semantic search, "
        "cryptographic integrity, and multi-agent relay."
    ),
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


app.include_router(agents.router)
app.include_router(memories.router)
app.include_router(relay.router)
app.include_router(billing.router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "version": settings.app_version}
