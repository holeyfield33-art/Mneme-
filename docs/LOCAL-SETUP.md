# Mneme private local setup

This profile runs Mneme on this computer with PostgreSQL and no external AI,
email, or sync calls. The current MCP endpoint is
`http://127.0.0.1:8010/mcp/`; its private database is exposed only on
`127.0.0.1:5434`. An older `mneme-local-postgres` container on port 5433 was
left untouched. Credentials and generated compose state are under ignored
`.local/` with a restricted Windows ACL. Never commit or print those files.

## Daily commands

Run from `C:\Users\SuperAdmin\.vscode\Mneme-`:

```powershell
.\scripts\local.ps1 status
.\scripts\local.ps1 start
.\scripts\local.ps1 stop
.\scripts\local.ps1 restart
```

`stop` preserves the PostgreSQL volume. `start` is idempotent, validates tracked
migration hashes, binds the API to loopback, and requires Docker Desktop. To test
durability after a change:

```powershell
.\.venv-local\Scripts\python.exe scripts\smoke_local.py write
.\scripts\local.ps1 restart
.\.venv-local\Scripts\python.exe scripts\smoke_local.py verify
```

The smoke test verifies offline mode, database connectivity, rejected anonymous
MCP, absent sync routes, authenticated store/get, keyword search, semantic-search
keyword fallback, Helios integrity, and stable identity/hash across restart.

## Agent access

Codex has a global MCP entry named `mneme-local`. It uses
`MNEME_LOCAL_API_KEY` from the user's environment; the secret value is not stored
in Codex's MCP table. Restart the Codex app or IDE extension after initial setup,
then use `/mcp` or `codex mcp get mneme-local` to confirm it is enabled.

For scripts and agent handoffs, write a request file without credentials:

```json
{
  "tool": "get_memory",
  "arguments": {"key": "workspace/horos-atg-mneme/latest"}
}
```

```powershell
.\.venv-local\Scripts\python.exe scripts\local_client.py --request-file request.json
```

The bootstrap key is `workspace/horos-atg-mneme/latest`. Exact prompts are stored
under `workspace/horos-atg-mneme/prompts/...`; agents should retrieve only the
records relevant to their current task. This workflow records prompts that agents
explicitly save. It does not intercept every application or chat automatically.
When preserving exact user text, pass `"attribution": "user"`; agent conclusions
default to `"agent"`. Attribution records the client's claim and is not identity
proof.

## Privacy and production boundary

- `MNEME_OFFLINE=true` prevents remote embeddings, local model downloads, cloud
  sync routes, cloud sync tools, and email. Semantic search degrades to PostgreSQL
  full-text search and reports `search_mode: keyword` on `/health`.
- Authentication is still required on loopback. MCP request context is reset at
  the end of each call to prevent namespace/database leakage between requests.
- Helios hashes now reuse the exact timestamp and source written to PostgreSQL, so
  stored memories verify after retrieval and update.
- PostgreSQL and ignored local files are not encrypted at rest by Mneme. Use OS
  disk encryption and protected backups if the prompt archive is sensitive.
- The profile is production-ready for one operator on this Windows host. It has
  not been load-tested or hardened as a public, multi-tenant service.

Validation on 2026-09-12: 179 tests passed with two upstream test-client
deprecation warnings; a live write/restart/read/search/integrity sequence passed.
