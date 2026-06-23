# Aletheia Mneme

**True memory for AI agents.**

Persistent AI memory server with semantic search, cryptographic integrity (Helios Core),
and a multi-agent relay sandbox. Free and open to use — all 16 tools available to every key.

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
- **Resend** transactional email
- **Render** deployment

## Architecture

```text
┌──────────────┐   ┌──────────────┐   ┌───────────────┐
│  MCP Client  │──▶│  FastAPI +   │──▶│  PostgreSQL   │
│  (AI Agent)  │   │  FastMCP     │   │  + pgvector   │
└──────────────┘   └──────┬───────┘   └───────────────┘
                          │
                   ┌──────┴──────┐
                   ▼             ▼
              ┌────────┐   ┌─────────┐
              │ Resend │   │ OpenAI  │
              │ Email  │   │Embedding│
              └────────┘   └─────────┘
```

## Tools (16 total — all free)

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

## API Keys

- `mneme_p_...` — full access to all 16 tools (semantic search, cloud sync, relay).

Get one for free via `POST /signup`, or run in `PERSONAL_MODE` with a single
hardcoded key. Keys are hashed with Argon2id. The raw key is returned once at
creation and never stored.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/signup` | Create a namespace + free full-access API key |
| POST | `/relay` | Multi-agent relay sandbox |
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
| `RESEND_API_KEY` | Yes | Resend email API key |
| `EMAIL_FROM` | Yes | Sender email address |
| `RELAY_SECRET` | Yes | Bearer token for relay endpoint |
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
