# Aletheia Mneme

**True memory for AI agents.**

Persistent AI memory server with semantic search, cryptographic integrity (Helios Core),
Stripe billing, and AppNest relay sandbox.

Part of the **Aletheia Sovereign Systems** product family — the memory layer of the
**TMRP (Trusted Machine-Readable Provenance)** stack.

> For the full technical overview — including the "Why Mneme?" rationale, Tri-Storage
> Architecture, and X-API-Key security model — see the
> [root README](../README.md).

---

## Stack

- **Python 3.11** · FastAPI · Uvicorn
- **PostgreSQL/Neon** + pgvector (HNSW index)
- **FastMCP** — Model Context Protocol server
- **Helios Core** — SHA-256 content hashing with canonical serialization
- **OpenAI** text-embedding-3-small (1536-dim vectors)
- **Stripe** subscription billing
- **Resend** transactional email
- **Render** deployment

## Architecture

```
┌──────────────┐   ┌──────────────┐   ┌───────────────┐
│  MCP Client  │──▶│  FastAPI +   │──▶│  PostgreSQL   │
│  (AI Agent)  │   │  FastMCP     │   │  + pgvector   │
└──────────────┘   └──────┬───────┘   └───────────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        ┌──────────┐ ┌────────┐ ┌─────────┐
        │  Stripe  │ │ Resend │ │ OpenAI  │
        │ Billing  │ │ Email  │ │Embedding│
        └──────────┘ └────────┘ └─────────┘
```

## Tools (16 total)

### Free Tier (8 tools)
| Tool | Description |
|------|-------------|
| `store_memory` | Store a memory with key, value, category |
| `get_memory` | Retrieve a memory by key |
| `list_memories` | List memories (limit 50 on free) |
| `search_memory` | Keyword full-text search |
| `forget_memory` | Soft-delete a memory |
| `update_memory` | Update a memory's value |
| `reinforce` | Increase confidence score |
| `get_stats` | Usage stats and tier info |

### Premium Tier (8 additional tools)
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

## API Keys

- **Free tier:** `mneme_f_...` — 8 tools, keyword search, 50-memory list cap
- **Premium tier:** `mneme_p_...` — All 16 tools, semantic search, cloud sync, relay

Keys are hashed with Argon2id. The raw key is returned once at creation and never stored.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/billing/checkout` | Create namespace + Stripe checkout |
| POST | `/billing/webhook` | Stripe webhook receiver |
| GET | `/billing/success` | Post-payment landing |
| POST | `/relay` | AppNest relay sandbox |
| POST | `/sync/push` | Push memories to remote |
| POST | `/sync/receive` | Receive memories from remote |
| * | `/mcp/*` | MCP protocol (tools) |

## Helios Core

Cryptographic content integrity for every memory:

1. Canonical JSON serialization (sorted keys, NFC normalization)
2. SHA-256 hash of the canonical form
3. Hash stored alongside memory for later verification
4. `verify_memory` tool recomputes and compares

Test vectors included in `test_vectors/vectors.json`.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | Neon PostgreSQL connection string |
| `OPENAI_API_KEY` | Yes | OpenAI API key for embeddings |
| `STRIPE_SECRET_KEY` | Yes | Stripe secret key |
| `STRIPE_WEBHOOK_SECRET` | Yes | Stripe webhook signing secret |
| `STRIPE_PRICE_ID` | Yes | Stripe price ID for premium |
| `RESEND_API_KEY` | Yes | Resend email API key |
| `EMAIL_FROM` | Yes | Sender email address |
| `APPNEST_RELAY_SECRET` | Yes | Bearer token for relay endpoint |
| `PERSONAL_MODE` | No | Enable single-user mode (default: false) |
| `PERSONAL_API_KEY` | No | API key for personal mode |
| `HELIOS_ENABLED` | No | Enable Helios hashing (default: true) |
| `LOCAL_EMBEDDINGS_FALLBACK` | No | Use local model instead of OpenAI |

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

# Run server (requires env vars)
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Deployment

Deployed on [Render](https://render.com) via `render.yaml`. Set all environment
variables in the Render dashboard before deploying.

## License

Proprietary — Aletheia Sovereign Systems.
