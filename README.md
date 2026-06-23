# Aletheia Mneme

**Persistent AI memory with semantic search, cryptographic integrity, and multi-agent relay.**
**The memory layer of the TMRP (Trusted Machine-Readable Provenance) stack.**

[![License: Proprietary](https://img.shields.io/badge/License-Proprietary-red.svg)](#license)

---

## Why Mneme?

### The Stateless Supply Chain Problem

On **June 29 2025**, the LiteLLM proxy — a single dependency used by thousands of AI
deployments — was [compromised](https://www.wiz.io/blog/wiz-research-discovers-critical-vulnerability-in-litellm), exposing every API key routed through it. The root cause
was architectural: teams delegated sensitive credential handling to a massive,
monolithic third-party gateway rather than maintaining sovereignty over their own
state.

This is the **Stateless Supply Chain** attack surface. When agents depend on remote,
centralised middleware to store keys, context, and session state, a single upstream
breach cascades across every deployment that trusts it.

**Mneme eliminates this attack class.** By providing a **local-first memory relay**,
agents never need to ship secrets, context windows, or session history to a third-party
message broker. Every memory operation — storage, search, relay, sync — runs inside
infrastructure you control.

| Risk Vector | Monolithic Proxy (e.g. LiteLLM) | Mneme Local-First |
|-------------|----------------------------------|-------------------|
| API key exposure | Keys aggregated in one target | Keys never leave your perimeter |
| Session state leakage | State held by third party | State is local, encrypted at rest |
| Supply chain blast radius | One CVE compromises all tenants | Sovereign deployment; no shared fate |
| Audit trail | Opaque middleware logs | Helios cryptographic content hashing |
| Vendor lock-in | Dependent on proxy availability | Self-hosted or managed, your choice |

### Sovereign-First Design

Mneme is designed so every deployment can run in **PERSONAL_MODE** — a single operator,
a single API key, zero external dependencies beyond your own database. Mneme is
**completely free**: every key has full access to all 16 tools, with no billing, no
paywall, and no tiers. The core memory engine runs identically on a laptop, an
air-gapped server, or a Kubernetes pod.

---

## Tri-Storage Architecture

Mneme's persistence layer is purpose-built around three storage concerns, each matched
to the access pattern it serves:

```text
┌─────────────────────────────────────────────────────────────────┐
│                        AI Agent (MCP Client)                    │
│                  Authorization: Bearer mneme_p_…                │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI + FastMCP Gateway                    │
│             MCPAuthMiddleware · Argon2id Key Verify             │
│             ContextVar Dependency Injection (DI)                │
└──────┬──────────────────┬──────────────────────┬────────────────┘
       │                  │                      │
       ▼                  ▼                      ▼
┌──────────────┐  ┌───────────────┐  ┌────────────────────────┐
│  PostgreSQL  │  │  Ephemeral    │  │   Vector Index         │
│  (Neon)      │  │  Relay Store  │  │   pgvector + HNSW      │
│              │  │               │  │                        │
│ • Namespaces │  │ • 24h TTL     │  │ • 1536-dim embeddings  │
│ • API keys   │  │ • Session     │  │ • Cosine similarity    │
│ • Memories   │  │   scoped      │  │ • OpenAI or local      │
│ • History    │  │ • Agent-       │  │   model fallback       │
│ • Relations  │  │   isolated    │  │ • Graceful degradation  │
│ • Sync log   │  │ • 300-memory  │  │   to keyword search    │
│              │  │   cap         │  │                        │
└──────────────┘  └───────────────┘  └────────────────────────┘
   State Store       Relay Store        Semantic Search Store
```

### 1. State Store — PostgreSQL + Neon

The authoritative persistence layer. Namespaces, API keys (Argon2id-hashed), memories,
version history, relationship graphs, and sync audit logs all reside in
a single PostgreSQL database, benefiting from ACID transactions and row-level security.

### 2. Relay Store — Ephemeral Multi-Agent Sandbox

The **Relay Store** provides short-lived, session-scoped memory partitions for
multi-agent coordination. Each relay session is automatically namespace-isolated (derived
from `session_id` + `agent_id`), capped at 300 memories, and **expires after 24 hours**.
This is Mneme's secure alternative to piping agent state through unverified message
brokers — no shared bus, no fan-out risk, no accumulated stale state.

### 3. Semantic Search Store — pgvector + HNSW

Every stored memory is embedded with **OpenAI text-embedding-3-small** (1536 dimensions)
and indexed via an HNSW graph (`m=16`, `ef_construction=64`, cosine distance). When OpenAI
is unavailable, the system degrades gracefully to **all-MiniLM-L6-v2** (local) or falls
back to PostgreSQL full-text search (`tsvector` / `tsquery`). Memories are never lost
because an embedding provider is down.

---

## X-API-Key Security Model

```text
Client presents Bearer key (mneme_f_… or mneme_p_…)
        │
        ▼
MCPAuthMiddleware extracts key
        │
        ▼
Prefix lookup (first 9 chars) against api_keys table
        │
        ▼
Argon2id password hash verification (constant-time)
        │
        ▼
Namespace loaded into ContextVar (zero parameter passing)
        │
        ▼
Tool function executes in tenant-isolated context
```

- **Raw keys are returned exactly once** at creation and transmitted via encrypted email.
  They are never stored in plaintext.
- **Argon2id** (memory-hard KDF) protects against offline brute-force even if the database
  is exfiltrated.
- **Prefix-based pre-filtering** avoids scanning every hashed row on every request.
- **PERSONAL_MODE** enables a single hardcoded key verified via `secrets.compare_digest`
  for sovereign deployments with no external auth dependencies.

---

## Multi-Agent Relay

The `/relay` endpoint provides a **secure, ephemeral coordination layer** for multi-agent
workflows — a direct alternative to plugging agents into unverified message brokers like
Redis Pub/Sub queues or third-party event buses.

| Property | Detail |
|----------|--------|
| **Auth** | Dedicated `RELAY_SECRET` bearer token (separate from user keys) |
| **Isolation** | Each `(session_id, agent_id)` pair gets its own namespace — agents cannot read each other's state |
| **TTL** | All relay memories expire after 24 hours automatically |
| **Capacity** | 300 memories per session (HTTP 429 on overflow) |
| **Operations** | `store`, `fetch`, `search` (keyword) |
| **Source tagging** | All relay memories are tagged `source: "relay"` for audit |

### Why not a message broker?

Traditional multi-agent patterns route state through shared brokers (Redis, RabbitMQ,
Kafka). These introduce:

- **Shared-fate failure** — broker outage halts all agents.
- **Fan-out credential exposure** — API keys embedded in messages are visible to all
  subscribers.
- **Unbounded state growth** — messages accumulate without TTL enforcement.

Mneme's relay avoids all three by providing session-scoped, time-limited, authenticated
memory partitions inside the same hardened perimeter as the core memory engine.

---

## Helios Core — Cryptographic Integrity

Every memory gets a **SHA-256 content hash** computed over a canonically serialized
snapshot of its immutable fields:

1. **Canonical form**: sorted keys, NFC Unicode normalization, strict ISO 8601 timestamps
2. **SHA-256** of the UTF-8-encoded canonical JSON
3. Stored in the `content_hash` column alongside the memory
4. Verified on demand via the `verify_memory` tool

Mutable metadata (version, access_count, confidence, timestamps) is excluded from the
hash, ensuring that routine updates do not invalidate integrity proofs.

Test vectors are provided in `test_vectors/vectors.json` for cross-implementation
validation.

---

## Tools (16 total — all free)

Every API key has full access to all 16 tools. There are no tiers or paywalls.

### Core (8 tools)

| Tool | Description |
|------|-------------|
| `store_memory` | Store a memory with key, value, category |
| `get_memory` | Retrieve a memory by key |
| `list_memories` | List memories |
| `search_memory` | Keyword full-text search |
| `forget_memory` | Soft-delete a memory |
| `update_memory` | Update a memory's value |
| `reinforce` | Increase confidence score |
| `get_stats` | Usage stats |

### Advanced (8 tools)

| Tool | Description |
|------|-------------|
| `semantic_search` | Vector cosine similarity search |
| `relate_memories` | Create relationships between memories |
| `get_related` | Get related memories by key |
| `memory_history` | Full edit history for a memory |
| `rollback_memory` | Restore a previous version |
| `export_memories` | Export all memories as JSON |
| `verify_memory` | Helios cryptographic integrity check |
| `cloud_sync` | Push/pull to another Mneme instance |

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check + version info |
| POST | `/signup` | Create a namespace + free full-access API key |
| POST | `/relay` | Multi-agent relay sandbox |
| POST | `/sync/push` | Push memories to remote Mneme instance (HTTPS, SSRF-protected) |
| POST | `/sync/receive` | Receive memories with conflict resolution |
| * | `/mcp/*` | MCP protocol mount (16 tools) |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL / Neon connection string |
| `OPENAI_API_KEY` | Yes | OpenAI API key for embeddings |
| `RESEND_API_KEY` | Yes | Resend email API key |
| `EMAIL_FROM` | Yes | Sender email address |
| `RELAY_SECRET` | Yes | Bearer token for relay endpoint |
| `PERSONAL_MODE` | No | Enable single-user mode (default: `false`) |
| `PERSONAL_API_KEY` | No | API key for personal mode |
| `HELIOS_ENABLED` | No | Enable Helios hashing (default: `true`) |
| `LOCAL_EMBEDDINGS_FALLBACK` | No | Use local model instead of OpenAI (default: `false`) |

---

## Development

```bash
cd aletheia-mneme
pip install -r requirements.txt

# Verify Helios test vectors
python -c "
from helios.verifier import verify_vectors
results, failures = verify_vectors('test_vectors/vectors.json')
for name, expected, got, passed in results:
    print(f'  {name}: {\"PASS\" if passed else \"FAIL\"}')
print(f'Failures: {failures}')
"

# Run tests
pytest tests/ -v --cov=.

# Run server (requires env vars)
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Deployment

Deployed on [Render](https://render.com) via `render.yaml`. Set all environment
variables in the Render dashboard before deploying.

## License

Proprietary — Aletheia Sovereign Systems.
