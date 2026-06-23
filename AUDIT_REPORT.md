# Aletheia Mneme — Technical Audit Report

**Audit Date:** 2026-03-24
**Scope:** `aletheia-mneme/` application code, database schema, dependency injection,
security model, and Stateless Supply Chain posture.
**Auditor:** TMRP Architecture Review

---

## Executive Summary

Aletheia Mneme is a **production-grade, multi-tenant AI memory server** implemented as a
FastAPI application exposing 16 tools via the Model Context Protocol (MCP). This audit
confirms that the codebase demonstrates strong security practices, clean separation of
concerns, and architectural decisions aligned with the TMRP goal of sovereign, local-first
AI infrastructure.

**Overall Assessment: PASS** — with observations and recommendations noted below.

---

## 1. Application Structure Analysis

### 1.1 Module Inventory

| Module | LOC Category | Responsibility | Coupling |
|--------|-------------|----------------|----------|
| `main.py` | Entrypoint | App factory, middleware, startup/shutdown, router mounts | High (expected) |
| `auth.py` | Security | API key generation, Argon2id hashing, MCPAuthMiddleware | Low |
| `storage.py` | Core | All 14 memory CRUD/search/graph operations | Low |
| `tools.py` | Interface | 16 MCP tool definitions, ContextVar access | Medium |
| `db.py` | Infrastructure | asyncpg pool lifecycle, pgvector codec registration | Low |
| `embeddings.py` | Infrastructure | OpenAI + local embedding with graceful fallback | Low |
| `signup.py` | Feature | Free namespace + full-access API key issuance | Low |
| `relay.py` | Feature | Ephemeral multi-agent relay sandbox | Low |
| `sync.py` | Feature | Cloud push/pull with SSRF protection | Low |
| `env.py` | Config | Lazy-loaded environment with validation | Low |
| `mailer.py` | Infrastructure | Resend transactional email (fire-and-forget) | Low |
| `helios/` | Integrity | Canonical serialization + SHA-256 content hashing | Zero external |

**Finding:** Clean single-responsibility decomposition. No circular imports. The only
high-coupling module (`main.py`) is the expected composition root.

### 1.2 Helios Subsystem

The `helios/` package is **zero-dependency on external services** — it imports only the
Python standard library (`hashlib`, `json`, `unicodedata`, `datetime`). This means
integrity verification works identically in air-gapped environments.

- `canon.py` — NFC normalization, strict ISO 8601 validation, sorted relationship arrays
- `hasher.py` — SHA-256 over canonical JSON bytes
- `objects.py` — Field selection (6 immutable fields hashed; mutable metadata excluded)
- `verifier.py` — Cross-implementation test vector validation

**Verdict:** Sound design. The explicit exclusion of mutable fields (version,
access_count, confidence, updated_at) from the hash is correct — routine metadata updates
do not invalidate integrity proofs.

---

## 2. FastAPI Dependency Injection Evaluation

### 2.1 DATABASE_URL Injection

**Implementation:**

```text
env.py: DATABASE_URL loaded lazily via __getattr__ + os.environ
    ↓
db.py: asyncpg.create_pool(env.DATABASE_URL, min_size=2, max_size=10)
    ↓
main.py: Pool created at startup, closed at shutdown (lifespan)
    ↓
MCPAuthMiddleware: Acquires connection from pool, sets ContextVar
    ↓
tools.py: _db() reads ContextVar — zero parameter passing
```

#### Assessment: PASS

- The `DATABASE_URL` is read **once** at pool creation time and never re-read at runtime.
- Connection pooling (`min_size=2`, `max_size=10`) prevents connection exhaustion.
- The `_init_connection` callback registers the pgvector codec per-connection.
- ContextVar injection (`current_db`) ensures each request gets its own connection without
  manual passing through the call chain.

**Observation:** The `DATABASE_URL` is a required key validated at import time via
`env._REQUIRED_KEYS`. Failure to set it produces a clear startup crash rather than a
cryptic runtime error. This is correct.

### 2.2 QDRANT_HOST — Not Implemented (By Design)

**Finding:** There is no `QDRANT_HOST` configuration in the codebase. Semantic search is
implemented via **pgvector** — the PostgreSQL vector extension — using an HNSW index
(`memories_embedding_hnsw`, cosine distance, `m=16`, `ef_construction=64`).

**Architectural Implication:** This is a deliberate design choice that **reduces
operational complexity**:

| Concern | Separate Qdrant Cluster | pgvector (Current) |
|---------|------------------------|-------------------|
| Deployment surface | +1 service to provision, monitor, patch | Zero — lives inside PostgreSQL |
| ACID transactions | Eventual consistency between PG and Qdrant | Same transaction as memory write |
| Backup/restore | Two backup strategies required | Single `pg_dump` captures everything |
| Network attack surface | Qdrant port exposed (6333/6334) | No additional ports |
| Connection overhead | Separate connection pool + auth | Reuses existing asyncpg pool |

**Recommendation:** The pgvector approach is **correct for the current scale**. If
semantic search volume exceeds what HNSW on PostgreSQL can serve at acceptable latency
(typically >10M vectors), a dedicated vector store (Qdrant, Pinecone, Weaviate) becomes
justified. At that point, add `QDRANT_HOST` / `QDRANT_API_KEY` as optional env vars with
a feature flag to route `semantic_search` calls to the external index while keeping
pgvector as the fallback.

### 2.3 ContextVar Pattern

The use of `contextvars.ContextVar` for `current_namespace` and `current_db` is the
**recommended FastAPI pattern** for request-scoped state in async applications:

- Thread-safe and async-safe (each task gets its own context copy).
- Avoids prop-drilling namespace/connection through every function signature.
- Set once in middleware, consumed in tools — clean separation.

**Verdict: PASS** — Idiomatic and correct.

---

## 3. Access Model — Completely Free

Mneme has **no billing, paywall, or tiers**. There is no Stripe dependency and no
`billing.py`. Every API key has full access to all 16 tools.

### 3.1 Key Issuance

- **`POST /signup`** — public, free endpoint that creates a namespace and mints a
  full-access API key (`mneme_p_…`), returning it and emailing it via Resend.
- **`PERSONAL_MODE`** — single-operator deployments use one hardcoded
  `PERSONAL_API_KEY` verified with `secrets.compare_digest`, requiring no signup.

### 3.2 Notes

| Criterion | Status | Detail |
|-----------|--------|--------|
| Any payment dependency? | **No** | `stripe` removed from `requirements.txt` and code |
| Any feature gating? | **No** | `_require_premium()` removed; all 16 tools open to every key |
| `tier` column retained? | **Yes** | Defaults to `premium`; kept for forward compatibility, no longer gates anything |
| List page size capped? | **No** | The requested `limit` is passed straight through |

---

## 4. Security Posture

### 4.1 Authentication

| Control | Implementation | Strength |
|---------|----------------|----------|
| Key hashing | Argon2id (memory-hard KDF) | Strong |
| Key format | `mneme_{f,p}_` + 40-char `secrets.token_urlsafe` | ~240 bits entropy |
| Key storage | Hash only; raw key returned once, emailed, never persisted | Strong |
| Prefix pre-filter | First 9 chars indexed for DB lookup before hash verify | Efficient + safe |
| Personal mode | `secrets.compare_digest` (constant-time) | Correct |
| Relay auth | Separate `RELAY_SECRET` bearer token | Correct isolation |

### 4.2 Input Validation

| Field | Limit | Enforcement |
|-------|-------|-------------|
| Memory key | 1–512 chars | Validated before DB write |
| Memory value | 1–100,000 chars | Validated before DB write |
| Category | 1–128 chars | Validated before DB write |
| Embedding text | Truncated to 8,000 chars | Before OpenAI API call |
| Relay session | 300 memories max | HTTP 429 on overflow |
| List page size | Caller-supplied `limit` | Uncapped (no tiers) |

### 4.3 SSRF Protection (Cloud Sync)

The `/sync/push` endpoint validates target URLs:

- **HTTPS only** — rejects `http://`, `ftp://`, etc.
- **No localhost** — rejects `127.0.0.1`, `::1`, `0.0.0.0`, `localhost`
- **No private IPs** — rejects RFC 1918 (`10.*`, `172.16–31.*`, `192.168.*`),
  link-local, loopback, reserved ranges via `ipaddress` module
- **No cloud metadata** — rejects `metadata.google.internal`

**Verdict: PASS** — Defence-in-depth SSRF mitigation.

### 4.4 Multi-Tenant Isolation

- All memory queries are scoped by `namespace_id` (WHERE clause).
- Relay namespaces are derived from `session_id` + `agent_id` hash — no collision.
- API keys are namespace-bound; a valid key for tenant A cannot access tenant B.
- Soft deletes honour namespace scope.

**Verdict: PASS** — No cross-tenant query path identified.

### 4.5 Relay Authentication

The `/relay` endpoint is gated by a dedicated `RELAY_SECRET` bearer token, compared in
constant time via `secrets.compare_digest`. It is independent of user API keys, so relay
access cannot be obtained with a tenant key (and vice versa).

**Verdict: PASS** — Constant-time comparison; relay access isolated from user API keys.

---

## 5. Stateless Supply Chain Risk Assessment

### 5.1 Dependency Posture

Mneme's core memory engine (`storage.py`, `auth.py`, `helios/`, `db.py`) depends on:

| Dependency | Purpose | Supply Chain Risk |
|------------|---------|-------------------|
| `asyncpg` | PostgreSQL driver | Low — C extension, well-audited |
| `argon2-cffi` | Password hashing | Low — wraps reference C implementation |
| `openai` | Embedding API client | Medium — but failure is gracefully degraded |
| `sentence-transformers` | Local embedding fallback | Medium — large transitive tree |
| `fastapi` + `uvicorn` | HTTP framework | Low — widely deployed, actively maintained |

**Key insight:** The `openai` and `sentence-transformers` packages are the only
medium-risk dependencies, and both sit behind the `get_embedding()` function which
**never raises** — it returns `(None, "none")` on any failure. This means a compromised
or unavailable embedding provider does not affect memory storage, retrieval, or integrity
verification.

### 5.2 Comparison to Monolithic Proxy Pattern

| Characteristic | Monolithic Proxy (LiteLLM pattern) | Mneme |
|----------------|-------------------------------------|-------|
| Credential handling | Proxy aggregates all provider keys | Each namespace holds only its own context |
| Blast radius | One CVE exposes all tenants' keys | Compromise of one namespace ≠ compromise of another |
| Audit trail | Proxy logs (opaque, mutable) | Helios SHA-256 hashes (cryptographic, verifiable) |
| Offline operation | Impossible — proxy is the gateway | `PERSONAL_MODE` + local embeddings = fully offline |
| State ownership | Third-party holds agent state | Operator holds all state — local PostgreSQL |

### 5.3 Residual Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| `DATABASE_URL` credential in env var | Low | Standard practice; rotate via provider (Neon) |
| OpenAI API key in env var | Low | Only used for embeddings; graceful fallback exists |
| No rate limiting on MCP tools | Medium | Consider adding `slowapi` throttling to `/mcp/*` |
| No key rotation endpoint | Low | New key can be generated via checkout; old key revoked via webhook |
| `sentence-transformers` transitive deps | Medium | Pin versions in `requirements.txt`; consider hash-pinning |

---

## 6. Database Schema Review

### 6.1 Migration Sequence

| Migration | Purpose | Idempotent? |
|-----------|---------|-------------|
| `001_init.sql` | 7 tables, pgcrypto, indexes | Yes (IF NOT EXISTS) |
| `002_pgvector.sql` | pgvector extension + embedding column | Yes |
| `003_hnsw_index.sql` | HNSW vector index (m=16, ef=64) | Yes |

### 6.2 Index Coverage

| Table | Indexed Columns | Purpose |
|-------|----------------|---------|
| `api_keys` | `key_prefix` | Fast Argon2 pre-filter |
| `memories` | `(namespace_id, key)` UNIQUE | Tenant-scoped uniqueness |
| `memories` | `embedding` HNSW (cosine) | Semantic nearest-neighbour |
| `memories` | `(namespace_id, is_deleted)` | Filtered list queries |
| `processed_events` | `event_id` UNIQUE | Webhook idempotency |

**Observation:** Full-text search (`to_tsvector`) is computed at query time rather than
stored in a generated column with a GIN index. For high-volume keyword search workloads,
adding a `tsvector` generated column + GIN index would improve performance.

---

## 7. Test Coverage Assessment

| Test Module | Coverage Area | Key Scenarios |
|-------------|--------------|---------------|
| `test_auth.py` | API key lifecycle | Generation, hashing, prefix lookup, Argon2 verify |
| `test_endpoints.py` | HTTP surface | Health, signup, relay, sync, MCP auth |
| `test_concurrency.py` | Race conditions | Concurrent memory updates, version conflicts |
| `test_isolation.py` | Multi-tenancy | Cross-namespace query prevention |
| `test_relay.py` | Relay sandbox | Session isolation, TTL, capacity limits |
| `test_storage.py` | Core engine | CRUD, search, embeddings, soft deletes, history |
| `test_tools.py` | MCP interface | Tool availability, error handling |
| `test_helios.py` | Integrity | Canonical form, SHA-256, test vector validation |

**Verdict:** Comprehensive coverage across all critical paths. Concurrency and isolation
tests are particularly noteworthy — these are often omitted in early-stage projects.

---

## 8. Recommendations

| # | Priority | Recommendation |
|---|----------|---------------|
| 1 | Medium | Add `slowapi` rate limiting to `/mcp/*` mount to prevent abuse |
| 2 | Low | Add GIN index on `tsvector` generated column for keyword search performance |
| 3 | Low | Pin dependency hashes in `requirements.txt` (`pip install --require-hashes`) |
| 4 | Low | Add a `/readiness` probe separate from `/health` for Kubernetes deployments |
| 5 | Info | Document the upgrade path to a dedicated vector store (Qdrant) when embedding volume exceeds pgvector capacity |
| 6 | Info | Consider adding structured logging correlation IDs for distributed tracing |

---

## 9. Conclusion

Aletheia Mneme is a well-architected, security-conscious AI memory server that achieves
its stated goal of providing a **sovereign, local-first alternative** to centralized AI
middleware. It is **completely free** — no billing, paywall, or tiers — with every API key
granted full access to all 16 tools, and `PERSONAL_MODE` operating with zero external
dependencies beyond the database. The dependency injection
pattern (ContextVars set by middleware, consumed by tools) is idiomatic and correct. The
`DATABASE_URL` is the sole infrastructure credential, injected via environment variable
and consumed once at pool creation.

The codebase's explicit defences against Stateless Supply Chain attacks — Argon2id key
hashing, ephemeral relay with TTL, SSRF-protected sync, Helios cryptographic integrity,
and graceful degradation when external providers fail — position it as a credible
alternative to the monolithic proxy pattern that led to breaches like LiteLLM.

---

Report generated for TMRP Architecture Review — Aletheia Sovereign Systems
