"""Generate isolated local secrets and apply tracked SQL migrations."""
import argparse
import asyncio
import hashlib
import json
import secrets

from local_config import ROOT, LOCAL, CONFIG, load_config

IMAGE = "pgvector/pgvector@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b"


def initialize():
    LOCAL.mkdir(exist_ok=True)
    if not CONFIG.exists():
        password = secrets.token_urlsafe(40)
        config = {
            "endpoint": "http://127.0.0.1:8010/mcp/",
            "health_endpoint": "http://127.0.0.1:8010/health",
            "personal_api_key": "mneme_p_" + secrets.token_urlsafe(40),
            "relay_secret": secrets.token_urlsafe(40),
            "database_url": f"postgresql://mneme:{password}@127.0.0.1:5434/mneme",
            "database_port": 5434,
            "service_port": 8010,
        }
        CONFIG.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        (LOCAL / "postgres-password").write_text(password, encoding="utf-8")
    if not (LOCAL / "postgres-password").exists():
        raise RuntimeError("Database password file is missing; restore it from your local backup.")
    # Separate project/volume from the user's pre-existing local compose deployment.
    compose = {
        "name": "mneme-private",
        "services": {"postgres": {
            "image": IMAGE,
            "restart": "unless-stopped",
            "environment": {
                "POSTGRES_USER": "mneme", "POSTGRES_DB": "mneme",
                "POSTGRES_PASSWORD_FILE": "/run/secrets/postgres_password",
            },
            "ports": [f"127.0.0.1:{load_config()['database_port']}:5432"],
            "volumes": ["data:/var/lib/postgresql/data"],
            "secrets": ["postgres_password"],
            "healthcheck": {"test": ["CMD-SHELL", "pg_isready -U mneme -d mneme"],
                            "interval": "3s", "timeout": "3s", "retries": 30},
        }},
        "volumes": {"data": {}},
        "secrets": {"postgres_password": {"file": "./postgres-password"}},
    }
    (LOCAL / "compose.json").write_text(json.dumps(compose, indent=2) + "\n", encoding="utf-8")
    print("Local configuration initialized; credentials remain in ignored .local files.")


async def migrate():
    import asyncpg
    config = load_config()
    conn = await asyncpg.connect(config["database_url"])
    try:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(706584332)")
            await conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations "
                               "(name TEXT PRIMARY KEY, sha256 TEXT NOT NULL, applied_at TIMESTAMPTZ DEFAULT NOW())")
            for path in sorted((ROOT / "aletheia-mneme" / "migrations").glob("*.sql")):
                sql = path.read_text(encoding="utf-8-sig")
                digest = hashlib.sha256(sql.encode()).hexdigest()
                existing = await conn.fetchval("SELECT sha256 FROM schema_migrations WHERE name=$1", path.name)
                if existing:
                    if existing != digest:
                        raise RuntimeError(f"Previously applied migration changed: {path.name}")
                    continue
                await conn.execute(sql)
                await conn.execute("INSERT INTO schema_migrations (name,sha256) VALUES ($1,$2)", path.name, digest)
                print(f"Applied {path.name}")
    finally:
        await conn.close()
    print("Local database schema ready.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init", "migrate"])
    args = parser.parse_args()
    if args.action == "init":
        initialize()
    else:
        asyncio.run(migrate())
