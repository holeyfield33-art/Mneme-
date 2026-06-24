# Render.com Deployment Setup for Aletheia Mneme

## Quick Start via render.yaml

The app is configured in [`aletheia-mneme/render.yaml`](aletheia-mneme/render.yaml). To deploy:

1. Connect your GitHub repo to Render.com
2. Click "New" → "Web Service" → "Build and deploy from a Git repository"
3. Select this repository
4. Render auto-detects the `render.yaml` file
5. Update the environment variables (see below)
6. Deploy

## Manual Setup (if render.yaml not detected)

### Service Configuration

| Field | Value |
|-------|-------|
| **Name** | aletheia-mneme |
| **Environment** | Python 3.11+ |
| **Build Command** | `pip install -r aletheia-mneme/requirements.txt` |
| **Start Command** | `cd aletheia-mneme && uvicorn main:app --host 0.0.0.0 --port $PORT` |
| **Root Directory** | `aletheia-mneme` |

## Environment Variable Setup

Set these in Render's **Environment** tab (mark sensitive ones as **secrets**), or in
your local shell / `.env` file.

### Render environment variables

| Variable | Required in Render | Example / Value | Notes |
|----------|--------------------|-----------------|-------|
| `DATABASE_URL` | Yes | `postgresql://render-db-host:5432/mneme` | PostgreSQL connection string |
| `OPENAI_API_KEY` | Yes | `sk-...` | OpenAI key for embeddings |
| `RESEND_API_KEY` | Yes | `re_...` | Resend API key |
| `EMAIL_FROM` | Yes | `noreply@yourapp.com` | Sender email address |
| `RELAY_SECRET` | Yes | strong random string | Relay bearer secret |
| `PERSONAL_MODE` | Optional | `false` | Recommended default; if `true`, `PERSONAL_API_KEY` is required |
| `PERSONAL_API_KEY` | Conditional | `your_personal_api_key` | Required only when `PERSONAL_MODE=true` |
| `HELIOS_ENABLED` | Optional | `true` | Helios integrity verification |
| `LOCAL_EMBEDDINGS_FALLBACK` | Optional | `false` | Local embeddings fallback |
| `PORT` | Render-managed | auto-set by Render | Used by start command (`--port $PORT`) |

### Local development environment variables

| Variable | Required locally | Example / Value | Notes |
|----------|------------------|-----------------|-------|
| `DATABASE_URL` | Yes | `postgresql://localhost:5432/mneme_local` | PostgreSQL connection string |
| `OPENAI_API_KEY` | Yes | `sk-...` | OpenAI key for embeddings |
| `RESEND_API_KEY` | Yes | `re_...` | Required for signup email flow |
| `EMAIL_FROM` | Yes | `dev@yourdomain.com` | Sender email address |
| `RELAY_SECRET` | Yes | strong random string | Relay endpoint auth |
| `PERSONAL_MODE` | Optional | `false` | Enable single-user mode |
| `PERSONAL_API_KEY` | Conditional | custom string | Required when `PERSONAL_MODE=true` |
| `HELIOS_ENABLED` | Optional | `true` | Enable/disable Helios hashing |
| `LOCAL_EMBEDDINGS_FALLBACK` | Optional | `false` | Local embeddings fallback |

### Database

- **DATABASE_URL**
  Postgres connection string. Example format:

  ```text
  postgres://user:password@host.render.com:5432/dbname
  ```

  - Create a PostgreSQL database in Render or use external provider (AWS RDS, Supabase, etc.)
  - Ensure pgvector extension is installed: `CREATE EXTENSION IF NOT EXISTS vector;`
  - Ensure HNSW index extension: `CREATE EXTENSION IF NOT EXISTS hnsw;`

### API Keys (get from respective platforms)

- **OPENAI_API_KEY** — OpenAI API key for embeddings and LLM calls
- **RESEND_API_KEY** — Resend API key for email sending
- **EMAIL_FROM** — Sender email address (e.g., `noreply@yourapp.com`)

### Relay

- **RELAY_SECRET** — Shared secret for relay operations (generate a strong random string)

### Local `.env` example

```dotenv
DATABASE_URL=postgresql://localhost:5432/mneme_local
OPENAI_API_KEY=sk-your-key
RESEND_API_KEY=re_your_key
EMAIL_FROM=dev@yourdomain.com
RELAY_SECRET=replace_with_long_random_secret
PERSONAL_MODE=false
# PERSONAL_API_KEY=your_personal_key_if_PERSONAL_MODE_true
HELIOS_ENABLED=true
LOCAL_EMBEDDINGS_FALLBACK=false
```

## Database Setup Steps

1. **Create PostgreSQL database** (if not using Render's managed DB):
   - External: Supabase, AWS RDS, or self-hosted Postgres 13+
   - Render managed: Create a PostgreSQL database instance

2. **Install required extensions**:

   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   CREATE EXTENSION IF NOT EXISTS hnsw;
   ```

3. **Run migrations** (post-deployment):

   ```bash
   # SSH into Render instance or run migration tool
   psql $DATABASE_URL < aletheia-mneme/migrations/001_init.sql
   psql $DATABASE_URL < aletheia-mneme/migrations/002_pgvector.sql
   psql $DATABASE_URL < aletheia-mneme/migrations/003_hnsw_index.sql
   ```

## Post-Deployment

### Test the deployment

```bash
# Health check
curl https://your-render-url.onrender.com/health

# Expected response:
# {"status":"ok","product":"Aletheia Mneme","version":"1.0.0","database":"connected"}
```

### MCP Endpoint Access

The MCP endpoint is at `/mcp` and supports two authentication methods:

#### Option 1: Bearer Token Header

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" https://your-render-url.onrender.com/mcp
```

#### Option 2: Query Parameter (for tools that only accept URLs)

```text
https://your-render-url.onrender.com/mcp?api_key=YOUR_API_KEY
```

Both `api_key`, `key`, and `token` query parameter names are supported.

## Issuing API Keys

Mneme is completely free — there is no billing. Mint a full-access key with the
public signup endpoint:

```bash
curl -X POST https://your-render-url.onrender.com/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com"}'
```

The response contains your `api_key` (also emailed via Resend). For single-operator
deployments, set `PERSONAL_MODE=true` and a `PERSONAL_API_KEY` instead.

## Render.yaml File Format

The deployment is defined in [`aletheia-mneme/render.yaml`](aletheia-mneme/render.yaml):

```yaml
services:
  - type: web
    name: aletheia-mneme
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: DATABASE_URL
        sync: false
      - key: OPENAI_API_KEY
        sync: false
      - key: RESEND_API_KEY
        sync: false
      - key: EMAIL_FROM
        sync: false
      - key: RELAY_SECRET
        sync: false
      - key: PERSONAL_MODE
        value: false
```

## Horos Configuration

The app is analyzed via **horos** (context graph generator). Key configuration in [`horos.json`](horos.json):

```json
{
  "python_source_roots": ["aletheia-mneme"],
  "external_modules": ["fastapi", "starlette", "pydantic", "uvicorn", "asyncpg", "pgvector", "openai", "resend", "httpx"]
}
```

This ensures all dependencies are correctly resolved during CI/deployment.

## Troubleshooting

### Build Fails: "ModuleNotFoundError"

- Check `requirements.txt` is in `aletheia-mneme/`
- Verify Python version (3.11+ required)
- Run locally: `pip install -r aletheia-mneme/requirements.txt`

### Database Connection Error

- Verify **DATABASE_URL** format: `postgres://user:pass@host:port/db`
- Ensure Postgres is accessible from Render (firewall rules)
- Test connection: `psql $DATABASE_URL -c "SELECT 1;"`

### Authentication Fails (401)

- Verify API key is valid in the database (`namespaces` table)
- Try Bearer header first: `Authorization: Bearer KEY`
- If using query param: encode special chars (e.g., `%` → `%25`)

### Health Check Fails

- Check database connection: `GET /health`
- Verify **DATABASE_URL** env var is set
- View logs in Render dashboard → "Logs" tab

## Additional Resources

- [render.yaml reference](https://render.com/docs/render-yaml)
- [Horos documentation](https://github.com/holeyfield33-art/horos)
- [FastAPI + Uvicorn on Render](https://render.com/docs/deploy-fastapi)
- [MCP Protocol](https://modelcontextprotocol.io/)
