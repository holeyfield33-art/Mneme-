import os

_cache = {}

_REQUIRED_KEYS = frozenset({
    "DATABASE_URL", "OPENAI_API_KEY", "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_ID", "RESEND_API_KEY",
    "EMAIL_FROM", "APPNEST_RELAY_SECRET",
})

_BOOL_MAP = {
    "PERSONAL_MODE": ("PERSONAL_MODE", "false"),
    "HELIOS_ENABLED": ("HELIOS_ENABLED", "true"),
    "LOCAL_EMBEDDINGS": ("LOCAL_EMBEDDINGS_FALLBACK", "false"),
}


def require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Missing required env var: {key}")
    return val


def __getattr__(name: str):
    """Lazy-load environment variables on first access."""
    if name.startswith("_"):
        raise AttributeError(name)
    if name in _cache:
        return _cache[name]
    if name in _REQUIRED_KEYS:
        val = require(name)
        _cache[name] = val
        return val
    if name in _BOOL_MAP:
        env_key, default = _BOOL_MAP[name]
        val = os.getenv(env_key, default).lower() == "true"
        _cache[name] = val
        return val
    if name == "PERSONAL_API_KEY":
        val = os.getenv("PERSONAL_API_KEY", "")
        _cache[name] = val
        return val
    raise AttributeError(f"module 'env' has no attribute {name!r}")


def _reset_cache():
    """Clear cached values — used in testing."""
    _cache.clear()
