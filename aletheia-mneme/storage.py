import asyncpg
from datetime import datetime, timezone
from helios.hasher import content_hash
from helios.objects import MemoryObject
import embeddings as emb
import structlog

log = structlog.get_logger()

MAX_KEY_LENGTH = 512
MAX_VALUE_LENGTH = 100_000
MAX_CATEGORY_LENGTH = 128


def _validate_input(key: str, value: str, category: str = "general"):
    """Validate memory input fields."""
    if not key or len(key) > MAX_KEY_LENGTH:
        raise ValueError(f"Key must be 1-{MAX_KEY_LENGTH} characters")
    if not value or len(value) > MAX_VALUE_LENGTH:
        raise ValueError(f"Value must be 1-{MAX_VALUE_LENGTH} characters")
    if category and len(category) > MAX_CATEGORY_LENGTH:
        raise ValueError(f"Category must be <= {MAX_CATEGORY_LENGTH} characters")

async def _compute_helios_hash(key: str, value: str, category: str, created_at: str) -> str | None:
    """Compute Helios content hash.  created_at must be the exact canonical string
    that will be (or was) persisted in helios_created_at — never generate it here."""
    try:
        obj = MemoryObject(
            category=category,
            created_at=created_at,
            key=key,
            relationships=[],
            source="user",
            value=value,
        )
        return content_hash(obj)
    except Exception as e:
        log.error("helios_hash_failed", error=str(e))
        return None

async def store_memory(namespace_id: str, key: str, value: str,
                       category: str, source: str, db,
                       expires_at: datetime | None = None) -> dict:
    _validate_input(key, value, category)
    vector, model = await emb.get_embedding(value)
    # Generate the canonical timestamp once — used in the hash AND stored verbatim.
    # TEXT column preserves the exact string; a native TIMESTAMP would reformat it.
    helios_created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    h = await _compute_helios_hash(key, value, category, helios_created_at)

    existing = await db.fetchrow(
        "SELECT id FROM memories WHERE namespace_id=$1 AND key=$2 AND is_deleted=FALSE",
        namespace_id, key
    )
    if existing:
        return await update_memory(namespace_id, key, value, db)

    row = await db.fetchrow("""
        INSERT INTO memories
          (namespace_id, key, value, category, source, content_hash,
           embedding_model, embedding, expires_at, helios_created_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
        RETURNING *
    """, namespace_id, key, value, category, source, h, model,
        vector, expires_at, helios_created_at)
    return dict(row)

async def get_memory(namespace_id: str, key: str, db) -> dict | None:
    row = await db.fetchrow("""
        SELECT * FROM memories
        WHERE namespace_id=$1 AND key=$2 AND is_deleted=FALSE
          AND (expires_at IS NULL OR expires_at > NOW())
    """, namespace_id, key)
    if row:
        await db.execute(
            "UPDATE memories SET last_accessed=NOW(), access_count=access_count+1 WHERE id=$1",
            row["id"]
        )
    return dict(row) if row else None

async def update_memory(namespace_id: str, key: str, value: str, db) -> dict:
    _validate_input(key, value)
    existing = await db.fetchrow(
        "SELECT * FROM memories WHERE namespace_id=$1 AND key=$2 AND is_deleted=FALSE",
        namespace_id, key
    )
    if not existing:
        raise ValueError(f"Memory not found: {key}")

    await db.execute("""
        INSERT INTO memory_history (memory_id, old_value, old_version)
        VALUES ($1, $2, $3)
    """, existing["id"], existing["value"], existing["version"])

    vector, model = await emb.get_embedding(value)
    # created_at is IMMUTABLE per the Helios spec — reuse whatever was stored.
    # For pre-migration rows helios_created_at is None; content_hash becomes None
    # (those rows are already flagged as unverifiable by verify_memory_helios).
    helios_created_at = existing.get("helios_created_at")
    h = await _compute_helios_hash(key, value, existing["category"], helios_created_at) \
        if helios_created_at else None

    row = await db.fetchrow("""
        UPDATE memories SET value=$1, content_hash=$2, embedding=$3,
          embedding_model=$4, version=version+1, last_updated=NOW()
        WHERE id=$5 RETURNING *
    """, value, h, vector, model, existing["id"])
    return dict(row)

async def forget_memory(namespace_id: str, key: str, db) -> bool:
    result = await db.execute(
        "UPDATE memories SET is_deleted=TRUE WHERE namespace_id=$1 AND key=$2",
        namespace_id, key
    )
    return result != "UPDATE 0"

async def list_memories(namespace_id: str, category: str | None,
                        limit: int, offset: int, db) -> list[dict]:
    query = """
        SELECT * FROM memories
        WHERE namespace_id=$1 AND is_deleted=FALSE
          AND (expires_at IS NULL OR expires_at > NOW())
    """
    params = [namespace_id]
    if category:
        query += " AND category=$2 ORDER BY last_updated DESC LIMIT $3 OFFSET $4"
        params += [category, limit, offset]
    else:
        query += " ORDER BY last_updated DESC LIMIT $2 OFFSET $3"
        params += [limit, offset]
    rows = await db.fetch(query, *params)
    return [dict(r) for r in rows]

async def keyword_search(namespace_id: str, query: str, limit: int, db) -> list[dict]:
    rows = await db.fetch("""
        SELECT *, ts_rank(to_tsvector('english', value), plainto_tsquery($2)) AS rank
        FROM memories
        WHERE namespace_id=$1 AND is_deleted=FALSE
          AND (expires_at IS NULL OR expires_at > NOW())
          AND to_tsvector('english', value) @@ plainto_tsquery($2)
        ORDER BY rank DESC LIMIT $3
    """, namespace_id, query, limit)
    return [dict(r) for r in rows]

async def semantic_search(namespace_id: str, query: str, limit: int, db) -> list[dict]:
    vector, _ = await emb.get_embedding(query)
    if vector is None:
        return await keyword_search(namespace_id, query, limit, db)
    rows = await db.fetch("""
        SELECT *, 1 - (embedding <=> $2) AS similarity
        FROM memories
        WHERE namespace_id=$1 AND is_deleted=FALSE
          AND (expires_at IS NULL OR expires_at > NOW())
          AND embedding IS NOT NULL
        ORDER BY embedding <=> $2
        LIMIT $3
    """, namespace_id, vector, limit)
    return [dict(r) for r in rows]

async def reinforce_memory(namespace_id: str, key: str, amount: float, db) -> dict:
    row = await db.fetchrow("""
        UPDATE memories SET confidence=LEAST(1.0, confidence+$3)
        WHERE namespace_id=$1 AND key=$2 AND is_deleted=FALSE RETURNING *
    """, namespace_id, key, amount)
    return dict(row) if row else {}

async def get_memory_history(namespace_id: str, key: str, db) -> list[dict]:
    mem = await db.fetchrow(
        "SELECT id FROM memories WHERE namespace_id=$1 AND key=$2", namespace_id, key
    )
    if not mem:
        return []
    rows = await db.fetch(
        "SELECT * FROM memory_history WHERE memory_id=$1 ORDER BY changed_at DESC", mem["id"]
    )
    return [dict(r) for r in rows]

async def rollback_memory(namespace_id: str, key: str, version: int, db) -> dict:
    mem = await db.fetchrow(
        "SELECT * FROM memories WHERE namespace_id=$1 AND key=$2", namespace_id, key
    )
    if not mem:
        raise ValueError(f"Memory not found: {key}")
    hist = await db.fetchrow(
        "SELECT * FROM memory_history WHERE memory_id=$1 AND old_version=$2",
        mem["id"], version
    )
    if not hist:
        raise ValueError(f"Version {version} not found")
    return await update_memory(namespace_id, key, hist["old_value"], db)

async def relate_memories(namespace_id: str, from_key: str, to_key: str,
                           rel_type: str, db) -> dict:
    row = await db.fetchrow("""
        INSERT INTO memory_relationships (namespace_id, from_key, to_key, rel_type)
        VALUES ($1,$2,$3,$4) RETURNING *
    """, namespace_id, from_key, to_key, rel_type)
    return dict(row)

async def get_related_memories(namespace_id: str, key: str, db) -> list[dict]:
    rows = await db.fetch("""
        SELECT * FROM memory_relationships
        WHERE namespace_id=$1 AND (from_key=$2 OR to_key=$2)
    """, namespace_id, key)
    return [dict(r) for r in rows]

async def export_memories(namespace_id: str, db) -> list[dict]:
    rows = await db.fetch(
        "SELECT * FROM memories WHERE namespace_id=$1 AND is_deleted=FALSE ORDER BY last_updated DESC",
        namespace_id
    )
    return [dict(r) for r in rows]

async def verify_memory_helios(namespace_id: str, key: str, db) -> dict:
    mem = await get_memory(namespace_id, key, db)
    if not mem:
        return {"valid": False, "error": "Memory not found"}
    # Rows stored before migration 005 have no helios_created_at.  The exact
    # timestamp that was hashed was never persisted, so recomputation is
    # impossible — report honestly rather than returning a misleading false.
    if not mem.get("helios_created_at"):
        return {
            "valid": False,
            "unverifiable": True,
            "reason": "pre-migration record: helios_created_at was not stored",
        }
    try:
        obj = MemoryObject(
            category=mem["category"],
            created_at=mem["helios_created_at"],   # exact canonical string, verbatim
            key=mem["key"],
            relationships=[],
            source=mem["source"],
            value=mem["value"],
        )
        computed = content_hash(obj)
        return {
            "valid": computed == mem["content_hash"],
            "computed_hash": computed,
            "stored_hash": mem["content_hash"],
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}
