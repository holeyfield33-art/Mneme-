# Aletheia Mneme

Persistent AI memory with semantic search, cryptographic integrity, and multi-agent relay.
The memory layer of the **TMRP** stack.

---

## Architecture

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| Relational store | PostgreSQL (SQLAlchemy ORM) |
| Vector / semantic search | Qdrant + OpenAI embeddings |
| Cache / pub-sub | Redis |
| Billing | Stripe |

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values.

| Variable | Description | Default |
|---|---|---|
| `SECRET_KEY` | HMAC signing key | `change-me-in-production` |
| `DATABASE_URL` | PostgreSQL DSN | `postgresql://mneme:mneme@localhost:5432/mneme` |
| `REDIS_URL` | Redis DSN | `redis://localhost:6379/0` |
| `QDRANT_HOST` | Qdrant hostname | `localhost` |
| `QDRANT_PORT` | Qdrant REST port | `6333` |
| `QDRANT_COLLECTION` | Qdrant collection name | `mneme_memories` |
| `OPENAI_API_KEY` | OpenAI key for embeddings | _(required for search)_ |
| `EMBEDDING_MODEL` | OpenAI model | `text-embedding-3-small` |
| `EMBEDDING_DIMENSION` | Vector size | `1536` |
| `STRIPE_SECRET_KEY` | Stripe secret key | _(required for billing)_ |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret | _(required for webhooks)_ |
| `STRIPE_PRICE_ID_PRO` | Stripe price ID for the Pro plan | _(required for checkout)_ |

---

## Services Required

| Service | Purpose | Docker image |
|---|---|---|
| PostgreSQL 16 | Persistent storage for agents, memories, relay messages, subscriptions | `postgres:16-alpine` |
| Redis 7 | Relay pub-sub, caching | `redis:7-alpine` |
| Qdrant 1.9 | Vector database for semantic search | `qdrant/qdrant:v1.9.2` |

---

## Launch Steps

### 1 — Clone and configure

```bash
git clone https://github.com/holeyfield33-art/Mneme-.git
cd Mneme-/aletheia-mneme
cp .env.example .env
# Edit .env and set SECRET_KEY, OPENAI_API_KEY, and Stripe keys
```

### 2 — Start infrastructure with Docker Compose

```bash
docker compose up -d db redis qdrant
```

### 3 — Install Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 4 — Run the API server

```bash
uvicorn app.main:app --reload
```

The API will be available at **http://localhost:8000**.
Interactive docs: **http://localhost:8000/docs**

### 5 — (Optional) Run everything with Docker Compose

```bash
docker compose up --build
```

---

## Running Tests

```bash
pytest
```

---

## API Overview

| Method | Path | Description |
|---|---|---|
| `POST` | `/agents/register` | Register a new agent, receive API key |
| `POST` | `/memories/` | Store a new memory |
| `GET` | `/memories/` | List memories (paginated) |
| `GET` | `/memories/{id}` | Get a single memory |
| `DELETE` | `/memories/{id}` | Soft-delete a memory |
| `POST` | `/memories/search` | Semantic search |
| `POST` | `/relay/` | Send a relay message to another agent |
| `GET` | `/relay/inbox` | Fetch and acknowledge undelivered messages |
| `GET` | `/billing/subscription` | Get current plan/status |
| `POST` | `/billing/checkout` | Create Stripe Checkout session |
| `POST` | `/billing/webhook` | Stripe webhook handler |
| `GET` | `/health` | Health check |

All protected endpoints require an `X-API-Key` header.
