import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
import env

ph = PasswordHasher()

def generate_api_key(tier: str) -> tuple[str, str]:
    """Returns (raw_key, key_hash). Store hash only, return raw once."""
    prefix = "mneme_f" if tier == "free" else "mneme_p"
    raw = prefix + "_" + secrets.token_urlsafe(40)
    hashed = ph.hash(raw)
    return raw, hashed

async def get_namespace_from_key(key: str, db) -> dict | None:
    if env.PERSONAL_MODE and secrets.compare_digest(key, env.PERSONAL_API_KEY):
        return {
            "id": "personal",
            "tier": "premium",
            "is_active": True,
            "email": None
        }
    prefix = key[:9] if len(key) >= 9 else key
    rows = await db.fetch(
        "SELECT * FROM api_keys WHERE key_prefix = $1 AND revoked_at IS NULL",
        prefix
    )
    for row in rows:
        try:
            if ph.verify(row["key_hash"], key):
                await db.execute(
                    "UPDATE api_keys SET last_used = NOW() WHERE id = $1", row["id"]
                )
                return await db.fetchrow(
                    "SELECT * FROM namespaces WHERE id = $1 AND is_active = TRUE",
                    row["namespace_id"]
                )
        except (VerifyMismatchError, VerificationError):
            continue
    return None
