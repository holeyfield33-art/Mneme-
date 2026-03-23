"""
Cryptographic integrity helpers for Aletheia Mneme.

Provides:
- SHA-256 content hashing
- HMAC-SHA256 signing / verification
"""
import hashlib
import hmac
import secrets


def hash_content(content: str) -> str:
    """Return the SHA-256 hex digest of *content*."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def sign_content(content: str, secret_key: str) -> str:
    """Return an HMAC-SHA256 hex digest of *content* using *secret_key*."""
    return hmac.new(
        secret_key.encode("utf-8"),
        content.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_signature(content: str, signature: str, secret_key: str) -> bool:
    """
    Return True when *signature* is a valid HMAC-SHA256 for *content*.

    Uses a constant-time comparison to prevent timing attacks.
    """
    expected = sign_content(content, secret_key)
    return hmac.compare_digest(expected, signature)


def generate_api_key() -> str:
    """Return a cryptographically secure random API key (hex, 64 chars)."""
    return secrets.token_hex(32)


def hash_api_key(api_key: str) -> str:
    """Return the SHA-256 hex digest of *api_key* for safe storage."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()
