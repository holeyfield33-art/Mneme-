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

## Required Environment Variables

Set these in Render's **Environment** tab (mark sensitive ones as **secrets**):

### Database
- **DATABASE_URL**  
  Postgres connection string. Example format:
  ```
  postgres://user:password@host.render.com:5432/dbname
  ```
  - Create a PostgreSQL database in Render or use external provider (AWS RDS, Supabase, etc.)
  - Ensure pgvector extension is installed: `CREATE EXTENSION IF NOT EXISTS vector;`
  - Ensure HNSW index extension: `CREATE EXTENSION IF NOT EXISTS hnsw;`

### API Keys (get from respective platforms)
- **OPENAI_API_KEY** — OpenAI API key for embeddings and LLM calls
- **STRIPE_SECRET_KEY** — Stripe secret key for payments
- **STRIPE_WEBHOOK_SECRET** — Stripe webhook signing secret (set up in Stripe dashboard)
- **STRIPE_PRICE_ID** — Stripe price ID (e.g., `price_xxxxx`)
- **RESEND_API_KEY** — Resend API key for email sending
- **EMAIL_FROM** — Sender email address (e.g., `noreply@yourapp.com`)

### AppNest/Relay
- **APPNEST_RELAY_SECRET** — Shared secret for relay operations (generate a strong random string)

## Optional Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| **PERSONAL_MODE** | `false` | Enable single-user mode (requires PERSONAL_API_KEY) |
| **PERSONAL_API_KEY** | empty | API key for personal mode |
| **HELIOS_ENABLED** | `true` | Enable Helios verification system |
| **LOCAL_EMBEDDINGS_FALLBACK** | `false` | Use local embeddings fallback (slower, no API cost) |

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
```
https://your-render-url.onrender.com/mcp?api_key=YOUR_API_KEY
```

Both `api_key`, `key`, and `token` query parameter names are supported.

## Stripe Integration

1. Set up webhook in Stripe Dashboard:
   - Endpoint URL: `https://your-render-url.onrender.com/billing/webhook`
   - Events: `checkout.session.completed`, `customer.subscription.deleted`
   - Copy signing secret → **STRIPE_WEBHOOK_SECRET**

2. Create a product and price:
   - Get the Price ID → **STRIPE_PRICE_ID**

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
      - key: STRIPE_SECRET_KEY
        sync: false
      - key: STRIPE_WEBHOOK_SECRET
        sync: false
      - key: STRIPE_PRICE_ID
        sync: false
      - key: RESEND_API_KEY
        sync: false
      - key: EMAIL_FROM
        sync: false
      - key: APPNEST_RELAY_SECRET
        sync: false
      - key: PERSONAL_MODE
        value: false
```

## Horos Configuration

The app is analyzed via **horos** (context graph generator). Key configuration in [`horos.json`](horos.json):

```json
{
  "python_source_roots": ["aletheia-mneme"],
  "external_modules": ["fastapi", "starlette", "pydantic", "uvicorn", "asyncpg", "pgvector", "openai", "stripe", "resend", "httpx"]
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
